"""Explainer video: light and dark style, the built-in editor themes, and importing a theme.

    python3 tools/video/editor-themes.py

Writes dist/videos/themes/themes.webm and .mp4, with English and German subtitles. While it
records, a Typecase window floats in the middle of the screen for about a minute; leave it visible
and don't touch it. The file chooser is left out (it would show your own folders): the theme files
are made beforehand and imported the way the Import button does it after they are chosen."""

import shutil
import tempfile
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene

STATE = {}
THEME = "harbor"

# A theme as GNOME Text Editor knows it: a light and a dark style scheme, paired in their metadata
HARBOR = {
    "harbor": ("Harbor", "Adwaita", "light", "dark-variant", "harbor-dark", {
        "text": 'foreground="#2B3A42" background="#F3EFE6"', "selection": 'background="#D9E6E3"',
        "current-line": 'background="#ECE6DA"', "cursor": 'foreground="#2A7F86"',
        "typecase:syntax": 'foreground="#A79F8F"', "typecase:link": 'foreground="#2A7F86"',
        "typecase:heading": 'foreground="#1F4E5F"', "typecase:code": 'background="#E9E2D4"',
        "typecase:code-block": 'foreground="#D8D0BF" background="#ECE6DA"',
    }),
    "harbor-dark": ("Harbor Dark", "Adwaita-dark", "dark", "light-variant", "harbor", {
        "text": 'foreground="#D8DEE0" background="#1C2A33"', "selection": 'background="#2F4A55"',
        "current-line": 'background="#22323C"', "cursor": 'foreground="#6FC3C9"',
        "typecase:syntax": 'foreground="#5E7480"', "typecase:link": 'foreground="#6FC3C9"',
        "typecase:heading": 'foreground="#E8D9B5"', "typecase:code": 'background="#263843"',
        "typecase:code-block": 'foreground="#3A505C" background="#22323C"',
    }),
}

# --- Helpers --------------------------------------------------------------------


def write_harbor(folder):
    files = []
    for scheme_id, (name, parent, variant, partner_key, partner, styles) in HARBOR.items():
        lines = [f'<style name="{style}" {attributes}/>' for style, attributes in styles.items()]
        text = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<style-scheme id="{scheme_id}" name="{name}" version="1.0" parent-scheme="{parent}">\n'
            "  <author>Ada Morrow</author>\n  <description>Sand and sea</description>\n"
            f'  <metadata>\n    <property name="variant">{variant}</property>\n'
            f'    <property name="{partner_key}">{partner}</property>\n  </metadata>\n  '
            + "\n  ".join(lines) + "\n</style-scheme>\n"
        )
        path = folder / f"{scheme_id}.xml"
        path.write_text(text, encoding="utf-8")
        files.append(path)
    return files


def press(widget):
    """Shows a button or row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.4
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def scroll_to(widget, length=1.0, above=24):
    """Scrolls the preferences smoothly until widget is near the top."""
    from gi.repository import Graphene, Gtk

    scrolled = widget.get_ancestor(Gtk.ScrolledWindow)
    adjustment = scrolled.get_vadjustment()
    _found, point = widget.compute_point(scrolled, Graphene.Point().init(0, 0))
    start = adjustment.get_value()
    target = max(0, min(start + point.y - above, adjustment.get_upper() - adjustment.get_page_size()))
    frames = max(1, round(length * 30))
    for frame in range(1, frames + 1):
        u = frame / frames
        adjustment.set_value(start + (target - start) * u * u * (3 - 2 * u))
        yield 1 / 30


def pick_theme(section, theme_id):
    preview = section._previews[theme_id]
    yield from press(preview)
    section._choose_theme(theme_id)


def guide_row(group):
    from gi.repository import Adw

    def walk(widget):
        child = widget.get_first_child()
        while child is not None:
            yield child
            yield from walk(child)
            child = child.get_next_sibling()

    return next(w for w in walk(group) if isinstance(w, Adw.ActionRow) and w.get_title() == "How to Build Your Own Theme")


# --- The scenes -----------------------------------------------------------------


def opening(win):
    folder = Path(tempfile.mkdtemp(prefix="typecase-video-themes-", dir=Path.home() / ".cache"))
    STATE["folder"] = folder
    STATE["files"] = write_harbor(folder)
    for group in ("The Lighthouse Keeper", "Manuscript"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 2.4


def style(win):
    yield 0.3
    win.activate_action("win.preferences", None)
    yield 0.8
    STATE["prefs"] = prefs = win.get_visible_dialog()
    section = prefs.editor_page
    yield from scroll_to(section.color_scheme, length=1.2, above=60)
    yield 0.4
    yield from press(section.color_scheme)
    section.color_scheme.set_selected(2)  # Dark
    yield 1.6
    yield from press(section.color_scheme)
    section.color_scheme.set_selected(1)  # Light
    yield 1.2


def builtin(win):
    section = STATE["prefs"].editor_page
    for theme_id in ("typecase-paper", "typecase-solarized", "typecase-calm"):
        yield 0.4
        yield from pick_theme(section, theme_id)
        yield 1.1


def import_theme(win):
    from gi.repository import Adw
    from typecase import themes

    prefs = STATE["prefs"]
    group = prefs.themes_group
    yield from scroll_to(group, length=1.2, above=140)
    yield 0.4
    yield from press(group.get_header_suffix())
    yield 0.6
    for path in STATE["files"]:
        themes.install(path)
    group.refresh()
    prefs._themes_changed()
    prefs.add_toast(Adw.Toast(title="Imported harbor.xml, harbor-dark.xml"))  # as the Import button reports it
    yield 1.4
    yield from scroll_to(prefs.editor_page.theme_box, length=1.2, above=60)
    yield 0.3
    yield from pick_theme(prefs.editor_page, THEME)
    yield 1.4


def guide(win):
    prefs = STATE["prefs"]
    row = guide_row(prefs.themes_group)
    yield from scroll_to(prefs.themes_group, length=1.0, above=140)
    yield 0.6
    from gi.repository import Gtk

    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 2.2
    row.unset_state_flags(Gtk.StateFlags.PRELIGHT)


def closing(win):
    STATE["prefs"].close()
    shutil.rmtree(STATE["folder"], ignore_errors=True)
    yield 2.4


SCENES = [
    Scene(
        "Choose the colors you like to write in.",
        "Wähle die Farben, in denen du gern schreibst.",
        intro,
    ),
    Scene(
        "Light, dark, or follow the system.",
        "Hell, dunkel oder wie das System.",
        style,
    ),
    Scene(
        "Five themes are built in, each in light and dark.",
        "Fünf Themen sind eingebaut, jedes in Hell und Dunkel.",
        builtin,
    ),
    Scene(
        "Import more: Typecase reads the theme files of GNOME Text Editor.",
        "Importiere weitere: Typecase liest die Themen-Dateien von GNOME Text Editor.",
        import_theme,
    ),
    Scene(
        "Or build your own. The guide shows how.",
        "Oder bau dein eigenes. Die Anleitung zeigt, wie.",
        guide,
    ),
    Scene(
        "Write in your colors.",
        "Schreib in deinen Farben.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="themes",
    title="Themes",
    topic="Make it yours",
    summary="Switch between light and dark, choose a built-in editor theme, or import one from GNOME Text Editor.",
    still=20,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
