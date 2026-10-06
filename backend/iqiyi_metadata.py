# -*- coding: utf-8 -*-
"""爱奇艺专辑元数据读取（只负责标题、集数和封面，不负责播放）。"""

from __future__ import annotations

import re
import threading
import time
from typing import Dict, List, Optional

import requests

_API = "https://pcw-api.iqiyi.com/albums/album/avlistinfo"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TTL = 1800.0
_cache: Dict[str, tuple[float, Dict]] = {}
_lock = threading.Lock()
_NO_PROXY = {"http": None, "https": None}


def _https(url: str) -> str:
    value = str(url or '').strip()
    value = ('https:' + value) if value.startswith('//') else value.replace('http://', 'https://', 1)
    # avlistinfo 默认给 120x160 竖版图，同一资源的 480x270 横版地址更适合列表卡片。
    # 接口会返回 `_m_601.jpg` 或 `_m_601_m1.jpg` 的 120x160 竖图，
    # 同一资源的横版规格统一使用 480x270。
    value = re.sub(r'_m_601(?:_m1)?\.jpg$', '_m_601_480_270.jpg', value, flags=re.IGNORECASE)
    return value


def _episode_number(item: Dict, fallback: int) -> int:
    value = item.get('order') or item.get('episode') or fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r'第\s*(\d+)\s*[集话]', str(item.get('name') or ''))
        return int(match.group(1)) if match else fallback


def fetch_album_metadata(album_id: str, timeout: int = 15) -> Dict:
    """返回 ``{'title', 'episodes': {集数: {'title', 'cover'}}}``。"""
    album_id = str(album_id or '').strip()
    if not album_id.isdigit():
        return {}
    with _lock:
        cached = _cache.get(album_id)
        if cached and time.time() - cached[0] < _TTL:
            return cached[1]

    try:
        response = requests.get(
            _API,
            params={'aid': album_id, 'size': 200, 'page': 1},
            headers={'User-Agent': _UA, 'Referer': 'https://www.iqiyi.com/'},
            timeout=timeout,
            proxies=_NO_PROXY,
        )
        response.raise_for_status()
        response.encoding = 'utf-8'
        payload = response.json()
        data = payload.get('data') or {}
        raw_items: List[Dict] = data.get('epsodelist') or []
        episodes: Dict[int, Dict] = {}
        for fallback, item in enumerate(raw_items, start=1):
            number = _episode_number(item, fallback)
            title = str(item.get('name') or item.get('shortTitle') or '').strip()
            episodes[number] = {
                'title': title,
                'cover': _https(item.get('imageUrl') or item.get('image_url') or ''),
                'duration': item.get('duration', 0),
                'description': item.get('description', ''),
            }
        result = {
            'album_id': album_id,
            'title': str(data.get('albumName') or '').strip(),
            'total': int(data.get('total') or data.get('videoCount') or len(episodes)),
            'episodes': episodes,
        }
    except Exception as exc:  # metadata must never prevent Silidm playback
        print(f"爱奇艺专辑元数据获取失败 ({album_id}): {exc}")
        return {}

    with _lock:
        _cache[album_id] = (time.time(), result)
    return result
