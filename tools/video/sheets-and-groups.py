"""Explainer video: creating, naming, ordering, moving, duplicating and deleting sheets and groups.

    python3 tools/video/sheets-and-groups.py

Writes dist/videos/sheets-and-groups/sheets-and-groups.webm and .mp4, with English and German
subtitles. While it records, a Typecase window floats in the middle of the screen for about a
minute and a half; leave it visible and don't touch it. The deleted copy goes to the trash of the
recording's own temporary home, not yours. Dragging with the mouse can't be played back; the
video moves entries with Alt+Up and the Move to dialog instead."""

import random

import videokit
from actions import label_of, library_rows, node, select
from videokit import Scene, zoom_to

GROUP = "Short Stories"
SHEET = "# The Ferryman\n\nThe ferry crossed twice a day, and never on Sundays."
RENAMED = "Ideas for Book Two"

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def type_text(win, text, pace=0.06, seed=11):
    """Types into the sheet like a person, a little unevenly."""
    noise = random.Random(seed)
    buffer = win.editor.buffer
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


def type_into(entry, text, pace=0.07, seed=4):
    """Types into the entry of a dialog, over its selected text."""
    noise = random.Random(seed)
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        yield pace * (1 + noise.uniform(-0.35, 0.35)) + (pace * 0.6 if text[count - 1] == " " else 0)


def press(widget):
    """Shows a button or menu row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def dialog_button(dialog, label):
    from gi.repository import Gtk

    for widget in walk(dialog):
        if isinstance(widget, Gtk.Button) and widget.get_label() == label:
            return widget
    raise LookupError(label)


def click(dialog, label):
    """Clicks a button of the dialog that is open."""
    button = dialog_button(dialog, label)
    yield from press(button)
    button.emit("clicked")


def row_menu(win, english):
    """Selects the row and opens its menu, as a right-click does. The menu opens beside the
    pointer and stays below the top edge, so that it fits into the picture for every row."""
    from gi.repository import Gdk, Graphene, Gtk

    select(win, english)
    label = label_of(win, english)
    _found, point = label.compute_point(win.list_view, Graphene.Point().init(label.get_width() * 0.6, label.get_height() / 2))
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = int(point.x), int(point.y), 1, 1
    menu = win.row_menu
    menu.set_position(Gtk.PositionType.RIGHT)
    menu.set_pointing_to(rect)
    _found, window_point = label.compute_point(win, Graphene.Point().init(0, label.get_height() / 2))
    height = MENU_HEIGHT
    menu.set_offset(0, max(0, round(60 - (window_point.y - height / 2))))
    menu.set_can_target(False)  # the real pointer, wherever it is, must not hover a row
    menu.popup()
    for widget in walk(menu):
        widget.unset_state_flags(Gtk.StateFlags.SELECTED | Gtk.StateFlags.PRELIGHT)
    return menu


MENU_HEIGHT = 404  # the row menu with its shadow, measured


def choose(menu, label):
    """Hovers a menu row and closes the menu, as a click on it would."""
    from gi.repository import Gtk

    row = None
    for widget in walk(menu):
        if isinstance(widget, Gtk.Label) and widget.get_label() == label:
            row = widget
            while row.__gtype__.name != "GtkModelButton" and row.get_parent() is not None:
                row = row.get_parent()
    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    row.grab_focus()
    yield 0.8
    row.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    menu.popdown()


def unselect(win):
    from gi.repository import Gtk

    win.selection.set_selected(Gtk.INVALID_LIST_POSITION)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 1.5
    yield zoom_to(library_rows(win), length=1.6, factor=1.4)
    yield 2.0


def new_group(win):
    yield zoom_to(None, length=1.0)
    unselect(win)  # nothing selected: the group goes to the top of the library
    win.activate_action("win.new-group", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield from type_into(dialog.get_extra_child(), GROUP)
    yield 0.6
    yield from click(dialog, "Rename")
    yield 1.2


def new_sheet(win):
    win.activate_action("win.new-sheet", None)
    yield 0.8
    win.editor.focus_editor()
    yield from type_text(win, SHEET)
    yield 1.8


def rename(win):
    yield 0.4
    menu = row_menu(win, "Ideas")
    yield 1.4
    yield from choose(menu, "Rename…")
    win.activate_action("win.rename", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield from type_into(dialog.get_extra_child(), RENAMED)
    yield 0.6
    yield from click(dialog, "Rename")
    yield 1.0


def order(win):
    yield zoom_to((0, 30, 560, 315), length=1.2, factor=1.5)  # the notes at the top of the library
    select(win, "Open Questions")
    yield 1.2
    win.activate_action("win.move-up", None)
    yield 2.0


def move(win):
    yield zoom_to(None, length=1.0)
    menu = row_menu(win, "Open Questions")
    yield 1.2
    yield from choose(menu, "Move to…")
    win.activate_action("win.move", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    choice = dialog.get_extra_child()
    labels = [choice.get_model().get_string(i) for i in range(choice.get_model().get_n_items())]
    choice.set_selected(labels.index("The Lighthouse Keeper"))
    yield 1.2
    yield from click(dialog, "Move")
    yield 1.4


def duplicate(win):
    menu = row_menu(win, "04 Low Tide")
    yield 1.2
    yield from choose(menu, "Duplicate")
    win.activate_action("win.duplicate", None)
    yield 1.8


def trash(win):
    menu = row_menu(win, "04 Low Tide (Copy)")
    yield 1.2
    yield from choose(menu, "Move to Trash…")
    win.activate_action("win.delete", None)
    yield 1.6
    yield from click(win.get_visible_dialog(), "Move to Trash")
    yield 1.4


def closing(win):
    select(win, "04 Low Tide")
    yield 1.0


SCENES = [
    Scene(
        "Your library is a folder on your computer. Each sheet is a Markdown file, and each group is a folder.",
        "Deine Bibliothek ist ein Ordner auf deinem Computer. Jedes Blatt ist eine Markdown-Datei, jede Gruppe ein "
        "Ordner.",
        intro,
    ),
    Scene(
        "Press Ctrl+Shift+N for a new group, and give it a name.",
        "Mit Strg+Umschalt+N legst du eine neue Gruppe an und gibst ihr einen Namen.",
        new_group,
        say="Press Control Shift N for a new group, and give it a name.",
    ),
    Scene(
        "Ctrl+N adds a sheet to it. Start with a heading, and the sheet takes its name.",
        "Mit Strg+N kommt ein Blatt hinein. Beginnst du mit einer Überschrift, bekommt das Blatt ihren Namen.",
        new_sheet,
        say="Control N adds a sheet to it. Start with a heading, and the sheet takes its name.",
    ),
    Scene(
        "To rename a sheet or group, press F2, or right-click it.",
        "Zum Umbenennen drückst du F2 oder klickst mit rechts darauf.",
        rename,
        say="To rename a sheet or group, press F 2, or right-click it.",
    ),
    Scene(
        "Drag entries into the order you want, or use Alt and the arrow keys.",
        "Ziehe Einträge in die Reihenfolge, die du willst, oder nimm Alt und die Pfeiltasten.",
        order,
    ),
    Scene(
        "Drop an entry onto another group to move it there, or choose Move to from the menu.",
        "Lass einen Eintrag auf einer anderen Gruppe los, um ihn dorthin zu verschieben, oder wähle „Verschieben "
        "nach…“ im Menü.",
        move,
    ),
    Scene(
        "Duplicate makes a copy right below, handy for trying out another version.",
        "„Duplizieren“ legt direkt darunter eine Kopie an, praktisch, um eine andere Fassung auszuprobieren.",
        duplicate,
    ),
    Scene(
        "What you delete goes to the trash of your computer, so you can get it back.",
        "Was du löschst, landet im Papierkorb deines Computers, du kannst es also zurückholen.",
        trash,
    ),
    Scene(
        "Just files and folders, ordered the way you think.",
        "Einfach Dateien und Ordner, so geordnet, wie du denkst.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="sheets-and-groups",
    title="Sheets and groups",
    topic="Organize",
    summary="Create, rename, order and move sheets and groups, make copies and delete what you no longer need.",
    still=20,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
