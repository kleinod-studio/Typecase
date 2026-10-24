import json
from pathlib import Path

from gi.repository import GLib

from .fileio import atomic_write_text

CONFIG_PATH = Path(GLib.get_user_config_dir()) / "typecase" / "config.json"
# Imported export templates (unpacked); in the Flatpak under ~/.var/app/…/data
TEMPLATES_DIR = Path(GLib.get_user_data_dir()) / "typecase" / "templates"


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
        data.pop("last_sheet", None)  # only valid for the previous library
        data.pop("expanded_groups", None)
    data["library_path"] = str(path)
    save(data)


# --- Settings ------------------------------------------------------------------

LINE_SPACINGS = ("compact", "normal", "relaxed")
COLOR_SCHEMES = ("system", "light", "dark")
SETTINGS_DEFAULTS = {
    "editor_font": None,  # None = interface font
    "editor_font_size": 15,
    "line_width": 70,  # characters per line in the text column
    "line_spacing": "normal",
    "color_scheme": "system",
}
FONT_SIZE_RANGE = (8, 48)
LINE_WIDTH_RANGE = (30, 200)


PROFILES = ("editor", "focus")  # normal editor and focus mode
_PREFIX = {"editor": "", "focus": "focus_"}


def settings(profile: str = "editor") -> dict:
    """A profile's settings, validated: anything invalid or missing is replaced by the default.
    For the focus profile these are its own values, even while it is currently using the editor's."""
    data = load()
    prefix = _PREFIX[profile]
    result = dict(SETTINGS_DEFAULTS)
    font = data.get(prefix + "editor_font")
    if isinstance(font, str) and font.strip():
        result["editor_font"] = font.strip()
    for key, (low, high) in [("editor_font_size", FONT_SIZE_RANGE), ("line_width", LINE_WIDTH_RANGE)]:
        value = data.get(prefix + key)
        if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
            result[key] = value
    if data.get(prefix + "line_spacing") in LINE_SPACINGS:
        result["line_spacing"] = data[prefix + "line_spacing"]
    if data.get(prefix + "color_scheme") in COLOR_SCHEMES:
        result["color_scheme"] = data[prefix + "color_scheme"]
    return result


def focus_uses_editor_settings() -> bool:
    """Does focus mode use the editor's settings? (Default: yes)"""
    return load().get("focus_same_as_editor") is not False


def effective_settings(focus_mode: bool) -> dict:
    """What should apply right now: in focus mode its own profile, unless it uses the editor's."""
    if focus_mode and not focus_uses_editor_settings():
        return settings("focus")
    return settings("editor")


def update_profile(profile: str, values: dict) -> None:
    update(**{_PREFIX[profile] + key: value for key, value in values.items()})


# --- Defaults for sheet metadata ------------------------------------------------

LANGUAGES = ("de-DE", "de-AT", "de-CH", "en-US", "en-GB", "fr-FR", "es-ES", "it-IT", "nl-NL")


def _system_language() -> str:
    for name in GLib.get_language_names():
        code = name.split(".")[0].split("@")[0].replace("_", "-")
        if code in LANGUAGES:
            return code
        for known in LANGUAGES:
            if known.split("-")[0] == code:
                return known
    return "en-US"


def sheet_defaults() -> dict:
    """Defaults for author and language. They apply as long as a sheet does not specify its own,
    and are not written into the files."""
    data = load()
    author = data.get("default_author")
    lang = data.get("default_lang")
    return {
        "author": author.strip() if isinstance(author, str) and author.strip() else None,
        "lang": lang if isinstance(lang, str) and lang.strip() else _system_language(),
    }
