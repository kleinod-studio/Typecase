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


# --- Einstellungen -------------------------------------------------------------

LINE_SPACINGS = ("compact", "normal", "relaxed")
COLOR_SCHEMES = ("system", "light", "dark")
SETTINGS_DEFAULTS = {
    "editor_font": None,  # None = Schrift der Oberfläche
    "editor_font_size": 15,
    "line_width": 70,  # Zeichen pro Zeile im Textblock
    "line_spacing": "normal",
    "color_scheme": "system",
}
FONT_SIZE_RANGE = (8, 48)
LINE_WIDTH_RANGE = (30, 200)


def settings() -> dict:
    """Die Einstellungen, geprüft: Ungültiges oder Fehlendes wird durch die Voreinstellung ersetzt."""
    data = load()
    result = dict(SETTINGS_DEFAULTS)
    font = data.get("editor_font")
    if isinstance(font, str) and font.strip():
        result["editor_font"] = font.strip()
    for key, (low, high) in [("editor_font_size", FONT_SIZE_RANGE), ("line_width", LINE_WIDTH_RANGE)]:
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
            result[key] = value
    if data.get("line_spacing") in LINE_SPACINGS:
        result["line_spacing"] = data["line_spacing"]
    if data.get("color_scheme") in COLOR_SCHEMES:
        result["color_scheme"] = data["color_scheme"]
    return result
