# -*- coding: utf-8 -*-
"""silidm.com（「电影先生」，苹果CMS 采集站）取流实现 —— 本项目唯一的外部视频来源。

取流要点（决定了这里的写法）：

* **没有第三方解析站、没有加密**：播放页里内联一段 ``player_aaaa`` JSON，
  ``url`` 字段就是 m3u8 直链（``encrypt: 0``），因此不需要任何解密步骤，
  也不需要 ``cryptography`` 之类的依赖。
* **直链域名会轮换**（``fengbao13.com`` / ``bfeng11.com`` …），所以每次播放都
  从播放页**现取**，绝不把域名写死。
* **分片常是相对路径**（``0000000.ts``），且可能是**嵌套 master playlist**
  （``index.m3u8`` → ``2000k/hls/mixed.m3u8`` → 分片）：取流时要递归展开，
  并把相对地址补成绝对地址，否则后端代理会拼错 URL。
* 播放页与详情页里已经带齐整季链接，所以 ``list.txt`` 可以只写**一行详情页**。

``list.txt`` 支持的写法::

    https://silidm.com/video/42675.html            # 详情页 —— 自动展开整季（推荐）
    https://silidm.com/play/42675-1-1.html         # 单集播放页
    https://silidm.com/play/42675.html             # 上面那种的简写，等价于 -1-1
    第1集 消失的记忆 上 | https://silidm.com/play/42675-1-1.html

合成集数 ID 形如 ``silidm_<vod_id>-<sid>-<nid>``，用于进度与本地缓存文件命名，
与来源站点解耦（换域名不影响已有进度）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from urllib3.util.retry import Retry

try:  # 允许以包或脚本两种方式导入
    from .settings import (
        HLS_SEGMENT_CACHE_DIR,
        HLS_SEGMENT_CACHE_MB,
        SILIDM_BASE,
        SILIDM_PREFETCH_WINDOW,
        SILIDM_SEGMENT_PARALLELISM,
    )
except ImportError:  # pragma: no cover - 直接以脚本方式导入时
    try:
        from settings import (
            HLS_SEGMENT_CACHE_DIR,
            HLS_SEGMENT_CACHE_MB,
            SILIDM_BASE,
            SILIDM_PREFETCH_WINDOW,
            SILIDM_SEGMENT_PARALLELISM,
        )
    except ImportError:
        HLS_SEGMENT_CACHE_DIR = Path("videos/.cache_segments")
        HLS_SEGMENT_CACHE_MB = 3000
        SILIDM_PREFETCH_WINDOW = 6
        SILIDM_BASE = "https://silidm.com"
        SILIDM_SEGMENT_PARALLELISM = 4


# 合成集数 ID 前缀：silidm_<vod_id>-<sid>-<nid>
EPISODE_ID_PREFIX = "silidm_"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9"

# /play/<vod_id>-<sid>-<nid>.html  与  /video/<vod_id>.html
# _PLAY_BARE_RE 是站点上同样有效的简写 /play/<vod_id>.html（等价于第 1 源第 1 集）。
# 必须显式支持：这类写法不匹配上面那条正则，若直接 return None，list.txt 里的一行
# 会被**静默跳过**（实测踩过：整部剧集在界面上直接消失，很难排查）。
_PLAY_PATH_RE = re.compile(r"/play/(\d+)-(\d+)-(\d+)\.html", re.IGNORECASE)
_PLAY_BARE_RE = re.compile(r"/play/(\d+)\.html", re.IGNORECASE)
_DETAIL_PATH_RE = re.compile(r"/video/(\d+)\.html", re.IGNORECASE)
_EPISODE_ID_RE = re.compile(r"^silidm_(\d+)-(\d+)-(\d+)$")

# 播放页里内联的播放信息（苹果CMS 通用，容错尾随分号）
_PLAYER_JSON_RE = re.compile(r"player_aaaa\s*=\s*(\{.*?\})\s*;?\s*</script>", re.S)
_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.IGNORECASE)
# 整季链接（只做提取，不依赖 a 标签的具体属性顺序）
_PLAY_LINK_RE = re.compile(r"/play/(\d+)-(\d+)-(\d+)\.html")

# master playlist 展开的最大层数（防御异常站点造成无限递归）
_MAX_PLAYLIST_DEPTH = 3

# 小于这个大小的分片不值得并行（探测+握手开销占大头）
_SEGMENT_MIN_PARALLEL_BYTES = 256 * 1024
# 本机代理不可用，走代理会 502
_NO_PROXY = {"http": None, "https": None}

_session_local = threading.local()


class SilidmError(RuntimeError):
    """silidm 取流链路异常，消息可直接展示给用户。"""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def _base() -> str:
    return str(SILIDM_BASE or "").rstrip("/")


def _thread_session() -> requests.Session:
    """取当前线程的 Session（连接池复用 + 自动重试）。

    实测：上游 CDN 对短时间多连接 TLS 敏感，偶发 SSLEOFError 或断连重置；
    挂载 Retry 适配器并在连接池复用下，可自动透明重试恢复，杜绝报错直接抛出。
    """
    session = getattr(_session_local, "session", None)
    if session is None:
        session = requests.Session()
        retry_strategy = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.2,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        adapter = requests.adapters.HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=16,
            pool_maxsize=32,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _session_local.session = session
    return session


def _get(url: str, timeout: int = 15):
    """禁用代理的 GET（带重试，避免瞬时网络抖动）。"""
    last_err = None
    for attempt in range(2):
        try:
            response = _thread_session().get(
                url,
                headers={"User-Agent": _UA, "Accept-Language": _ACCEPT_LANGUAGE},
                timeout=timeout,
                proxies=_NO_PROXY,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            last_err = exc
            if attempt < 1:
                time.sleep(0.2)
    if last_err:
        raise last_err
    raise SilidmError("请求失败")


def _get_text(url: str, timeout: int = 15) -> str:
    return _get(url, timeout=timeout).text


# --------------------------------------------------------------------------
# URL / ID 工具
# --------------------------------------------------------------------------

def is_silidm_url(value: str) -> bool:
    """粗略判断是否为本站链接（详情页或播放页）。"""
    base = _base()
    if not base:
        return False
    host = base.split("//", 1)[-1].lower()
    return host in (value or "").lower()


def is_play_url(value: str) -> bool:
    return bool(_PLAY_PATH_RE.search(value or ""))


def is_detail_url(value: str) -> bool:
    return bool(_DETAIL_PATH_RE.search(value or ""))


def parse_play_path(value: str) -> Optional[Tuple[str, str, str]]:
    """从播放页链接里取出 ``(vod_id, sid, nid)``。

    兼容两种写法：完整的 ``/play/<vod>-<sid>-<nid>.html``，以及站点的简写
    ``/play/<vod>.html``（按第 1 源第 1 集处理）。
    """
    match = _PLAY_PATH_RE.search(value or "")
    if match:
        return match.groups()
    bare = _PLAY_BARE_RE.search(value or "")
    if bare:
        return (bare.group(1), "1", "1")
    return None


def parse_detail_id(value: str) -> Optional[str]:
    """从详情页链接里取出 ``vod_id``。"""
    match = _DETAIL_PATH_RE.search(value or "")
    return match.group(1) if match else None


def normalize_url(value: str) -> Optional[str]:
    """归一成标准链接，保证同一集在任何写法下得到同一个 ID。"""
    base = _base()
    if not base:
        return None
    play = parse_play_path(value)
    if play:
        return f"{base}/play/{play[0]}-{play[1]}-{play[2]}.html"
    detail = parse_detail_id(value)
    if detail:
        return f"{base}/video/{detail}.html"
    return None


def make_episode_id(play_url: str) -> Optional[str]:
    play = parse_play_path(play_url)
    if not play:
        return None
    return f"{EPISODE_ID_PREFIX}{play[0]}-{play[1]}-{play[2]}"


def is_episode_id(value: str) -> bool:
    return bool(_EPISODE_ID_RE.match(value or ""))


def url_from_episode_id(episode_id: str) -> Optional[str]:
    match = _EPISODE_ID_RE.match(episode_id or "")
    if not match:
        return None
    base = _base()
    if not base:
        return None
    return f"{base}/play/{match.group(1)}-{match.group(2)}-{match.group(3)}.html"


# --------------------------------------------------------------------------
# 元数据（标题 / 封面）
# --------------------------------------------------------------------------

def _clean_play_title(raw: str) -> str:
    """把 ``《熊出没之神奇宝物2》第1集-在线观看高清完整未删减版-动漫-电影先生``
    压成 ``熊出没之神奇宝物2 第1集``。"""
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    titled = re.match(r"《(.+?)》\s*(第\s*\d+\s*[集话回]?)?", text)
    if titled:
        name = titled.group(1).strip()
        episode = (titled.group(2) or "").replace(" ", "")
        return f"{name} {episode}".strip()
    return text.split("-")[0].strip() or text


def _clean_detail_title(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "")).strip()
    titled = re.match(r"《(.+?)》", text)
    if titled:
        return titled.group(1).strip()
    return text.split("-")[0].strip() or text


def _extract_cover(html: str) -> str:
    """从页面里挑一张能当封面的图。

    只认 ``vod-info`` 主图区与 ``og:image``。**不要**退化成"页面里第一张
    vod 图"：实测播放页首图是「热播轮播」，结果同一次列表里两个完全不同的
    视频拿到了同一张封面。宁可返回空串（前端有占位图），也不要给错图。
    """
    for pattern in (
        r'class=["\'][^"\']*(?:desktop-vod-info|mobile-vod-info|vod-info)[^"\']*["\'][\s\S]{0,2200}?<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']',
        r'<img[^>]+class=["\'][^"\']*module-item-pic[^"\']*["\'][^>]+(?:data-src|src)=["\']([^"\']+)["\']',
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"',
    ):
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if value and not value.endswith("loading.gif"):
                return value
    return ""


_DETAIL_CACHE_TTL_SECONDS = 1800.0
# vod_id -> (抓取时间, {'title', 'cover'})：一季几十集逐集写 list.txt 时避免重复抓页面
_detail_cache: Dict[str, Tuple[float, Dict]] = {}


def _detail_cached(vod_id: str, timeout: int) -> Optional[Dict]:
    entry = _detail_cache.get(vod_id)
    if entry and time.time() - entry[0] < _DETAIL_CACHE_TTL_SECONDS:
        return entry[1]
    try:
        detail = fetch_detail(f"{_base()}/video/{vod_id}.html", timeout=timeout)
    except Exception:  # noqa: BLE001 - 详情页失败时退回到播放页兜底
        return None
    info = {"title": detail.get("title", ""), "cover": detail.get("cover", "")}
    if len(_detail_cache) > 128:
        _detail_cache.clear()
    _detail_cache[vod_id] = (time.time(), info)
    return info


def fetch_metadata(play_url: str, timeout: int = 15) -> Dict:
    """抓单集元数据；失败返回空字典（不抛异常，以免拖垮整个列表页）。

    标题与封面都取自**详情页**：播放页上没有该剧自己的主图，从播放页猜封面
    会拿到「热播轮播」里别的剧的图（实测踩过），所以这里宁可多抓一次详情页。
    """
    play = parse_play_path(play_url)
    if play:
        info = _detail_cached(play[0], timeout)
        if info and info.get("title"):
            return {
                "title": f"{info['title']} 第{play[2]}集",
                "cover": info.get("cover", ""),
                "duration": 0,
                "album": info["title"],
            }

    target = normalize_url(play_url) or play_url
    try:
        html = _get_text(target, timeout=timeout)
    except Exception:  # noqa: BLE001 - 元数据失败不应影响列表展示
        return {}

    match = _TITLE_RE.search(html)
    return {
        "title": _clean_play_title(match.group(1)) if match else "",
        "cover": _extract_cover(html),
        "duration": 0,
        "album": "",
    }


def fetch_detail(detail_url: str, timeout: int = 20) -> Dict:
    """抓详情页并展开整季。

    返回 ``{'title', 'cover', 'episodes': [{'index', 'title', 'url', 'episode_id'}]}``。
    同一个视频通常挂在多个播放源下（``sid``），这里取**集数最多**的那一组；
    并列时取 ``sid`` 最小的，保证结果稳定。
    """
    target = normalize_url(detail_url) or detail_url
    html = _get_text(target, timeout=timeout)

    title_match = _TITLE_RE.search(html)
    title = _clean_detail_title(title_match.group(1)) if title_match else ""

    grouped: Dict[str, List[Tuple[int, str, str]]] = {}
    for vod_id, sid, nid in _PLAY_LINK_RE.findall(html):
        grouped.setdefault(sid, []).append((int(nid), vod_id, sid))

    if not grouped:
        raise SilidmError("详情页里没有找到任何剧集链接（站点结构可能已改版）")

    # 集数最多优先，其次 sid 最小
    best_sid = max(sorted(grouped), key=lambda s: (len(grouped[s]), -int(s)))
    items = sorted(set(grouped[best_sid]), key=lambda item: item[0])

    episodes = []
    for order, (nid, vod_id, sid) in enumerate(items, start=1):
        play_url = f"{_base()}/play/{vod_id}-{sid}-{nid}.html"
        episodes.append({
            "index": order,
            "title": f"{title} 第{nid}集".strip(),
            "url": play_url,
            "episode_id": f"{EPISODE_ID_PREFIX}{vod_id}-{sid}-{nid}",
        })

    return {"title": title, "cover": _extract_cover(html), "episodes": episodes}


# --------------------------------------------------------------------------
# 解析取流
# --------------------------------------------------------------------------

def resolve_m3u8(play_url: str, timeout: int = 15) -> str:
    """从播放页取出 m3u8 直链。失败抛 :class:`SilidmError`。"""
    target = normalize_url(play_url) or play_url
    try:
        html = _get_text(target, timeout=timeout)
    except Exception as error:  # noqa: BLE001
        raise SilidmError(f"播放页打开失败: {error}") from error

    match = _PLAYER_JSON_RE.search(html)
    if not match:
        raise SilidmError("播放页里没有播放信息（站点结构可能已改版）")

    try:
        info = json.loads(match.group(1))
    except ValueError as error:
        raise SilidmError(f"播放信息解析失败: {error}") from error

    if str(info.get("encrypt", "0")) not in ("0", ""):
        raise SilidmError("该站点此集为加密播放，暂不支持")
    if str(info.get("points", "0")) not in ("0", ""):
        raise SilidmError("该集需要付费点数，暂不支持")

    play = str(info.get("url") or "").strip()
    if not play:
        raise SilidmError("播放信息里没有取到播放地址")
    return play


def _resolve_media_playlist(m3u8_url: str, timeout: int = 15,
                            depth: int = 0) -> Tuple[str, str]:
    """把（可能是 master 的）播放列表展开到真正的分片列表。

    返回 ``(用于拼接相对地址的 base_url, 分片列表文本)``。
    master playlist 只取第一个变体 —— 实测本站每个变体就是同一个流的档位。
    """
    if depth > _MAX_PLAYLIST_DEPTH:
        raise SilidmError("播放列表嵌套层数过深，已中止")

    text = _get_text(m3u8_url, timeout=timeout)
    if not text.lstrip().startswith("#EXTM3U"):
        raise SilidmError("播放地址已失效（返回的不是播放列表）")

    if "#EXT-X-STREAM-INF" in text:
        for line in text.splitlines():
            candidate = line.strip()
            if candidate and not candidate.startswith("#"):
                return _resolve_media_playlist(
                    urljoin(m3u8_url, candidate), timeout=timeout, depth=depth + 1
                )
        raise SilidmError("master 播放列表里没有可用的变体")

    return m3u8_url, text


def _absolutize(playlist: str, base_url: str) -> str:
    """把列表里的相对地址补成绝对地址（不代理时也要给浏览器可用的地址）。"""
    lines = []
    for line in playlist.splitlines():
        text = line.strip()
        if not text:
            lines.append(line)
        elif not text.startswith("#"):
            lines.append(urljoin(base_url, text))
        elif text.startswith(("#EXT-X-KEY:", "#EXT-X-MAP:")):
            # 补全加密密钥或初始化片段中的相对 URI 地址
            rewritten = re.sub(
                r'URI=["\']([^"\']+)["\']',
                lambda m: f'URI="{urljoin(base_url, m.group(1))}"',
                line,
            )
            lines.append(rewritten)
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


# 播放列表解析结果缓存：episode_id -> (存入时间, [分片绝对地址])
# 价值在于「切集/重播时不必再解析一次」，同时给分片代理路由提供地址表
# （``/api/hls/<id>/seg/<n>.ts`` 请求里只带序号，不带真实地址）。
# 上游直链带签名且短时效，所以 TTL 不能长；过期或未命中就重新解析一次。
_PLAYLIST_CACHE_TTL_SECONDS = 600.0
_PLAYLIST_TEXT_CACHE_TTL_SECONDS = 300.0
_PLAYLIST_CACHE_MAX_EPISODES = 64

_playlist_cache: "OrderedDict[str, Tuple[float, List[str]]]" = OrderedDict()
_playlist_cache_lock = threading.Lock()

_playlist_text_cache: "OrderedDict[str, Tuple[float, str]]" = OrderedDict()
_playlist_text_cache_lock = threading.Lock()


def _store_segment_urls(episode_id: str, segment_urls: List[str]) -> None:
    with _playlist_cache_lock:
        _playlist_cache[episode_id] = (time.time(), list(segment_urls))
        _playlist_cache.move_to_end(episode_id)
        while len(_playlist_cache) > _PLAYLIST_CACHE_MAX_EPISODES:
            _playlist_cache.popitem(last=False)


def cached_segment_urls(episode_id: str) -> Optional[List[str]]:
    """取该集最近一次解析出的分片地址表（过期返回 None）。"""
    with _playlist_cache_lock:
        entry = _playlist_cache.get(episode_id)
        if entry:
            _playlist_cache.move_to_end(episode_id)
    if not entry:
        return None
    stored_at, urls = entry
    if time.time() - stored_at > _PLAYLIST_CACHE_TTL_SECONDS:
        return None
    return urls


def proxied_playlist(episode_id: str, play_url: str, timeout: int = 15) -> str:
    """解析并返回「分片 URI 改写成后端代理地址」的播放列表。

    本站分片多为**相对路径**，所以必须先用 ``urljoin`` 还原成绝对地址再交给
    代理下载（否则后端会以播放列表 URL 为基准拼出一个必然 404 的地址）。
    带有文本级内存缓存，多次刷新或多设备起播时 0ms 响应。
    """
    with _playlist_text_cache_lock:
        text_entry = _playlist_text_cache.get(episode_id)
        if text_entry and time.time() - text_entry[0] < _PLAYLIST_TEXT_CACHE_TTL_SECONDS:
            _playlist_text_cache.move_to_end(episode_id)
            return text_entry[1]

    m3u8 = resolve_m3u8(play_url, timeout=timeout)
    base_url, playlist = _resolve_media_playlist(m3u8, timeout=timeout)

    if "#EXT-X-KEY" in playlist or "#EXT-X-MAP" in playlist:
        # 加密流/初始化分片不做改写，但相对地址必须补绝对，否则浏览器会以
        # /api/hls/<id>/index.m3u8 为基准去解析，必然 404。
        return _absolutize(playlist, base_url)

    rewritten: List[str] = []
    segment_urls: List[str] = []
    for line in playlist.splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            rewritten.append(f"seg/{len(segment_urls)}.ts")
            segment_urls.append(urljoin(base_url, text))
        else:
            rewritten.append(line)

    if not segment_urls:
        raise SilidmError("解析结果中没有可用的分片")

    result = "\n".join(rewritten) + "\n"
    _store_segment_urls(episode_id, segment_urls)

    with _playlist_text_cache_lock:
        _playlist_text_cache[episode_id] = (time.time(), result)
        _playlist_text_cache.move_to_end(episode_id)
        while len(_playlist_text_cache) > _PLAYLIST_CACHE_MAX_EPISODES:
            _playlist_text_cache.popitem(last=False)

    return result


def segment_url_for(episode_id: str, index: int, timeout: int = 15) -> Optional[str]:
    """按序号取分片真实地址；缓存未命中（含服务重启/过期）时重新解析一次。"""
    urls = cached_segment_urls(episode_id)
    if urls is None:
        play_url = url_from_episode_id(episode_id)
        if not play_url:
            return None
        try:
            proxied_playlist(episode_id, play_url, timeout=timeout)
        except SilidmError:
            return None
        urls = cached_segment_urls(episode_id)
    if not urls or index < 0 or index >= len(urls):
        return None
    return urls[index]


def _segment_parallelism() -> int:
    """并行连接数（1 表示退回单连接）。"""
    try:
        value = int(SILIDM_SEGMENT_PARALLELISM)
    except (TypeError, ValueError):
        return 4
    return max(1, min(16, value))


_segment_pool = ThreadPoolExecutor(max_workers=24)


def fetch_segment(url: str, timeout: int = 30) -> bytes:
    """下载分片：HEAD/Range 快速定界 + Range 多连接并行 + 片内失败重试 + 连接池复用。

    为什么必须复用连接与子分片重试：上游对频繁新建的 TCP/TLS 很敏感，实测多连接并发时
    若某条连接遇到 TLS EOF 重置，如果全片直接弃用并行，会退化到 1Mbps 慢速单连接；
    加上片内指数退避重试后，4 路并行稳定性接近 100%，单片拉取提速 3~5 倍。
    """
    parallelism = _segment_parallelism()
    session = _thread_session()
    headers = {"User-Agent": _UA}

    if parallelism <= 1:
        return session.get(url, headers=headers, timeout=timeout, proxies=_NO_PROXY).content

    total = None
    # 优先尝试极低开销的 HEAD 请求获取 Content-Length（实测 ~0.15s，省去整包探测）
    try:
        head = session.head(url, headers=headers, timeout=min(10, timeout), proxies=_NO_PROXY)
        if head.status_code == 200 and head.headers.get("Content-Length"):
            total = int(head.headers["Content-Length"])
    except Exception:
        pass

    if total is None:
        try:
            probe = session.get(
                url,
                headers={**headers, "Range": "bytes=0-0"},
                timeout=timeout,
                proxies=_NO_PROXY,
            )
            if probe.status_code == 200:
                # 服务端忽略 Range，整段都给了
                return probe.content
            if probe.status_code == 206:
                total = int((probe.headers.get("Content-Range") or "/0").rsplit("/", 1)[-1])
        except Exception:
            pass

    if total is None or total < _SEGMENT_MIN_PARALLEL_BYTES:
        return session.get(url, headers=headers, timeout=timeout, proxies=_NO_PROXY).content

    parts = max(2, min(parallelism, total // (128 * 1024)))
    step = total // parts

    def fetch_part(index: int) -> Tuple[int, bytes]:
        low = index * step
        high = total - 1 if index == parts - 1 else (index + 1) * step - 1
        part_headers = {**headers, "Range": "bytes=%d-%d" % (low, high)}
        last_exc = None
        for attempt in range(3):
            try:
                part_session = _thread_session()
                response = part_session.get(
                    url,
                    headers=part_headers,
                    timeout=timeout,
                    proxies=_NO_PROXY,
                )
                response.raise_for_status()
                return index, response.content
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.12 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise SilidmError("子分片拉取失败")

    try:
        chunks: List[bytes] = [b""] * parts
        for index, data in _segment_pool.map(fetch_part, range(parts)):
            chunks[index] = data
        return b"".join(chunks)
    except Exception:
        # 并行拉取偶发失败时退回单连接重试，保证稳定性
        for attempt in range(2):
            try:
                return session.get(url, headers=headers, timeout=timeout, proxies=_NO_PROXY).content
            except Exception:
                if attempt < 1:
                    time.sleep(0.3)
        return session.get(url, headers=headers, timeout=timeout, proxies=_NO_PROXY).content


# --------------------------------------------------------------------------
# 本地分片磁盘/内存缓存 & 智能管线预加载
# --------------------------------------------------------------------------

_ram_segment_cache: "OrderedDict[str, bytes]" = OrderedDict()
_ram_segment_cache_lock = threading.Lock()
MAX_RAM_SEGMENTS = 32

_prefetch_pool = ThreadPoolExecutor(max_workers=8)
_latest_playhead: Dict[str, int] = {}
_prefetch_lock = threading.Lock()


def _get_ram_cache(key: str) -> Optional[bytes]:
    with _ram_segment_cache_lock:
        data = _ram_segment_cache.get(key)
        if data is not None:
            _ram_segment_cache.move_to_end(key)
        return data


def _set_ram_cache(key: str, data: bytes) -> None:
    with _ram_segment_cache_lock:
        _ram_segment_cache[key] = data
        _ram_segment_cache.move_to_end(key)
        while len(_ram_segment_cache) > MAX_RAM_SEGMENTS:
            _ram_segment_cache.popitem(last=False)


def _segment_cache_path(episode_id: str, index: int) -> Path:
    folder = Path(HLS_SEGMENT_CACHE_DIR) / episode_id
    return folder / f"{index}.ts"


def get_cached_or_fetch_segment(episode_id: str, index: int, timeout: int = 30) -> bytes:
    """获取分片内容（RAM 缓存优先 -> 本地磁盘缓存 -> 远程拉取并写入缓存）。

    本地命中响应时间 < 1ms，重复播放或回退拖动 0 缓冲卡顿。
    """
    cache_key = f"{episode_id}:{index}"
    ram_data = _get_ram_cache(cache_key)
    if ram_data is not None:
        return ram_data

    disk_path = _segment_cache_path(episode_id, index)
    if disk_path.is_file() and disk_path.stat().st_size > 0:
        try:
            data = disk_path.read_bytes()
            try:
                os.utime(disk_path, None)
            except OSError:
                pass
            _set_ram_cache(cache_key, data)
            return data
        except OSError:
            pass

    segment_url = segment_url_for(episode_id, index, timeout=timeout)
    if not segment_url:
        raise SilidmError(f"未找到分片真实地址: {episode_id} #{index}")

    data = fetch_segment(segment_url, timeout=timeout)

    try:
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = disk_path.with_name(f"{index}.ts.tmp_{threading.get_ident()}_{time.time_ns()}")
        tmp_path.write_bytes(data)
        os.replace(tmp_path, disk_path)
    except OSError:
        pass

    _set_ram_cache(cache_key, data)
    return data


def prefetch_segments(episode_id: str, current_index: int, window: int = 6) -> None:
    """在后台静默预加载当前播放位置后续的 N 个分片到本地缓存中。

    当播放器请求 index 时，后台已经提前拉好了 index+1 ~ index+window，
    播放器走到下一片时直接命中本地缓存，彻底消除公网波动导致的卡顿。
    """
    with _prefetch_lock:
        _latest_playhead[episode_id] = current_index

    def _worker():
        urls = cached_segment_urls(episode_id)
        if not urls:
            play_url = url_from_episode_id(episode_id)
            if not play_url:
                return
            try:
                proxied_playlist(episode_id, play_url)
                urls = cached_segment_urls(episode_id)
            except Exception:
                return
        if not urls:
            return

        total_segs = len(urls)
        end_idx = min(total_segs, current_index + 1 + max(1, window))
        for tgt_idx in range(current_index + 1, end_idx):
            with _prefetch_lock:
                latest = _latest_playhead.get(episode_id, current_index)
            # 用户拖动进度条跳转时，中止已偏离当前视口太远的旧预取任务
            if abs(tgt_idx - latest) > window + 2:
                break

            target_file = _segment_cache_path(episode_id, tgt_idx)
            if target_file.is_file() and target_file.stat().st_size > 0:
                continue

            if tgt_idx >= len(urls):
                continue
            tgt_url = urls[tgt_idx]
            if not tgt_url:
                continue

            try:
                data = fetch_segment(tgt_url, timeout=25)
                if data:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    tmp_file = target_file.with_name(
                        f"{tgt_idx}.ts.tmp_{threading.get_ident()}_{time.time_ns()}"
                    )
                    tmp_file.write_bytes(data)
                    os.replace(tmp_file, target_file)
                    _set_ram_cache(f"{episode_id}:{tgt_idx}", data)
            except Exception:
                # 预取失败静默忽略，不干扰正常播放
                pass

    _prefetch_pool.submit(_worker)


def cleanup_segment_cache(max_mb: int = 3000) -> None:
    """清理过期的 HLS 分片磁盘缓存，防止磁盘被撑满。

    按剧集文件夹最后访问时间排序，淘汰最久未观看的剧集分片。
    """
    cache_dir = Path(HLS_SEGMENT_CACHE_DIR)
    if not cache_dir.is_dir():
        return
    try:
        max_bytes = max_mb * 1024 * 1024
        target_bytes = int(max_bytes * 0.7)
        total_size = 0
        ep_dirs = []
        for d in cache_dir.iterdir():
            if d.is_dir():
                d_size = 0
                latest_mtime = d.stat().st_mtime
                for f in d.iterdir():
                    if f.is_file():
                        st = f.stat()
                        d_size += st.st_size
                        if st.st_mtime > latest_mtime:
                            latest_mtime = st.st_mtime
                total_size += d_size
                ep_dirs.append({"path": d, "size": d_size, "time": latest_mtime})

        if total_size <= max_bytes:
            return

        # 最久未访问的排前面
        ep_dirs.sort(key=lambda x: x["time"])
        for item in ep_dirs:
            if total_size <= target_bytes:
                break
            try:
                import shutil
                shutil.rmtree(item["path"], ignore_errors=True)
                total_size -= item["size"]
            except Exception:
                pass
    except Exception:
        pass


# --------------------------------------------------------------------------
# 下载合并（离线保存整集时使用）
# --------------------------------------------------------------------------

def _clean_env() -> Dict[str, str]:
    """去掉代理环境变量：本机 http_proxy 会让 ffmpeg 走 httpproxy 协议导致拉流失败。"""
    env = {k: v for k, v in os.environ.items()
           if k.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


def _progress_value_to_seconds(key: str, value: str) -> Optional[float]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if key in ("out_time_us", "out_time_ms"):
        # 注意：ffmpeg 的 out_time_ms 实际也是微秒（历史遗留），按微秒处理
        return number / 1_000_000
    if key == "out_time":
        parts = value.split(":")
        if len(parts) == 3:
            try:
                hours, minutes, seconds = (float(p) for p in parts)
            except ValueError:
                return None
            return hours * 3600 + minutes * 60 + seconds
    return None


def stream_to_mp4(url: str, out_path, duration_hint: float = 0,
                  progress_callback=None) -> str:
    """用 ffmpeg 把单集拉成完整 mp4（只在「下载到本地」时使用；在线播放走 HLS 代理）。

    ``progress_callback(stage, percent)`` 中 stage 取值：
    ``resolving`` / ``downloading`` / ``merging``。
    """
    out_path = Path(out_path)
    m3u8 = resolve_m3u8(url)
    if progress_callback:
        progress_callback("resolving", 8)

    temp_path = out_path.with_name(f".temp_{out_path.stem}_silidm.mp4")
    command = [
        "ffmpeg", "-y",
        "-loglevel", "error",
        # 属防御性设置：若上游把分片伪装成非 .ts 扩展名，ffmpeg 7.x 默认的
        # 扩展名校验（extension_picky）会直接拒收。
        "-extension_picky", "0",
        "-allowed_extensions", "ALL",
        "-rw_timeout", "30000000",
        "-i", m3u8,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        str(temp_path),
    ]

    tail: List[str] = []
    last_seconds = 0.0
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_clean_env(),
        )
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                if key in ("out_time_us", "out_time_ms", "out_time"):
                    seconds = _progress_value_to_seconds(key, value)
                    if seconds is not None:
                        last_seconds = max(last_seconds, seconds)
                        if duration_hint > 0 and progress_callback:
                            ratio = min(1.0, max(0.0, seconds / duration_hint))
                            progress_callback("downloading", 10 + int(ratio * 85))
                    continue
                if key in ("progress", "frame", "fps", "bitrate", "total_size", "speed"):
                    continue
            tail.append(line)
            tail = tail[-40:]
        process.wait()

        if process.returncode != 0:
            detail = " | ".join(tail[-6:]) or "未知错误"
            raise SilidmError(f"ffmpeg 拉流失败: {detail}")

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise SilidmError("ffmpeg 未产出有效视频文件")

        # 上游 CDN 偶发在拉了几秒后中断（TLS 会话被服务端失效），此时 ffmpeg 仍可能
        # 以退出码 0 结束，留下一个只有几秒的残片。用进度回读的时长挡住这种静默截断。
        if duration_hint > 0 and 0 < last_seconds < duration_hint * 0.8:
            raise SilidmError(
                f"拉流提前中断：仅获取到约 {int(last_seconds)}s / 共 {int(duration_hint)}s，请重试"
            )

        if progress_callback:
            progress_callback("merging", 97)
        os.replace(temp_path, out_path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

    return str(out_path)
