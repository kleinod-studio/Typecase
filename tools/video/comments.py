"""Explainer video: comments. A passage gets a comment, it folds into a pill with a bubble in the
margin, a comment on its own comes from the bar, the caret jumps between them, the Word export
keeps them in the margin, and one is removed again.

    python3 tools/video/comments.py

Writes dist/videos/comments/comments.webm and .mp4, with English and German subtitles. While it
records, a Typecase window floats in the middle of the screen for about a minute; leave it visible
and don't touch it. The tooltip over the bubble needs a real pointer, so a small popover stands in
for it."""

import importlib.util
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pills_video = _load("images_links_footnotes", "images-links-footnotes.py")
spelling_video = _load("spell_checking", "spell-checking.py")
text_of, place, type_text, press = pills_video.text_of, pills_video.place, pills_video.type_text, pills_video.press
bar_button, format_ = pills_video.bar_button, pills_video.format_
menu_item, walk = spelling_video.menu_item, spelling_video.walk
export_video = _load("export_a_sheet", "export-a-sheet.py")
choose_row, area = export_video.choose, export_video.area

PASSAGE = "tapped the glass twice"
NOTE = "Show more of her nerves here?"
AFTER = "with every stone."
ALONE = "What does the wind sound like?"
STATE = {}

# --- Helpers --------------------------------------------------------------------


def scroll_to_offset(win, offset, fraction=0.3, frames=24):
    """Scrolls smoothly until the line of offset sits at fraction of the page height."""
    view, buffer = win.editor.view, win.editor.buffer
    adjustment = view.get_vadjustment()
    y = view.get_iter_location(buffer.get_iter_at_offset(offset)).y
    start = adjustment.get_value()
    target = max(0, min(y - adjustment.get_page_size() * fraction, adjustment.get_upper() - adjustment.get_page_size()))
    for frame in range(1, frames + 1):
        u = frame / frames
        adjustment.set_value(start + (target - start) * u * u * (3 - 2 * u))
        yield 1 / 30


def margin_rect(win, start, end, above=40, below=40):
    """The lines from start to end with the margin to their left, where the bubbles are."""
    from gi.repository import Graphene, Gtk

    view, buffer = win.editor.view, win.editor.buffer

    def window_y(offset, bottom):
        found = view.get_iter_location(buffer.get_iter_at_offset(offset))
        _x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, found.x, found.y + (found.height if bottom else 0))
        _found, point = view.compute_point(win, Graphene.Point().init(0, y))
        return point.y

    _found, bounds = view.compute_bounds(win)
    margin = view.get_left_margin()
    left = bounds.get_x() + margin - 70
    width = bounds.get_width() - 2 * margin + 140
    top, bottom = window_y(start, False) - above, window_y(end, True) + below
    return (left, top, width, bottom - top)


def first_bubble(win):
    rect, offset, notes = win.editor.pills.bubbles()[0]
    return rect, offset, notes


def show_tooltip(win, text, rect):
    """A popover in the look of a tooltip, below the bubble (a real one needs a real pointer)."""
    from gi.repository import Gdk, Gtk

    view = win.editor.view
    x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, int(rect.get_x()), int(rect.get_y()))
    popover = Gtk.Popover(has_arrow=False, autohide=False, can_target=False, can_focus=False)
    popover.set_child(Gtk.Label(label=text, margin_start=4, margin_end=4))
    popover.set_parent(view)
    popover.set_position(Gtk.PositionType.BOTTOM)
    target = Gdk.Rectangle()
    target.x, target.y, target.width, target.height = x, y, int(rect.get_width()), int(rect.get_height())
    popover.set_pointing_to(target)
    popover.popup()
    return popover


def wait_for_dialog(win, limit=3.0):
    waited = 0.0
    while win.get_visible_dialog() is None and waited < limit:
        yield 0.1
        waited += 0.1


def context_menu(win, offset):
    """Opens the editor's context menu at offset, below the text there."""
    from gi.repository import Gdk, Gtk

    view, buffer = win.editor.view, win.editor.buffer
    place(win, offset)
    view.activate_action("menu.popup", None)
    popover = next(w for w in walk(view) if isinstance(w, Gtk.PopoverMenu) and w.get_visible())
    popover.set_can_target(False)  # the real pointer, wherever it is, must not hover a row
    found = view.get_iter_location(buffer.get_iter_at_offset(offset))
    x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, found.x, found.y)
    target = Gdk.Rectangle()
    target.x, target.y, target.width, target.height = x, y, 1, found.height
    popover.set_position(Gtk.PositionType.BOTTOM)
    popover.set_pointing_to(target)
    return popover


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import export_dialog

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    for group in ("The Lighthouse Keeper", "Manuscript"):
        node(win, group)[1].set_expanded(True)
    select(win, "02 The Storm")
    win._open_selected()
    win.editor.focus_editor()
    place(win, 0)


def intro(win):
    yield 1.8


def add(win):
    text = text_of(win)
    start = text.index(PASSAGE)
    yield zoom_to(margin_rect(win, 0, text.index("change its mind.")), length=1.0, factor=1.35)
    buffer = win.editor.buffer
    buffer.select_range(buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(start + len(PASSAGE)))
    yield 1.2
    format_(win, "comment")
    yield 0.7
    yield from type_text(win, NOTE)
    yield 1.0


def fold(win):
    text = text_of(win)
    place(win, text.index("as if the needle"))  # the comment folds into a pill
    yield 1.0
    rect, _offset, _notes = first_bubble(win)
    STATE["bubble"] = rect
    yield 2.6


def read(win):
    popover = show_tooltip(win, NOTE, STATE["bubble"])
    yield 2.4
    popover.popdown()
    popover.unparent()
    yield 0.4
    _rect, offset, _notes = first_bubble(win)
    place(win, offset)  # what a click on the bubble does: into the comment
    win.editor.focus_editor()
    yield 2.0
    place(win, text_of(win).index("as if the needle"))
    yield 0.6


def alone(win):
    yield zoom_to(None, length=0.9)
    text = text_of(win)
    end = text.index(AFTER) + len(AFTER)
    yield from scroll_to_offset(win, end, fraction=0.45)
    place(win, end)
    win.editor.focus_editor()
    yield 0.8
    yield from press(bar_button(win, "comment"))
    format_(win, "comment")
    yield 0.6
    yield from type_text(win, ALONE, seed=3)
    yield 1.0
    place(win, text_of(win).index("She lit"))
    yield 1.4


def jump(win):
    for _number in range(2):
        win.activate_action("win.next-comment", None)
        yield 2.0


def export(win):
    place(win, text_of(win).index("She lit"))
    win.editor.focus_editor()
    win.activate_action("win.export", None)
    yield from wait_for_dialog(win)
    if win.get_visible_dialog() is None:
        win._export()
        yield from wait_for_dialog(win)
    yield 0.4
    dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=0.8, factor=1.4)
    yield 0.6
    yield from choose_row(dialog.format_row, "Word Document (DOCX)")
    yield 1.4
    yield from press(dialog.comments_row)
    dialog.comments_row.set_active(True)
    yield 2.2
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.4


def remove(win):
    from gi.repository import Gtk

    text = text_of(win)
    yield from scroll_to_offset(win, 0, fraction=0.0)
    yield zoom_to(margin_rect(win, 0, text.index("change its mind.")), length=0.9, factor=1.35)
    start = text.index(PASSAGE)
    popover = context_menu(win, start + 2)
    yield 0.1
    popover.grab_focus()  # the menu's first row would take the focus, and look chosen
    for widget in walk(popover):
        widget.unset_state_flags(Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.SELECTED)
    yield 0.9
    # Glide down to the row that gets clicked, large enough to read it
    row = menu_item(popover, "Remove Comment")
    _found, menu = popover.compute_bounds(win)
    _found, line = row.compute_bounds(win)
    middle = line.get_y() + line.get_height() / 2
    yield zoom_to((menu.get_x() - 60, middle - 110, menu.get_width() + 120, 220), length=1.0, factor=1.5)
    yield 0.3
    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    row.grab_focus()
    yield 1.6
    row.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.2
    popover.popdown()
    win.editor.remove_comment()
    yield zoom_to(margin_rect(win, 0, text.index("change its mind.")), length=0.8, factor=1.35)
    place(win, text_of(win).index("as if the needle"))
    yield 1.8


def closing(win):
    yield zoom_to(None, length=1.0)
    yield 1.4


SCENES = [
    Scene(
        "When you revise, you leave yourself notes. Comments keep them right next to the text.",
        "Beim Überarbeiten hinterlässt du dir Notizen. Kommentare halten sie direkt am Text.",
        intro,
    ),
    Scene(
        "Select a passage and press Ctrl+Alt+M. Then write your note.",
        "Markiere eine Stelle und drück Strg+Alt+M. Dann schreib deine Notiz.",
        add,
        say="Select a passage and press Control Alt M. Then write your note.",
    ),
    Scene(
        "The comment folds into a pill. The bubble in the margin shows where it is.",
        "Der Kommentar klappt zu einer Pille zusammen. Die Blase am Rand zeigt, wo er steht.",
        fold,
    ),
    Scene(
        "Point at the bubble to read it. A click takes you inside.",
        "Zeig auf die Blase, um ihn zu lesen. Ein Klick führt hinein.",
        read,
    ),
    Scene(
        "Without a selection, the comment stands on its own. The button in the bar does the same.",
        "Ohne Markierung steht der Kommentar für sich. Der Knopf in der Leiste macht dasselbe.",
        alone,
    ),
    Scene(
        "Ctrl+Alt+Page Down takes you from comment to comment.",
        "Mit Strg+Alt+Bild ab springst du von Kommentar zu Kommentar.",
        jump,
        say="Control Alt Page Down takes you from comment to comment.",
    ),
    Scene(
        "A PDF never shows your comments. In Word, they can stay in the margin, for your editor.",
        "Im PDF fehlen Kommentare immer. In Word bleiben sie auf Wunsch am Rand, fürs Lektorat.",
        export,
    ),
    Scene(
        "Note done? Remove it, and the text stays.",
        "Notiz erledigt? Entfern sie, der Text bleibt.",
        remove,
    ),
    Scene(
        "Your notes stay with your text, in a plain Markdown file.",
        "Deine Notizen bleiben beim Text, in der ganz normalen Markdown-Datei.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="comments",
    title="Comments",
    topic="Write",
    summary="Leave yourself notes in the text, see them in the margin, jump between them, and keep them for an editor in Word.",
    still=30,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
