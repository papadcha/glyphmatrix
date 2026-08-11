from __future__ import annotations

import json
from pathlib import Path

_CONFIG_PATH = Path.home() / ".glyphmatrix" / "config.json"


def _load() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(data, indent=2))


def get_api_key() -> str | None:
    return _load().get("google_fonts_api_key")


def set_api_key(key: str) -> None:
    data = _load()
    data["google_fonts_api_key"] = key
    _save(data)
