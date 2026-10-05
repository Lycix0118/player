"""Filesystem boundaries used by the application."""

import json
import os
from pathlib import Path
from typing import Any, Optional


def safe_resolve_path(base_dir: Path, user_path: str) -> Optional[Path]:
    """Resolve a user path below ``base_dir`` and reject traversal attempts."""
    try:
        resolved_base = base_dir.resolve()
        clean_path = (user_path or "").strip().lstrip("/\\")
        target = (resolved_base / clean_path).resolve()
        if target.is_relative_to(resolved_base):
            return target
    except (OSError, ValueError, TypeError):
        pass
    return None


def ensure_directories(*directories: Path) -> None:
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, ValueError, TypeError):
        return default


def write_json_atomic(path: Path, value: Any) -> None:
    """Write JSON via a sibling temporary file and atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)
