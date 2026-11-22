"""Explainer video: a group's sheets as one continuous text, and the outline to jump between headings.

    python3 tools/video/group-view-and-outline.py

Writes dist/videos/group-view-and-outline/group-view-and-outline.webm and .mp4, with English and
German subtitles. While it records, a Typecase window floats in the middle of the screen for about
a minute; leave it visible and don't touch it."""

import random

import videokit
from actions import node, select
from videokit import Scene, zoom_to

TYPED = " She folded the letter twice and put it in the log."

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def type_text(buffer, text, pace=0.06, seed=5):
    """Types at the cursor like a person, a little unevenly."""
    noise = random.Random(seed)
    for char in text:
        buffer.insert_at_cursor(char)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if char == " ":
            pause += pace * 0.6
        elif char in ",.":
            pause += pace * 3
        yield pause


def press(widget):
    """Shows a button or row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def scroll(adjustment, target, frames=45):
    """A smooth scroll, as with the mouse wheel."""
    start = adjustment.get_value()
    target = max(0, min(target, adjustment.get_upper() - adjustment.get_page_size()))
    for frame in range(1, frames + 1):
        u = frame / frames
        adjustment.set_value(start + (target - start) * u * u * (3 - 2 * u))
        yield 1 / 30


def section(win, stem):
    return next(editor for editor in win.group_view.editors if editor.path.stem == stem)


def section_header(win, stem):
    from gi.repository import Gtk

    for widget in walk(win.group_view):
        if isinstance(widget, Gtk.Button) and isinstance(widget.get_child(), Gtk.Label) and widget.get_child().get_label() == stem:
            return widget
    raise LookupError(stem)


def outline_row(win, title):
    for row in walk(win.outline_list):
        if getattr(row, "target", None) and row.get_child().get_label() == title:
            return row
    raise LookupError(title)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 2.0


def group_view(win):
    select(win, "Manuscript")
    yield 1.6
    from gi.repository import Graphene

    adjustment = win.group_view.get_vadjustment()
    # Down to where the second sheet begins: the line and its name in view, a third from the top
    header = section_header(win, "02 The Storm")
    _found, point = header.compute_point(win.group_view.get_child(), Graphene.Point().init(0, 0))
    yield from scroll(adjustment, point.y - adjustment.get_page_size() * 0.35, frames=75)
    yield 1.0


def write(win):
    editor = section(win, "03 The Letter")
    buffer = editor.buffer
    end = buffer.get_end_iter()
    while end.backward_char() and end.get_char() == "\n":  # right after the last paragraph, on its line
        pass
    end.forward_char()
    win.group_view.active = editor
    editor.view.grab_focus()
    buffer.place_cursor(end)
    win.group_view.reveal_caret(editor)
    yield 1.0
    yield from type_text(buffer, TYPED)
    yield 1.2


def counts(win):
    yield zoom_to(win.content_title, length=1.0, factor=1.5)
    yield 2.4
    yield zoom_to(None, length=0.8)


def outline(win):
    win.activate_action("win.outline", None)
    yield 3.4


def jump(win):
    row = outline_row(win, "The lamp")
    win.outline_list.select_row(row)
    row.grab_focus()
    yield 0.6
    yield from press(row)
    win.outline_list.emit("row-activated", row)
    yield 2.6


def single(win):
    header = section_header(win, "02 The Storm")
    yield 0.4
    yield from press(header)
    header.emit("clicked")
    yield 2.2


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Long texts grow sheet by sheet. Sometimes you want to see them as a whole.",
        "Lange Texte wachsen Blatt für Blatt. Manchmal willst du sie als Ganzes sehen.",
        intro,
    ),
    Scene(
        "Select a group, and all its sheets appear one after another, like one long text.",
        "Wählst du eine Gruppe, stehen alle ihre Blätter untereinander, wie ein langer Text.",
        group_view,
    ),
    Scene(
        "Write right here. Each sheet is still saved to its own file.",
        "Du schreibst direkt hier. Jedes Blatt wird trotzdem in seiner eigenen Datei gespeichert.",
        write,
    ),
    Scene(
        "The word count now covers the whole group.",
        "Die Wortzahl gilt jetzt für die ganze Gruppe.",
        counts,
    ),
    Scene(
        "Ctrl+Shift+O opens the outline: every heading of the group, in one list.",
        "Mit Strg+Umschalt+O öffnest du die Gliederung: alle Überschriften der Gruppe in einer Liste.",
        outline,
        say="Control Shift O opens the outline: every heading of the group, in one list.",
    ),
    Scene(
        "Pick one, and you jump right there. It works for a single sheet, too.",
        "Wähle eine aus, und du springst genau dorthin. Das geht auch in einem einzelnen Blatt.",
        jump,
    ),
    Scene(
        "Click a sheet's name to open it on its own.",
        "Ein Klick auf den Namen eines Blatts öffnet es für sich allein.",
        single,
    ),
    Scene(
        "Write in pieces, read as a whole.",
        "In Stücken schreiben, als Ganzes lesen.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="group-view-and-outline",
    title="Group view and outline",
    topic="Organize",
    summary="Read and write a whole group as one text, and jump to any heading from the outline.",
    still=20,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
