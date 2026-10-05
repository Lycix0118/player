"""Application configuration and runtime paths.

This module is deliberately dependency-light so services and tests can import
configuration without importing the FastAPI application.
"""

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR = BASE_DIR / "videos"
FRONTEND_DIR = BASE_DIR / "frontend"
COVERS_DIR = BASE_DIR / "covers"
SUBTITLES_DIR = BASE_DIR / "subtitles"
STATE_FILE = BASE_DIR / ".player_state.json"


def _load_config_module():
    try:
        import config  # type: ignore
    except ImportError:
        return None
    return config


_config = _load_config_module()


def _value(name: str, default: str) -> str:
    if _config is not None and hasattr(_config, name):
        return str(getattr(_config, name))
    return os.getenv(name, default)


BILIBILI_COOKIE = _value("BILIBILI_COOKIE", "")
MAX_CACHE_SIZE_MB = int(_value("MAX_CACHE_SIZE_MB", "700"))
TARGET_CACHE_SIZE_MB = int(_value("TARGET_CACHE_SIZE_MB", "500"))
MIN_FREE_DISK_MB = int(_value("MIN_FREE_DISK_MB", "800"))
OUTBOUND_MAX_CONCURRENCY = int(os.getenv("OUTBOUND_MAX_CONCURRENCY", "8"))
OUTBOUND_MAX_QPS = float(os.getenv("OUTBOUND_MAX_QPS", "6"))
OUTBOUND_MAX_COOLDOWN = int(os.getenv("OUTBOUND_MAX_COOLDOWN", "300"))


def set_bilibili_cookie(cookie: str) -> None:
    """Update the process-level cookie used by outbound Bilibili requests."""
    global BILIBILI_COOKIE
    BILIBILI_COOKIE = cookie


def log_startup_configuration() -> None:
    """Keep the existing startup diagnostics in one place."""
    if not BILIBILI_COOKIE:
        print("提示: 未配置B站Cookie，将以访客身份运行（画质最高480P，且无法解析字幕）")
    elif "SESSDATA=" not in BILIBILI_COOKIE:
        print("【画质提醒】检测到 config.py 中已填 Cookie，但缺少核心凭证 SESSDATA！")
        print("       B站会将此会话视为未登录访客，视频流将被限制在 480P。")
        print("       请在 config.py 中补充 SESSDATA=xxx; 以解锁 1080P/720P 高清画质。")
    else:
        print("【配置成功】已加载含 SESSDATA 的 B站登录 Cookie，支持高清流(1080P/720P)与字幕解析。")

    print(
        f"[磁盘策略] 视频缓存上限: {MAX_CACHE_SIZE_MB}MB | "
        f"目标保留水位: {TARGET_CACHE_SIZE_MB}MB | "
        f"磁盘底线预警: {MIN_FREE_DISK_MB}MB"
    )


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
