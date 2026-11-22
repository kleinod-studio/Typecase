"""Explainer video: the properties of a sheet, its notes and its attachments.

    python3 tools/video/properties-notes-attachments.py

Writes dist/videos/properties-notes-attachments/properties-notes-attachments.webm and .mp4, with
English and German subtitles. While it records, a Typecase window floats in the middle of the
screen for about a minute; leave it visible and don't touch it. The file chooser of the plus button
is left out (it would show your own folders); the attachment is made from tools/video/lighthouse.svg."""

import random
import subprocess
import tempfile
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
SUBTITLE = ": A Name from the Sea"
NOTE = "Check: did the lighthouse have a radio in 1871? Ask the museum."
RENAMED = "03 The Letter from the Sea"

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def pause_after(char, pace, noise):
    pause = pace * (1 + noise.uniform(-0.35, 0.35))
    if char == " ":
        pause += pace * 0.6
    elif char in ",.?:":
        pause += pace * 3
    return pause


def append_to(entry, text, pace=0.07, seed=4):
    """Types at the end of an entry."""
    noise = random.Random(seed)
    entry.grab_focus()
    start = entry.get_text()
    for count in range(1, len(text) + 1):
        entry.set_text(start + text[:count])
        entry.set_position(-1)
        yield pause_after(text[count - 1], pace, noise)


def type_into(entry, text, pace=0.07, seed=4):
    """Types into the entry of a dialog, over its selected text."""
    noise = random.Random(seed)
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        yield pause_after(text[count - 1], pace, noise)


def type_buffer(buffer, text, pace=0.05, seed=8):
    noise = random.Random(seed)
    for char in text:
        buffer.insert_at_cursor(char)
        yield pause_after(char, pace, noise)


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


def dialog_button(dialog, label):
    from gi.repository import Gtk

    for widget in walk(dialog):
        if isinstance(widget, Gtk.Button) and widget.get_label() == label:
            return widget
    raise LookupError(label)


def inspector_area(win):
    """The properties pane, as a rectangle in the window."""
    _found, bounds = win.inspector.compute_bounds(win)
    return (bounds.get_x() - 40, bounds.get_y(), bounds.get_width() + 40, bounds.get_height())


# --- The scenes -----------------------------------------------------------------


def opening(win):
    win.inspector.stack.set_visible_child_name("details")
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "03 The Letter")
    win.editor.focus_editor()


def intro(win):
    yield 2.0


def open_properties(win):
    yield 0.4
    yield from press(inspector_button(win))
    win.inspector_split.set_show_sidebar(True)
    yield 2.0


def document(win):
    yield zoom_to(inspector_area(win), length=1.0, factor=1.4)
    yield 0.4
    yield from append_to(win.inspector.subtitle_row, SUBTITLE)
    yield 1.4


def status(win):
    row = win.inspector.status_row
    choices = win.inspector._choices["status"]
    wanted = next((value for value in choices if value.lower().startswith("revis")), choices[-1])
    yield 0.6
    yield from press(row)
    row.set_selected(choices.index(wanted))
    yield 2.4


def notes(win):
    win.inspector.stack.set_visible_child_name("notes")
    yield 1.0
    view = win.inspector.notes_view
    view.grab_focus()
    yield from type_buffer(view.get_buffer(), NOTE)
    yield 1.4


def attachments(win):
    from gi.repository import Gio

    folder = Path(tempfile.mkdtemp())
    picture = folder / "sea-chart.png"
    subprocess.run(["rsvg-convert", "-w", "800", str(HERE / "lighthouse.svg"), "-o", str(picture)], check=True)
    yield 0.6
    win.inspector._add_files([Gio.File.new_for_path(str(picture))])
    yield 3.0


def rename(win):
    yield zoom_to(None, length=1.0)
    win.editor.flush()
    win.activate_action("win.rename", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield from type_into(dialog.get_extra_child(), RENAMED)
    yield 0.6
    button = dialog_button(dialog, "Rename")
    yield from press(button)
    button.emit("clicked")
    yield 1.0
    yield zoom_to(inspector_area(win), length=1.0, factor=1.4)
    yield 1.8


def closing(win):
    yield zoom_to(None, length=0.8)
    yield 0.6


SCENES = [
    Scene(
        "Every sheet can carry more than its text: properties, notes and files.",
        "Jedes Blatt kann mehr als seinen Text tragen: Eigenschaften, Notizen und Dateien.",
        intro,
    ),
    Scene(
        "Press Alt+Enter, or click the button at the top right, to open the properties.",
        "Mit Alt+Enter oder einem Klick auf den Knopf oben rechts öffnest du die Eigenschaften.",
        open_properties,
        say="Press Alt Enter, or click the button at the top right, to open the properties.",
    ),
    Scene(
        "Title, subtitle and author are used when you export, for example on the cover page.",
        "Titel, Untertitel und Autor nutzt Typecase beim Export, zum Beispiel für das Deckblatt.",
        document,
        say="Title, subtitle and author are used when you export, for example on the cover page.",
    ),
    Scene(
        "The status shows how far a sheet has come: draft, revision or final.",
        "Der Status zeigt, wie weit ein Blatt ist: Entwurf, Überarbeitung oder fertig.",
        status,
    ),
    Scene(
        "Notes are for you alone. They stay with the sheet, but never appear in the text or the export.",
        "Notizen sind nur für dich. Sie gehören zum Blatt, tauchen aber nie im Text oder im Export auf.",
        notes,
    ),
    Scene(
        "Drop files onto the attachments, or use the plus button. Typecase keeps a copy next to the sheet.",
        "Zieh Dateien auf die Anhänge oder nimm den Plus-Knopf. Typecase legt eine Kopie neben das Blatt.",
        attachments,
        say="Drop files onto the attachments, or use the plus button. Type case keeps a copy next to the sheet.",
    ),
    Scene(
        "Move or rename the sheet, and its notes and attachments go along.",
        "Verschiebst oder benennst du das Blatt um, kommen Notizen und Anhänge mit.",
        rename,
    ),
    Scene(
        "Everything about a sheet, in one place.",
        "Alles rund um ein Blatt, an einem Ort.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="properties-notes-attachments",
    title="Properties, notes and attachments",
    topic="Plot",
    summary="Give a sheet a title, author and status, keep private notes with it and attach files that move along.",
    still=30,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
