"""Explainer video: a word goal per sheet, its ring, the floating badge and the rings in the library.

    python3 tools/video/writing-goals.py

Writes dist/videos/writing-goals/writing-goals.webm and .mp4, with English and German subtitles.
While it records, a Typecase window floats in the middle of the screen for about a minute; leave it
visible and don't touch it."""

import random

import videokit
from actions import library_rows, node, select
from videokit import Scene, zoom_to

TYPED = "\n- a keeper who counts the ships that pass, and marks each one with a star"

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def type_text(buffer, text, pace=0.06, seed=3):
    """Types at the cursor like a person, a little unevenly."""
    noise = random.Random(seed)
    for char in text:
        buffer.insert_at_cursor(char)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if char == " ":
            pause += pace * 0.6
        elif char in ",.":
            pause += pace * 3
        elif char == "\n":
            pause += pace * 4
        yield pause


def press(widget):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def inspector_button(win):
    from gi.repository import Gtk

    for widget in walk(win):
        if isinstance(widget, Gtk.ToggleButton) and widget.get_action_name() == "win.inspector" and widget.get_mapped():
            return widget
    raise LookupError("properties button")


def area(win, widget, margin=24):
    _found, bounds = widget.compute_bounds(win)
    return (bounds.get_x() - margin, bounds.get_y() - margin, bounds.get_width() + 2 * margin, bounds.get_height() + 2 * margin)


def words_now(win):
    from typecase.textstats import count_words

    buffer = win.editor.buffer
    return count_words(buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True))


# --- The scenes -----------------------------------------------------------------


def opening(win):
    win.inspector.stack.set_visible_child_name("goal")
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 1.0
    yield zoom_to(area(win, win.goal_badge, margin=60), length=1.2, factor=1.5)
    yield 1.8
    yield zoom_to(None, length=0.8)


def set_goal(win):
    select(win, "Ideas")
    yield 1.0
    yield from press(inspector_button(win))
    win.inspector_split.set_show_sidebar(True)
    yield 1.4
    row = win.inspector.goal_row
    row.set_enable_expansion(True)
    row.set_expanded(True)
    yield 0.8
    from typecase.textstats import count_words

    # A round number, reached with the last words of the line typed in a moment
    goal = (words_now(win) + count_words(TYPED)) // 5 * 5
    win.inspector.goal_spin.set_value(goal)
    yield 1.2


def ring(win):
    yield zoom_to(area(win, win.inspector.goal_view), length=1.0, factor=1.5)
    yield 3.0
    yield zoom_to(None, length=0.8)


def badge(win):
    yield from press(inspector_button(win))
    win.inspector_split.set_show_sidebar(False)
    win.editor.focus_editor()
    buffer = win.editor.buffer
    end = buffer.get_end_iter()
    while end.backward_char() and end.get_char() == "\n":  # right after the list, on its last line
        pass
    end.forward_char()
    buffer.place_cursor(end)
    yield 1.0
    yield zoom_to((640, 360, 640, 360), length=1.0, factor=1.3)
    yield from type_text(buffer, TYPED)
    yield 0.6


def reached(win):
    yield 1.4
    yield from press(win.goal_badge)
    yield zoom_to(None, length=0.8)
    win.inspector_split.set_show_sidebar(True)
    yield 2.6


def overview(win):
    win.inspector_split.set_show_sidebar(False)
    yield 0.4
    yield zoom_to(library_rows(win), length=1.0, factor=1.4)
    yield 2.2
    yield zoom_to(None, length=0.8)
    select(win, "Manuscript")
    yield 0.6
    win.group_mode.set_active_name("cards")
    yield 2.4


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Set yourself a goal, and see how far you've come.",
        "Setz dir ein Ziel und sieh, wie weit du schon bist.",
        intro,
    ),
    Scene(
        "Open the properties, and switch on a word goal in the Goal tab.",
        "Öffne die Eigenschaften und schalte im Reiter „Ziel“ ein Wortziel ein.",
        set_goal,
    ),
    Scene(
        "The ring shows how much you've written, and how much is still to go.",
        "Der Ring zeigt, wie viel du geschrieben hast und wie viel noch fehlt.",
        ring,
    ),
    Scene(
        "With the properties closed, a small badge keeps counting as you type.",
        "Sind die Eigenschaften zu, zählt ein kleines Kärtchen beim Tippen mit.",
        badge,
    ),
    Scene(
        "Reach your goal, and the ring turns green.",
        "Erreichst du dein Ziel, wird der Ring grün.",
        reached,
    ),
    Scene(
        "The rings in the library and on the cards show the progress of every sheet at a glance.",
        "Die Ringe in der Bibliothek und auf den Karten zeigen den Fortschritt jedes Blatts auf einen Blick.",
        overview,
    ),
    Scene(
        "Small steps, every day.",
        "Kleine Schritte, jeden Tag.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="writing-goals",
    title="Writing goals",
    topic="Plot",
    summary="Set a word goal for a sheet and watch the rings fill up as you write.",
    still=20,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
