"""Explainer video: the editor's font, size, line width and line spacing, and settings of focus mode's own.

    python3 tools/video/fonts-and-layout.py

Writes dist/videos/fonts-and-layout/fonts-and-layout.webm and .mp4, with English and German
subtitles. While it records, a Typecase window floats in the middle of the screen for about a
minute; leave it visible and don't touch it. Focus mode would go full screen; the recording keeps
the window as it is. The font chooser is left out; the font button shows the chosen font."""

import videokit
from actions import node, select
from videokit import Scene, zoom_to

FONT = "Noto Serif"
STATE = {}

# --- Helpers --------------------------------------------------------------------


def boolean(value):
    from gi.repository import GLib

    return GLib.Variant.new_boolean(value)


def press(widget):
    """Shows a button or row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.4
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def spin_to(row, value, pace=0.14):
    """Counts a spin row up or down to value, the way clicking its buttons does."""
    yield from press(row)
    start = row.get_value()
    step = row.get_adjustment().get_step_increment() * (1 if value > start else -1)
    current = start
    while (value - current) * step > 0:
        current += step
        row.set_value(current)
        yield pace


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


def open_preferences(win):
    win.activate_action("win.preferences", None)
    yield 0.8
    STATE["prefs"] = win.get_visible_dialog()


# --- The scenes -----------------------------------------------------------------


def opening(win):
    win.fullscreen = lambda: None
    win.unfullscreen = lambda: None
    for group in ("The Lighthouse Keeper", "Manuscript"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 2.4


def font(win):
    from gi.repository import Pango

    yield 0.3
    yield from open_preferences(win)
    section = STATE["prefs"].editor_page
    yield from scroll_to(section.system_font, length=0.9, above=90)
    yield 0.5
    yield from press(section.system_font)
    section.system_font.set_active(False)
    yield 0.7
    yield from press(section.font_button)
    section.font_button.set_font_desc(Pango.FontDescription.from_string(FONT))
    yield 1.6


def layout(win):
    section = STATE["prefs"].editor_page
    yield 0.3
    yield from spin_to(section.font_size, 17)
    yield 0.4
    yield from spin_to(section.line_width, 60, pace=0.2)
    yield 0.4
    yield from press(section.line_spacing)
    section.line_spacing.set_selected(2)  # Relaxed
    yield 1.2


def result(win):
    STATE["prefs"].close()
    yield 3.4


def focus(win):
    yield 0.3
    yield from open_preferences(win)
    prefs = STATE["prefs"]
    yield from scroll_to(prefs.focus_same, length=1.4, above=120)
    yield 0.4
    yield from press(prefs.focus_same)
    prefs.focus_same.set_active(False)
    yield 0.8
    yield from scroll_to(prefs.focus_page.font_size, length=1.0, above=160)
    yield 0.3
    yield from spin_to(prefs.focus_page.font_size, 21)
    yield 0.8
    prefs.close()
    yield 0.6
    win.lookup_action("focus-mode").change_state(boolean(True))
    win.editor.focus_editor()
    yield 3.2


def closing(win):
    win.lookup_action("focus-mode").change_state(boolean(False))
    yield 2.0


SCENES = [
    Scene(
        "Make the editor feel like yours.",
        "Mach den Editor zu deinem.",
        intro,
    ),
    Scene(
        "Pick any font on your computer.",
        "Wähle eine beliebige Schrift auf deinem Computer.",
        font,
    ),
    Scene(
        "Set the size, how wide the lines are and how much space is between them.",
        "Stell die Größe ein, wie breit die Zeilen sind und wie viel Abstand dazwischen ist.",
        layout,
    ),
    Scene(
        "Every change shows right away.",
        "Jede Änderung siehst du sofort.",
        result,
    ),
    Scene(
        "Focus mode can have settings of its own.",
        "Der Fokusmodus kann eigene Einstellungen haben.",
        focus,
    ),
    Scene(
        "Your words, your way.",
        "Deine Worte, dein Stil.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="fonts-and-layout",
    title="Fonts and layout",
    topic="Make it yours",
    summary="Choose the editor's font, size, line width and line spacing, and give focus mode its own.",
    still=24,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
