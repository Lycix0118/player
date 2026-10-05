"""Shared outbound HTTP client, throttling and retry policy."""

import asyncio
import random
import threading
import time
from typing import Dict, Optional

import aiohttp
import requests

try:
    from .settings import (
        OUTBOUND_MAX_CONCURRENCY,
        OUTBOUND_MAX_COOLDOWN,
        OUTBOUND_MAX_QPS,
    )
except ImportError:
    from settings import (
        OUTBOUND_MAX_CONCURRENCY,
        OUTBOUND_MAX_COOLDOWN,
        OUTBOUND_MAX_QPS,
    )


HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "referer": "https://www.bilibili.com/",
}

_http_session: Optional[aiohttp.ClientSession] = None
_active_loop = None
_outbound_sem = None
_outbound_lock = None
_global_download_lock = None
_download_locks: Dict[str, asyncio.Lock] = {}
_next_earliest_ts = 0.0

_sync_lock = threading.Lock()
_sync_next_earliest_ts = 0.0
_cooldowns: Dict[str, float] = {}


async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    loop = asyncio.get_running_loop()
    if _http_session is None or _http_session.closed or getattr(_http_session, "_loop", None) != loop:
        _http_session = aiohttp.ClientSession(
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=25, connect=10),
        )
    return _http_session


async def close_http_session() -> None:
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
    _http_session = None


def _ensure_async_primitives() -> None:
    global _active_loop, _outbound_sem, _outbound_lock, _global_download_lock, _download_locks
    loop = asyncio.get_running_loop()
    if _active_loop != loop:
        _active_loop = loop
        _outbound_sem = asyncio.Semaphore(OUTBOUND_MAX_CONCURRENCY)
        _outbound_lock = asyncio.Lock()
        _global_download_lock = asyncio.Lock()
        _download_locks = {}


async def get_download_lock(key: str) -> asyncio.Lock:
    _ensure_async_primitives()
    async with _global_download_lock:
        if key not in _download_locks:
            if len(_download_locks) > 300:
                for item in list(_download_locks)[:100]:
                    if not _download_locks[item].locked():
                        _download_locks.pop(item, None)
            _download_locks[key] = asyncio.Lock()
        return _download_locks[key]


def _endpoint_key(url: str) -> str:
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")
        head = "/".join(parts[:2]) if parts else ""
        return f"{parsed.scheme}://{parsed.netloc}/{head}"
    except (TypeError, ValueError):
        return url


def _in_cooldown(url: str) -> bool:
    return time.monotonic() < _cooldowns.get(_endpoint_key(url), 0.0)


def _set_cooldown(url: str, base_seconds: float) -> None:
    now = time.monotonic()
    key = _endpoint_key(url)
    target = now + min(base_seconds, OUTBOUND_MAX_COOLDOWN)
    if target > _cooldowns.get(key, 0.0):
        if len(_cooldowns) > 200:
            for item in list(_cooldowns)[:50]:
                if _cooldowns[item] < now:
                    _cooldowns.pop(item, None)
        _cooldowns[key] = target


def _jitter(seconds: float) -> float:
    return max(0.0, seconds + random.uniform(-seconds * 0.2, seconds * 0.2))


async def _await_global_qps_window() -> None:
    global _next_earliest_ts
    _ensure_async_primitives()
    async with _outbound_lock:
        now = time.monotonic()
        gap = 1.0 / max(OUTBOUND_MAX_QPS, 0.0001)
        wait = max(0.0, _next_earliest_ts - now)
        if wait:
            await asyncio.sleep(wait)
        _next_earliest_ts = time.monotonic() + _jitter(gap)


async def limited_get(
    url: str,
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    retries: int = 3,
) -> Optional[aiohttp.ClientResponse]:
    if _in_cooldown(url):
        return None
    _ensure_async_primitives()
    session = await get_http_session()
    backoff = 0.5
    for attempt in range(retries):
        async with _outbound_sem:
            await _await_global_qps_window()
            try:
                response = await session.get(url, params=params, headers=headers)
                if response.status == 200:
                    return response
                if response.status in (403, 429):
                    _set_cooldown(url, 60.0 * (2 ** attempt))
                    response.release()
                    return None
                if not 500 <= response.status < 600:
                    response.release()
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
        await asyncio.sleep(_jitter(backoff))
        backoff = min(backoff * 2, 8.0)
    return None


def limited_get_sync(
    url: str,
    params: Optional[Dict] = None,
    headers: Optional[Dict] = None,
    timeout: int = 15,
    retries: int = 3,
):
    global _sync_next_earliest_ts
    if _in_cooldown(url):
        return None
    backoff = 0.5
    for attempt in range(retries):
        with _sync_lock:
            now = time.monotonic()
            gap = 1.0 / max(OUTBOUND_MAX_QPS, 0.0001)
            wait = max(0.0, _sync_next_earliest_ts - now)
            if wait:
                time.sleep(wait)
            _sync_next_earliest_ts = time.monotonic() + _jitter(gap)
        try:
            response = requests.get(url, params=params, headers=headers or HEADERS, timeout=timeout)
            if response.status_code == 200:
                return response
            if response.status_code in (403, 429):
                _set_cooldown(url, 60.0 * (2 ** attempt))
                return None
            if not 500 <= response.status_code < 600:
                return None
        except requests.exceptions.RequestException:
            pass
        time.sleep(_jitter(backoff))
        backoff = min(backoff * 2, 8.0)
    return None
