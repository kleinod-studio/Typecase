"""Editor themes: GtkSourceView style schemes, each with a light and a dark variant.

A theme is the standard file format of GNOME's text editors (a style scheme XML file), so any
scheme from GNOME Text Editor or the web can be imported. Typecase reads a few extra styles of
its own (typecase:syntax, typecase:link, …) for the Markdown styling; schemes without them get
colors derived from their text color. Light and dark variants are paired through the scheme's
metadata (light-variant / dark-variant, as GNOME Text Editor does) or the "-dark" suffix."""

import os
import re
import shutil
import tempfile
import tomllib
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path

from gi.repository import Gdk, Gio, GLib, GtkSource

BUILTIN_DIR = Path(__file__).resolve().parent / "themes"
USER_DIR = Path(GLib.get_user_data_dir()) / "typecase" / "themes"
DEFAULT = "typecase-standard"
BUILTIN = ("typecase-standard", "typecase-paper", "typecase-solarized", "typecase-calm", "typecase-high-contrast")
MAX_SIZE = 512 * 1024

# Omarchy (an Arch Linux desktop) keeps the colors of its current theme in a small file; from it
# Typecase builds a theme of its own that follows the desktop. The path is fixed in Omarchy itself.
OMARCHY_ID = "typecase-omarchy"
OMARCHY_DIR = Path.home() / ".local" / "state" / "omarchy" / "current"
GENERATED_DIR = Path(GLib.get_user_cache_dir()) / "typecase" / "themes"


def builtin_name(theme_id: str) -> str | None:
    return {
        "typecase-standard": _("Standard"),
        "typecase-paper": _("Paper"),
        "typecase-solarized": _("Solarized"),
        "typecase-calm": _("Calm"),
        "typecase-high-contrast": _("High Contrast"),
    }.get(theme_id)


class ThemeError(Exception):
    """A file that cannot be imported as a theme; the message is shown to the user."""


@dataclass
class Theme:
    id: str  # the light variant's scheme id (or the only one)
    name: str
    light: str
    dark: str
    builtin: bool
    files: tuple[Path, ...] = ()  # imported themes: their scheme files
    omarchy: bool = False  # follows the colors of the current Omarchy theme


_manager: GtkSource.StyleSchemeManager | None = None


def _system_paths() -> list[str]:
    """Where GtkSourceView keeps its own schemes (Adwaita, solarized-light, …), which our themes
    use as parents: built into the library in newer versions, as files in older ones."""
    return [path for path in GtkSource.StyleSchemeManager.get_default().get_search_path() if path not in (str(USER_DIR), str(BUILTIN_DIR))]


def manager() -> GtkSource.StyleSchemeManager:
    """A scheme manager for Typecase's own themes and the imported ones; only those are offered
    (see available()), the system's schemes serve as their parents."""
    global _manager
    if _manager is None:
        update_omarchy()
        _manager = GtkSource.StyleSchemeManager()
        _manager.set_search_path([str(GENERATED_DIR), str(USER_DIR), str(BUILTIN_DIR), *_system_paths()])
    return _manager


def rescan() -> None:
    manager().force_rescan()


def _partner(scheme: GtkSource.StyleScheme, ids: set[str], dark: bool) -> str | None:
    wanted = scheme.get_metadata("dark-variant" if dark else "light-variant")
    if wanted in ids:
        return wanted
    sid = scheme.get_id()
    guess = sid + "-dark" if dark else (sid[: -len("-dark")] if sid.endswith("-dark") else None)
    return guess if guess in ids else None


def _is_dark(scheme: GtkSource.StyleScheme) -> bool:
    variant = scheme.get_metadata("variant")
    if variant in ("light", "dark"):
        return variant == "dark"
    background = _color(scheme, "text", "background")
    return background is not None and _luminance(background) < 0.5


def available() -> list[Theme]:
    """The built-in themes in their fixed order, then the imported ones by name."""
    schemes = manager()
    builtin = [Theme(sid, builtin_name(sid), sid, sid + "-dark", True) for sid in BUILTIN]
    if schemes.get_scheme(OMARCHY_ID) is not None:
        # One variant: an Omarchy theme is either light or dark (Omarchy is a name, not translated)
        builtin.append(Theme(OMARCHY_ID, "Omarchy", OMARCHY_ID, OMARCHY_ID, True, omarchy=True))
    imported: list[Theme] = []
    user_files = {}
    for path in USER_DIR.glob("*.xml") if USER_DIR.is_dir() else []:
        scheme_id = _scheme_id(path)
        if scheme_id:
            user_files[scheme_id] = path
    ids = set(user_files)
    seen: set[str] = set()
    for sid in sorted(ids):
        scheme = schemes.get_scheme(sid)
        if scheme is None or sid in seen:
            continue
        if _is_dark(scheme):
            light, dark = _partner(scheme, ids, dark=False) or sid, sid
        else:
            light, dark = sid, _partner(scheme, ids, dark=True) or sid
        if light in seen or dark in seen:
            continue
        seen.update((light, dark))
        name = schemes.get_scheme(light).get_name() if schemes.get_scheme(light) else sid
        files = tuple(user_files[s] for s in sorted({light, dark}))
        imported.append(Theme(light, name, light, dark, False, files))
    return builtin + sorted(imported, key=lambda theme: theme.name.casefold())


def find(theme_id: str | None) -> Theme:
    themes = available()
    return next((theme for theme in themes if theme.id == theme_id), themes[0])


def scheme(theme_id: str | None, dark: bool) -> GtkSource.StyleScheme:
    theme = find(theme_id)
    found = manager().get_scheme(theme.dark if dark else theme.light)
    return found or manager().get_scheme(DEFAULT + ("-dark" if dark else ""))


# --- Omarchy -------------------------------------------------------------------

_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_omarchy_monitor: Gio.FileMonitor | None = None
_omarchy_timeout = 0
_omarchy_callbacks: list = []


def _hex_mix(a: str, b: str, amount: float) -> str:
    """Hex color a moved towards b by amount (0..1)."""
    channels = [round(int(a[i:i + 2], 16) + (int(b[i:i + 2], 16) - int(a[i:i + 2], 16)) * amount) for i in (1, 3, 5)]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def omarchy_xml(colors: dict) -> str | None:
    """A style scheme from the colors of an Omarchy theme (its colors.toml); None if the colors
    needed (text and background) are missing."""
    def color(key, fallback=None):
        value = colors.get(key)
        return value.lower() if isinstance(value, str) and _HEX.fullmatch(value) else fallback

    text, background = color("foreground"), color("background")
    if not text or not background:
        return None
    dark = colors.get("mode") != "light"
    accent = color("accent", color("blue", text))
    styles = {
        "text": (text, background),
        "selection": (None, color("selection", _hex_mix(background, accent, 0.3))),
        "current-line": (None, color("lighter_background", _hex_mix(background, text, 0.05))),
        "cursor": (accent, None),
        "typecase:syntax": (color("dark_foreground", _hex_mix(text, background, 0.55)), None),
        "typecase:heading": (color("bright_foreground", text), None),
        "typecase:link": (accent, None),
        "typecase:code": (None, color("lighter_background", _hex_mix(background, text, 0.07))),
        "typecase:code-block": (color("muted", _hex_mix(background, text, 0.15)), color("lighter_background", _hex_mix(background, text, 0.04))),
    }
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- Made by Typecase from the colors of the current Omarchy theme; rebuilt when it changes. -->",
        f'<style-scheme id="{OMARCHY_ID}" name="Omarchy" version="1.0" parent-scheme="{"Adwaita-dark" if dark else "Adwaita"}">',
        "  <metadata>",
        f'    <property name="variant">{"dark" if dark else "light"}</property>',
        "  </metadata>",
    ]
    for name, (foreground, fill) in styles.items():
        attributes = (f' foreground="{foreground}"' if foreground else "") + (f' background="{fill}"' if fill else "")
        lines.append(f'  <style name="{name}"{attributes}/>')
    lines.append("</style-scheme>")
    return "\n".join(lines) + "\n"


def update_omarchy() -> bool:
    """(Re)builds the Omarchy theme from the current Omarchy colors, or removes it when there are
    none. Returns whether it changed."""
    from .fileio import atomic_write_text

    target = GENERATED_DIR / f"{OMARCHY_ID}.xml"
    try:
        with open(OMARCHY_DIR / "theme" / "colors.toml", "rb") as file:
            xml = omarchy_xml(tomllib.load(file))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        xml = None
    try:
        old = target.read_text(encoding="utf-8")
    except OSError:
        old = None
    if xml == old:
        return False
    try:
        if xml is None:
            target.unlink(missing_ok=True)
        else:
            GENERATED_DIR.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, xml)
    except OSError:
        return False
    return True


def watch_omarchy(on_change) -> None:
    """Calls on_change() after the Omarchy theme changed (a new theme was set in Omarchy)."""
    global _omarchy_monitor
    _omarchy_callbacks.append(on_change)
    if _omarchy_monitor is not None or not OMARCHY_DIR.is_dir():
        return

    def changed():
        global _omarchy_timeout
        _omarchy_timeout = 0
        if update_omarchy():
            rescan()
            for callback in list(_omarchy_callbacks):
                callback()
        return GLib.SOURCE_REMOVE

    def on_event(*_args):
        # Omarchy replaces several files in a row; wait until it is done
        global _omarchy_timeout
        if _omarchy_timeout:
            GLib.source_remove(_omarchy_timeout)
        _omarchy_timeout = GLib.timeout_add(400, changed)

    try:
        _omarchy_monitor = Gio.File.new_for_path(str(OMARCHY_DIR)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
    except GLib.Error:
        return
    _omarchy_monitor.connect("changed", on_event)


# --- Colors for the Markdown styling ------------------------------------------


def _color(scheme: GtkSource.StyleScheme, style_id: str, prop: str) -> Gdk.RGBA | None:
    style = scheme.get_style(style_id)
    value = getattr(style.props, prop) if style is not None else None
    if not value:
        return None
    color = Gdk.RGBA()
    return color if color.parse(value) else None


def _luminance(color: Gdk.RGBA) -> float:
    return 0.2126 * color.red + 0.7152 * color.green + 0.0722 * color.blue


def _with_alpha(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    result = color.copy()
    result.alpha = alpha
    return result


def palette(scheme: GtkSource.StyleScheme) -> dict:
    """The colors Typecase needs, taken from the scheme's typecase:* styles where it has them,
    otherwise derived from its text and link colors."""
    dark = _is_dark(scheme)
    background = _color(scheme, "text", "background") or _rgba("#1d1d20" if dark else "#ffffff")
    text = _color(scheme, "text", "foreground") or _rgba("#c0bfbc" if dark else "#504e55")
    link = _color(scheme, "typecase:link", "foreground") or _color(scheme, "def:net-address", "foreground") or _rgba("#78aeed" if dark else "#1c71d8")
    return {
        "dark": dark,
        "background": background,
        "text": text,
        "syntax": _color(scheme, "typecase:syntax", "foreground") or _with_alpha(text, 0.4),
        "link": link,
        "list-marker": _color(scheme, "typecase:list-marker", "foreground") or link,
        "heading": _color(scheme, "typecase:heading", "foreground"),  # None: the text color
        "code": _color(scheme, "typecase:code", "background") or _with_alpha(text, 0.07),
        "block-fill": _color(scheme, "typecase:code-block", "background") or _with_alpha(text, 0.04),
        "block-border": _color(scheme, "typecase:code-block", "foreground") or _with_alpha(text, 0.15),
        "caret": _color(scheme, "cursor", "foreground") or text,
    }


def _mix(a: Gdk.RGBA, b: Gdk.RGBA, amount: float) -> str:
    """a moved towards b by amount (0..1), as a CSS color."""
    def channel(x, y):
        return round((x + (y - x) * amount) * 255)
    return f"rgb({channel(a.red, b.red)},{channel(a.green, b.green)},{channel(a.blue, b.blue)})"


def window_css(palette: dict) -> str:
    """libadwaita colors for the whole window, derived from the theme (as GNOME Text Editor does):
    header bars blend with the text, sidebars and cards are shades of the same background, and the
    accent is the theme's link color."""
    bg, fg, accent = palette["background"], palette["text"], palette["link"]
    css = lambda color: color.to_string()  # noqa: E731
    on_accent = "#000000" if _luminance(accent) > 0.6 else "#ffffff"
    sidebar = _mix(bg, fg, 0.06)
    raised = _mix(bg, fg, 0.03)
    card = css(bg) if not palette["dark"] else _mix(bg, fg, 0.10)
    return (
        ":root {"
        f" --window-bg-color: {raised}; --window-fg-color: {css(fg)};"
        f" --view-bg-color: {css(bg)}; --view-fg-color: {css(fg)};"
        f" --headerbar-bg-color: {css(bg)}; --headerbar-fg-color: {css(fg)}; --headerbar-backdrop-color: {css(bg)};"
        f" --sidebar-bg-color: {sidebar}; --sidebar-fg-color: {css(fg)}; --sidebar-backdrop-color: {sidebar};"
        f" --secondary-sidebar-bg-color: {sidebar}; --secondary-sidebar-fg-color: {css(fg)}; --secondary-sidebar-backdrop-color: {sidebar};"
        f" --popover-bg-color: {raised}; --popover-fg-color: {css(fg)};"
        f" --dialog-bg-color: {raised}; --dialog-fg-color: {css(fg)};"
        f" --card-bg-color: {card}; --card-fg-color: {css(fg)};"
        f" --accent-bg-color: {css(accent)}; --accent-fg-color: {on_accent}; --accent-color: {css(accent)};"
        " }"
    )


def _rgba(spec: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(spec)
    return color


# --- Importing and removing -----------------------------------------------------


def _scheme_id(path: Path) -> str | None:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    return root.get("id") if root.tag == "style-scheme" else None


def peek(path: Path) -> tuple[str, str]:
    """Checks a file before importing; returns (scheme id, name). Raises ThemeError."""
    try:
        if path.stat().st_size > MAX_SIZE:
            raise ThemeError(_("The file is too large for a theme."))
        root = ElementTree.parse(path).getroot()
    except OSError as error:
        raise ThemeError(error.strerror or str(error)) from error
    except ElementTree.ParseError as error:
        raise ThemeError(_("The file is not a valid theme (style scheme XML).")) from error
    scheme_id, name = root.get("id"), root.get("name") or root.get("_name")
    if root.tag != "style-scheme" or not scheme_id or not name:
        raise ThemeError(_("The file is not a valid theme (style scheme XML)."))
    if "/" in scheme_id or scheme_id.startswith(".") or scheme_id.startswith("typecase-"):
        raise ThemeError(_("The theme’s ID “%s” is reserved or not allowed.") % scheme_id)
    return scheme_id, name


def install(path: Path) -> str:
    """Copies a scheme file into the themes folder (replacing one with the same ID) and checks
    that GtkSourceView can load it. Returns the scheme id. Raises ThemeError or OSError."""
    scheme_id, _name = peek(path)
    USER_DIR.mkdir(parents=True, exist_ok=True)
    target = USER_DIR / f"{scheme_id}.xml"
    handle, temporary = tempfile.mkstemp(dir=USER_DIR, prefix=".", suffix=".part")
    os.close(handle)
    try:
        shutil.copyfile(path, temporary)
        # Load it on its own first: a scheme GtkSourceView rejects must not replace a working one.
        check = GtkSource.StyleSchemeManager()
        staging = Path(tempfile.mkdtemp(dir=USER_DIR, prefix=".check-"))
        try:
            shutil.copyfile(temporary, staging / f"{scheme_id}.xml")
            check.set_search_path([str(staging), str(BUILTIN_DIR), *_system_paths()])
            if check.get_scheme(scheme_id) is None:
                raise ThemeError(_("GtkSourceView could not load this theme."))
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    rescan()
    return scheme_id


# --- Saving a built-in theme as a starting point --------------------------------

# The styles a saved theme spells out, with what they color (comments in the file).
_STYLES = (
    ("text", "Text color and page background"),
    ("selection", "Selected text"),
    ("cursor", "Text cursor"),
    ("typecase:syntax", "Markdown marks such as # ** _ (shown faintly)"),
    ("typecase:heading", "Headings (leave out to use the text color)"),
    ("typecase:link", "Links; also the accent color of the window"),
    ("typecase:list-marker", "List bullets and numbers (leave out to use the link color)"),
    ("typecase:code", "Background of `inline code`"),
    ("typecase:code-block", "Code blocks: frame (foreground) and fill (background)"),
)


def _xml_attribute(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def theme_xml(theme_id: str, dark: bool, new_id: str, new_name: str, partner_id: str) -> str:
    """A built-in variant as a commented, self-contained scheme file with a new id, ready to edit
    and import. Code highlighting keeps coming from the same parent scheme."""
    source = scheme(theme_id, dark)
    parent_id = ElementTree.parse(source.get_filename()).getroot().get("parent-scheme")
    variant = "dark" if dark else "light"
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- An editor theme for Typecase: a GtkSourceView style scheme. Change the colors, then import",
        "     the file under Preferences → Writing → Themes. Guide: https://kleinod.studio/typecase/themes/ -->",
        f'<style-scheme id="{_xml_attribute(new_id)}" name="{_xml_attribute(new_name)}" version="1.0"'
        + (f' parent-scheme="{_xml_attribute(parent_id)}"' if parent_id else "")
        + ">",
        f"  <description>{_xml_attribute(new_name)}</description>",
        "  <metadata>",
        f'    <property name="variant">{variant}</property>',
        f'    <property name="{"dark" if variant == "light" else "light"}-variant">{_xml_attribute(partner_id)}</property>',
        "  </metadata>",
    ]
    for style_id, comment in _STYLES:
        style = source.get_style(style_id)
        attributes = []
        for prop in ("foreground", "background"):
            value = getattr(style.props, prop) if style is not None else None
            if value:
                attributes.append(f'{prop}="{_xml_attribute(value)}"')
        lines.append(f"  <!-- {comment} -->")
        if attributes:
            lines.append(f'  <style name="{style_id}" {" ".join(attributes)}/>')
        else:
            lines.append(f'  <!-- <style name="{style_id}" foreground="#000000"/> -->')
    lines.append("</style-scheme>")
    return "\n".join(lines) + "\n"


def save_builtin(theme_id: str, folder: Path, name: str) -> list[Path]:
    """Saves both variants of a built-in theme into folder as "<name>.xml" and "<name> (dark).xml"
    (never overwriting: a free name is chosen). Their ids are derived from the name, so the files
    can be imported next to the original. Returns the written files."""
    from .fileio import atomic_write_text
    from .library import unique_path

    light = unique_path(folder, name, ".xml")
    dark = unique_path(folder, light.stem + " (dark)", ".xml")
    slug = re.sub(r"[^a-z0-9]+", "-", light.stem.casefold()).strip("-") or "theme"
    light_id, dark_id = slug, slug + "-dark"
    atomic_write_text(light, theme_xml(theme_id, False, light_id, light.stem, dark_id))
    atomic_write_text(dark, theme_xml(theme_id, True, dark_id, light.stem, light_id))
    return [light, dark]
