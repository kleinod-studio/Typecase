"""Icons and colors of sheets and groups in the library, without GTK.

A sheet keeps its look in its front matter ("icon: star", "color: orange"), a group in its
folder file (FOLDER_FILE), so both travel along when they are moved, copied or synced. Only
names are stored: the icons and colors themselves come from GNOME, and the colors follow the
light and dark style."""

import json
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path

from . import frontmatter
from .fileio import atomic_write_text, read_text
from .library import FOLDER_FILE, _read_folder_file

DEFAULT_SHEET_ICON = "text-x-generic-symbolic"
DEFAULT_GROUP_ICON = "folder-symbolic"

# (stored name, icon name). The icons come from the GNOME icon theme, except the book, which
# it does not have. Only names from this list are shown; others are ignored.
ICONS = [
    ("star", "starred-symbolic"),
    ("heart", "emote-love-symbolic"),
    ("bookmark", "user-bookmarks-symbolic"),
    ("pin", "view-pin-symbolic"),
    ("flag", "emoji-flags-symbolic"),
    ("important", "dialog-warning-symbolic"),
    ("question", "dialog-question-symbolic"),
    ("book", "typecase-book-symbolic"),
    ("idea", "emoji-objects-symbolic"),
    ("person", "avatar-default-symbolic"),
    ("place", "mark-location-symbolic"),
    ("home", "user-home-symbolic"),
    ("calendar", "x-office-calendar-symbolic"),
    ("clock", "alarm-symbolic"),
    ("mail", "mail-unread-symbolic"),
    ("lock", "changes-prevent-symbolic"),
    ("picture", "image-x-generic-symbolic"),
    ("camera", "camera-photo-symbolic"),
    ("music", "audio-x-generic-symbolic"),
    ("art", "applications-graphics-symbolic"),
    ("science", "applications-science-symbolic"),
    ("game", "input-gaming-symbolic"),
    ("food", "emoji-food-symbolic"),
    ("nature", "emoji-nature-symbolic"),
    ("travel", "emoji-travel-symbolic"),
    ("sun", "weather-clear-symbolic"),
    ("moon", "weather-clear-night-symbolic"),
]
ICON_NAMES = dict(ICONS)

# The accent colors of libadwaita, in its order.
COLORS = ["blue", "teal", "green", "yellow", "orange", "red", "pink", "purple", "slate"]


def icon_label(name: str) -> str:
    """The name of an icon for tooltips and screen readers."""
    labels = {
        # Translators: names of the icons a sheet or group can have in the library
        "star": _("Star"), "heart": _("Heart"), "bookmark": _("Bookmark"), "pin": _("Pin"),
        "flag": _("Flag"), "important": _("Important"), "question": _("Question"), "book": _("Book"),
        "idea": _("Idea"), "person": _("Person"), "place": _("Place"), "home": _("Home"),
        "calendar": _("Calendar"), "clock": _("Clock"), "mail": _("Envelope"), "lock": _("Lock"),
        "picture": _("Picture"), "camera": _("Camera"), "music": _("Music"), "art": _("Art"),
        "science": _("Science"), "game": _("Game"), "food": _("Food"),
        "nature": _("Nature"), "travel": _("Travel"), "sun": _("Sun"), "moon": _("Moon"),
    }
    return labels.get(name, name)


def color_label(name: str) -> str:
    labels = {
        # Translators: the colors a sheet or group can have in the library
        "blue": _("Blue"), "teal": _("Teal"), "green": _("Green"), "yellow": _("Yellow"),
        "orange": _("Orange"), "red": _("Red"), "pink": _("Pink"), "purple": _("Purple"),
        "slate": _("Slate"),
    }
    return labels.get(name, name)


@dataclass(frozen=True)
class Look:
    """An icon and a color by their stored names; None is the standard."""

    icon: str | None = None
    color: str | None = None

    @classmethod
    def of(cls, icon, color) -> "Look":
        """From stored values; anything unknown counts as the standard."""
        icon = icon.strip().casefold() if isinstance(icon, str) else None
        color = color.strip().casefold() if isinstance(color, str) else None
        return cls(icon if icon in ICON_NAMES else None, color if color in COLORS else None)

    def icon_name(self, is_group: bool) -> str:
        if self.icon:
            return ICON_NAMES[self.icon]
        return DEFAULT_GROUP_ICON if is_group else DEFAULT_SHEET_ICON


def from_metadata(data: dict) -> Look:
    return Look.of(data.get("icon"), data.get("color"))


def metadata_changes(look: Look) -> dict:
    """Front matter fields for a look; the standard removes them."""
    return {"icon": look.icon, "color": look.color}


class LookIndex:
    """Reads the look of sheets (for the library) and caches it until a file changes."""

    def __init__(self):
        self._cache: dict[Path, tuple[float, int, Look]] = {}

    def of_sheet(self, path: Path) -> Look:
        try:
            stat = path.stat()
            cached = self._cache.get(path)
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return cached[2]
            header, _body = frontmatter.split(read_text(path))
        except (OSError, UnicodeDecodeError):
            return Look()
        look = from_metadata(frontmatter.parse(header))
        self._cache[path] = (stat.st_mtime, stat.st_size, look)
        return look


def of_group(folder: Path) -> Look:
    data = _read_folder_file(folder)
    return Look.of(data.get("icon"), data.get("color"))


def set_for_group(folder: Path, look: Look) -> None:
    """Stores a group's look in its folder file; other keys stay. The standard removes it again,
    and the file only if nothing else is left in it."""
    data = _read_folder_file(folder)
    for key, value in (("icon", look.icon), ("color", look.color)):
        if value:
            data[key] = value
        else:
            data.pop(key, None)
    path = folder / FOLDER_FILE
    if data:
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    elif path.exists():
        path.unlink()


def set_for_sheet(path: Path, look: Look) -> None:
    """Writes a sheet's look into its front matter on disk; text and other fields stay as they are.
    For the sheet open in the editor, use its set_metadata() instead. Raises OSError or
    UnicodeDecodeError."""
    header, body = frontmatter.split(read_text(path))
    new = frontmatter.update(header, metadata_changes(look))
    if new != header:
        atomic_write_text(path, frontmatter.join(new, body))
