import sys
import os
import re
import subprocess
import shutil
import requests
import json
import time
import locale
from functools import reduce
from hashlib import md5
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio
import aiohttp
from typing import Optional, Dict, List, Any
import threading
import uuid

try:
    from .filesystem import ensure_directories, safe_resolve_path
    from .http_client import (
        HEADERS,
        close_http_session,
        get_download_lock,
        get_http_session,
        limited_get,
        limited_get_sync,
    )
    from .settings import (
        BILIBILI_COOKIE,
        COVERS_DIR,
        DEFAULT_PLAYER_SETTINGS,
        FRONTEND_DIR,
        MAX_CACHE_SIZE_MB,
        MIN_FREE_DISK_MB,
        SILIDM_PREFETCH_WINDOW,
        STATE_FILE,
        SUBTITLES_DIR,
        TARGET_CACHE_SIZE_MB,
        VIDEOS_DIR,
        log_startup_configuration,
        set_bilibili_cookie,
    )
    from . import silidm as silidm_service
    from . import iqiyi_metadata as iqiyi_service
    from . import time_limits as time_limits_service
except ImportError:
    from filesystem import ensure_directories, safe_resolve_path
    from http_client import (
        HEADERS,
        close_http_session,
        get_download_lock,
        get_http_session,
        limited_get,
        limited_get_sync,
    )
    from settings import (
        BILIBILI_COOKIE,
        COVERS_DIR,
        DEFAULT_PLAYER_SETTINGS,
        FRONTEND_DIR,
        MAX_CACHE_SIZE_MB,
        MIN_FREE_DISK_MB,
        SILIDM_PREFETCH_WINDOW,
        STATE_FILE,
        SUBTITLES_DIR,
        TARGET_CACHE_SIZE_MB,
        VIDEOS_DIR,
        log_startup_configuration,
        set_bilibili_cookie,
    )
    import silidm as silidm_service
    import iqiyi_metadata as iqiyi_service
    import time_limits as time_limits_service

log_startup_configuration()

# --- 外部来源解析器分派 -----------------------------------------------------
# 每个来源模块都提供同一组接口：is_episode_id / url_from_episode_id /
# make_episode_id / fetch_metadata / proxied_playlist / segment_url_for /
# fetch_segment / stream_to_mp4。这里按 episode_id 前缀挑对应的实现，
# 路由与下载逻辑就都不必关心来源差异。
# 目前只有 silidm 一个外部来源（爱奇艺链路已整体移除）；保留这层分派是为了
# 以后新增来源时只补一个同接口模块、不必再动路由。
_RESOLVERS = {
    "silidm": silidm_service,
}
# 走「HLS 流式播放（不预下载）」的来源标记
_STREAM_SOURCES = ("silidm",)


def _resolver_for_episode_id(episode_id: str):
    """按 episode_id 前缀挑解析器；不认识返回 None。"""
    for name, service in _RESOLVERS.items():
        if service.is_episode_id(episode_id):
            return service
    return None

# Download tasks are transient; watch progress is persisted in STATE_FILE.
_download_tasks: Dict[str, Dict] = {}
_progress_lock = asyncio.Lock()

# --- Bilibili Downloader Logic ---

# --- 磁盘空间与视频缓存 LRU 管理 ---
_cache_cleanup_lock = threading.Lock()

def clean_orphan_temp_files(force_all: bool = False) -> int:
    """清理因网络中断、下载合并异常等遗留的临时音视频碎片（.temp_* / .faststart_*）"""
    now = time.time()
    cleaned_count = 0
    cleaned_bytes = 0
    try:
        if not VIDEOS_DIR.exists():
            return 0
        for root, _, files in os.walk(VIDEOS_DIR):
            for f in files:
                if f.startswith('.temp_') or f.startswith('.faststart_'):
                    p = Path(root) / f
                    try:
                        # 启动时强制全部清理；运行时清理超过 5 分钟前遗留的（避免误删当前正在合并的文件）
                        if force_all or (now - p.stat().st_mtime > 300):
                            size = p.stat().st_size
                            p.unlink(missing_ok=True)
                            cleaned_count += 1
                            cleaned_bytes += size
                    except Exception:
                        pass
        if cleaned_count > 0:
            print(f"[临时文件清理] 已清理 {cleaned_count} 个残留临时碎片，释放 {cleaned_bytes / (1024 * 1024):.2f} MB 空间")
    except Exception as e:
        print(f"清理临时文件异常: {e}")
    return cleaned_count

def get_cache_stats() -> dict:
    """获取当前视频缓存占用、视频列表及服务器磁盘剩余空间"""
    total_bytes = 0
    video_files = []
    try:
        if VIDEOS_DIR.exists():
            for root, _, files in os.walk(VIDEOS_DIR):
                for f in files:
                    if f.endswith('.mp4') and not f.startswith('.'):
                        p = Path(root) / f
                        try:
                            st = p.stat()
                            # 优先采用最后访问时间 (atime)，若文件系统未更新则回落至修改时间 (mtime)
                            last_access = max(st.st_atime, st.st_mtime)
                            video_files.append({
                                'path': p,
                                'size': st.st_size,
                                'last_access': last_access,
                                'name': p.name
                            })
                            total_bytes += st.st_size
                        except Exception:
                            pass
        disk_free = shutil.disk_usage(VIDEOS_DIR).free if VIDEOS_DIR.exists() else shutil.disk_usage('.').free
    except Exception as e:
        print(f"获取磁盘状态异常: {e}")
        disk_free = 1024 * 1024 * 1024 * 10

    return {
        'total_bytes': total_bytes,
        'video_files': video_files,
        'disk_free_bytes': disk_free
    }

def cleanup_video_cache(needed_bytes: int = 0) -> dict:
    """
    基于双重水位线的 LRU 视频缓存回收：
    1. 当预计缓存占用 (当前占用 + needed_bytes) > MAX_CACHE_SIZE_MB
    2. 或预计磁盘剩余 (当前剩余 - needed_bytes) < MIN_FREE_DISK_MB
    按访问时间由远及近删除旧视频，直到缓存回落至 TARGET_CACHE_SIZE_MB 且磁盘剩余安全。
    * 绝不删除 list.txt、.cache_episodes.json、封面或字幕。
    """
    with _cache_cleanup_lock:
        clean_orphan_temp_files(force_all=False)

        stats = get_cache_stats()
        total_bytes = stats['total_bytes']
        video_files = stats['video_files']
        disk_free_bytes = stats['disk_free_bytes']

        max_cache_bytes = MAX_CACHE_SIZE_MB * 1024 * 1024
        target_cache_bytes = TARGET_CACHE_SIZE_MB * 1024 * 1024
        min_free_bytes = MIN_FREE_DISK_MB * 1024 * 1024

        trigger_by_cache = (total_bytes + needed_bytes) > max_cache_bytes
        trigger_by_disk = (disk_free_bytes - needed_bytes) < min_free_bytes

        if not (trigger_by_cache or trigger_by_disk):
            return {
                "triggered": False,
                "deleted_count": 0,
                "freed_bytes": 0,
                "current_cache_mb": round(total_bytes / (1024 * 1024), 2),
                "disk_free_mb": round(disk_free_bytes / (1024 * 1024), 2)
            }

        reasons = []
        if trigger_by_cache:
            reasons.append(f"视频缓存预计达 {(total_bytes + needed_bytes)/(1024*1024):.1f}MB (上限: {MAX_CACHE_SIZE_MB}MB)")
        if trigger_by_disk:
            reasons.append(f"服务器磁盘可用预计降至 {(disk_free_bytes - needed_bytes)/(1024*1024):.1f}MB (警戒线: {MIN_FREE_DISK_MB}MB)")

        print(f"[空间预警] 触发 LRU 视频缓存回收: {' | '.join(reasons)}")

        # 按最后访问时间升序排序（最旧的排在最前面，优先被淘汰）
        video_files.sort(key=lambda x: x['last_access'])

        deleted_count = 0
        freed_bytes = 0

        for item in video_files:
            # 当缓存已降至目标安全水位，且磁盘剩余高于安全警戒线时，停止清理
            current_estimated_cache = total_bytes - freed_bytes + needed_bytes
            current_estimated_free_disk = disk_free_bytes + freed_bytes - needed_bytes
            if current_estimated_cache <= target_cache_bytes and current_estimated_free_disk >= min_free_bytes:
                break

            p: Path = item['path']
            size: int = item['size']
            try:
                p.unlink(missing_ok=True)
                freed_bytes += size
                deleted_count += 1
                print(f"[LRU 淘汰] 已清理旧视频: {p.name} ({size / (1024 * 1024):.1f} MB)")
            except Exception as e:
                print(f"删除旧视频缓存失败 ({p.name}): {e}")

        if hasattr(silidm_service, "cleanup_segment_cache"):
            silidm_service.cleanup_segment_cache()

        print(f"[缓存回收完毕] 共清理 {deleted_count} 个视频，释放 {freed_bytes / (1024 * 1024):.1f} MB。"
              f" 当前缓存: {(total_bytes - freed_bytes)/(1024*1024):.1f} MB，"
              f" 磁盘剩余: {(disk_free_bytes + freed_bytes)/(1024*1024):.1f} MB")

        return {
            "triggered": True,
            "deleted_count": deleted_count,
            "freed_bytes": freed_bytes,
            "current_cache_mb": round((total_bytes - freed_bytes) / (1024 * 1024), 2),
            "disk_free_mb": round((disk_free_bytes + freed_bytes) / (1024 * 1024), 2)
        }

def optimize_existing_videos_faststart_bg():
    """后台轻量巡检：若发现本地已有 MP4 未开启 faststart，则自动无损转换为 faststart（moov置顶）"""
    try:
        for root, _, files in os.walk(VIDEOS_DIR):
            for f in files:
                if f.endswith('.mp4') and not f.startswith('.'):
                    p = Path(root) / f
                    try:
                        with open(p, 'rb') as fp:
                            header = fp.read(1024)
                            if b'moov' in header:
                                continue
                        # 需要转换
                        tmp_p = p.with_name(f".faststart_{p.name}")
                        cmd = ['ffmpeg', '-y', '-i', str(p), '-c', 'copy', '-movflags', '+faststart', str(tmp_p)]
                        res = subprocess.run(cmd, capture_output=True)
                        if res.returncode == 0 and tmp_p.exists():
                            tmp_p.replace(p)
                            print(f"⚡ [FastStart 优化] 已优化本地视频: {p.name}")
                        else:
                            tmp_p.unlink(missing_ok=True)
                    except Exception:
                        pass
    except Exception as e:
        print(f"后台 FastStart 扫描异常: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动阶段：确保目录存在
    ensure_directories(VIDEOS_DIR, COVERS_DIR, SUBTITLES_DIR)

    # 启动时清理孤儿临时分片并执行一次缓存水位检查
    clean_orphan_temp_files(force_all=True)
    cleanup_video_cache(needed_bytes=0)

    threading.Thread(target=optimize_existing_videos_faststart_bg, daemon=True).start()
    yield
    # 关闭阶段：清理异步资源
    await close_http_session()
    print("[服务退出] HTTP会话已安全关闭")

app = FastAPI(title="Video Player Backend", lifespan=lifespan)

# 设置locale以支持中文排序
try:
    locale.setlocale(locale.LC_COLLATE, 'zh_CN.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_COLLATE, 'Chinese (Simplified)_China.936')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_COLLATE, 'zh_CN')
        except locale.Error:
            pass

# 挂载前端静态文件服务
app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
# 模块化前端资源使用独立静态挂载，避免 catch-all 路由把缺失模块回退成 index.html。
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="frontend-js")
app.mount("/styles", StaticFiles(directory=str(FRONTEND_DIR / "styles")), name="frontend-styles")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 中文友好的排序函数
def chinese_sort_key(text: str) -> list:
    """生成中文友好的排序键"""
    import unicodedata
    normalized = unicodedata.normalize('NFKD', text)
    result = []
    for char in normalized:
        if char.isdigit():
            result.append(('0', char))
        elif char.isascii() and char.isalpha():
            result.append(('1', char.lower()))
        else:
            result.append(('2', char))
    return result

def sort_folders_chinese(folders: List[dict]) -> List[dict]:
    """按中文友好的方式排序文件夹"""
    try:
        return sorted(folders, key=lambda x: locale.strxfrm(x['name']))
    except (AttributeError, TypeError):
        return sorted(folders, key=lambda x: chinese_sort_key(x['name']))

# 内存缓存（带上限淘汰机制，防内存溢出）
MAX_CACHE_SIZE = 1000
_video_parts_cache: Dict[str, Any] = {}
_wbi_key_cache: Optional[str] = None
_wbi_key_cache_time: float = 0

def get_cached(key: str) -> Any:
    return _video_parts_cache.get(key)

def set_cached(key: str, value: Any) -> None:
    if len(_video_parts_cache) >= MAX_CACHE_SIZE:
        for k in list(_video_parts_cache.keys())[:150]:
            _video_parts_cache.pop(k, None)
    _video_parts_cache[key] = value

# WBI签名相关常量和函数
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]

async def get_wbi_keys_async(cookie: Optional[str] = None) -> Optional[str]:
    """异步获取WBI密钥，带缓存（5分钟有效）"""
    global _wbi_key_cache, _wbi_key_cache_time

    current_time = time.time()
    if _wbi_key_cache and (current_time - _wbi_key_cache_time) < 300:
        return _wbi_key_cache

    try:
        session = await get_http_session()
        headers = HEADERS.copy()
        if cookie:
            headers['Cookie'] = cookie

        async with session.get('https://api.bilibili.com/x/web-interface/nav', headers=headers) as response:
            if response.status == 200:
                json_content = await response.json()
                wbi_img = json_content.get('data', {}).get('wbi_img', {})
                if wbi_img.get('img_url') and wbi_img.get('sub_url'):
                    img_url: str = wbi_img['img_url']
                    sub_url: str = wbi_img['sub_url']
                    img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                    sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]

                    wbi_key = get_mixin_key(img_key + sub_key)
                    _wbi_key_cache = wbi_key
                    _wbi_key_cache_time = current_time
                    return wbi_key
    except Exception as e:
        print(f"异步获取WBI密钥失败: {e}")
    return None

def get_wbi_keys(cookie: Optional[str] = None) -> Optional[str]:
    """同步获取WBI密钥，带缓存（5分钟有效），供后台下载线程使用"""
    global _wbi_key_cache, _wbi_key_cache_time

    current_time = time.time()
    if _wbi_key_cache and (current_time - _wbi_key_cache_time) < 300:
        return _wbi_key_cache

    try:
        headers = HEADERS.copy()
        if cookie:
            headers['Cookie'] = cookie

        resp = limited_get_sync('https://api.bilibili.com/x/web-interface/nav', headers=headers, timeout=10)
        if resp and resp.status_code == 200:
            json_content = resp.json()
            wbi_img = json_content.get('data', {}).get('wbi_img', {})
            if wbi_img.get('img_url') and wbi_img.get('sub_url'):
                img_url: str = wbi_img['img_url']
                sub_url: str = wbi_img['sub_url']
                img_key = img_url.rsplit('/', 1)[1].split('.')[0]
                sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]

                wbi_key = get_mixin_key(img_key + sub_key)
                _wbi_key_cache = wbi_key
                _wbi_key_cache_time = current_time
                return wbi_key
    except Exception as e:
        print(f"同步获取WBI密钥失败: {e}")
    return None

def sign_wbi_params(params: dict, wbi_key: str) -> dict:
    params['wts'] = str(int(time.time()))
    sorted_params = dict(sorted(params.items()))
    query_parts = []
    for k, v in sorted_params.items():
        v_str = str(v).replace("'", "").replace("!", "").replace("(", "").replace(")", "").replace("*", "")
        query_parts.append(f'{k}={v_str}')
    query_string = '&'.join(query_parts)
    w_rid = md5((query_string + wbi_key).encode()).hexdigest()
    params['w_rid'] = w_rid
    return params

def format_webvtt_time(seconds: float) -> str:
    """将秒数转换为WebVTT时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

def extract_bvid_from_url(url_or_bvid: str) -> str:
    """从URL中提取BV号或直接返回校验通过的BV号"""
    url_or_bvid = url_or_bvid.strip()
    if url_or_bvid.startswith('http'):
        match = re.search(r'/video/(BV[a-zA-Z0-9]+)', url_or_bvid)
        if match:
            return match.group(1)
        raise ValueError(f"Could not extract BV ID from URL: {url_or_bvid}")
    else:
        if re.match(r'^BV[a-zA-Z0-9]+$', url_or_bvid):
            return url_or_bvid
        raise ValueError(f"Invalid BV ID format: {url_or_bvid}")

# --- list.txt 行解析（B站 / silidm 混排） ---

def parse_list_entry(line: str) -> Optional[Dict]:
    """解析 list.txt 的单行，支持 B站 与 silidm（电影先生）混排。

    可识别写法（``|`` 为可选标题分隔符，放在标识任意一侧都行）::

        BV1xxxxxxxxx
        https://www.bilibili.com/video/BV1xxxxxxxxx
        https://silidm.com/video/40717.html        # 详情页 —— 一行展开整季
        https://silidm.com/play/40717-1-1.html     # 单集播放页
        第1集 露营好时光 | https://silidm.com/play/40717-1-1.html

    返回 ``{'kind': 'bilibili'|'silidm', 'key': bvid 或 URL, 'title': 自定义标题或 None}``；
    无法识别时返回 None。**无法识别的 http 链接会打印一行提示**：不支持静默跳过，
    否则写错格式的链接只会表现为「这个合集莫名其妙空了」，极难排查。
    """
    raw = (line or "").strip()
    if not raw or raw.startswith('#'):
        return None

    album_match = re.search(r'(?:albumid|album_id|aid)\s*[:=]\s*(\d+)', raw, re.IGNORECASE)
    album_id = album_match.group(1) if album_match else None
    parts = [part.strip() for part in raw.split('|')] if '|' in raw else [raw]
    identifier = next(
        (p for p in parts if p.startswith('http') or re.match(r'^BV[a-zA-Z0-9]+$', p)),
        None,
    )
    if not identifier:
        return None
    title = next((p for p in parts if p and p != identifier and not re.search(r'(?:albumid|album_id|aid)\s*[:=]', p, re.IGNORECASE)), None)

    if silidm_service.is_silidm_url(identifier):
        normalized = silidm_service.normalize_url(identifier)
        if not normalized:
            return None
        # 详情页（/video/<id>.html）会自动展开整季，单集播放页则只出这一集
        return {'kind': 'silidm', 'key': normalized, 'title': title, 'album_id': album_id}

    try:
        bvid = extract_bvid_from_url(identifier)
    except ValueError:
        print(f"[list.txt] 无法识别的视频来源，该行已跳过: {raw}")
        return None
    return {'kind': 'bilibili', 'key': bvid, 'title': title}


async def get_bv_detail_async(bvid: str) -> Optional[Dict]:
    """获取单个 BV 的详细信息（官方 view API，含标题、封面、时长及所有分P）"""
    cache_key = f"view_{bvid}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    resp = await limited_get(url)
    if resp and resp.status == 200:
        try:
            data = await resp.json()
            if data.get('code') == 0:
                vdata = data['data']
                res = {
                    'bvid': bvid,
                    'title': vdata.get('title', ''),
                    'pic': vdata.get('pic', ''),
                    'duration': vdata.get('duration', 0),
                    'pages': vdata.get('pages', [])
                }
                set_cached(cache_key, res)
                return res
        except Exception as e:
            print(f"解析 BV 详情失败 ({bvid}): {e}")
    return None

async def get_folder_episodes_async(folder_path: str) -> List[Dict]:
    """
    核心：解析文件夹下 list.txt 中的所有 BV（支持多 BV 集合与单个 BV 多个分P）
    展开生成统一的连续集数列表 (index: 1, 2, 3...)
    """
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    if not target_folder or not target_folder.exists() or not target_folder.is_dir():
        return []

    list_file = target_folder / "list.txt"
    if not list_file.exists():
        return []

    try:
        list_mtime_ns = list_file.stat().st_mtime_ns
    except OSError:
        return []

    # 元数据字段变更时自动绕过旧进程内缓存。
    cache_key = f"folder_episodes_v4_{folder_path}:{list_mtime_ns}"
    cached = get_cached(cache_key)
    if cached is not None:
        return cached

    cache_file = target_folder / ".cache_episodes.json"
    if cache_file.exists():
        try:
            if cache_file.stat().st_mtime >= list_file.stat().st_mtime:
                cached_data = json.loads(cache_file.read_text(encoding='utf-8'))
                if cached_data:
                    stale_silidm = any(
                        (ep.get('source') == 'silidm' or str(ep.get('bvid', '')).startswith('silidm_')) and (
                            str(ep.get('title', '')).startswith('silidm 视频')
                            or not ep.get('cover_source')
                            # 旧缓存可能是爱奇艺接口原始的 120x160 竖版地址。
                            or (ep.get('album_id') and re.search(r'_m_601(?:_m1)?\.jpg$', str(ep.get('cover_source', '')), re.IGNORECASE))
                        ) for ep in cached_data
                    )
                    if stale_silidm:
                        cached_data = None
                if cached_data:
                    for ep in cached_data:
                        # 旧版缓存没有 source/url 字段，补默认值保持向后兼容
                        ep.setdefault('source', 'bilibili')
                        ep.setdefault('url', '')
                        cover_filename = f"{ep['bvid']}_p{ep['page']}.jpg"
                        if (COVERS_DIR / cover_filename).exists():
                            ep['cover_url'] = f"/covers/{cover_filename}"
                    set_cached(cache_key, cached_data)
                    return cached_data
        except Exception:
            pass

    with open(list_file, 'r', encoding='utf-8') as f:
        raw_lines = [line for line in f if line.strip() and not line.startswith('#')]

    # 逐行解析并去重（严格保持 list.txt 原始顺序，B站与外部来源可任意混排）
    entries: List[Dict] = []
    seen_keys = set()
    for line in raw_lines:
        entry = parse_list_entry(line)
        if not entry:
            continue
        dedupe_key = (entry['kind'], entry['key'])
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        entries.append(entry)

    if not entries:
        return []

    # silidm 详情页：一行就代表整季，先展开成单集条目（保持 list.txt 的原始顺序）
    detail_urls = [e['key'] for e in entries
                   if e['kind'] == 'silidm' and silidm_service.is_detail_url(e['key'])]
    detail_map: Dict[str, Dict] = {}
    if detail_urls:
        detail_results = await asyncio.gather(
            *[asyncio.to_thread(silidm_service.fetch_detail, url) for url in detail_urls],
            return_exceptions=True,
        )
        detail_map = {url: (r if isinstance(r, dict) else {})
                      for url, r in zip(detail_urls, detail_results)}

    expanded: List[Dict] = []
    seen_expanded = set()
    for entry in entries:
        items = [entry]
        if entry['kind'] == 'silidm' and silidm_service.is_detail_url(entry['key']):
            detail = detail_map.get(entry['key']) or {}
            items = []
            for sub in detail.get('episodes') or []:
                display = sub['title']
                if entry.get('title'):
                    display = f"{entry['title']} {display}"
                items.append({
                    'kind': 'silidm',
                    'key': sub['url'],
                    'title': display,
                    'episode_title': sub.get('title', display),
                    'series_title': detail.get('title', ''),
                    'cover': detail.get('cover', ''),
                    'album_id': entry.get('album_id'),
                    'from_detail': True,
                })
            if not items:
                print(f"silidm 详情页未展开出剧集，已跳过: {entry['key']}")
        for item in items:
            dedupe = (item['kind'], item['key'])
            if dedupe in seen_expanded:
                continue
            seen_expanded.add(dedupe)
            expanded.append(item)
    entries = expanded

    bvids = [e['key'] for e in entries if e['kind'] == 'bilibili']
    # 详情页展开出来的条目已自带标题/封面，只有单独写的播放页才需要再抓一次
    silidm_urls = [e['key'] for e in entries
                   if e['kind'] == 'silidm' and not e.get('from_detail')]

    # 并发安全拉取：B站详情 + silidm 元数据
    bv_results = await asyncio.gather(*[get_bv_detail_async(bvid) for bvid in bvids], return_exceptions=True)
    bv_detail_map = {bvid: r for bvid, r in zip(bvids, bv_results) if r and not isinstance(r, Exception)}
    sil_results = await asyncio.gather(
        *[asyncio.to_thread(silidm_service.fetch_metadata, url) for url in silidm_urls],
        return_exceptions=True,
    )
    silidm_meta_map = {url: (r if isinstance(r, dict) else {})
                       for url, r in zip(silidm_urls, sil_results)}

    album_ids = sorted({str(e.get('album_id')) for e in entries if e.get('album_id')})
    album_results = await asyncio.gather(
        *[asyncio.to_thread(iqiyi_service.fetch_album_metadata, album_id) for album_id in album_ids],
        return_exceptions=True,
    )
    album_map = {
        album_id: (result if isinstance(result, dict) else {})
        for album_id, result in zip(album_ids, album_results)
    }

    episodes = []
    idx = 1

    for entry in entries:
        override = entry.get('title')

        if entry['kind'] == 'bilibili':
            detail = bv_detail_map.get(entry['key'])
            if not detail:
                continue

            pages = detail.get('pages', [])
            bvid = detail['bvid']
            bv_title = detail['title']
            bv_pic = detail['pic']

            if len(pages) <= 1:
                p = pages[0] if pages else {'page': 1, 'cid': 0, 'part': bv_title, 'duration': detail['duration']}
                clean_title = override or p.get('part') or bv_title
                cover_filename = f"{bvid}_p{p['page']}.jpg"
                has_local_cover = (COVERS_DIR / cover_filename).exists()

                episodes.append({
                    "index": idx,
                    "title": clean_title,
                    "page": p.get('page', 1),
                    "bvid": bvid,
                    "cid": p.get('cid', 0),
                    "duration": p.get('duration') or detail.get('duration', 0),
                    "cover_url": f"/covers/{cover_filename}" if has_local_cover else "",
                    "cover_source": p.get('first_frame') or bv_pic,
                    "has_subtitle": None,
                    "source": "bilibili",
                    "url": f"https://www.bilibili.com/video/{bvid}",
                })
                idx += 1
            else:
                # 单个 BV 内含多个分 P
                for p in pages:
                    sub_title = p.get('part') or f"P{p['page']}"
                    if override:
                        display_title = f"{override} - {sub_title}"
                    else:
                        display_title = f"{bv_title} - {sub_title}" if len(bvids) > 1 else sub_title
                    cover_filename = f"{bvid}_p{p['page']}.jpg"
                    has_local_cover = (COVERS_DIR / cover_filename).exists()

                    episodes.append({
                        "index": idx,
                        "title": display_title,
                        "page": p.get('page', 1),
                        "bvid": bvid,
                        "cid": p.get('cid', 0),
                        "duration": p.get('duration', 0),
                        "cover_url": f"/covers/{cover_filename}" if has_local_cover else "",
                        "cover_source": p.get('first_frame') or bv_pic,
                        "has_subtitle": None,
                        "source": "bilibili",
                        "url": f"https://www.bilibili.com/video/{bvid}?p={p.get('page', 1)}",
                    })
                    idx += 1
        elif entry['kind'] == 'silidm':
            # silidm 单集：ID 形如 silidm_<vod>-<sid>-<nid>，进度与缓存文件据此命名
            url = entry['key']
            episode_id = silidm_service.make_episode_id(url)
            if not episode_id:
                continue

            meta = silidm_meta_map.get(url) or {}
            album = album_map.get(str(entry.get('album_id'))) or {}
            play = silidm_service.parse_play_path(url)
            episode_number = int(play[2]) if play else 0
            album_episode = (album.get('episodes') or {}).get(episode_number) or {}
            page = 1
            cover_filename = f"{episode_id}_p{page}.jpg"
            has_local_cover = (COVERS_DIR / cover_filename).exists()
            qiyi_title = album_episode.get('title', '')
            qiyi_cover = album_episode.get('cover', '')

            episodes.append({
                "index": idx,
                "title": qiyi_title or override or entry.get('title') or meta.get('title') or f"silidm 视频 {episode_id}",
                "episode_title": qiyi_title or entry.get('episode_title') or meta.get('title', ''),
                "series_title": album.get('title') or entry.get('series_title') or meta.get('album', ''),
                "page": page,
                "bvid": episode_id,
                "cid": 0,
                "duration": meta.get('duration', 0),
                # 本地缓存优先，未缓存时使用外部元数据封面
                "cover_url": (f"/covers/{cover_filename}" if has_local_cover else qiyi_cover),
                "cover_source": qiyi_cover or entry.get('cover') or meta.get('cover', ''),
                "metadata_source": "iqiyi" if qiyi_title or qiyi_cover else "silidm",
                "album_id": entry.get('album_id', ''),
                "has_subtitle": False,
                "source": "silidm",
                "url": url,
            })
            idx += 1

    if episodes:
        set_cached(cache_key, episodes)
        try:
            cache_file.write_text(json.dumps(episodes, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    return episodes

async def download_and_cache_cover_async(bvid: str, page: int, cover_url: str) -> str:
    """异步下载并缓存封面图片，返回本地路径"""
    if not cover_url:
        return ""

    if cover_url.startswith('//'):
        cover_url = 'https:' + cover_url

    cover_filename = f"{bvid}_p{page}.jpg"
    cover_path = COVERS_DIR / cover_filename

    if cover_path.exists():
        return f"/covers/{cover_filename}"

    try:
        # 爱奇艺等外部图床检测并拒收 B 站 Referer（会 403 触发熔断）；非 B 站图床清空 Referer 或设为主站
        headers = None
        if "iqiyipic.com" in cover_url:
            headers = {"Referer": "https://www.iqiyi.com/"}
        elif not any(domain in cover_url for domain in ("bilibili.com", "hdslb.com")):
            headers = {"Referer": ""}

        response = await limited_get(cover_url, headers=headers)
        if response and response.status == 200:
            content = await response.read()
            with open(cover_path, 'wb') as f:
                f.write(content)
            return f"/covers/{cover_filename}"
    except Exception as e:
        print(f"异步下载封面失败: {e}")

    return ""

async def check_subtitle_availability_async(bvid: str, page: int, cid: int) -> bool:
    """异步检查视频是否有字幕可用（纯异步非阻塞）"""
    if not BILIBILI_COOKIE or not cid:
        return False
    try:
        wbi_key = await get_wbi_keys_async(BILIBILI_COOKIE)
        if not wbi_key:
            return False

        params = {'bvid': bvid, 'cid': cid}
        signed_params = sign_wbi_params(params, wbi_key)

        player_api_url = "https://api.bilibili.com/x/player/wbi/v2"
        headers = HEADERS.copy()
        headers['Cookie'] = BILIBILI_COOKIE

        response = await limited_get(player_api_url, params=signed_params, headers=headers)
        if not response or response.status != 200:
            return False

        subtitle_data = await response.json()
        if subtitle_data.get('code') != 0:
            return False

        subtitles_list = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
        user_subtitle = next((s for s in subtitles_list if s.get('ai_type') == 0 and s.get('subtitle_url')), None)
        return user_subtitle is not None
    except Exception as e:
        print(f"异步检查字幕可用性失败: {e}")
        return False

async def download_and_cache_subtitle(bvid: str, page: int, cid: int) -> str:
    """下载并缓存字幕文件，返回本地路径（纯异步非阻塞）"""
    if not BILIBILI_COOKIE or not cid:
        return ""
    try:
        subtitle_filename = f"{bvid}_p{page}.vtt"
        subtitle_path = SUBTITLES_DIR / subtitle_filename

        if subtitle_path.exists():
            return f"/subtitles/{subtitle_filename}"

        wbi_key = await get_wbi_keys_async(BILIBILI_COOKIE)
        if not wbi_key:
            return ""

        params = {'bvid': bvid, 'cid': cid}
        signed_params = sign_wbi_params(params, wbi_key)

        player_api_url = "https://api.bilibili.com/x/player/wbi/v2"
        headers = HEADERS.copy()
        headers['Cookie'] = BILIBILI_COOKIE

        response = await limited_get(player_api_url, params=signed_params, headers=headers)
        if not response or response.status != 200:
            return ""

        subtitle_data = await response.json()
        if subtitle_data.get('code') != 0:
            return ""

        subtitles_list = subtitle_data.get('data', {}).get('subtitle', {}).get('subtitles', [])
        user_subtitle = next((s for s in subtitles_list if s.get('ai_type') == 0 and s.get('subtitle_url')), None)
        if not user_subtitle:
            return ""

        subtitle_url = user_subtitle.get('subtitle_url')
        if subtitle_url.startswith('//'):
            subtitle_url = 'https:' + subtitle_url

        sub_resp = await limited_get(subtitle_url)
        if not sub_resp or sub_resp.status != 200:
            return ""

        subtitle_content = await sub_resp.json()

        with open(subtitle_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for line in subtitle_content.get('body', []):
                start_time = format_webvtt_time(line.get('from', 0))
                end_time = format_webvtt_time(line.get('to', 0))
                content = line.get('content', '')
                f.write(f"{start_time} --> {end_time}\n{content}\n\n")

        return f"/subtitles/{subtitle_filename}"
    except Exception as e:
        print(f"下载字幕失败: {e}")
        return ""

def stream_download_file(url: str, output_path: Path, headers: Optional[Dict] = None, chunk_size: int = 128 * 1024, progress_callback=None) -> None:
    """流式下载大文件到磁盘，避免全量载入内存导致 OOM"""
    req_headers = HEADERS.copy()
    if headers:
        req_headers.update(headers)
    with requests.get(url, headers=req_headers, stream=True, timeout=(10, 60)) as r:
        r.raise_for_status()
        total = int(r.headers.get('content-length') or 0)
        downloaded = 0
        with open(output_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

def download_and_merge(bvid: str, p_info: dict, target_dir: Path, progress_callback=None) -> str:
    """
    按需下载音视频流并调用 ffmpeg 合并
    采用分块流式写入磁盘，避免内存溢出；临时文件使用安全前缀并保证清理
    """
    page = p_info.get('page', 1)
    cid = p_info.get('cid', 0)
    part_title = p_info.get('part') or f"{bvid}_p{page}"
    clean_name = re.sub(r'[\\/*?:"<>|]', "", part_title).strip()
    if not clean_name:
        clean_name = f"{bvid}_p{page}"
    final_video_path = target_dir / f"{bvid}_p{page}.mp4"
    merged_temp_path = target_dir / f".temp_{bvid}_p{page}_merged.mp4"

    if final_video_path.exists():
        print(f"Video '{clean_name}.mp4' already exists. Skipping download.")
        return str(final_video_path)

    req_headers = HEADERS.copy()
    if BILIBILI_COOKIE:
        req_headers['Cookie'] = BILIBILI_COOKIE

    # 1. 获取 session (可选)
    session = ""
    session_url = f'https://www.bilibili.com/video/{bvid}?p={page}'
    session_response = limited_get_sync(session_url, headers=req_headers)
    if session_response:
        session_match = re.search(r'"session":"(.*?)"', session_response.text)
        if session_match:
            session = session_match.group(1)

    # 2. 获取音视频播放流地址（带 Cookie 和 WBI 签名，请求 1080P+/1080P 最高画质）
    playurl = 'https://api.bilibili.com/x/player/playurl'
    params = {
        'cid': cid,
        'bvid': bvid,
        'qn': '112',  # 优先最高画质 (1080P+/1080P/720P)
        'fnver': '0',
        'fnval': '4048',  # 现代 DASH 格式，解锁更高分辨率与更优画质
        'fourk': '1'
    }
    if session:
        params['session'] = session

    play_response = None
    try:
        wbi_key = get_wbi_keys(BILIBILI_COOKIE)
        if wbi_key:
            signed_params = sign_wbi_params(params.copy(), wbi_key)
            playurl_wbi = 'https://api.bilibili.com/x/player/wbi/playurl'
            play_response = limited_get_sync(playurl_wbi, params=signed_params, headers=req_headers)
    except Exception as e:
        print(f"WBI playurl 签名请求异常: {e}")

    if not play_response or play_response.status_code != 200:
        play_response = limited_get_sync(playurl, params=params, headers=req_headers)

    if not play_response:
        raise Exception("Failed to get play URLs from Bilibili.")

    play_data = play_response.json()
    if play_data['code'] != 0:
        raise Exception(f"API error getting play URLs: {play_data.get('message', 'Unknown error')}")

    try:
        dash_data = play_data['data']['dash']
        videos = dash_data.get('video', [])
        if not videos:
            raise KeyError("No video streams found in dash data")

        # 优先 AVC (H.264)，全平台设备与浏览器免转码硬件直解
        avc_videos = [v for v in videos if v.get('codecs', '').startswith('avc1')]
        candidate_videos = avc_videos if avc_videos else videos

        # 按画质 id (112 > 80 > 64 > 32 > 16) 从高到低选取最高画质流
        best_video = max(candidate_videos, key=lambda v: v.get('id', 0), default=videos[0])
        video_url = best_video.get('baseUrl') or best_video.get('base_url')

        audios = dash_data.get('audio', [])
        best_audio = max(audios, key=lambda a: a.get('id', 0), default=audios[0] if audios else None)
        audio_url = best_audio.get('baseUrl') or best_audio.get('base_url')

        print(f"[{bvid}] 成功锁定高清流: 画质代码 {best_video.get('id')} ({best_video.get('width')}x{best_video.get('height')}), 编码: {best_video.get('codecs')}")
        if best_video.get('id', 0) <= 32 and "SESSDATA=" not in BILIBILI_COOKIE:
            print(f"[{bvid}] 提示: 当前获取到的是 480P 流。如需 1080P/720P，请在 config.py 中补充 SESSDATA 并重启服务。")
    except (KeyError, IndexError) as e:
        raise Exception(f"Could not parse audio/video URLs from API response: {e}")

    # 3. 流式分块下载临时文件
    temp_audio_path = target_dir / f".temp_{bvid}_p{page}_audio.mp3"
    temp_video_path = target_dir / f".temp_{bvid}_p{page}_video.mp4"

    try:
        if progress_callback:
            progress_callback('downloading_audio', 10)
        audio_callback = (lambda done, total: progress_callback('downloading_audio', 10 + min(20, int(done / total * 20)) if total else 20)) if progress_callback else None
        stream_download_file(audio_url, temp_audio_path, headers=req_headers, progress_callback=audio_callback)
        if progress_callback:
            progress_callback('downloading_video', 30)
        video_callback = (lambda done, total: progress_callback('downloading_video', 30 + min(55, int(done / total * 55)) if total else 55)) if progress_callback else None
        stream_download_file(video_url, temp_video_path, headers=req_headers, progress_callback=video_callback)

        # 4. 调用 ffmpeg 合并音视频流（关键：追加 -movflags +faststart 将 moov 元数据置顶，支持秒拖进度条）
        command = [
            'ffmpeg',
            '-i', str(temp_video_path),
            '-i', str(temp_audio_path),
            '-c', 'copy',
            '-movflags', '+faststart',
            '-y',
            str(merged_temp_path)
        ]
        if progress_callback:
            progress_callback('merging', 90)
        subprocess.run(command, shell=False, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        os.replace(merged_temp_path, final_video_path)
    except subprocess.CalledProcessError as e:
        final_video_path.unlink(missing_ok=True)
        raise Exception(f"ffmpeg merge failed: {e.stderr}")
    finally:
        # 始终清理临时音视频文件
        temp_audio_path.unlink(missing_ok=True)
        temp_video_path.unlink(missing_ok=True)
        merged_temp_path.unlink(missing_ok=True)

    return str(final_video_path)

def _read_player_state() -> Dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def _write_player_state(data: Dict) -> None:
    temp = STATE_FILE.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, STATE_FILE)

_STAGE_LABELS = {
    'resolving': '解析视频源',
    'downloading': '下载视频',
    'downloading_audio': '下载音频',
    'downloading_video': '下载视频',
    'merging': '合并视频',
}


def _download_episode_sync(ep: Dict, target_folder: Path, progress_callback=None) -> str:
    """按来源分派下载：B站走官方 DASH 合并，外部来源（silidm）走 ffmpeg 拉流。"""
    service = _RESOLVERS.get(str(ep.get('source') or ''))
    if service is not None:
        if not ep.get('url'):
            raise Exception(f"{ep.get('source')} 条目缺少原始链接")
        final_path = target_folder / f"{ep['bvid']}_p{ep['page']}.mp4"
        return service.stream_to_mp4(
            ep['url'], final_path, float(ep.get('duration') or 0), progress_callback
        )
    return download_and_merge(ep['bvid'], {
        'page': ep['page'], 'cid': ep['cid'], 'part': ep['title']
    }, target_folder, progress_callback)


async def _download_episode_task(task_id: str, folder_path: str, ep: Dict) -> None:
    task = _download_tasks[task_id]
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    try:
        await asyncio.to_thread(cleanup_video_cache, 200 * 1024 * 1024)
        task['status'] = 'downloading'
        task['stage'] = '准备下载'
        task['progress'] = 5

        def on_progress(stage, progress):
            task['stage'] = _STAGE_LABELS.get(stage, stage)
            task['progress'] = max(5, min(99, int(progress)))

        await asyncio.to_thread(_download_episode_sync, ep, target_folder, on_progress)
        task.update(status='ready', stage='已完成', progress=100)
    except Exception as exc:
        task.update(status='failed', stage='下载失败', progress=0, error=str(exc))

@app.get("/api/progress/{folder_path:path}")
async def get_watch_progress(folder_path: str):
    state = _read_player_state().get('progress', {})
    prefix = folder_path.strip('/')
    return {key: value for key, value in state.items() if key.startswith(prefix + '|')}

@app.post("/api/progress")
async def save_watch_progress(payload: Dict[str, Any]):
    folder = str(payload.get('folder_path', '')).strip('/')
    bvid = str(payload.get('bvid', '')).strip()
    page = int(payload.get('page') or 1)
    if not folder or not bvid:
        raise HTTPException(status_code=400, detail='folder_path and bvid are required')
    key = f'{folder}|{bvid}|{page}'
    position = max(0, float(payload.get('position') or 0))
    duration = max(0, float(payload.get('duration') or 0))
    completed = bool(payload.get('completed')) or (duration > 0 and position / duration >= 0.92)
    async with _progress_lock:
        state = _read_player_state()
        progress = state.setdefault('progress', {})
        progress[key] = {'folder_path': folder, 'bvid': bvid, 'page': page, 'position': position, 'duration': duration, 'completed': completed, 'updated_at': int(time.time())}
        await asyncio.to_thread(_write_player_state, state)
    return progress[key]

@app.post("/api/download/{folder_path:path}/{item_index}")
async def start_download(folder_path: str, item_index: int, bvid: Optional[str] = Query(None), page: Optional[int] = Query(None)):
    episodes = await get_folder_episodes_async(folder_path)
    ep = next((item for item in episodes if bvid and page is not None and item['bvid'] == bvid and item['page'] == page), None)
    ep = ep or next((item for item in episodes if item.get('index') == item_index), None)
    if not ep:
        raise HTTPException(status_code=404, detail='Episode not found')
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    if not target_folder:
        raise HTTPException(status_code=404, detail='Folder not found')
    final_path = target_folder / f"{ep['bvid']}_p{ep['page']}.mp4"
    if final_path.exists():
        return {'status': 'ready', 'progress': 100, 'video_url': f"/static/{folder_path}/{final_path.name}"}

    # 外部来源（silidm）：没有本地缓存时直接转流式播放（边下边播），
    # 不再等待「整集下载 + ffmpeg 合并」——那是十几秒到几分钟的等待。
    if ep.get('source') in _STREAM_SOURCES:
        return {'status': 'ready', 'progress': 100, 'stream': True,
                'video_url': _hls_playback_url(ep)}

    for task_id, task in _download_tasks.items():
        if task.get('folder_path') == folder_path and task.get('bvid') == ep['bvid'] and task.get('page') == ep['page'] and task.get('status') in {'queued', 'downloading'}:
            return {'task_id': task_id, **task}
    task_id = uuid.uuid4().hex
    _download_tasks[task_id] = {'folder_path': folder_path, 'bvid': ep['bvid'], 'page': ep['page'], 'status': 'queued', 'stage': '排队中', 'progress': 0}
    asyncio.create_task(_download_episode_task(task_id, folder_path, ep))
    return {'task_id': task_id, **_download_tasks[task_id]}

@app.get("/api/download/tasks/{task_id}")
async def get_download_task(task_id: str):
    task = _download_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail='Download task not found')
    return {'task_id': task_id, **task}


def _hls_playback_url(ep: Dict) -> str:
    """外部来源条目的流式播放地址（m3u8 代理路由）。"""
    return f"/api/hls/{ep['bvid']}/index.m3u8"


@app.get("/api/hls/{episode_id}/index.m3u8")
async def get_hls_playlist(episode_id: str):
    """HLS 播放列表代理 —— 外部来源（silidm）流式播放专用。

    行为说明：

    * 每次请求都**重新**解析一遍播放页：直链带签名且短时效，不能长期缓存复用。
    * 列表里的分片 URI 会被**改写成后端代理地址** ``seg/<n>.ts``，
      由 :func:`get_hls_segment` 代为下载（多连接并行，见 ``silidm.fetch_segment``）。
      原因是上游 CDN 对单条连接限速，低于流的码率，浏览器直连会卡。
    * 带 ``#EXT-X-KEY`` / ``#EXT-X-MAP`` 的流不做改写，保持浏览器直连。
    """
    service = _resolver_for_episode_id(episode_id)
    if service is None:
        raise HTTPException(status_code=400, detail='Invalid episode id')
    url = service.url_from_episode_id(episode_id)
    if not url:
        raise HTTPException(status_code=400, detail='Invalid episode id')
    try:
        playlist = await asyncio.to_thread(service.proxied_playlist, episode_id, url)
        # 在返回播放列表的同时，后台异步提前预热并预加载前几个分片（0~2），
        # 从而在浏览器刚解析完 manifest 的瞬间，分片 0 已经就绪，实现秒开起播
        if hasattr(service, "prefetch_segments"):
            service.prefetch_segments(episode_id, 0, window=3)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f'解析失败: {exc}')
    return Response(
        content=playlist,
        media_type='application/vnd.apple.mpegurl',
        headers={'Cache-Control': 'no-store'},
    )


@app.get("/api/hls/{episode_id}/seg/{index}.ts")
async def get_hls_segment(episode_id: str, index: int):
    """HLS 分片代理 —— 支持内存与磁盘缓存、并行下载及滑动窗口预加载。"""
    service = _resolver_for_episode_id(episode_id)
    if service is None:
        raise HTTPException(status_code=400, detail='Invalid episode id')
    try:
        if hasattr(service, "get_cached_or_fetch_segment"):
            data = await asyncio.to_thread(service.get_cached_or_fetch_segment, episode_id, index)
            # 触发后台滑动窗口预加载后续分片（默认后推 6 个分片，约 18~20 秒缓冲量）
            prefetch_window = getattr(service, "SILIDM_PREFETCH_WINDOW", 6)
            service.prefetch_segments(episode_id, index, window=prefetch_window)
        else:
            segment_url = await asyncio.to_thread(service.segment_url_for, episode_id, index)
            if not segment_url:
                raise HTTPException(status_code=404, detail='Segment not found')
            data = await asyncio.to_thread(service.fetch_segment, segment_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f'分片下载失败: {exc}')
    return Response(
        content=data,
        media_type='video/mp2t',
        headers={'Cache-Control': 'public, max-age=86400'},
    )


# --- API Endpoints ---

@app.get("/api/folders")
async def list_folders(path: str = ""):
    """获取文件夹列表，支持统计每个合集的视频数量"""
    if not VIDEOS_DIR.is_dir():
        return JSONResponse(content=[], headers={"Content-Type": "application/json; charset=utf-8"})

    if path and path.strip():
        target_path = safe_resolve_path(VIDEOS_DIR, path)
        if not target_path or not target_path.exists() or not target_path.is_dir():
            raise HTTPException(status_code=404, detail=f"Folder not found: {path}")
    else:
        target_path = VIDEOS_DIR

    folders = []
    try:
        for item in target_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                relative_path = str(item.relative_to(VIDEOS_DIR)).replace('\\', '/')
                list_file = item / "list.txt"
                has_list_file = list_file.exists()
                video_count = 0

                if has_list_file:
                    # 优先读取已落盘的缓存分集数，避免首页遍历触发阻塞式全量网络刮削
                    cache_file = item / ".cache_episodes.json"
                    if cache_file.exists():
                        try:
                            cached_data = json.loads(cache_file.read_text(encoding='utf-8'))
                            if isinstance(cached_data, list):
                                video_count = len(cached_data)
                        except Exception:
                            pass
                    if video_count == 0:
                        try:
                            with open(list_file, 'r', encoding='utf-8') as f:
                                lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
                                video_count = len(lines)
                        except Exception:
                            pass

                downloaded_count = 0
                if has_list_file:
                    try:
                        downloaded_count = len([f for f in item.iterdir() if f.is_file() and f.suffix.lower() == '.mp4' and not f.name.startswith('.')])
                    except Exception:
                        pass

                folder_info = {
                    "name": item.name,
                    "path": relative_path,
                    "parent_path": path if path and path.strip() else None,
                    "children": [],
                    "has_list_file": has_list_file,
                    "video_count": video_count,
                    "downloaded_count": downloaded_count,
                    "depth": len(path.split('/')) if path and path.strip() else 0,
                    "is_folder": True
                }
                folders.append(folder_info)
    except PermissionError:
        pass

    sorted_folders = sort_folders_chinese(folders)
    return JSONResponse(content=sorted_folders, headers={"Content-Type": "application/json; charset=utf-8"})

@app.get("/api/settings/cookie/status")
async def get_cookie_status():
    return {"has_cookie": bool(BILIBILI_COOKIE.strip())}


@app.get("/api/settings")
async def get_settings():
    state = _read_player_state()
    settings = dict(DEFAULT_PLAYER_SETTINGS)
    saved = state.get("settings", {})
    if isinstance(saved, dict):
        for k in DEFAULT_PLAYER_SETTINGS:
            if k in saved:
                settings[k] = saved[k]
    settings["has_cookie"] = bool(BILIBILI_COOKIE.strip())
    return JSONResponse(content=settings, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/settings")
async def update_settings(request: Request):
    global BILIBILI_COOKIE
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    async with _progress_lock:
        state = _read_player_state()
        saved = state.setdefault("settings", {})
        if not isinstance(saved, dict):
            saved = {}
            state["settings"] = saved

        if "autoplay" in payload:
            saved["autoplay"] = bool(payload["autoplay"])
        if "subtitles" in payload:
            saved["subtitles"] = bool(payload["subtitles"])
        if "theme" in payload and isinstance(payload["theme"], str):
            saved["theme"] = payload["theme"].strip()
        if "cookie" in payload and isinstance(payload["cookie"], str):
            c = payload["cookie"].strip()
            if c:
                BILIBILI_COOKIE = c
                set_bilibili_cookie(c)
                saved["cookie"] = c

        await asyncio.to_thread(_write_player_state, state)

    settings = dict(DEFAULT_PLAYER_SETTINGS)
    for k in DEFAULT_PLAYER_SETTINGS:
        if k in saved:
            settings[k] = saved[k]
    settings["has_cookie"] = bool(BILIBILI_COOKIE.strip())
    return JSONResponse(content=settings, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/settings/cookie")
async def update_cookie(request: Request):
    global BILIBILI_COOKIE
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    cookie = payload.get("cookie")
    if not isinstance(cookie, str):
        raise HTTPException(status_code=400, detail="Cookie must be a string")
    cookie = cookie.strip()
    if not cookie or len(cookie) > 20000:
        raise HTTPException(status_code=400, detail="Invalid cookie")
    BILIBILI_COOKIE = cookie
    set_bilibili_cookie(cookie)
    async with _progress_lock:
        state = _read_player_state()
        saved = state.setdefault("settings", {})
        if not isinstance(saved, dict):
            saved = {}
            state["settings"] = saved
        saved["cookie"] = cookie
        await asyncio.to_thread(_write_player_state, state)
    return {"success": True, "has_cookie": True}


# --- 观看限时管理 API ---

@app.get("/api/time-limits/status")
async def get_time_limits():
    """获取当前限时配置、今日各合集及总用时与剩余时间"""
    async with _progress_lock:
        state = _read_player_state()
        status = time_limits_service.get_time_limits_status(state, VIDEOS_DIR)
    return JSONResponse(content=status, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/time-limits/config")
async def save_time_limits_config(request: Request):
    """保存限时配置（总限时开关、全局限时、各目录限时、家长PIN）"""
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    async with _progress_lock:
        state = _read_player_state()
        time_limits_service.update_time_limits_config(state, payload)
        await asyncio.to_thread(_write_player_state, state)
        status = time_limits_service.get_time_limits_status(state, VIDEOS_DIR)
    return JSONResponse(content=status, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/time-limits/heartbeat")
async def record_playback_heartbeat(request: Request):
    """播放过程中定期上报心跳累计物理观看时间"""
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    folder_path = str(payload.get("folder_path") or "")
    delta_seconds = float(payload.get("delta_seconds") or 0.0)

    async with _progress_lock:
        state = _read_player_state()
        result, locked = time_limits_service.record_heartbeat(state, folder_path, delta_seconds, VIDEOS_DIR)
        await asyncio.to_thread(_write_player_state, state)

    return JSONResponse(content=result, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/time-limits/extend")
async def grant_bonus_time(request: Request):
    """家长临时给指定合集或全局追加观看时长（加时）"""
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    extend_type = str(payload.get("type") or "folder")
    folder_path = str(payload.get("folder_path") or "")
    minutes = int(payload.get("minutes") or 15)

    async with _progress_lock:
        state = _read_player_state()
        res = time_limits_service.extend_time(state, extend_type, folder_path, minutes)
        await asyncio.to_thread(_write_player_state, state)
        status = time_limits_service.get_time_limits_status(state, VIDEOS_DIR)

    return JSONResponse(content={"result": res, "status": status}, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/time-limits/reset-today")
async def reset_today_time():
    """家长重置今日所有观看计时（清零重计）"""
    async with _progress_lock:
        state = _read_player_state()
        time_limits_service.reset_today_usage(state)
        await asyncio.to_thread(_write_player_state, state)
        status = time_limits_service.get_time_limits_status(state, VIDEOS_DIR)
    return JSONResponse(content=status, headers={"Content-Type": "application/json; charset=utf-8"})


@app.post("/api/time-limits/verify-pin")
async def verify_pin_code(request: Request):
    """校验家长4位口令（若未配置则直接返回true）"""
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON") from error

    pin = str(payload.get("pin") or "")
    async with _progress_lock:
        state = _read_player_state()
        valid = time_limits_service.verify_parent_pin(state, pin)
    return JSONResponse(content={"valid": valid}, headers={"Content-Type": "application/json; charset=utf-8"})


@app.get("/api/cache/status")
async def get_cache_status():
    """获取视频缓存使用量与磁盘剩余空间监控"""
    stats = get_cache_stats()
    return JSONResponse(content={
        "max_cache_size_mb": MAX_CACHE_SIZE_MB,
        "target_cache_size_mb": TARGET_CACHE_SIZE_MB,
        "min_free_disk_mb": MIN_FREE_DISK_MB,
        "current_cache_size_mb": round(stats['total_bytes'] / (1024 * 1024), 2),
        "free_disk_space_mb": round(stats['disk_free_bytes'] / (1024 * 1024), 2),
        "cached_videos_count": len(stats['video_files']),
        "cached_videos": [
            {
                "name": v['name'],
                "size_mb": round(v['size'] / (1024 * 1024), 2),
                "last_access": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(v['last_access']))
            }
            for v in sorted(stats['video_files'], key=lambda x: x['last_access'], reverse=True)
        ]
    }, headers={"Content-Type": "application/json; charset=utf-8"})

@app.post("/api/cache/clean")
async def manual_cache_clean():
    """手动触发视频缓存 LRU 清理"""
    res = await asyncio.to_thread(cleanup_video_cache, 0)
    return JSONResponse(content=res, headers={"Content-Type": "application/json; charset=utf-8"})


@app.get("/api/folders/{folder_path:path}/details")
async def get_videos_details(folder_path: str):
    """获取视频详细信息（封面、字幕可用性）"""
    episodes = await get_folder_episodes_async(folder_path)
    if not episodes:
        raise HTTPException(status_code=404, detail=f"Folder '{folder_path}' has no episodes")

    detailed_parts = []
    subtitle_flags = await asyncio.gather(*[
        check_subtitle_availability_async(ep['bvid'], ep['page'], ep['cid']) for ep in episodes
    ], return_exceptions=True)
    for ep, subtitle_flag in zip(episodes, subtitle_flags):
        detailed_parts.append({
            "index": ep["index"],
            "page": ep["page"],
            "bvid": ep["bvid"],
            "cover_source": ep.get('cover_source', ''),
            "duration": ep.get('duration', 0),
            "has_subtitle": subtitle_flag is True
        })

    return JSONResponse(content=detailed_parts, headers={"Content-Type": "application/json; charset=utf-8"})


@app.get("/api/folders/{folder_path:path}")
async def list_videos_in_folder(folder_path: str):
    """
    返回指定合集下的分集列表（完整支持多 BV 列表和单个 BV 多分P）
    """
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    if not target_folder or not target_folder.exists() or not target_folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder '{folder_path}' not found")

    list_file = target_folder / "list.txt"
    if not list_file.exists():
        raise HTTPException(status_code=404, detail=f"'list.txt' not found in folder '{folder_path}'")

    episodes = await get_folder_episodes_async(folder_path)
    if not episodes:
        raise HTTPException(status_code=500, detail="Could not fetch video episodes for the BV list.")

    return JSONResponse(content=episodes, headers={"Content-Type": "application/json; charset=utf-8"})

async def _build_stream_covers(episode_id: str, page_numbers: List[int]) -> Dict[str, str]:
    """为外部来源条目（silidm）获取封面（复用 B站 那套本地封面缓存命名）。"""
    service = _resolver_for_episode_id(episode_id)
    if service is None:
        return {}
    url = service.url_from_episode_id(episode_id)
    if not url:
        return {}

    covers: Dict[str, str] = {}
    pending = []
    for page in page_numbers:
        cover_filename = f"{episode_id}_p{page}.jpg"
        if (COVERS_DIR / cover_filename).exists():
            covers[str(page)] = f"/covers/{cover_filename}"
        else:
            pending.append(page)

    if pending:
        meta = await asyncio.to_thread(service.fetch_metadata, url)
        cover_source = (meta or {}).get('cover', '')
        if cover_source:
            for page in pending:
                downloaded = await download_and_cache_cover_async(episode_id, page, cover_source)
                if downloaded:
                    covers[str(page)] = downloaded
    return covers


@app.get("/api/batch/covers/{bvid}")
async def get_batch_covers(bvid: str, pages: str):
    """批量并发获取封面，带缓存与限流保护（支持 B站 BV 号与外部来源合成 ID）"""
    try:
        page_numbers = [int(p.strip()) for p in pages.split(',') if p.strip().isdigit()]
        if not page_numbers:
            return JSONResponse(content={"covers": {}}, headers={"Content-Type": "application/json; charset=utf-8"})

        if _resolver_for_episode_id(bvid) is not None:
            return JSONResponse(
                content={"covers": await _build_stream_covers(bvid, page_numbers)},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

        if not re.match(r'^BV[a-zA-Z0-9]+$', bvid):
            return JSONResponse(content={"covers": {}}, headers={"Content-Type": "application/json; charset=utf-8"})

        bv_detail = await get_bv_detail_async(bvid)
        if not bv_detail:
            return JSONResponse(content={"covers": {}}, headers={"Content-Type": "application/json; charset=utf-8"})

        pages_data = bv_detail.get('pages', [])
        page_to_cover = {}
        for p in pages_data:
            if p['page'] in page_numbers:
                page_to_cover[p['page']] = p.get('first_frame') or bv_detail.get('pic', '')

        for page_num in page_numbers:
            if page_num not in page_to_cover:
                page_to_cover[page_num] = bv_detail.get('pic', '')

        covers = {}
        download_tasks = []

        for page_num in page_numbers:
            cover_url = page_to_cover.get(page_num, '')
            if cover_url:
                cover_filename = f"{bvid}_p{page_num}.jpg"
                cover_path = COVERS_DIR / cover_filename
                if cover_path.exists():
                    covers[str(page_num)] = f"/covers/{cover_filename}"
                else:
                    async def fetch_one(p=page_num, u=cover_url):
                        downloaded = await download_and_cache_cover_async(bvid, p, u)
                        return str(p), downloaded
                    download_tasks.append(fetch_one())

        if download_tasks:
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, tuple) and res[1]:
                    covers[res[0]] = res[1]

        return JSONResponse(content={"covers": covers}, headers={"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:
        print(f"批量获取封面失败: {e}")
        return JSONResponse(content={"covers": {}}, headers={"Content-Type": "application/json; charset=utf-8"})

@app.get("/api/cover/{bvid}/{page_number}")
async def get_video_cover(bvid: str, page_number: int):
    """异步获取单个视频封面（支持 B站 BV 号与外部来源合成 ID）"""
    try:
        if _resolver_for_episode_id(bvid) is not None:
            cover_filename = f"{bvid}_p{page_number}.jpg"
            if (COVERS_DIR / cover_filename).exists():
                return JSONResponse(content={"cover_url": f"/covers/{cover_filename}", "cached": True}, headers={"Content-Type": "application/json; charset=utf-8"})
            covers = await _build_stream_covers(bvid, [page_number])
            return JSONResponse(content={"cover_url": covers.get(str(page_number), ""), "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})

        if not re.match(r'^BV[a-zA-Z0-9]+$', bvid):
            return JSONResponse(content={"cover_url": "", "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})

        cover_filename = f"{bvid}_p{page_number}.jpg"
        cover_path = COVERS_DIR / cover_filename
        if cover_path.exists():
            return JSONResponse(content={"cover_url": f"/covers/{cover_filename}", "cached": True}, headers={"Content-Type": "application/json; charset=utf-8"})

        bv_detail = await get_bv_detail_async(bvid)
        if not bv_detail:
            return JSONResponse(content={"cover_url": "", "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})

        pages_data = bv_detail.get('pages', [])
        cover_source = bv_detail.get('pic', '')
        for p in pages_data:
            if p['page'] == page_number:
                cover_source = p.get('first_frame') or cover_source
                break

        if not cover_source:
            return JSONResponse(content={"cover_url": "", "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})

        cover_url = await download_and_cache_cover_async(bvid, page_number, cover_source)
        return JSONResponse(content={"cover_url": cover_url, "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})
    except Exception as e:
        print(f"获取封面失败: {e}")
        return JSONResponse(content={"cover_url": "", "cached": False}, headers={"Content-Type": "application/json; charset=utf-8"})

@app.get("/api/play/{folder_path:path}/{item_index}")
async def play_video(
    folder_path: str,
    item_index: int,
    bvid: Optional[str] = Query(None),
    page: Optional[int] = Query(None)
):
    """
    按需下载并播放视频，支持多BV集合与单个BV多分P
    兼容通过 index、page 或 (bvid, page) 寻址
    """
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    if not target_folder or not target_folder.exists() or not target_folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder '{folder_path}' not found")

    episodes = await get_folder_episodes_async(folder_path)
    if not episodes:
        raise HTTPException(status_code=404, detail="'list.txt' is empty or could not be parsed.")

    target_ep = None
    if bvid and page is not None:
        target_ep = next((ep for ep in episodes if ep['bvid'] == bvid and ep['page'] == page), None)

    if not target_ep:
        target_ep = next((ep for ep in episodes if ep.get('index') == item_index), None)
        if not target_ep:
            target_ep = next((ep for ep in episodes if ep.get('page') == item_index), None)

    if not target_ep:
        raise HTTPException(status_code=404, detail=f"Episode {item_index} not found in this album.")

    target_bvid = target_ep['bvid']
    target_page = target_ep['page']
    target_cid = target_ep['cid']
    target_title = target_ep['title']
    target_source = target_ep.get('source', 'bilibili')

    clean_name = re.sub(r'[\\/*?:"<>|]', "", target_title).strip() or f"{target_bvid}_p{target_page}"
    final_video_path = target_folder / f"{target_bvid}_p{target_page}.mp4"
    legacy_video_path = safe_resolve_path(target_folder, f"{clean_name}.mp4")

    def find_existing_video() -> Optional[Path]:
        for candidate in (final_video_path, legacy_video_path):
            if candidate and candidate.exists() and candidate.is_file():
                return candidate
        return None

    # 字幕仅 B站 提供；外部来源拿不到字幕，直接跳过
    has_subtitle = False
    subtitle_url = ""
    if target_source == 'bilibili':
        has_subtitle = await check_subtitle_availability_async(target_bvid, target_page, target_cid)
        if has_subtitle:
            subtitle_url = await download_and_cache_subtitle(target_bvid, target_page, target_cid)

    # 快捷路径：若已存在合成好的视频（同名或 BV 命名），直接返回并刷新 LRU 活跃度
    existing_video_path = find_existing_video()
    if existing_video_path:
        try:
            os.utime(existing_video_path, None)
        except Exception:
            pass
        return {
            "status": "ready",
            "video_url": f"/static/{folder_path}/{existing_video_path.name}",
            "has_subtitle": has_subtitle,
            "subtitle_url": subtitle_url
        }

    # 外部来源（silidm）条目：无本地缓存时走流式播放，避免阻塞在整集下载上
    if target_source in _STREAM_SOURCES:
        return {
            "status": "ready",
            "stream": True,
            "video_url": _hls_playback_url(target_ep),
            "has_subtitle": has_subtitle,
            "subtitle_url": subtitle_url
        }

    # 加锁执行下载与合并，防并发冲突与写损坏
    lock_key = f"{target_bvid}_{target_page}"
    lock = await get_download_lock(lock_key)
    async with lock:
        # 再次确认是否在等待锁期间已被其他请求下载完成
        existing_video_path = find_existing_video()
        if existing_video_path:
            try:
                os.utime(existing_video_path, None)
            except Exception:
                pass
            return {
                "status": "ready",
                "video_url": f"/static/{folder_path}/{existing_video_path.name}",
                "has_subtitle": has_subtitle,
                "subtitle_url": subtitle_url
            }

        try:
            # 下载前执行 LRU 回收检查，预估需要约 200MB 空间（临时音视频+最终合并文件）
            await asyncio.to_thread(cleanup_video_cache, 200 * 1024 * 1024)

            await asyncio.to_thread(_download_episode_sync, target_ep, target_folder, None)

            # 下载完成后刷新时间戳并再次核查水位
            if final_video_path.exists():
                try:
                    os.utime(final_video_path, None)
                except Exception:
                    pass
            await asyncio.to_thread(cleanup_video_cache, 0)

            return {
                "status": "ready",
                "video_url": f"/static/{folder_path}/{final_video_path.name}",
                "has_subtitle": has_subtitle,
                "subtitle_url": subtitle_url
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to download video: {str(e)}")

def stream_video_with_range(request: Request, file_path: Path) -> StreamingResponse:
    """带标准 HTTP 206 Partial Content 与 Range 支持的专业流媒体响应器"""
    stat_result = file_path.stat()
    file_size = stat_result.st_size
    range_header = request.headers.get("range")
    content_type = "video/mp4"

    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=86400",
    }

    if not range_header:
        def full_iter(chunk_size=1024 * 512):
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    yield chunk

        headers = {
            **base_headers,
            "Content-Length": str(file_size),
        }
        return StreamingResponse(full_iter(), status_code=200, headers=headers, media_type=content_type)

    if file_size == 0:
        return StreamingResponse(iter([]), status_code=416, headers={"Content-Range": "bytes */0"})

    range_match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not range_match:
        raise HTTPException(status_code=416, detail="Invalid Range Header")

    start_str, end_str = range_match.groups()
    if not start_str and not end_str:
        raise HTTPException(status_code=416, detail="Invalid Range Header")

    if not start_str:
        suffix_length = int(end_str)
        if suffix_length <= 0:
            raise HTTPException(status_code=416, detail="Invalid Range Header")
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)

    if start >= file_size or start > end:
        headers = {
            "Content-Range": f"bytes */{file_size}",
            "Accept-Ranges": "bytes"
        }
        return StreamingResponse(iter([]), status_code=416, headers=headers)

    content_length = end - start + 1

    def ranged_iter(start_pos: int, length: int, chunk_size=1024 * 512):
        with open(file_path, "rb") as f:
            f.seek(start_pos)
            bytes_left = length
            while bytes_left > 0:
                read_size = min(chunk_size, bytes_left)
                data = f.read(read_size)
                if not data:
                    break
                bytes_left -= len(data)
                yield data

    headers = {
        **base_headers,
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Content-Length": str(content_length),
    }
    return StreamingResponse(
        ranged_iter(start, content_length),
        status_code=206,
        headers=headers,
        media_type=content_type
    )

@app.get("/static/{folder_path:path}/{file_name}")
async def serve_static_video(folder_path: str, file_name: str, request: Request):
    """服务视频静态文件（完整支持 HTTP 206 Partial Content，秒级响应进度条拖动）"""
    file_path = safe_resolve_path(VIDEOS_DIR, f"{folder_path}/{file_name}")
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        os.utime(file_path, None)  # 刷新最后访问时间，供 LRU 机制准确淘汰
    except Exception:
        pass
    return stream_video_with_range(request, file_path)


@app.get("/covers/{file_name}")
async def serve_cover_image(file_name: str):
    """服务封面静态文件（校验防路径穿越）"""
    file_path = safe_resolve_path(COVERS_DIR, file_name)
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Cover image not found.")
    return FileResponse(file_path)

@app.get("/subtitles/{file_name}")
async def serve_subtitle_file(file_name: str):
    """服务字幕静态文件（校验防路径穿越）"""
    file_path = safe_resolve_path(SUBTITLES_DIR, file_name)
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Subtitle file not found.")
    return FileResponse(file_path, media_type="text/vtt")

@app.get("/api/subtitle/{folder_path:path}/{item_index}")
async def get_subtitle(
    folder_path: str,
    item_index: int,
    bvid: Optional[str] = Query(None),
    page: Optional[int] = Query(None)
):
    """获取指定分集的字幕文件"""
    target_folder = safe_resolve_path(VIDEOS_DIR, folder_path)
    if not target_folder or not target_folder.exists() or not target_folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Folder not found: {folder_path}")

    episodes = await get_folder_episodes_async(folder_path)
    target_ep = None
    if bvid and page is not None:
        target_ep = next((ep for ep in episodes if ep['bvid'] == bvid and ep['page'] == page), None)
    if not target_ep:
        target_ep = next((ep for ep in episodes if ep.get('index') == item_index), None)
    if not target_ep:
        raise HTTPException(status_code=404, detail=f"Episode {item_index} not found.")

    subtitle_path = await download_and_cache_subtitle(target_ep['bvid'], target_ep['page'], target_ep['cid'])
    if not subtitle_path:
        raise HTTPException(status_code=404, detail="No subtitle available for this video.")

    return {"subtitle_url": subtitle_path}

# --- Frontend Routes ---
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """服务前端主页"""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding='utf-8'))
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)

@app.get("/{file_path:path}")
async def serve_frontend_files(file_path: str):
    """服务前端静态文件（严格校验防止路径穿越）"""
    file = safe_resolve_path(FRONTEND_DIR, file_path)
    if file and file.exists() and file.is_file():
        if file_path.endswith(('.js', '.css')):
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
            return FileResponse(file, headers=headers)
        return FileResponse(file)

    if file_path.endswith(('.js', '.css', '.map')):
        raise HTTPException(status_code=404, detail="Frontend asset not found")

    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding='utf-8'))
    return HTMLResponse("<h1>File not found</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    print("[启动] 儿童视频播放器服务器启动中...")
    print(f"[目录] 视频目录: {VIDEOS_DIR.resolve()}")
    print(f"[目录] 前端目录: {FRONTEND_DIR.resolve()}")
    print("[服务] 服务地址: http://localhost:8000")
    print("[就绪] 完整支持多BV合集列表 + 流式分块 + 任务互斥锁 + 路径安全隔离 + LRU磁盘缓存管理")
    uvicorn.run(app, host="0.0.0.0", port=8000)
