"""Explainer video: Markdown tables. A table is inserted and filled in with Tab, its columns line
up while typing, the "+" buttons and the context menu add and remove rows and columns, a colon
aligns a column, Tidy Table puts a hand-typed table in order, and the PDF export shows them as in
a book.

    python3 tools/video/markdown-tables.py

Writes dist/videos/tables/tables.webm and .mp4, with English and German subtitles. Needs the
installed Typecase Flatpak for the PDF (it brings Pandoc and WeasyPrint; the code of this checkout
runs inside it) and Papers to show it. While it records, a Typecase window floats in the middle of
the screen for about two minutes and Papers opens over it at the end; leave it all visible and
don't touch it."""

import importlib.util
import subprocess
from pathlib import Path

import videokit
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pills_video = _load("images_links_footnotes", "images-links-footnotes.py")
spelling_video = _load("spell_checking", "spell-checking.py")
comments_video = _load("comments", "comments.py")
export_video = _load("export_a_sheet", "export-a-sheet.py")
text_of, place, type_text, press = pills_video.text_of, pills_video.place, pills_video.type_text, pills_video.press
bar_button, format_, lines_rect = pills_video.bar_button, pills_video.format_, pills_video.lines_rect
menu_item, walk = spelling_video.menu_item, spelling_video.walk
context_menu, scroll_to_offset = comments_video.context_menu, comments_video.scroll_to_offset
choose_row, area, open_button = export_video.choose, export_video.area, export_video.open_button
bring_in, close, temp, hidden_start = export_video.bring_in, export_video.close, export_video.temp, export_video.hidden_start
X, Y = export_video.X, export_video.Y

SHEET = """# Supplies

What the station needs before winter:

And the tools, as Ben typed them by hand:

| Tool | Box |
|--|--|
| Hammer | 2 |
| Spirit level | 1 |
"""
STATE = {}

# --- Helpers --------------------------------------------------------------------


def editor(win):
    return win.editor


def line_offset(win, number, column=0):
    return editor(win).buffer.get_iter_at_line_offset(number, column)[1].get_offset()


def table_rect(win, first, last, above=60, below=60):
    """The lines of a table, roomy enough for the "+" buttons beside it."""
    text = text_of(win)
    lines = text.split("\n")
    start = sum(len(line) + 1 for line in lines[:first])
    end = sum(len(line) + 1 for line in lines[: last + 1]) - 1
    return lines_rect(win, start, end, above=above, below=below)


def current_table(win):
    line = editor(win)._cursor_line()
    return next((a, b) for a, b in editor(win).styler.tables if a <= line <= b)


def zoom_table(win, length=1.0, factor=1.35):
    first, last = current_table(win)
    return zoom_to(table_rect(win, first, last + 1), length=length, factor=factor)


def tab(win, back=False):
    editor(win).move_in_table(not back)
    editor(win).focus_editor()


def fill(win, cells, pause=0.5, seed=3):
    """Types the cells one after the other, with Tab after every one but the last."""
    for number, cell in enumerate(cells):
        yield from type_text(win, cell, seed=seed + number)
        yield pause
        if number < len(cells) - 1:
            tab(win)
            yield 0.35


def open_menu(win, offset):
    """The editor's context menu at offset, with nothing hovered yet."""
    from gi.repository import Gtk

    popover = context_menu(win, offset)
    yield 0.1
    popover.grab_focus()  # the menu's first row would take the focus, and look chosen
    for widget in walk(popover):
        widget.unset_state_flags(Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.SELECTED)
    STATE["menu"] = popover
    # The table's items are at the end of the menu: lift it so it ends inside the window
    _found, bounds = popover.compute_bounds(win)
    overhang = bounds.get_y() + bounds.get_height() - (win.get_height() - 12)
    if overhang > 0:
        popover.set_offset(0, -round(overhang))
    yield 0.2


def zoom_menu(win, labels, length=1.0, factor=1.45):
    """Zooms to the rows of the menu with these labels."""
    popover = STATE["menu"]
    _found, menu = popover.compute_bounds(win)
    rows = [menu_item(popover, label).compute_bounds(win)[1] for label in labels]
    top = min(row.get_y() for row in rows)
    bottom = max(row.get_y() + row.get_height() for row in rows)
    return zoom_to((menu.get_x() - 80, top - 70, menu.get_width() + 160, bottom - top + 140), length=length, factor=factor)


def hover(label, seconds=1.4):
    """Lights up one row of the open menu, the way the pointer would."""
    from gi.repository import Gtk

    popover = STATE["menu"]
    for widget in walk(popover):
        widget.unset_state_flags(Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.SELECTED)
    row = menu_item(popover, label)
    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    row.grab_focus()
    yield seconds


def click(win, label, kind):
    """Clicks the lit row: the menu closes and the table changes."""
    from gi.repository import Gtk

    row = menu_item(STATE["menu"], label)
    row.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.2
    STATE["menu"].popdown()
    editor(win).edit_table(kind)
    yield 0.4


def export_pdf(win):
    """Exports the sheet as it is now, in the background, with this checkout's code inside the
    installed Flatpak (which brings Pandoc and WeasyPrint)."""
    work = temp("typecase-video-tables-")
    sheet = work / "Supplies.md"
    sheet.write_text(text_of(win), encoding="utf-8")
    STATE["pdf"] = work / "Supplies.pdf"
    STATE["export"] = subprocess.Popen(
        ["flatpak", "run", f"--filesystem={ROOT}:ro", f"--filesystem={work}", f"--env=TYPECASE_CODE={ROOT / 'src'}",
         "--command=python3", "studio.kleinod.Typecase", str(HERE / "flatpak_export.py"),
         str(sheet), str(ROOT / "src" / "typecase" / "templates" / "text"), "pdf", str(STATE["pdf"])],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


def start_papers(pdf):
    """Papers with settings of its own: one page across the width, so the table is large."""
    home = temp("typecase-video-papers-")
    settings = home / "cfg" / "glib-2.0" / "settings"
    settings.mkdir(parents=True)
    (settings / "keyfile").write_text(
        "[org/gnome/papers/default]\nshow-sidebar=false\ndual-page=false\nsizing-mode='fit-width'\n\n"
        "[org/gnome/papers]\nnight-mode=false\n"
    )
    env = {"XDG_CONFIG_HOME": str(home / "cfg"), "XDG_DATA_HOME": str(home / "data"), "XDG_STATE_HOME": str(home / "state"),
           "XDG_CACHE_HOME": str(home / "cache"), "GSETTINGS_BACKEND": "keyfile", "GIO_USE_VFS": "local",
           "ADW_DEBUG_COLOR_SCHEME": "prefer-light", "LANGUAGE": "en"}
    hidden_start("org.gnome.Papers", ["papers", str(pdf)], env)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import export_dialog

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    path = win.library_path / "Supplies.md"
    path.write_text(SHEET, encoding="utf-8")
    win._reload(select_path=path)
    win._open_selected()
    editor(win).focus_editor()
    place(win, text_of(win).index("winter:") + len("winter:"))


def intro(win):
    yield 2.0


def insert(win):
    yield from press(bar_button(win, "table"))
    format_(win, "table")
    yield 0.6
    yield zoom_table(win, length=1.1)
    yield 2.4


def titles(win):
    yield 0.3
    yield from fill(win, ["Item", "Where from", "Amount"])
    yield 0.8
    tab(win, back=True)  # Shift+Tab
    yield 1.4
    tab(win)
    yield 1.0


def grow(win):
    tab(win)  # into the first row
    yield 0.6
    yield from type_text(win, "Lamp mantles", pace=0.11, seed=5)
    yield 1.2
    tab(win)
    yield 0.3
    yield from fill(win, ["Harbour shop", "2"], seed=8)
    yield 1.0


def new_row(win):
    tab(win)
    yield 0.4
    yield from fill(win, ["Lamp oil", "Supply ship", "40 l"], seed=11)
    yield 0.8
    tab(win)  # in the very last cell: a new row
    yield 1.2
    yield zoom_table(win, length=0.8)
    yield from fill(win, ["Rope", "Harbour shop", "25 m"], seed=14)
    yield 1.0


def buttons(win):
    yield zoom_table(win, length=0.9, factor=1.3)
    yield 1.2
    column, row = editor(win)._table_buttons["column-end"], editor(win)._table_buttons["row-end"]
    yield from press(column)
    editor(win).edit_table("column-end")
    yield 0.6
    yield from type_text(win, "Note", seed=17)
    yield 1.4
    yield from press(row)
    editor(win).edit_table("row-end")
    yield 0.4
    yield zoom_table(win, length=0.6, factor=1.3)
    yield from type_text(win, "Matches", seed=19)
    yield 1.2


def rows(win):
    text = text_of(win)
    yield from open_menu(win, text.index("Lamp oil") + 2)
    yield zoom_menu(win, ["Add Row Above", "Add Row Below"])
    yield 0.6
    yield from hover("Add Row Above", 1.6)
    yield from hover("Add Row Below", 1.6)
    yield from hover("Add Row Above", 1.0)
    yield from click(win, "Add Row Above", "row-above")
    yield zoom_table(win, length=0.8, factor=1.3)
    yield 1.4


def columns(win):
    yield from open_menu(win, editor(win).buffer.get_iter_at_mark(editor(win).buffer.get_insert()).get_offset())
    yield zoom_menu(win, ["Add Column Left", "Add Column Right"])
    yield 0.6
    yield from hover("Add Column Left", 1.6)
    yield from hover("Add Column Right", 1.6)
    yield from hover("Add Column Left", 1.0)
    yield from click(win, "Add Column Left", "column-left")
    yield zoom_table(win, length=0.8, factor=1.3)
    yield 1.4


def remove(win):
    yield from open_menu(win, editor(win).buffer.get_iter_at_mark(editor(win).buffer.get_insert()).get_offset())
    yield zoom_menu(win, ["Remove Row", "Remove Column"])
    yield 0.6
    yield from hover("Remove Row", 1.6)
    yield from hover("Remove Column", 1.6)
    yield from hover("Remove Row", 0.8)
    yield from click(win, "Remove Row", "remove-row")
    yield zoom_table(win, length=0.7, factor=1.3)
    yield 1.2
    yield from open_menu(win, editor(win).buffer.get_iter_at_mark(editor(win).buffer.get_insert()).get_offset())
    yield zoom_menu(win, ["Remove Row", "Remove Column"], length=0.7)
    yield from hover("Remove Column", 1.2)
    yield from click(win, "Remove Column", "remove-column")
    yield zoom_table(win, length=0.7, factor=1.3)
    yield 1.6


def align(win):
    first, _last = current_table(win)
    separator = text_of(win).split("\n")[first + 1]
    pipes = [i for i, char in enumerate(separator) if char == "|"]
    end = line_offset(win, first + 1, pipes[3])  # the end of Amount's dashes
    yield zoom_to(table_rect(win, first, first + 2, above=40, below=40), length=0.9, factor=1.5)
    place(win, end - 1)
    editor(win).focus_editor()
    yield 1.0
    buffer = editor(win).buffer
    buffer.delete(buffer.get_iter_at_offset(end - 1), buffer.get_iter_at_offset(end))
    yield 0.3
    yield from type_text(win, ":", seed=21)
    yield 2.0
    export_pdf(win)


def tidy(win):
    yield zoom_to(None, length=0.8)
    text = text_of(win)
    start = text.index("| Tool")
    yield from scroll_to_offset(win, start, fraction=0.35)
    yield zoom_to(lines_rect(win, start, text.index("| 1 |") + 5, above=50, below=50), length=0.9, factor=1.45)
    yield 1.2
    yield from open_menu(win, text.index("Hammer") + 2)
    yield zoom_menu(win, ["Tidy Table"], factor=1.4)
    yield from hover("Tidy Table", 1.6)
    from gi.repository import Gtk

    menu_item(STATE["menu"], "Tidy Table").set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.2
    STATE["menu"].popdown()
    editor(win).tidy_table()
    text = text_of(win)
    yield zoom_to(lines_rect(win, start, text.index("Spirit level") + 20, above=50, below=50), length=0.8, factor=1.45)
    yield 2.0


def export(win):
    yield zoom_to(None, length=0.8)
    win.activate_action("win.export", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=0.8, factor=1.4)
    yield from choose_row(dialog.format_row, "PDF")
    yield 0.8
    process = STATE["export"]
    while process.poll() is None:
        yield 0.2
    if process.returncode:
        raise RuntimeError(process.stderr.read().decode())
    start_papers(STATE["pdf"])
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    win._on_exported(STATE["pdf"], None, [])
    yield 1.0
    yield from press(open_button(win))
    yield from bring_in("org.gnome.Papers", 1280, 720, X, Y)
    yield 3.0


def closing(win):
    close("org.gnome.Papers")
    yield 1.4


SCENES = [
    Scene(
        "Sometimes a list isn't enough. Typecase writes tables in plain Markdown, and helps you keep them tidy.",
        "Manchmal reicht eine Liste nicht. Typecase schreibt Tabellen in ganz normalem Markdown und hilft dir, sie ordentlich zu halten.",
        intro,
    ),
    Scene(
        "Press Ctrl+Shift+T, or use the table button. The first title is already selected, so you can start typing right away.",
        "Drück Strg+Umschalt+T oder nimm den Tabellen-Knopf. Der erste Titel ist schon markiert, du kannst gleich lostippen.",
        insert,
        say="Press Control Shift T, or use the table button. The first title is already selected, so you can start typing right away.",
    ),
    Scene(
        "Tab takes you to the next cell. Shift+Tab goes back.",
        "Tab bringt dich in die nächste Zelle. Umschalt+Tab geht zurück.",
        titles,
        say="Tab takes you to the next cell. Shift Tab goes back.",
    ),
    Scene(
        "As a cell grows, the whole column moves along with it. The columns always line up, without a single extra space in your file.",
        "Wird eine Zelle länger, rückt die ganze Spalte mit. Die Spalten stehen immer untereinander, ohne ein einziges zusätzliches Leerzeichen in deiner Datei.",
        grow,
    ),
    Scene(
        "In the very last cell, Tab adds a new row.",
        "In der allerletzten Zelle legt Tab eine neue Zeile an.",
        new_row,
    ),
    Scene(
        "While you're in a table, two small plus buttons appear. The one beside the titles adds a column, the one beside the last row adds a row.",
        "Solange du in einer Tabelle bist, erscheinen zwei kleine Plus-Knöpfe. Der neben den Titeln fügt eine Spalte hinzu, der neben der letzten Zeile eine Zeile.",
        buttons,
    ),
    Scene(
        "Right-click inside the table for more. Add a row above or below the one you're in…",
        "Mit einem Rechtsklick in die Tabelle gibt es mehr. Füg eine Zeile über oder unter deiner ein …",
        rows,
    ),
    Scene(
        "…or a column to the left or right of your cell.",
        "… oder eine Spalte links oder rechts von deiner Zelle.",
        columns,
    ),
    Scene(
        "Remove Row and Remove Column take away the one the cursor is in. And Ctrl+Z brings it back, if you change your mind.",
        "Zeile entfernen und Spalte entfernen nehmen die weg, in der die Schreibmarke steht. Und Strg+Z holt sie zurück, wenn du es dir anders überlegst.",
        remove,
        say="Remove Row and Remove Column take away the one the cursor is in. And Control Z brings it back, if you change your mind.",
    ),
    Scene(
        "A colon in the line under the titles aligns a column in the export: on the left for left, on both sides for center, on the right for right.",
        "Ein Doppelpunkt in der Zeile unter den Titeln richtet eine Spalte im Export aus: links für links, auf beiden Seiten für mittig, rechts für rechts.",
        align,
    ),
    Scene(
        "A table typed by hand already lines up on screen. If you want the file itself to look neat too, for other editors, Tidy Table adds the spaces for you.",
        "Eine von Hand getippte Tabelle steht auf dem Bildschirm schon gerade. Soll auch die Datei selbst ordentlich aussehen, für andere Editoren, fügt Tabelle ordnen die Leerzeichen für dich ein.",
        tidy,
    ),
    Scene(
        "In the export, tables get a calm look, with lines across, as in a book.",
        "Im Export bekommen Tabellen ein ruhiges Aussehen, mit waagerechten Linien, wie in einem Buch.",
        export,
    ),
    Scene(
        "And in your Markdown file, they stay plain text, readable in any editor.",
        "Und in deiner Markdown-Datei bleiben sie reiner Text, lesbar in jedem Editor.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="tables",
    title="Tables",
    topic="Write",
    summary="Insert a table, move between cells with Tab, add and remove rows and columns, align and tidy columns, and export them as in a book.",
    still=40,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
