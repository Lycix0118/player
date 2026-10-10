"""Time limit management service for children's video player.

Supports:
- Daily global time limit shared across all videos
- Per-folder daily time limits for leaf categories
- Precise active playback tracking via heartbeat
- Temporary parental extension and PIN verification
"""

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_today_key() -> str:
    """Return today's date formatted as YYYY-MM-DD."""
    return datetime.date.today().isoformat()


def get_playable_leaf_folders(videos_dir: Path) -> List[Dict[str, str]]:
    """Scan VIDEOS_DIR to find all leaf / playable directories."""
    if not videos_dir.exists() or not videos_dir.is_dir():
        return []

    leaf_folders: List[Dict[str, str]] = []
    for item in sorted(videos_dir.rglob('*')):
        if not item.is_dir():
            continue
        # Avoid hidden directories (.git, .cache, etc.)
        if any(part.startswith('.') for part in item.relative_to(videos_dir).parts):
            continue

        has_list = (item / "list.txt").is_file()
        has_video = False
        try:
            has_video = any(
                f.is_file() and f.suffix.lower() in ('.mp4', '.mkv', '.webm', '.ts') and not f.name.startswith('.')
                for f in item.iterdir()
            )
        except Exception:
            pass

        has_subdirs = False
        try:
            has_subdirs = any(f.is_dir() and not f.name.startswith('.') for f in item.iterdir())
        except Exception:
            pass

        # Consider a folder leaf if it explicitly has list.txt, contains videos, or has no subdirectories
        if has_list or has_video or not has_subdirs:
            rel_path = str(item.relative_to(videos_dir)).replace('\\', '/')
            leaf_folders.append({
                "name": item.name,
                "path": rel_path
            })

    return leaf_folders


def prune_old_logs(state: Dict[str, Any], keep_days: int = 14) -> None:
    """Retain only the last `keep_days` of daily watch logs to keep player state lean."""
    logs = state.get("daily_watch_logs")
    if not isinstance(logs, dict):
        return

    today = datetime.date.today()
    cutoff_date = today - datetime.timedelta(days=keep_days)
    cutoff_str = cutoff_date.isoformat()

    keys_to_remove = [k for k in logs.keys() if isinstance(k, str) and k < cutoff_str]
    for k in keys_to_remove:
        logs.pop(k, None)


def get_time_limits_status(state: Dict[str, Any], videos_dir: Path) -> Dict[str, Any]:
    """Calculate and return full time limit configuration and today's usage status."""
    time_limits_cfg = state.get("time_limits", {})
    if not isinstance(time_limits_cfg, dict):
        time_limits_cfg = {}

    enabled = bool(time_limits_cfg.get("enabled", False))
    global_limit_minutes = max(0, int(time_limits_cfg.get("global_limit_minutes") or 0))
    raw_folder_limits = time_limits_cfg.get("folder_limits") or {}
    folder_limits = {
        str(k).replace('\\', '/').strip('/'): max(0, int(v or 0))
        for k, v in raw_folder_limits.items()
        if isinstance(k, str)
    }
    parent_pin = str(time_limits_cfg.get("parent_pin") or "").strip()

    today = get_today_key()
    daily_logs = state.get("daily_watch_logs") or {}
    today_log = daily_logs.get(today) or {}

    total_used_seconds = max(0.0, float(today_log.get("total_seconds") or 0.0))
    raw_folders_usage = today_log.get("folders") or {}
    folders_usage = {
        str(k).replace('\\', '/').strip('/'): max(0.0, float(v or 0.0))
        for k, v in raw_folders_usage.items()
        if isinstance(k, str)
    }

    bonus_global_minutes = max(0, int(today_log.get("bonus_global_minutes") or 0))
    raw_bonus_folders = today_log.get("bonus_folder_minutes") or {}
    bonus_folder_minutes = {
        str(k).replace('\\', '/').strip('/'): max(0, int(v or 0))
        for k, v in raw_bonus_folders.items()
        if isinstance(k, str)
    }

    # Yesterday and recent history
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    yesterday_log = daily_logs.get(yesterday) or {}
    yesterday_used_seconds = max(0.0, float(yesterday_log.get("total_seconds") or 0.0))

    recent_history = []
    for d, log_data in sorted(daily_logs.items(), reverse=True):
        if not isinstance(log_data, dict):
            continue
        recent_history.append({
            "date": d,
            "total_seconds": int(max(0.0, float(log_data.get("total_seconds") or 0.0))),
            "folders": {
                str(k).replace('\\', '/').strip('/'): int(max(0.0, float(v or 0.0)))
                for k, v in (log_data.get("folders") or {}).items()
                if isinstance(k, str)
            }
        })
    recent_history = recent_history[:7]

    # Global limit calculations
    effective_global_limit_minutes = (global_limit_minutes + bonus_global_minutes) if global_limit_minutes > 0 else 0
    effective_global_limit_seconds = effective_global_limit_minutes * 60
    global_remaining_seconds: Optional[int] = None
    if effective_global_limit_seconds > 0:
        global_remaining_seconds = max(0, effective_global_limit_seconds - int(total_used_seconds))
    global_is_locked = bool(enabled and effective_global_limit_seconds > 0 and total_used_seconds >= effective_global_limit_seconds)

    # Scanned leaf folders
    available_folders = get_playable_leaf_folders(videos_dir)
    # Ensure any folder that has limits configured is also included even if empty
    seen_paths = {f["path"] for f in available_folders}
    for fpath in folder_limits.keys():
        if fpath and fpath not in seen_paths:
            available_folders.append({
                "name": fpath.split('/')[-1],
                "path": fpath
            })
            seen_paths.add(fpath)

    folder_items = []
    for f in available_folders:
        folder_path = f["path"]
        limit_min = folder_limits.get(folder_path, 0)
        bonus_min = bonus_folder_minutes.get(folder_path, 0)
        effective_limit_min = (limit_min + bonus_min) if limit_min > 0 else 0
        effective_limit_sec = effective_limit_min * 60
        used_sec = int(folders_usage.get(folder_path, 0.0))

        folder_remaining_sec: Optional[int] = None
        if effective_limit_sec > 0:
            folder_remaining_sec = max(0, effective_limit_sec - used_sec)

        folder_self_locked = bool(enabled and effective_limit_sec > 0 and used_sec >= effective_limit_sec)
        is_locked = bool(enabled and (folder_self_locked or global_is_locked))

        # Effective remaining seconds for this specific folder (combination of folder & global)
        effective_remaining_sec: Optional[int] = None
        if folder_remaining_sec is not None and global_remaining_seconds is not None:
            effective_remaining_sec = min(folder_remaining_sec, global_remaining_seconds)
        elif folder_remaining_sec is not None:
            effective_remaining_sec = folder_remaining_sec
        elif global_remaining_seconds is not None:
            effective_remaining_sec = global_remaining_seconds

        folder_items.append({
            "name": f["name"],
            "path": folder_path,
            "limit_minutes": limit_min,
            "bonus_minutes": bonus_min,
            "effective_limit_minutes": effective_limit_min,
            "used_seconds": used_sec,
            "remaining_seconds": effective_remaining_sec,
            "self_locked": folder_self_locked,
            "is_locked": is_locked
        })

    return {
        "date": today,
        "yesterday_date": yesterday,
        "yesterday_used_seconds": int(yesterday_used_seconds),
        "recent_history": recent_history,
        "enabled": enabled,
        "has_parent_pin": bool(parent_pin),
        "global_limit_minutes": global_limit_minutes,
        "bonus_global_minutes": bonus_global_minutes,
        "effective_global_limit_minutes": effective_global_limit_minutes,
        "total_used_seconds": int(total_used_seconds),
        "global_remaining_seconds": global_remaining_seconds,
        "global_is_locked": global_is_locked,
        "folders": folder_items
    }


def record_heartbeat(
    state: Dict[str, Any],
    folder_path: str,
    delta_seconds: float,
    videos_dir: Path
) -> Tuple[Dict[str, Any], bool]:
    """Accrue active playback watch time and return updated limits and lock flag."""
    prune_old_logs(state)

    clean_path = str(folder_path or "").replace('\\', '/').strip('/')
    clamped_delta = max(0.5, min(float(delta_seconds), 60.0))

    today = get_today_key()
    logs = state.setdefault("daily_watch_logs", {})
    today_log = logs.setdefault(today, {
        "total_seconds": 0.0,
        "bonus_global_minutes": 0,
        "folders": {},
        "bonus_folder_minutes": {}
    })

    today_log["total_seconds"] = float(today_log.get("total_seconds", 0.0)) + clamped_delta
    folders_dict = today_log.setdefault("folders", {})
    if clean_path:
        folders_dict[clean_path] = float(folders_dict.get(clean_path, 0.0)) + clamped_delta

    # Re-evaluate status
    status = get_time_limits_status(state, videos_dir)

    # Check if folder or global is locked
    is_locked = False
    lock_reason: Optional[str] = None
    remaining_seconds: Optional[int] = None

    if status["enabled"]:
        if status["global_is_locked"]:
            is_locked = True
            lock_reason = "global"
            remaining_seconds = 0
        else:
            folder_info = next((f for f in status["folders"] if f["path"] == clean_path), None)
            if folder_info:
                remaining_seconds = folder_info["remaining_seconds"]
                if folder_info["is_locked"]:
                    is_locked = True
                    lock_reason = "folder"
                    remaining_seconds = 0
            else:
                remaining_seconds = status["global_remaining_seconds"]

    return {
        "status": "ok",
        "should_lock": is_locked,
        "lock_reason": lock_reason,
        "folder_path": clean_path,
        "delta_seconds": clamped_delta,
        "remaining_seconds": remaining_seconds,
        "global_remaining_seconds": status["global_remaining_seconds"],
        "date": today
    }, is_locked


def update_time_limits_config(state: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Save time limits configuration."""
    cfg = state.setdefault("time_limits", {})
    if not isinstance(cfg, dict):
        cfg = {}
        state["time_limits"] = cfg

    if "enabled" in payload:
        cfg["enabled"] = bool(payload["enabled"])

    if "global_limit_minutes" in payload:
        cfg["global_limit_minutes"] = max(0, int(payload["global_limit_minutes"] or 0))

    if "folder_limits" in payload and isinstance(payload["folder_limits"], dict):
        current_folder_limits = cfg.setdefault("folder_limits", {})
        for k, v in payload["folder_limits"].items():
            clean_k = str(k).replace('\\', '/').strip('/')
            if clean_k:
                current_folder_limits[clean_k] = max(0, int(v or 0))

    if "parent_pin" in payload:
        pin = str(payload["parent_pin"] or "").strip()
        # Pin must be 4 digits or empty string to clear
        if pin == "" or (pin.isdigit() and len(pin) == 4):
            cfg["parent_pin"] = pin

    return cfg


def extend_time(
    state: Dict[str, Any],
    extend_type: str,
    folder_path: str,
    minutes: int
) -> Dict[str, Any]:
    """Grant temporary bonus minutes for today."""
    today = get_today_key()
    logs = state.setdefault("daily_watch_logs", {})
    today_log = logs.setdefault(today, {
        "total_seconds": 0.0,
        "bonus_global_minutes": 0,
        "folders": {},
        "bonus_folder_minutes": {}
    })

    added_minutes = max(1, min(int(minutes), 240))
    clean_path = str(folder_path or "").replace('\\', '/').strip('/')

    if extend_type == "global":
        today_log["bonus_global_minutes"] = int(today_log.get("bonus_global_minutes", 0)) + added_minutes
    elif extend_type == "folder" and clean_path:
        bonus_folders = today_log.setdefault("bonus_folder_minutes", {})
        bonus_folders[clean_path] = int(bonus_folders.get(clean_path, 0)) + added_minutes
    elif extend_type == "unlock_today":
        # Unlock today by granting large bonus
        if clean_path:
            bonus_folders = today_log.setdefault("bonus_folder_minutes", {})
            bonus_folders[clean_path] = int(bonus_folders.get(clean_path, 0)) + 1440
        today_log["bonus_global_minutes"] = int(today_log.get("bonus_global_minutes", 0)) + 1440

    return {
        "success": True,
        "type": extend_type,
        "folder_path": clean_path,
        "added_minutes": added_minutes,
        "date": today
    }


def reset_today_usage(state: Dict[str, Any]) -> None:
    """Reset today's usage logs to zero."""
    today = get_today_key()
    logs = state.get("daily_watch_logs")
    if isinstance(logs, dict) and today in logs:
        logs[today] = {
            "total_seconds": 0.0,
            "bonus_global_minutes": 0,
            "folders": {},
            "bonus_folder_minutes": {}
        }


def verify_parent_pin(state: Dict[str, Any], pin: str) -> bool:
    """Verify if parent PIN matches."""
    cfg = state.get("time_limits") or {}
    expected_pin = str(cfg.get("parent_pin") or "").strip()
    if not expected_pin:
        # If no PIN configured, any verification is handled by frontend math challenge
        return True
    return str(pin).strip() == expected_pin
