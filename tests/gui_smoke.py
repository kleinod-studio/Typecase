"""Drives the real user interface automatically and checks the protection against data loss.

Needs a running desktop session. Run: python3 tests/gui_smoke.py
Uses a temporary folder and its own configuration; none of your data is touched."""

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# TYPECASE_CODE: test other code, e.g. the copy installed in the Flatpak (/app/share/typecase)
sys.path.insert(0, os.environ.get("TYPECASE_CODE", str(ROOT / "src")))

# Inside the home directory so the system trash works (it often doesn't on /tmp).
TMP = Path(tempfile.mkdtemp(prefix="typecase-smoke-", dir=Path.home() / ".cache"))
LIB = TMP / "lib"
LIB.mkdir()
(LIB / "a.md").write_text("Alpha", encoding="utf-8")
(LIB / "b.md").write_text("Beta", encoding="utf-8")
os.environ["XDG_CONFIG_HOME"] = str(TMP / "cfg")
os.environ["XDG_DATA_HOME"] = str(TMP / "data")  # imported templates
(TMP / "cfg" / "typecase").mkdir(parents=True)
# A tiny spelling dictionary of our own, so the test needs no installed language packs.
(TMP / "cfg" / "enchant" / "hunspell").mkdir(parents=True)
(TMP / "cfg" / "enchant" / "hunspell" / "de_DE.aff").write_text("SET UTF-8\n")
(TMP / "cfg" / "enchant" / "hunspell" / "de_DE.dic").write_text("5\nDas\nHaus\nsteht\nhier\nkurz\n")
(TMP / "cfg" / "typecase" / "config.json").write_text(f'{{"library_path": "{LIB}"}}')

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from typecase.main import TypecaseApplication, _fall_back_to_utf8  # noqa: E402

try:  # as on a real start: without matching locale data (Flatpak), use C.UTF-8 instead of ASCII
    import locale

    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    _fall_back_to_utf8()

failures = []
checked = []


def check(condition, message):
    checked.append(message)
    print(("ok    " if condition else "FAIL  "), message)
    if not condition:
        failures.append(message)


def text(ed):
    return ed.buffer.get_text(*ed.buffer.get_bounds(), True)


def wait_until(condition, timeout=3.0):
    """Waits (via 'yield from' inside the step generator) until condition() is true, for at most timeout seconds.
    More robust than fixed pauses when file notifications take longer on a busy machine."""
    waited = 0.0
    while not condition() and waited < timeout:
        yield 0.1
        waited += 0.1


def body(path):
    """Body of a file without its front matter (new sheets get a creation date in the front matter)."""
    from typecase.frontmatter import split

    return split(path.read_text(encoding="utf-8"))[1]


def read(name):
    return (LIB / name).read_text(encoding="utf-8")


def steps(win, app):
    ed = win.editor
    sel = win.selection

    sel.set_selected(0)
    check(ed.path == LIB / "a.md", "Selecting sheet a opens it")
    check(not win.list_view.get_single_click_activate(), "Hovering with the mouse does not select a sheet")
    check(text(ed) == "Alpha", "Text of a is shown in the editor")

    ed.buffer.insert_at_cursor(" eins")
    yield from wait_until(lambda: read("a.md") == " einsAlpha")
    check(read("a.md") == " einsAlpha" and text(ed) == " einsAlpha", "Autosave writes after a short pause")

    ed.buffer.insert_at_cursor("X")
    expected_a = text(ed)
    check(expected_a == " einsXAlpha", "Input appears in the editor")
    sel.set_selected(1)  # switch immediately, before the timer fires
    check(read("a.md") == expected_a, "Switching sheets saves unsaved input first")
    check(ed.path == LIB / "b.md", "Sheet b is open")
    check(not ed.buffer.props.can_undo, "Undo does not bring back another sheet")

    ed.buffer.insert_at_cursor("Y")
    ed.buffer.undo()
    check(text(ed) == "Beta", "Undo works within the sheet")
    ed.buffer.redo()
    check(text(ed) == "YBeta", "Redo works within the sheet")
    yield from wait_until(lambda: read("b.md") == "YBeta")
    check(read("b.md") == "YBeta", "Autosave after undo/redo")

    # Saving fails: folder is read-only
    ed.buffer.insert_at_cursor("Z")
    expected_b = text(ed)
    os.chmod(LIB, stat.S_IRUSR | stat.S_IXUSR)
    sel.set_selected(0)
    check(ed.path == LIB / "b.md", "Switching is refused when saving fails")
    check(text(ed) == expected_b and read("b.md") == "YBeta", "Input is kept when saving fails")
    check(sel.get_selected() == 1, "Selection jumps back to the open sheet")
    check(not [p for p in LIB.iterdir() if p.name.endswith(".tmp")], "No temporary files left behind")

    os.chmod(LIB, stat.S_IRWXU)
    sel.set_selected(0)
    check(ed.path == LIB / "a.md", "Switching works again once saving is possible")
    check(read("b.md") == expected_b, "Held-back input was saved afterwards")

    # --- New, rename, delete ---
    def select(path):
        win.selection.set_selected(win._index_of(path))
        if path.suffix == ".md" and ed.path != path:
            check(False, f"Selecting {path.name} opens it in the editor (open: {ed.path and ed.path.name})")

    win.lookup_action("new-sheet").activate(None)
    new_sheet = LIB / "Untitled.md"
    check(new_sheet.exists() and ed.path == new_sheet, "New sheet is created and opened")
    check(not (LIB / "a.md").read_text().startswith("Untitled"), "New sheet overwrites nothing")
    win.lookup_action("new-sheet").activate(None)
    check((LIB / "Untitled 2.md").exists(), "Second new sheet gets an unused name")

    win.lookup_action("new-group").activate(None)
    check((LIB / "New Group").is_dir(), "New group is created")
    win._do_rename(win._selected_node(), "Romane")
    check((LIB / "Romane").is_dir() and not (LIB / "New Group").exists(), "Group is renamed")
    check(win._selected_node().path == LIB / "Romane", "Renamed group stays selected")

    win.lookup_action("new-sheet").activate(None)  # a group is selected, so the sheet goes into it
    inner = LIB / "Romane" / "Untitled.md"
    check(inner.exists() and ed.path == inner, "New sheet goes into the selected group")
    ed.buffer.insert_at_cursor("Kapitel")
    win._do_rename(win._selected_node(), "Entwurf")
    inner = LIB / "Romane" / "Entwurf.md"
    check(inner.exists() and ed.path == inner, "Open sheet is renamed, editor follows")
    check(body(inner) == "Kapitel", "Unsaved input survives renaming")

    # Rename the group without selecting it (selecting a group opens the group view)
    win._do_rename(win.tree_model.get_item(win._index_of(LIB / "Romane")).get_item().node, "Bücher")
    inner = LIB / "Bücher" / "Entwurf.md"
    check(ed.path == inner, "Group containing the open sheet renamed, editor follows")
    ed.buffer.insert_at_cursor("!")
    check(ed.flush() and body(inner) in ("!Kapitel", "Kapitel!"), "After renaming, saving goes to the new location")

    select(LIB / "Untitled 2.md")
    win._do_rename(win._selected_node(), "a")
    check((LIB / "Untitled 2.md").exists() and read("a.md") != "", "Renaming to an existing name is refused")
    win._do_rename(win._selected_node(), "../böse")
    check((LIB / "Untitled 2.md").exists(), "Invalid name is refused")

    select(inner)
    win._do_delete(win._selected_node())
    check(not inner.exists() and ed.path is None, "Deleted open sheet disappears, editor closes")
    check(win.content_title.get_subtitle() == "", "No counter without an open sheet")
    select(LIB / "Bücher")
    win._do_delete(win._selected_node())
    check(not (LIB / "Bücher").exists(), "Group is deleted")
    check(win._index_of(LIB / "Bücher") is None, "Deleted group disappears from the sidebar")

    select(LIB / "a.md")
    check(ed.path == LIB / "a.md", "A sheet can be opened again afterwards")

    # Continuing lists in the editor (Enter key as on a real keyboard)
    from gi.repository import Gdk

    win.lookup_action("new-sheet").activate(None)
    list_sheet = ed.path
    enter = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))

    def press_enter():
        return enter.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType(0))

    ed.buffer.insert_at_cursor("1. Eins")
    yield 0.4  # the counter updates shortly after typing
    check(win.content_title.get_subtitle() == "1 word · 7 characters", "Counter shows words and characters")
    check(press_enter() and text(ed) == "1. Eins\n2. ", "Enter continues a numbered list")
    ed.buffer.insert_at_cursor("Zwei")
    press_enter()
    check(text(ed) == "1. Eins\n2. Zwei\n3. ", "Number increments")
    check(press_enter() and text(ed) == "1. Eins\n2. Zwei\n", "Empty list item ends the list")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n2. Zwei\n3. ", "Undo reverts ending the list in one step")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n2. Zwei", "Undo reverts the continuation in one step")
    ed.buffer.set_text("Absatz")
    ed.buffer.place_cursor(ed.buffer.get_end_iter())
    check(not press_enter(), "Plain text: Enter is left alone")

    # Renumbering and indenting
    def press(keyval, state=0):
        return enter.emit("key-pressed", keyval, 0, Gdk.ModifierType(state))

    def cursor_to(line, column):
        ed.buffer.place_cursor(ed.buffer.get_iter_at_line_offset(line, column)[1])

    ed.buffer.set_text("1. Eins\n2. Zwei\n3. Drei")
    cursor_to(0, 7)
    press(Gdk.KEY_Return)
    check(text(ed) == "1. Eins\n2. \n3. Zwei\n4. Drei", "Inserted item: following items are renumbered")
    ed.buffer.insert_at_cursor("Neu")
    check(press(Gdk.KEY_Tab) and text(ed) == "1. Eins\n    1. Neu\n2. Zwei\n3. Drei", "Tab indents and renumbers both levels")
    cursor = ed.buffer.get_iter_at_mark(ed.buffer.get_insert())
    check((cursor.get_line(), cursor.get_line_offset()) == (1, 10), "Cursor stays after the word")
    check(press(Gdk.KEY_ISO_Left_Tab, Gdk.ModifierType.SHIFT_MASK) and text(ed) == "1. Eins\n2. Neu\n3. Zwei\n4. Drei", "Shift+Tab outdents")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n    1. Neu\n2. Zwei\n3. Drei", "Undo reverts outdenting in one step")

    ed.buffer.set_text("- A")
    ed.buffer.place_cursor(ed.buffer.get_end_iter())
    press(Gdk.KEY_Return)
    press(Gdk.KEY_Tab)
    check(text(ed) == "- A\n    - ", "Tab indents an empty sub-item")
    press(Gdk.KEY_Return)
    check(text(ed) == "- A\n- ", "Enter on an empty sub-item outdents first")
    press(Gdk.KEY_Return)
    check(text(ed) == "- A\n", "Enter on an empty top-level item ends the list")
    ed.buffer.set_text("Normaler Text")
    check(not press(Gdk.KEY_Tab), "Tab outside of lists stays a normal tab")

    # Markdown styling while typing
    def tags_at(offset):
        return {t.props.name for t in ed.buffer.get_iter_at_offset(offset).get_tags()}

    ed.buffer.set_text("")
    ed.buffer.insert_at_cursor("# Titel\nEin **fettes** Wort")
    yield 0.2
    check("md-h1" in tags_at(3) and "md-syntax" in tags_at(0), "Heading becomes large, # is dimmed")
    check("md-bold" in tags_at(15) and "md-syntax" in tags_at(12), "Bold becomes bold, ** is dimmed")
    ed.buffer.insert(ed.buffer.get_iter_at_offset(14), " ")  # "** fettes**" is no longer bold
    yield 0.2
    check("md-bold" not in tags_at(16), "Styling disappears when the markup breaks")
    ed.buffer.set_text("```\n**kein fett**\n```\nnach dem Block **fett**")
    yield 0.2
    check("md-codeblock" in tags_at(6) and "md-bold" not in tags_at(6), "Code block: content styled as code, not bold")
    check("md-bold" in tags_at(40), "Styling resumes after the code block")

    # Code block: frame lines and syntax colors
    ed.buffer.set_text("Text\n```python\nreturn 42\n```\nnoch Text\n```\nohne Sprache\n```")
    yield 0.2
    check(ed.styler.code_blocks == [(1, 3, True), (5, 7, True)], "Code blocks are detected for the frame")
    colored = [t for t in ed.buffer.get_iter_at_offset(16).get_tags() if t.props.foreground_set and not (t.props.name or "").startswith("md-")]
    check(colored, "Code block with a language gets syntax colors")
    plain = [t for t in ed.buffer.get_iter_at_offset(43).get_tags() if t.props.foreground_set]
    check(not plain, "Code block without a language stays uncolored")
    ed.buffer.insert(ed.buffer.get_iter_at_offset(14), "x")  # ```pythonx: unknown language
    yield 0.2
    colored = [t for t in ed.buffer.get_iter_at_offset(17).get_tags() if t.props.foreground_set and not (t.props.name or "").startswith("md-")]
    check(not colored, "Colors disappear for an unknown language")

    # Formatting: bar and keyboard shortcuts
    def fmt(kind):
        win.lookup_action("format").activate(GLib.Variant.new_string(kind))

    def select_text(a, b):
        ed.buffer.select_range(ed.buffer.get_iter_at_offset(a), ed.buffer.get_iter_at_offset(b))

    ed.buffer.set_text("Ein Wort hier")
    select_text(4, 8)
    fmt("bold")
    check(text(ed) == "Ein **Wort** hier", "Bold wraps the selection")
    fmt("bold")
    check(text(ed) == "Ein Wort hier", "Applying bold again removes it")
    fmt("underline")
    check(text(ed) == "Ein <u>Wort</u> hier", "Underline inserts <u>…</u>")
    ed.buffer.undo()
    check(text(ed) == "Ein Wort hier", "Undo reverts a formatting change in one step")
    ed.buffer.place_cursor(ed.buffer.get_iter_at_offset(6))
    fmt("italic")
    check(text(ed) == "Ein *Wort* hier", "Without a selection, the word under the cursor is formatted")
    ed.buffer.set_text("Titel\nEins\nZwei")
    ed.buffer.place_cursor(ed.buffer.get_start_iter())
    fmt("h2")
    check(text(ed) == "## Titel\nEins\nZwei", "Heading puts ## in front of the line")
    select_text(9, 17)
    fmt("numbered")
    check(text(ed) == "## Titel\n1. Eins\n2. Zwei", "Numbered list applies to all selected lines")
    accels = {kind: app.get_accels_for_action(f"win.format::{kind}") for kind in ("bold", "italic", "underline", "link", "h1", "paragraph")}
    check(accels == {"bold": ["<Control>b"], "italic": ["<Control>i"], "underline": ["<Control>u"], "link": ["<Control>k"], "h1": ["<Control>1"], "paragraph": ["<Control>0"]}, "Formatting shortcuts are registered")
    bold_button = win.format_bar.get_first_child()
    ed.buffer.set_text("klick")
    select_text(0, 5)
    bold_button.emit("clicked")
    check(text(ed) == "**klick**", "Button in the bar applies formatting")
    check(win.format_revealer.get_reveal_child(), "Formatting bar is visible initially")
    from typecase import config as cfg2

    cfg2.update(format_bar=False)
    win.apply_settings()
    check(not win.format_revealer.get_reveal_child(), "Formatting bar can be turned off")
    cfg2.update(format_bar=True)
    win.apply_settings()

    # Mouse pointer and text cursor
    check(ed.view.get_cursor() is not None and ed.view.get_cursor().get_name() == "text", "Text pointer appears over the text area")
    check(ed.view.underline_caret and ed.view.has_css_class("underline-caret"), "Text cursor is an underline initially (GTK cursor hidden)")
    # Don't turn this off: without a visible cursor, the arrow keys only scroll instead of moving it.
    check(ed.view.get_cursor_visible(), "Arrow keys still move the text cursor (cursor-visible stays on)")
    cfg2.update(underline_caret=False)
    win.apply_settings()
    check(not ed.view.underline_caret and not ed.view.has_css_class("underline-caret"), "Can be turned off: then the normal text cursor is back")
    cfg2.update(underline_caret=True)
    win.apply_settings()
    ed.flush()
    select(LIB / "a.md")

    # Remembering state: a second window restores sheet, groups and size
    group = LIB / "Merken"
    group.mkdir()
    (group / "Blatt.md").write_text("gemerkt")
    win._reload()
    select(group)
    win.selection.get_selected_item().set_expanded(True)
    select(group / "Blatt.md")
    from typecase import config

    check(config.load().get("last_sheet") == "Merken/Blatt.md", "Last sheet is remembered")
    win._save_state()
    check(config.load().get("expanded_groups") == ["Merken"], "Expanded groups are remembered")
    saved = config.load()
    # Under tiling window managers a window counts as maximized; then only that is remembered.
    check(isinstance(saved.get("window_width"), int) or saved.get("window_maximized") is True, "Window size is remembered")
    from typecase.window import TypecaseWindow

    win.inspector_split.set_show_sidebar(True)
    win._save_state()
    second = TypecaseWindow(application=app)
    second.present()  # the window only grows past the breakpoint width once shown, which is when libadwaita used to reveal it
    yield 0.8
    check(not second.inspector_split.get_show_sidebar(), "Properties pane is always hidden at startup")
    second.inspector_split.set_collapsed(True)  # window starts narrow and then becomes wide (tiling, maximizing)
    second.inspector_split.set_collapsed(False)
    check(not second.inspector_split.get_show_sidebar(), "Widening the window does not reveal the properties pane")
    win.inspector_split.set_show_sidebar(False)
    check(second.editor.path == group / "Blatt.md", "Restart opens the last sheet")
    check(second._index_of(group / "Blatt.md") is not None, "Restart expands the group again")
    check(text(second.editor) == "gemerkt", "Restart loads the text of the last sheet")
    check(second.editor.flush(), "Second window has nothing unsaved")
    second.destroy()  # no close(): that would overwrite the test's window size and state
    check(app.get_windows() == [win], "Only the test window is still open")
    select(LIB / "a.md")

    # Context menu: a real right-click on the first row
    first_row = win.list_view.get_first_child().get_first_child()  # TreeExpander of the first row
    right_click = next(c for c in first_row.observe_controllers() if isinstance(c, Gtk.GestureClick))
    right_click.emit("pressed", 1, 20.0, 10.0)
    check(win.row_menu.is_visible(), "Right-click opens the context menu")
    win.row_menu.popdown()

    # Context menu: actions must be found from the popover
    while win.get_visible_dialog() is not None:
        win.get_visible_dialog().force_close()
    win.row_menu.popup()
    win.row_menu.activate_action("win.rename", None)
    check(win.get_visible_dialog() is not None, "Context menu: Rename opens the dialog")
    win.get_visible_dialog().force_close()
    win.row_menu.activate_action("win.delete", None)
    check(win.get_visible_dialog() is not None, "Context menu: Delete asks for confirmation")
    win.get_visible_dialog().force_close()
    win.row_menu.popdown()

    # --- External changes (sync tools, other editors) ---
    def conflict_copies():
        return sorted(p for p in LIB.iterdir() if "conflict" in p.name)

    def answer_dialog(response):
        dialog = win.get_visible_dialog()
        dialog.emit("response", response)
        dialog.force_close()

    sheet_b = LIB / "b.md"
    select(sheet_b)
    sheet_b.write_text("Von außen", encoding="utf-8")
    yield from wait_until(lambda: text(ed) == "Von außen")
    check(text(ed) == "Von außen" and win.get_visible_dialog() is None, "External change is reloaded without asking")

    ed.buffer.insert_at_cursor("Ich ")
    yield from wait_until(lambda: read("b.md") == text(ed))
    check(read("b.md") == text(ed) and not ed.in_conflict, "Our own save does not count as an external change")

    ed.buffer.insert_at_cursor("tippe")
    mine = text(ed)
    sheet_b.write_text("Fremd 1", encoding="utf-8")
    check(not ed.flush(), "Saving is refused when the file was changed externally")
    check(read("b.md") == "Fremd 1", "External change is not overwritten")
    check(ed.in_conflict and win.get_visible_dialog() is not None, "Conflict dialog appears")
    answer_dialog("mine")
    copies = conflict_copies()
    check(read("b.md") == mine and len(copies) == 1 and copies[0].read_text() == "Fremd 1", "Keep my version: the other one is saved as a copy next to it")
    check(win._index_of(copies[0]) is not None, "Conflict copy appears in the sidebar")
    yield 1.0
    check(not ed.in_conflict and win.get_visible_dialog() is None, "No new conflict after the decision")

    ed.buffer.insert_at_cursor("!")
    mine = text(ed)
    sheet_b.write_text("Fremd 2", encoding="utf-8")  # before autosave kicks in
    yield from wait_until(lambda: ed.in_conflict)
    check(ed.in_conflict and win.get_visible_dialog() is not None, "Conflict is detected even without saving")
    check(read("b.md") == "Fremd 2", "Autosave does not overwrite the external change")
    answer_dialog("theirs")
    check(text(ed) == "Fremd 2" and read("b.md") == "Fremd 2", "Load other version: the sheet shows it")
    check(any(p.read_text() == mine for p in conflict_copies()), "Load other version: mine is saved as a copy next to it")

    sheet_b.unlink()
    yield from wait_until(lambda: ed.path is None and win._index_of(sheet_b) is None)
    check(ed.path is None and win._index_of(sheet_b) is None, "Sheet deleted externally closes and disappears")

    select(LIB / "a.md")
    ed.buffer.insert_at_cursor("Rettung")
    mine = text(ed)
    (LIB / "a.md").unlink()
    yield from wait_until(lambda: (LIB / "a.md").exists())
    check(read("a.md") == mine and ed.path == LIB / "a.md", "Deleted externally with unsaved input: the text is saved again")

    (LIB / "Extern.md").write_text("x")
    (LIB / "ExternGruppe").mkdir()
    (LIB / "ExternGruppe" / "Innen.md").write_text("y")
    yield from wait_until(lambda: win._index_of(LIB / "Extern.md") is not None and win._index_of(LIB / "ExternGruppe") is not None)
    check(win._index_of(LIB / "Extern.md") is not None, "New sheet created externally appears")
    check(win._index_of(LIB / "ExternGruppe") is not None, "New group created externally appears")
    (LIB / "ExternGruppe" / "Zwei.md").write_text("z")
    yield from wait_until(lambda: str(LIB / "ExternGruppe" / "Zwei.md") in repr(win._tree_signature))
    win.tree_model.get_item(win._index_of(LIB / "ExternGruppe")).set_expanded(True)  # without selecting (opens the group view)
    check(win._index_of(LIB / "ExternGruppe" / "Zwei.md") is not None, "New groups are watched too")
    check(ed.path == LIB / "a.md", "Open sheet stays open when the tree refreshes")
    select(LIB / "a.md")

    # Full-text search
    (LIB / "ExternGruppe" / "Fabel.md").write_text("Vorher.\nEs war einmal ein Drache, der schlief.\n")
    (LIB / "Drachenkunde.md").write_text("Nichts hier.")
    yield from wait_until(lambda: win._index_of(LIB / "Drachenkunde.md") is not None)
    win.lookup_action("search").activate(None)
    check(win.search_bar.get_search_mode() and win.search_button.get_active(), "Ctrl+Shift+F opens search")
    win.search_entry.set_text("drache")
    yield from wait_until(lambda: win.sidebar_stack.get_visible_child_name() == "results")  # the search entry waits briefly
    rows = []
    row = win.results.get_row_at_index(0)
    while row is not None:
        rows.append(row.hit)
        row = win.results.get_row_at_index(len(rows))
    check(win.sidebar_stack.get_visible_child_name() == "results", "Results replace the folder tree")
    check([h.name for h in rows] == ["Drachenkunde", "Fabel"], "Name matches first, then text matches")
    ed.buffer.insert_at_cursor("Ein Drache auch hier ")  # unsaved, in the open sheet
    win.search_entry.set_text("drache ")
    win.search_entry.set_text("drache")
    yield 0.6
    names = []
    row = win.results.get_row_at_index(0)
    while row is not None:
        names.append(row.hit.name)
        row = win.results.get_row_at_index(len(names))
    check(ed.path.stem in names, "Search also finds unsaved text in the open sheet")
    win._open_hit(next(h for h in rows if h.name == "Fabel"))
    yield 0.3
    selected = ed.buffer.get_text(*ed.buffer.get_selection_bounds(), True) if ed.buffer.get_has_selection() else ""
    check(ed.path == LIB / "ExternGruppe" / "Fabel.md" and selected == "Drache", "Result opens the sheet and selects the match")
    win.search_entry.set_text("Einhorn")
    yield 0.6
    check(win.sidebar_stack.get_visible_child_name() == "no-results", "\"No matches\" is shown")
    win.search_entry.emit("stop-search")
    check(not win.search_bar.get_search_mode() and win.sidebar_stack.get_visible_child_name() == "library", "Escape closes search, folder tree comes back")
    check(win._index_of(LIB / "ExternGruppe" / "Fabel.md") == win.selection.get_selected(), "Opened sheet is selected in the tree")
    check(win.find_bar.get_search_mode() and win.find_bar.entry.get_text() == "Drache", "Result copies the search term into the sheet's find bar")
    win.find_bar.set_search_mode(False)

    # Find and replace within the sheet
    bar = win.find_bar
    ed.buffer.set_text("Rot und rot und ROT, dazu Blau.")
    ed.buffer.place_cursor(ed.buffer.get_start_iter())
    win.lookup_action("find").activate(None)
    check(bar.get_search_mode() and bar.context.get_highlight(), "Ctrl+F opens the find bar with highlighting")
    bar.entry.set_text("rot")
    yield from wait_until(lambda: bar.context.get_occurrences_count() == 3)

    def selection():
        bounds = ed.buffer.get_selection_bounds()
        return (bounds[0].get_offset(), bounds[1].get_offset()) if bounds else None

    check(bar.context.get_occurrences_count() == 3, "All three matches are counted (case-insensitive)")
    check(selection() == (0, 3) and bar.label.get_text() == "1 of 3", "First match is selected: 1 of 3")
    bar.find_next()
    check(selection() == (8, 11) and bar.label.get_text() == "2 of 3", "Next jumps to the second match")
    bar.find_previous()
    check(selection() == (0, 3), "Previous jumps to the first match")
    bar.find_previous()
    check(selection() == (16, 19), "Previous from the first match wraps around to the end")
    bar.replace_entry.set_text("Grün")
    bar.replace()
    check(text(ed) == "Rot und rot und Grün, dazu Blau.", "Replace replaces only the selected match")
    bar.replace_all()
    check(text(ed) == "Grün und Grün und Grün, dazu Blau.", "Replace All replaces the rest")
    ed.buffer.undo()
    check(text(ed) == "Rot und rot und Grün, dazu Blau.", "Undo reverts Replace All in one step")
    bar.entry.set_text("Gelb")
    yield 0.6
    check(bar.label.get_text() == "No matches" and bar.entry.has_css_class("error"), "\"No matches\" is shown")
    win.lookup_action("replace").activate(None)
    check(bar.replace_toggle.get_active(), "Ctrl+H opens the bar with replace")
    bar.entry.emit("stop-search")
    check(not bar.get_search_mode() and not bar.context.get_highlight(), "Escape closes the bar and removes the highlighting")
    select(LIB / "a.md")

    # Moving: drag and drop, "Move to …"
    def row_widget(path):
        child = win.list_view.get_first_child()
        while child is not None:
            expander = child.get_first_child()
            row = expander.get_list_row() if isinstance(expander, Gtk.TreeExpander) else None
            if row is not None and row.get_item().node.path == path:
                return expander
            child = child.get_next_sibling()
        return None

    def controller(widget, kind):
        return next(c for c in widget.observe_controllers() if isinstance(c, kind))

    select(LIB / "a.md")
    content = read("a.md")
    group_row = row_widget(LIB / "ExternGruppe")
    check(isinstance(controller(row_widget(LIB / "a.md"), Gtk.DragSource), Gtk.DragSource), "Entries can be dragged")
    # The middle of a group row means "into it"; the upper or lower edge would mean before or after it.
    dropped = controller(group_row, Gtk.DropTarget).emit("drop", str(LIB / "a.md"), 0.0, group_row.get_height() / 2)
    moved = LIB / "ExternGruppe" / "a.md"
    check(dropped and (LIB / "a.md").exists(), "The drop is accepted, but nothing moves before the drag has ended")
    yield from wait_until(lambda: moved.exists())
    check(dropped and moved.exists() and not (LIB / "a.md").exists(), "Dropping onto a group moves into it")
    check(ed.path == moved and moved.read_text() == content, "Open sheet moves along, content unchanged")
    check(win._index_of(moved) is not None and win.selection.get_selected() == win._index_of(moved), "Moved sheet is visible and selected")
    dropped = controller(row_widget(LIB / "Extern.md"), Gtk.DropTarget).emit("drop", str(moved), 0.0, 0.0)
    yield from wait_until(lambda: (LIB / "a.md").exists())
    check(dropped and (LIB / "a.md").exists() and ed.path == LIB / "a.md", "Dropping onto a sheet moves into its group")
    check(win._index_of(LIB / "a.md") == win._index_of(LIB / "Extern.md") - 1, "Dropped onto the upper half, it lands right before that sheet")
    check(not win._move(LIB / "ExternGruppe", LIB / "ExternGruppe"), "A group cannot be moved into itself")
    (LIB / "Merken" / "a.md").write_text("anderes")
    check(not win._move(LIB / "a.md", LIB / "Merken") and read("a.md") == content, "An item with the same name at the target is never overwritten")
    (LIB / "Merken" / "a.md").unlink()
    root_drop = controller(win.sidebar_stack.get_child_by_name("library"), Gtk.DropTarget)
    check(not root_drop.emit("drop", "Ein Stück Text aus dem Editor", 0.0, 0.0), "Unrelated dragged text is ignored")
    # A drag of our own: the move waits until the drag has ended (otherwise Wayland keeps the pointer)
    win._dragging = True
    check(root_drop.emit("drop", str(LIB / "ExternGruppe" / "Zwei.md"), 0.0, 0.0), "Dropping into the empty area is accepted")
    for _ in range(20):
        GLib.MainContext.default().iteration(False)
    check((LIB / "ExternGruppe" / "Zwei.md").exists(), "While the drag is still running, nothing is moved")
    win._on_drag_end(None, None, False)
    check((LIB / "Zwei.md").exists() and not (LIB / "ExternGruppe" / "Zwei.md").exists(), "When the drag ends, the entry is moved")

    select(LIB / "Extern.md")
    win.lookup_action("move").activate(None)
    dialog = win.get_visible_dialog()
    choice = dialog.get_extra_child()
    labels = [choice.get_model().get_string(i) for i in range(choice.get_model().get_n_items())]
    check("ExternGruppe" in labels and "Library (top level)" not in labels, "Move to … offers suitable targets")
    choice.set_selected(labels.index("ExternGruppe"))
    dialog.emit("response", "move")
    dialog.force_close()
    check((LIB / "ExternGruppe" / "Extern.md").exists() and ed.path == LIB / "ExternGruppe" / "Extern.md", "Move to … moves via the keyboard")
    select(LIB / "a.md")

    # Metadata: front matter hidden, properties pane on the right
    from typecase.frontmatter import parse, split
    from gi.repository import Adw

    meta = LIB / "Meta.md"
    meta.write_text("---\ntitle: Der Drache\ncssclass: wide   # fremdes Feld\n---\nEs war einmal.\n", encoding="utf-8")
    yield from wait_until(lambda: win._index_of(meta) is not None)
    select(meta)
    check(text(ed) == "Es war einmal.\n", "Front matter is hidden in the editor")
    check(win.inspector.title_row.get_text() == "Der Drache", "Properties pane shows the title from the front matter")
    check(win.content_title.get_subtitle().startswith("3 words"), "Word counter does not count the front matter")
    ed.buffer.insert(ed.buffer.get_end_iter(), "Ende.")
    ed.flush()
    check(meta.read_text().startswith("---\ntitle: Der Drache\ncssclass: wide   # fremdes Feld\n---\n") and body(meta) == "Es war einmal.\nEnde.", "Saving puts the front matter back in front, unchanged")

    inspector = win.inspector
    win.lookup_action("inspector").activate(None)
    check(win.inspector_split.get_show_sidebar(), "Properties pane can be shown")
    pages = [page.get_name() for page in inspector.stack.get_pages()]
    check(pages == ["details", "goal", "notes"], f"Properties pane has the tabs Details, Goal and Notes ({pages})")
    inspector.stack.set_visible_child_name("goal")
    from typecase import config as cfg_tabs

    check(cfg_tabs.load().get("inspector_page") == "goal", "The last open tab is remembered")
    inspector.stack.set_visible_child_name("details")
    inspector.author_row.set_text("Anna")
    inspector.keywords_row.set_text("Roman, Entwurf ,")
    inspector.status_row.set_selected(1)
    ed.flush()
    data = parse(split(meta.read_text())[0])
    check(data.get("author") == "Anna" and data.get("keywords") == ["Roman", "Entwurf"] and data.get("status") == "draft", "Input in the properties pane ends up in the front matter")
    check(data.get("cssclass") == "wide" and "# fremdes Feld" in meta.read_text(), "Unknown fields are preserved")
    inspector.author_row.set_text("")
    ed.flush()
    check("author" not in parse(split(meta.read_text())[0]), "Cleared field disappears from the front matter")
    check(not ed.buffer.props.can_undo or text(ed) == "Es war einmal.\nEnde.", "Text is unaffected by metadata changes")

    meta.write_text(meta.read_text().replace("title: Der Drache", "title: Fridolin"), encoding="utf-8")
    yield from wait_until(lambda: inspector.title_row.get_text() == "Fridolin")
    check(inspector.title_row.get_text() == "Fridolin" and not ed.in_conflict, "External change to the front matter is picked up")
    check(text(ed) == "Es war einmal.\nEnde.", "Text stays unchanged meanwhile")

    # Writing goal
    check(not inspector.goal_row.get_enable_expansion() and not inspector.goal_view.get_visible(), "No ring without a writing goal")
    inspector.goal_row.set_enable_expansion(True)
    ed.flush()
    check(parse(split(meta.read_text())[0]).get("goal") == "1000", "Enabled writing goal ends up in the front matter (default 1000)")
    inspector.goal_spin.set_value(8)
    ed.flush()
    check(parse(split(meta.read_text())[0]).get("goal") == "8", "Changed word goal is saved")
    check(win.content_title.get_subtitle().startswith("4 of 8 words"), "Header bar shows the goal")
    meta_rings = [r for r in win._row_rings if r.path == meta and r.get_mapped()]

    def ring_target(ring):
        # Target value of the animation: in the background the window's frame clock pauses, so the ring stops moving.
        animation = ring._animation
        return animation.get_value_to() if animation.get_state() == Adw.AnimationState.PLAYING else ring.value

    check(
        len(meta_rings) == 1 and meta_rings[0].get_visible() and abs(ring_target(meta_rings[0]) - 0.5) < 0.01,
        "Library shows a progress ring next to the sheet",
    )
    check(not any(r.get_visible() for r in win._row_rings if r.path is not None and r.path != meta), "Sheets without a goal have no ring")
    check(inspector.goal_view.get_visible() and "50%" in inspector.goal_view.status_label.get_label(), "Ring shows the progress")
    check(not win.goal_revealer.get_reveal_child(), "Goal card is hidden while the properties pane is open")
    win.inspector_split.set_show_sidebar(False)
    check(win.goal_revealer.get_reveal_child() and win.goal_badge.label.get_label() == "4 / 8", "Goal card at the bottom right when the properties pane is closed")
    yield from wait_until(lambda: win.goal_revealer.get_child_revealed())
    area = win.goal_revealer.get_parent()
    bounds = win.goal_revealer.compute_bounds(area)[1]
    check(
        bounds.get_x() + bounds.get_width() > area.get_width() - 40 and bounds.get_y() + bounds.get_height() > area.get_height() - 200,
        "Goal card sits in the bottom-right corner",
    )
    format_bounds = win.format_revealer.compute_bounds(area)[1]
    check(not bounds.intersection(format_bounds)[0], "Goal card does not cover the formatting bar")
    win.goal_badge.emit("clicked")
    check(win.inspector_split.get_show_sidebar(), "Clicking the goal card opens the properties pane")
    ed.buffer.insert(ed.buffer.get_end_iter(), " Und dann kam der Drache.")
    ed.flush()
    yield from wait_until(lambda: inspector.goal_view.ring.has_css_class("success"))
    check(inspector.goal_view.ring.has_css_class("success") and inspector.goal_view.status_label.get_label() == "Goal reached", "Reached goal turns green")
    inspector.goal_row.set_enable_expansion(False)
    ed.flush()
    check("goal" not in parse(split(meta.read_text())[0]) and not inspector.goal_view.get_visible(), "Disabled goal disappears from the front matter")
    win.inspector_split.set_show_sidebar(False)
    check(not win.goal_revealer.get_reveal_child() and not win.goal_revealer.get_can_target(), "No goal card without a goal (and no invisible click area)")
    check(not any(r.get_visible() for r in win._row_rings if r.path == meta), "Without a goal the ring disappears from the library")
    check(all(r.get_accessible_role() == Gtk.AccessibleRole.PROGRESS_BAR for r in win._row_rings), "Screen readers know the rings as progress bars")
    win.inspector_split.set_show_sidebar(True)
    check(not win.content_title.get_subtitle().startswith("9 of"), "Header bar without a goal")
    ed.buffer.set_text("Es war einmal.\nEnde.")
    ed.flush()

    # Notes and attachments (third tab of the properties pane)
    inspector.stack.set_visible_child_name("notes")
    notes = inspector.notes_view.get_buffer()
    notes.set_text("Drache braucht einen Namen.\n\nIdee: Fridolin")
    check(ed.flush() and parse(split(meta.read_text())[0])["notes"] == "Drache braucht einen Namen.\n\nIdee: Fridolin", "Notes are saved as a block in the front matter")
    check(body(meta) == "Es war einmal.\nEnde." and "Fridolin" not in text(ed), "Notes stay out of the text")
    check("cssclass: wide   # fremdes Feld" in meta.read_text(), "Other fields stay untouched when notes are written")
    select(LIB / "a.md")
    check(notes.get_text(*notes.get_bounds(), False) == "", "Another sheet shows its own (empty) notes")
    select(meta)
    check("Fridolin" in notes.get_text(*notes.get_bounds(), False), "The notes come back with their sheet")
    notes.set_text("")
    check(ed.flush() and "notes" not in parse(split(meta.read_text())[0]), "Empty notes disappear from the front matter")

    win.lookup_action("new-sheet").activate(None)
    sheet = ed.path
    photo = TMP / "Foto.jpg"
    photo.write_bytes(b"jpeg")
    inspector._add_files([Gio.File.new_for_path(str(photo)), Gio.File.new_for_path(str(photo))])
    folder = sheet.parent / ".attachments" / sheet.stem
    check(sorted(p.name for p in folder.iterdir()) == ["Foto 2.jpg", "Foto.jpg"] and photo.exists(), "Attachments are copied next to the sheet, never overwritten")
    check([r.get_title() for r in inspector._attachment_rows] == ["Foto.jpg", "Foto 2.jpg"], "The properties pane lists the attachments")
    check(win._index_of(sheet.parent / ".attachments") is None, "The attachments folder does not show up in the library")
    win._do_rename(win._selected_node(), "Beilage")
    sheet = sheet.with_name("Beilage.md")
    check((sheet.parent / ".attachments" / "Beilage" / "Foto.jpg").exists() and not folder.exists(), "Attachments follow a renamed sheet")
    inspector._remove_attachment("Foto 2.jpg")
    check([r.get_title() for r in inspector._attachment_rows] == ["Foto.jpg"], "Removing an attachment moves it to the trash")
    win._do_delete(win._selected_node())
    check(not sheet.exists() and not (sheet.parent / ".attachments").exists(), "Deleting a sheet takes its attachments along into the trash")
    select(meta)

    # Spell checking (libspelling, with the test dictionary)
    from typecase import spelling

    if not spelling.available():
        print("skip   Spell checking: libspelling is not installed")
    else:
        spell_sheet = LIB / "Rechtschreibung.md"
        spell_sheet.write_text("---\nlang: de-DE\n---\nDas Hauss steht `Codewrt` hier: https://kleinod.studio\n", encoding="utf-8")
        yield from wait_until(lambda: win._index_of(spell_sheet) is not None)
        select(spell_sheet)
        tag = ed.spell_adapter.get_tag()

        def misspelled():
            found, it = [], ed.buffer.get_start_iter()
            while not it.is_end():
                if it.starts_tag(tag):
                    end = it.copy()
                    end.forward_to_tag_toggle(tag)
                    found.append(ed.buffer.get_text(it, end, False))
                it.forward_char()
            return found

        yield from wait_until(lambda: misspelled() != [])
        check(misspelled() == ["Hauss"], f"Misspelled words are marked, code and web addresses are skipped ({misspelled()})")
        check(win.lookup_action("spell-check").get_state().get_boolean(), "Spell checking is on in the editor")
        win.lookup_action("spell-check").activate(None)
        check(not ed.spell_adapter.get_enabled() and config.load().get("spell_check") is False, "F7 switches it off and remembers that")
        win.lookup_action("spell-check").activate(None)
        check(ed.spell_adapter.get_enabled(), "F7 switches it on again")
        ed.set_metadata({"lang": "fr-FR"})
        check(not ed.spell_adapter.get_enabled() and "fr-FR" in win._missing_dictionaries, "Without a dictionary for the sheet's language, a notice appears once")
        ed.set_metadata({"lang": "de-AT"})
        check(ed.spell_adapter.get_enabled() and ed.spell_adapter.get_checker().get_language() == "de_DE", "Another variant of the language is used if needed")
        ed.flush()
        win.lookup_action("focus-mode").activate(None)
        check(not ed.spell_adapter.get_enabled(), "Focus mode checks no spelling unless switched on")
        win.lookup_action("focus-mode").activate(None)
        yield from wait_until(lambda: not win.is_fullscreen())
        check(ed.spell_adapter.get_enabled(), "Back in the editor, spelling is checked again")
        select(meta)

    # Export
    from typecase import export, export_templates
    from typecase.export_dialog import ExportDialog, pdf_available, run_export

    check(win.lookup_action("export").get_enabled(), "Export is available with an open sheet")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(isinstance(dialog, ExportDialog) and dialog.template_row.get_model().get_n_items() >= 1, "Export dialog offers format and template")
    dialog.format_row.set_selected(export.FORMATS.index("pdf"))
    check(dialog.export_button.get_sensitive() == pdf_available() and bool(dialog.format_row.get_subtitle()) != pdf_available(), "Without WebKitGTK, the dialog says so before exporting a PDF")
    dialog.force_close()
    if export.pandoc_path() is None:
        print("      (Pandoc is missing here; export files are only checked in the Flatpak)")
    else:
        results = {}
        for fmt in export.FORMATS:
            run_export(
                "---\ntitle: Der Drache\n---\nEs war eine <u>Höhle</u>.\n", fmt, export_templates.available(None)[0],
                TMP / ("export" + export.EXTENSIONS[fmt]), meta, "Der Drache", {"lang": "de-DE"},
                lambda path, error, fmt=fmt: results.__setitem__(fmt, (path, error)),
            )
        yield from wait_until(lambda: len(results) == 3, timeout=30)
        check(results["docx"][1] is None and results["html"][1] is None, f"Export without errors: {results}")
        if pdf_available():
            check(results["pdf"][1] is None and (TMP / "export.pdf").read_bytes()[:4] == b"%PDF", "PDF is created")
        else:
            check(results["pdf"][1] == "PDF export needs WebKitGTK 6.0." and not (TMP / "export.pdf").exists(), "Without WebKit, a clear message instead of a PDF")
        check((TMP / "export.docx").read_bytes()[:2] == b"PK", "DOCX is created")
        check("Der Drache" in (TMP / "export.html").read_text(encoding="utf-8"), "HTML contains the title")
        check(not [p for p in TMP.iterdir() if "typecase-tmp" in p.name], "No partial export files left behind")

    # Manual order of sheets and exporting a whole group
    from typecase.library import FOLDER_FILE, Node as LibNode, scan

    book = LIB / "Book"
    book.mkdir()
    for number in (10, 2, 1):
        (book / f"Chapter {number}.md").write_text(f"# Chapter {number}\n\nText {number}.\n", encoding="utf-8")
    yield from wait_until(lambda: win._index_of(book) is not None)
    win._reload(expand={book})
    order = lambda: [node.path.name for node in scan(book)]  # noqa: E731
    check(order() == ["Chapter 1.md", "Chapter 10.md", "Chapter 2.md"], "Without a manual order, sheets are alphabetical")
    win._place(book / "Chapter 2.md", book / "Chapter 1.md", after=True)
    check(order() == ["Chapter 1.md", "Chapter 2.md", "Chapter 10.md"], "Dropping between rows reorders the sheets")
    check((book / FOLDER_FILE).is_file(), "The order is stored in a hidden file in the group")
    check(win._index_of(book / "Chapter 2.md") < win._index_of(book / "Chapter 10.md"), "The library shows the new order")
    select(book / "Chapter 10.md")
    win.lookup_action("move-up").activate(None)
    check(order() == ["Chapter 1.md", "Chapter 10.md", "Chapter 2.md"], "Move Up (Alt+Up) moves the sheet one place up")
    win.lookup_action("move-down").activate(None)
    check(order() == ["Chapter 1.md", "Chapter 2.md", "Chapter 10.md"], "Move Down (Alt+Down) moves it back")
    win._do_rename(LibNode("Chapter 1", book / "Chapter 1.md"), "Prologue")
    check(order()[0] == "Prologue.md", "A renamed sheet keeps its place")
    select(book)
    win.lookup_action("export-selection").activate(None)
    dialog = win.get_visible_dialog()
    check(isinstance(dialog, ExportDialog) and dialog.title_row.get_visible() and dialog.title_row.get_text() == "Book", "Exporting a group asks for a title (the group name)")
    combined = dialog._text
    dialog.force_close()
    check(combined.index("Chapter 1") < combined.index("Chapter 2") < combined.index("Chapter 10"), "The group is combined in the manual order")
    if export.pandoc_path() is not None:
        results = {}
        run_export(export.with_title(combined, "Book"), "html", export_templates.available(None)[0], TMP / "book.html", book / "Book.md", "Book", {}, lambda path, error: results.__setitem__("html", error))
        yield from wait_until(lambda: "html" in results, timeout=15)
        html = (TMP / "book.html").read_text(encoding="utf-8") if results.get("html") is None else ""
        check(html.find(">Book<") < html.find("Chapter 1") < html.find("Chapter 10") and html.find(">Book<") > 0, "The exported group has the title and all chapters in order")

    # Group view: all sheets of the selected group one after another, each saved to its own file
    gv = win.group_view
    inspector_shown, sidebar_shown = win.inspector_split.get_show_sidebar(), win.split.get_show_sidebar()
    # In a narrow window the sidebars would cover the text and take the focus.
    win.inspector_split.set_show_sidebar(False)
    if win.split.get_collapsed():
        win.split.set_show_sidebar(False)
    chapters = [book / "Prologue.md", book / "Chapter 2.md", book / "Chapter 10.md"]
    check(gv.group == book and win.content_stack.get_visible_child_name() == "group", "Selecting a group shows the group view")
    check(gv.paths() == chapters and ed.path is None, "The group view shows the sheets in the manual order; no sheet is open twice")
    check(win.content_title.get_title() == "Book" and "12 words" in win.content_title.get_subtitle(), "Title and counts belong to the group")
    first, second, third = gv.editors
    yield from wait_until(lambda: first.view.get_height() > 0)
    first.buffer.place_cursor(first.buffer.get_end_iter())
    first.view.grab_focus()
    gv._on_key_pressed(None, Gdk.KEY_Down, 0, 0, first)
    check(gv.active is second and second.buffer.get_iter_at_mark(second.buffer.get_insert()).is_start(), "Down on the last line continues in the next sheet")
    gv._on_key_pressed(None, Gdk.KEY_Up, 0, 0, second)
    check(gv.active is first and first.buffer.get_iter_at_mark(first.buffer.get_insert()).is_end(), "Up on the first line goes back to the end of the previous sheet")
    first.buffer.place_cursor(first.buffer.get_start_iter())
    check(not gv._on_key_pressed(None, Gdk.KEY_Down, 0, 0, first), "Down inside a sheet stays in the sheet")

    start = second.buffer.get_iter_at_offset(text(second).index("Text 2"))
    end = start.copy()
    end.forward_chars(4)
    second.buffer.select_range(start, end)
    second.view.grab_focus()
    win.lookup_action("format").activate(GLib.Variant.new_string("bold"))
    check("**Text** 2" in text(second) and "**" not in text(first), "The formatting bar acts on the section with the caret")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(isinstance(dialog, ExportDialog) and dialog.title_row.get_visible(), "Export in the group view exports the whole group")
    dialog.force_close()
    check("**Text** 2" in body(book / "Chapter 2.md"), "Before exporting, the group view saves every sheet")

    (book / "Chapter 10.md").write_text("# Chapter 10\n\nVon außen.\n", encoding="utf-8")
    yield from wait_until(lambda: "Von außen" in text(third))
    check("Von außen" in text(third) and win.get_visible_dialog() is None, "External change reloads only that section")
    third.buffer.insert(third.buffer.get_end_iter(), "Meins")
    mine = text(third)
    (book / "Chapter 10.md").write_text("Fremd im Buch", encoding="utf-8")
    yield from wait_until(lambda: third.in_conflict)
    check(third.in_conflict and not win._flush(), "Conflict in a section: switching away is refused")
    answer_dialog("mine")
    copies = [p for p in book.iterdir() if "conflict" in p.name]
    check(body(book / "Chapter 10.md") == mine and any(p.read_text() == "Fremd im Buch" for p in copies), "Conflict in a section: both versions are kept")
    for copy in copies:
        copy.unlink()
    yield from wait_until(lambda: gv.paths() == chapters)

    (book / "Epilogue.md").write_text("Ende.", encoding="utf-8")
    yield from wait_until(lambda: book / "Epilogue.md" in gv.paths())
    check(gv.paths()[-1] == book / "Epilogue.md", "A sheet added to the group appears at the end of the group view")
    second = gv.editor_for(book / "Chapter 2.md")
    second.buffer.insert(second.buffer.get_end_iter(), "Ungesichert")
    win._place(book / "Chapter 10.md", book / "Prologue.md", after=False)
    check("Ungesichert" in body(book / "Chapter 2.md"), "Reordering saves unsaved text in the group view first")
    check(gv.paths()[0] == book / "Chapter 10.md", "The group view follows the new order")
    second = gv.editor_for(book / "Chapter 2.md")
    second.buffer.insert(second.buffer.get_end_iter(), " Weiter")
    win._do_rename(LibNode("Book", book, []), "Buch")
    book = LIB / "Buch"
    check(gv.group == book and all(p.parent == book for p in gv.paths()), "Renaming the shown group keeps the group view open")
    check(body(book / "Chapter 2.md").endswith("Ungesichert Weiter"), "Renaming the group saves unsaved text first")

    gv.editor_for(book / "Epilogue.md").buffer.insert_at_cursor("Zuletzt ")
    win._open_sheet(book / "Prologue.md")
    check(ed.path == book / "Prologue.md" and gv.group is None and win.content_stack.get_visible_child_name() == "sheet", "The header of a section opens that sheet on its own")
    check(body(book / "Epilogue.md") == "Zuletzt Ende.", "Leaving the group view saves every sheet")
    select(book)
    check(gv.group == book and ed.path is None, "Back to the group view")
    gv.editor_for(book / "Epilogue.md").buffer.insert_at_cursor("Ganz ")
    select(meta)
    check(ed.path == meta and gv.group is None and body(book / "Epilogue.md") == "Ganz Zuletzt Ende.", "Selecting a sheet leaves the group view and saves it")
    win.lookup_action("export").activate(None)  # a single sheet: no switch for subgroups
    dialog = win.get_visible_dialog()
    check(not dialog.page_break_row.get_visible(), "Exporting a sheet offers no page breaks for subgroups")
    dialog.force_close()
    (book / "Appendix").mkdir()
    (book / "Appendix" / "Sources.md").write_text("Quellen.", encoding="utf-8")
    yield from wait_until(lambda: win._index_of(book / "Appendix") is not None)
    select(book)
    headings = []
    child = gv._box.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.Label) and "title-3" in child.get_css_classes() and child.get_accessible_role() == Gtk.AccessibleRole.HEADING:
            headings.append(child.get_label())
        child = child.get_next_sibling()
    check(headings == ["Buch", "Appendix"], f"The group view marks where each subgroup starts ({headings})")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(dialog.page_break_row.get_visible() and dialog.page_break_row.get_active(), "A group with subgroups offers a new page for each one")
    check(export.PAGE_BREAK in dialog._page_break_text and export.PAGE_BREAK not in dialog._text, "Only the page-break version contains page breaks")
    dialog.force_close()
    select(meta)
    win.inspector_split.set_show_sidebar(inspector_shown)
    win.split.set_show_sidebar(sidebar_shown)

    # Duplicating a sheet and a group (context menu "Duplicate")
    ed.buffer.insert_at_cursor("Neu: ")
    win.lookup_action("duplicate").activate(None)
    meta_copy = LIB / "Meta (Copy).md"
    check(ed.path == meta_copy and meta_copy.read_text() == meta.read_text() and body(meta).startswith("Neu: "), "Duplicating a sheet saves it first and opens the copy")
    check(win._index_of(meta_copy) == win._index_of(meta) + 1, "The copy appears right below the original")
    select(book)
    win.lookup_action("duplicate").activate(None)
    book_copy = LIB / "Buch (Copy)"
    check(gv.group == book_copy and [p.name for p in gv.paths()] == [p.name for p in win._group_sheets(book)], "Duplicating a group copies all of its sheets and shows the copy")
    for path in (meta_copy, book_copy):
        win._do_delete(win.tree_model.get_item(win._index_of(path)).get_item().node)
    select(meta)

    # Custom templates: save as a file, import, choose in the export dialog, remove
    from typecase import config as tc_config
    from typecase.preferences import PreferencesDialog

    check(tc_config.TEMPLATES_DIR.is_relative_to(TMP), "Test uses its own templates folder")
    prefs = PreferencesDialog(win.apply_settings)
    page = prefs.templates_page
    check(len(page._rows) == 1, "Preferences show the bundled template")
    template_file = TMP / ("Mein Brief" + export_templates.EXTENSION)
    export_templates.pack(export_templates.available(None)[0], template_file)
    check(template_file.is_file(), "Template can be saved as a file")
    page._install(template_file)
    check(len(page._rows) == 2 and (tc_config.TEMPLATES_DIR / "mein-brief").is_dir(), "Imported template appears in the preferences")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(dialog.template_row.get_model().get_n_items() == 2, "Export dialog offers the imported template")
    dialog.template_row.set_selected(1)
    chosen = dialog._templates[1]
    dialog.force_close()
    if export.pandoc_path() is not None:
        results = {}
        run_export("Text.\n", "html", chosen, TMP / "eigen.html", meta, None, {}, lambda path, error: results.__setitem__("html", error))
        yield from wait_until(lambda: "html" in results, timeout=15)
        check(results.get("html") is None and (TMP / "eigen.html").is_file(), "Export with the imported template")
    page._remove(chosen)
    check(len(page._rows) == 1 and not (tc_config.TEMPLATES_DIR / "mein-brief").exists(), "Removed template goes to the trash")

    from typecase import config as cfg

    cfg.update(default_author="Sascha")
    win.apply_settings()
    check(inspector.author_default.get_label() == "Sascha" and inspector.author_default.get_visible(), "Default author appears as a placeholder")
    check("author" not in parse(split(meta.read_text())[0]), "Default is not written to the file")

    editor_keys = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))
    before = text(ed)
    check(editor_keys.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType.ALT_MASK) and not win.inspector_split.get_show_sidebar(), "Alt+Enter toggles the properties pane")
    check(text(ed) == before, "Alt+Enter does not insert a line break")

    # Keyword filter
    lyrik = LIB / "Merken" / "Lyrik.md"
    lyrik.write_text("---\nkeywords: [Gedicht]\n---\nVerse.\n", encoding="utf-8")
    yield from wait_until(lambda: str(lyrik) in repr(win._tree_signature))
    win._fill_keyword_list()
    offered = []
    row = win.keyword_list.get_row_at_index(0)
    while row is not None:
        offered.append(row.keyword)
        row = win.keyword_list.get_row_at_index(len(offered))
    check(offered == [None, "Entwurf", "Gedicht", "Roman"], "Filter offers all keywords (plus All Sheets)")
    win.set_keyword_filter("roman")
    check(win._index_of(meta) is not None and win._index_of(LIB / "a.md") is None, "Filter shows only matching sheets (case-insensitive)")
    check(win.filter_banner.get_revealed(), "Banner shows the active filter")
    win.set_keyword_filter("Gedicht")
    check(win._index_of(lyrik) is not None and win._index_of(meta) is None, "Matches inside groups are shown expanded")
    meta.write_text(meta.read_text().replace("keywords: [Roman, Entwurf]", "keywords: [Roman, Entwurf, Gedicht]"), encoding="utf-8")
    yield from wait_until(lambda: win._index_of(meta) is not None)
    check(win._index_of(meta) is not None, "Keyword added externally appears in the filtered tree")
    win.filter_banner.emit("button-clicked")
    check(not win.filter_banner.get_revealed() and win._index_of(LIB / "a.md") is not None, "Clearing the filter shows all sheets again")
    win.set_keyword_filter("Gedicht")

    win.lookup_action("new-sheet").activate(None)
    check(not win.filter_banner.get_revealed() and win._index_of(ed.path) is not None, "New sheet clears the filter and is visible")
    created = parse(split(ed.path.read_text())[0]).get("created", "")
    now = GLib.DateTime.new_now_local()
    check(created.startswith(now.format("%Y-%m-%dT")) and len(created) == 16 and text(ed) == "", "New sheet gets a creation date and time in the front matter")
    from typecase.inspector import format_created

    check(inspector.created_row.get_subtitle() == format_created(created) and ":" in inspector.created_row.get_subtitle(), "Properties pane shows the creation date and time")
    check(isinstance(inspector.created_row, Adw.ActionRow) and not isinstance(inspector.created_row, Adw.EntryRow), "Created is not editable")
    check(not isinstance(inspector.modified_row, Adw.EntryRow), "Last modified is not editable")
    select(LIB / "a.md")

    # Focus mode: Ctrl+Shift+Enter in the text, header bar at the top edge, Escape
    from gi.repository import Gdk

    editor_keys = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))
    ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
    text_before = text(ed)
    check(ed.path and ed.path.name == "a.md", "Checkpoint F2 before focus mode: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    win.inspector_split.set_show_sidebar(True)
    check(editor_keys.emit("key-pressed", Gdk.KEY_Return, 0, ctrl_shift), "Ctrl+Shift+Enter is intercepted in the text")
    check(not win.inspector_split.get_show_sidebar(), "Focus mode hides the properties pane")
    check(win.focus_mode and not win.split.get_show_sidebar(), "Focus mode hides the sidebar")
    check(not win.content_view.get_reveal_top_bars(), "Focus mode hides the header bar")
    check(win.format_revealer.get_reveal_child(), "Formatting bar is present in focus mode too")
    from typecase import config as cfg3

    cfg3.update(focus_format_bar=False)
    win.apply_settings()
    check(not win.format_revealer.get_reveal_child(), "The bar can be hidden in focus mode")
    bottom = win.content_view.get_height()
    win._on_content_motion(None, 200, bottom - 2)
    check(win.format_revealer.get_reveal_child(), "Mouse at the bottom edge reveals the hidden bar")
    win._on_content_motion(None, 200, bottom - 400)
    check(not win.format_revealer.get_reveal_child(), "Moving the mouse away from the edge hides it again")
    cfg3.update(focus_format_bar=True, focus_typewriter=False, focus_dim=False)
    win.apply_settings()
    check(not ed.view.typewriter and not ed.view.dim_others, "Focus aids can be turned off")
    cfg3.update(focus_typewriter=True, focus_dim=True)
    win.apply_settings()
    check(text(ed) == text_before, "The shortcut inserts no line break")
    yield 1.5
    check(win.is_fullscreen(), "Focus mode switches to fullscreen")
    check(ed.view.typewriter and ed.view.dim_others, "Focus aids are on in focus mode")
    # Compare with the height the margins were computed for: while the window grows into fullscreen,
    # the current height can briefly be ahead of the last layout pass.
    ed.view.queue_resize()
    yield from wait_until(lambda: ed.view.get_top_margin() == getattr(ed.view, "allocated_height", -2) // 2, timeout=6)
    check(
        ed.view.get_top_margin() == getattr(ed.view, "allocated_height", -2) // 2 > 0,
        "Typewriter mode adds half the height as top margin",
    )
    check(not win.inspector_split.get_show_sidebar() and not win.split.get_show_sidebar(), "Sidebars stay hidden in fullscreen")
    check(ed.path and ed.path.name == "a.md", "Checkpoint F3 in focus mode: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    margin = ed.view.get_left_margin()
    check(margin > 100 and margin == ed.view.get_right_margin(), "Text area is centered with limited width")
    win._on_content_motion(None, 200, 2)
    check(win.content_view.get_reveal_top_bars(), "Mouse at the top edge reveals the header bar")
    win._on_content_motion(None, 200, 400)
    check(not win.content_view.get_reveal_top_bars(), "Moving the mouse away from the edge hides it again")
    window_keys = next(
        c for c in win.observe_controllers()
        if isinstance(c, Gtk.EventControllerKey) and c.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE
    )
    check(window_keys.emit("key-pressed", Gdk.KEY_Escape, 0, Gdk.ModifierType(0)), "Escape is intercepted")
    check(not win.focus_mode and win.split.get_show_sidebar() and win.content_view.get_reveal_top_bars(), "Escape leaves focus mode and restores everything")
    check(win.inspector_split.get_show_sidebar(), "Properties pane comes back after focus mode")
    check(win.format_revealer.get_reveal_child(), "Formatting bar comes back after focus mode")
    win.inspector_split.set_show_sidebar(False)
    check(ed.path and ed.path.name == "a.md", "Checkpoint F4 after Escape: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    yield 1.5
    check(not win.is_fullscreen(), "Fullscreen ends with focus mode")
    check(not ed.view.typewriter and not ed.view.dim_others, "No focus aids outside of focus mode")
    yield from wait_until(lambda: ed.view.get_top_margin() == 48)
    check(ed.view.get_top_margin() == 48, "Normal margins come back")
    check(ed.path and ed.path.name == "a.md", "Checkpoint F5 fullscreen off: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    check(not window_keys.emit("key-pressed", Gdk.KEY_Escape, 0, Gdk.ModifierType(0)), "Escape outside of focus mode is left alone")

    # Preferences
    from gi.repository import Adw
    from typecase import config

    win.lookup_action("preferences").activate(None)
    prefs = win.get_visible_dialog()
    check(ed.path and ed.path.name == "a.md", "Checkpoint preferences opened: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    check(prefs is not None and type(prefs).__name__ == "PreferencesDialog", "Ctrl+Comma opens the preferences")
    check(app.get_accels_for_action("win.preferences") == ["<Control>comma"], "Ctrl+Comma is registered")
    prefs.editor_page.font_size.set_value(22)
    prefs.editor_page.line_width.set_value(55)
    prefs.editor_page.line_spacing.set_selected(2)
    prefs.editor_page.color_scheme.set_selected(2)
    saved = config.settings()
    check((saved["editor_font_size"], saved["line_width"], saved["line_spacing"]) == (22, 55, "relaxed"), "Changes are saved immediately")
    check(ed.view.line_width_chars == 55 and ed.view.get_pixels_inside_wrap() == 10, "Width and line spacing take effect immediately")
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK, "Dark style takes effect immediately")
    prefs.editor_page.system_font.set_active(False)
    from gi.repository import Pango

    prefs.editor_page.font_button.set_font_desc(Pango.FontDescription.from_string("Monospace"))
    check(config.settings()["editor_font"] == "Monospace", "Custom font is saved")

    # Editor themes: tiles, light/dark variant, import and removal
    from typecase import themes

    check(tc_config.TEMPLATES_DIR.is_relative_to(TMP) and themes.USER_DIR.is_relative_to(TMP), "Test uses its own themes folder")
    tiles = prefs.editor_page._previews
    check(list(tiles) == list(themes.BUILTIN) and tiles["typecase-standard"].get_selected(), "Five built-in themes, Standard selected")
    tiles["typecase-paper"].emit("activate")
    check(config.settings()["editor_theme"] == "typecase-paper" and tiles["typecase-paper"].get_selected() and not tiles["typecase-standard"].get_selected(), "Choosing a tile saves the theme")
    check(ed.buffer.get_style_scheme().get_id() == "typecase-paper-dark", "The editor uses the dark variant while the style is dark")
    check(ed.styler.tags["link"].props.foreground_rgba.to_string() == "rgb(217,160,102)", "Links take the theme's color")
    check("rgb(43,37,32)" in win._theme_css.to_string(), "The group view takes the theme's background")
    check("--sidebar-bg-color" in win._theme_css_text and "--accent-bg-color: rgb(217,160,102)" in win._theme_css_text, "The rest of the window is tinted to match the theme")
    scheme_xml = TMP / "nacht.xml"
    scheme_xml.write_text('<?xml version="1.0"?><style-scheme id="nacht" name="Nacht" version="1.0"><style name="text" foreground="#dddddd" background="#101820"/></style-scheme>')
    themes.install(scheme_xml)
    prefs.themes_group.refresh()
    prefs._themes_changed()
    check("nacht" in prefs.editor_page._previews and "nacht" in prefs.focus_page._previews, "An imported theme appears as a tile")
    titles = [row.get_title() for row in prefs.themes_group._rows]
    check(titles[:5] == [t.name for t in themes.available()[:5]] and "Nacht" in titles and titles[-1] == "How to Build Your Own Theme", "The theme list shows built-in and imported themes and links the guide")
    prefs.editor_page._previews["nacht"].emit("activate")
    check(ed.buffer.get_style_scheme().get_id() == "nacht", "A theme with one variant is used for light and dark")
    prefs.themes_group._remove(next(t for t in themes.available() if t.id == "nacht"))
    check("nacht" not in prefs.editor_page._previews and config.settings()["editor_theme"] == themes.DEFAULT, "Removing the chosen theme falls back to Standard")
    check(ed.buffer.get_style_scheme().get_id() == "typecase-standard-dark", "The editor falls back to Standard, too")
    check("--sidebar-bg-color" not in win._theme_css_text, "Standard keeps the usual GNOME colors")
    prefs.editor_page._previews["typecase-calm"].emit("activate")
    prefs.editor_page.reset()
    check(ed.path and ed.path.name == "a.md", "Checkpoint after reset: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    check(config.settings() == config.SETTINGS_DEFAULTS, "Reset restores the defaults")
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT, "Style follows the system again")

    # Separate settings for focus mode
    focus = prefs.focus_page
    check(prefs.focus_same.get_active() and not focus.groups[0].get_visible(), "Focus mode initially uses the editor settings (its own are hidden)")
    page = prefs.get_visible_page()
    check(page.get_name() == "editor" and focus.page is page, "Editor and focus mode share one page")
    prefs.focus_same.set_active(False)
    check(all(group.get_visible() for group in focus.groups), "Switching off shows focus mode's own settings")
    focus.color_scheme.set_selected(2)
    focus.font_size.set_value(26)
    focus._previews["typecase-solarized"].emit("activate")
    check(ed.buffer.get_style_scheme().get_id() in ("typecase-standard", "typecase-standard-dark"), "Outside of focus mode the editor theme stays")
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT, "Outside of focus mode the editor style stays")
    prefs.force_close()
    check(ed.path and ed.path.name == "a.md", "Checkpoint preferences closed: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    win.lookup_action("focus-mode").activate(None)
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK, "Focus mode switches to its own style (dark)")
    check("26pt" in ed._css.to_string(), "Focus mode uses its own font size")
    check(ed.buffer.get_style_scheme().get_id() == "typecase-solarized-dark", "Focus mode uses its own theme")
    win.lookup_action("focus-mode").activate(None)
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT and "15pt" in ed._css.to_string(), "Back in the editor, its settings apply again")
    yield from wait_until(lambda: not win.is_fullscreen())
    config.update(focus_same_as_editor=True)
    check(ed.path and ed.path.name == "a.md", "Checkpoint after focus mode: a.md still open (open: " + str(ed.path and ed.path.name) + ")")

    # Window: sidebar, fullscreen, keyboard shortcuts, about
    shown = win.split.get_show_sidebar()
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() != shown, "F9 action toggles the sidebar")
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() == shown, "F9 action shows it again")
    check(ed.path and ed.path.name == "a.md", "Checkpoint after sidebar: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    # Relative to the current state: in a narrow (tiled) window the sidebar starts collapsed.
    shown = win.split.get_show_sidebar()
    win.sidebar_button.emit("clicked")  # like a click
    check(win.split.get_show_sidebar() != shown and win.sidebar_button.get_active() == (not shown), "Button toggles the sidebar")
    win.sidebar_button.emit("clicked")
    check(win.split.get_show_sidebar() == shown and win.sidebar_button.get_active() == shown, "Button toggles it back")
    win.lookup_action("fullscreen").activate(None)
    yield 1.5  # the window manager needs a moment
    check(win.is_fullscreen(), "F11 action turns fullscreen on")
    win.lookup_action("fullscreen").activate(None)
    yield 1.5
    check(not win.is_fullscreen(), "F11 action turns fullscreen off")
    check(ed.path and ed.path.name == "a.md", "Checkpoint after fullscreen: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    win.lookup_action("show-shortcuts").activate(None)
    check(win.get_visible_dialog() is not None, "Keyboard shortcuts overview opens")
    win.get_visible_dialog().force_close()
    app.lookup_action("about").activate(None)
    check(win.get_visible_dialog() is not None, "About dialog opens")
    win.get_visible_dialog().force_close()
    check(ed.path and ed.path.name == "a.md", "Checkpoint after about dialog: a.md still open (open: " + str(ed.path and ed.path.name) + ")")
    accels = {name: app.get_accels_for_action(name) for name in ["win.fullscreen", "win.toggle-sidebar", "app.quit"]}
    check(accels == {"win.fullscreen": ["F11"], "win.toggle-sidebar": ["F9", "<Shift><Control>l"], "app.quit": ["<Control>q"]}, "Keyboard shortcuts are registered")

    # Quitting (Ctrl+Q) saves as well
    ed.buffer.insert_at_cursor("W")
    expected_a = text(ed)
    while win.get_visible_dialog() is not None:  # An open rename dialog would intercept the close first.
        win.get_visible_dialog().force_close()
    app.lookup_action("quit").activate(None)
    check(read("a.md") == expected_a, "Quitting saves unsaved input")
    app.quit()


def on_activate(app):
    from typecase.window import TypecaseWindow

    win = TypecaseWindow(application=app)  # do_activate then uses this window
    win.present()
    gen = steps(win, app)

    def advance():
        try:
            delay = next(gen)
        except StopIteration:
            return GLib.SOURCE_REMOVE
        except Exception as error:  # test errors should end the run, not leave it hanging
            check(False, f"Unexpected error: {error!r}")
            app.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(int(delay * 1000), advance)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(500, advance)


app = TypecaseApplication()
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)  # runs separately from an already open Typecase
app.connect("activate", on_activate)
app.run(None)

os.chmod(LIB, stat.S_IRWXU)
shutil.rmtree(TMP, ignore_errors=True)
if not checked:
    failures.append("No checks were run")
print(f"\n{len(checked)} checks, " + ("all passed." if not failures else f"{len(failures)} failed."))
sys.exit(1 if failures else 0)
