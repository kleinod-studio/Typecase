import json
from pathlib import Path

from gi.repository import GLib

from .fileio import atomic_write_text

CONFIG_PATH = Path(GLib.get_user_config_dir()) / "typecase" / "config.json"


def load() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> None:
    atomic_write_text(CONFIG_PATH, json.dumps(data, indent=2))


def get_library_path() -> Path | None:
    value = load().get("library_path")
    if not isinstance(value, str):
        return None
    path = Path(value)
    return path if path.is_dir() else None


def update(**values) -> None:
    data = load()
    data.update(values)
    save(data)


def set_library_path(path: Path) -> None:
    data = load()
    if data.get("library_path") != str(path):
        data.pop("last_sheet", None)  # gilt nur für die bisherige Bibliothek
        data.pop("expanded_groups", None)
    data["library_path"] = str(path)
    save(data)
