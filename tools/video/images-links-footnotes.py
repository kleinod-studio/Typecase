"""Explainer video: pictures, links and footnotes, and the pills they fold into.

    python3 tools/video/images-links-footnotes.py

Writes dist/videos/images-links-footnotes/images-links-footnotes.webm and .mp4, with English and
German subtitles. While it records, a Typecase window floats in the middle of the screen for about
a minute and a half; leave it visible and don't touch it. The file chooser of the image button is
left out (it would show your own folders); the picture comes from tools/video/lighthouse.svg."""

import random
import subprocess
import tempfile
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
CAPTION = "The tower at low tide"
ALT = "A lighthouse on a small rocky island"
URL = "https://en.wikipedia.org/wiki/Causeway"
NOTE = "Built by the first keeper, in 1871."

# --- Helpers --------------------------------------------------------------------


def boolean(value):
    from gi.repository import GLib

    return GLib.Variant.new_boolean(value)


def text_of(win):
    buffer = win.editor.buffer
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)  # with the folded pills


def place(win, offset):
    buffer = win.editor.buffer
    buffer.place_cursor(buffer.get_iter_at_offset(offset))


def type_text(win, text, pace=0.06, seed=9):
    """Types into the sheet like a person; a selection is typed over."""
    noise = random.Random(seed)
    buffer = win.editor.buffer
    buffer.delete_selection(True, True)
    for char in text:
        buffer.insert_at_cursor(char)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if char == " ":
            pause += pace * 0.6
        elif char in ",.":
            pause += pace * 3
        yield pause


def type_into(row, text, pace=0.06, seed=4):
    """Types into an entry row of a dialog."""
    noise = random.Random(seed)
    row.grab_focus()
    for count in range(1, len(text) + 1):
        row.set_text(text[:count])
        row.set_position(count)
        yield pace * (1 + noise.uniform(-0.35, 0.35)) + (pace * 0.6 if text[count - 1] == " " else 0)


def lines_rect(win, start, end, above=16, below=16):
    """The text lines from offset `start` to `end`, across the text column, as a rectangle in the window."""
    from gi.repository import Graphene, Gtk

    view = win.editor.view
    buffer = win.editor.buffer

    def window_y(offset, bottom):
        place_ = view.get_iter_location(buffer.get_iter_at_offset(offset))
        _x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, place_.x, place_.y + (place_.height if bottom else 0))
        _found, point = view.compute_point(win, Graphene.Point().init(0, y))
        return point.y

    top, bottom = window_y(start, False) - above, window_y(end, True) + below
    _found, bounds = view.compute_bounds(win)
    width = bounds.get_width()
    return (bounds.get_x() + width * 0.15, top, width * 0.7, bottom - top)


def bar_button(win, kind):
    child = win.format_bar.get_first_child()
    while child is not None:
        target = child.get_action_target_value() if hasattr(child, "get_action_target_value") else None
        if target is not None and target.get_string() == kind:
            return child
        child = child.get_next_sibling()
    raise LookupError(kind)


def press(button):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    button.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.35
    button.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    button.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def image_line(win):
    """The line of the sheet's picture and the picture, as the editor sees them."""
    from typecase import images

    for number, line in enumerate(text_of(win).split("\n")):
        found = images.in_line(line) if "![" in line else []
        if found:
            return number, found[0]
    raise LookupError("image")


def format_(win, kind):
    from gi.repository import GLib

    win.activate_action("win.format", GLib.Variant.new_string(kind))


# --- The scenes -----------------------------------------------------------------


def opening(win):
    for group in ("The Lighthouse Keeper", "Manuscript"):
        node(win, group)[1].set_expanded(True)
    select(win, "02 The Storm")
    win.editor.focus_editor()
    place(win, 0)


def intro(win):
    yield 1.5


def pills(win):
    text = text_of(win)
    buffer = win.editor.buffer
    # All three pills in view: the note in the first paragraph, the picture, the link below it
    view = win.editor.view
    adjustment = view.get_vadjustment()
    link_y = view.get_iter_location(buffer.get_iter_at_offset(text.index("[Beaufort"))).y
    start_value = adjustment.get_value()
    target = min(link_y - adjustment.get_page_size() * 0.6, adjustment.get_upper() - adjustment.get_page_size())
    for frame in range(1, 25):  # a smooth scroll, as with the mouse wheel
        u = frame / 24
        adjustment.set_value(start_value + (target - start_value) * u * u * (3 - 2 * u))
        yield 1 / 30
    yield 0.4
    start = text.index("^[")
    yield zoom_to(lines_rect(win, start, text.index("stone.", start) + 6), length=1.2, margin=0.02)
    yield 1.4
    place(win, text.index("[Beaufort"))  # the link unfolds
    yield 2.6
    place(win, text.index("By evening"))  # and folds again
    yield 1.0


def insert_image(win):
    yield zoom_to(None, length=1.0)
    select(win, "04 Low Tide")
    yield 1.0
    win.editor.focus_editor()
    buffer = win.editor.buffer
    buffer.place_cursor(buffer.get_end_iter())
    yield 0.6
    yield from press(bar_button(win, "image"))
    yield 0.5
    from gi.repository import Gio

    folder = Path(tempfile.mkdtemp())
    picture = folder / "tower.png"
    subprocess.run(["rsvg-convert", "-w", "1200", str(HERE / "lighthouse.svg"), "-o", str(picture)], check=True)
    win.editor.insert_image_files([Gio.File.new_for_path(str(picture))])
    yield 2.0


def edit_image(win):
    number, image = image_line(win)
    win.editor.edit_image(number, image)
    yield 1.0
    dialog = win.get_visible_dialog()
    dialog.size_row.set_selected(2)  # Medium
    yield 0.8
    dialog.align_row.set_selected(2)  # Center
    yield 0.8
    yield from type_into(dialog.caption_row, CAPTION)
    yield 0.4
    yield from type_into(dialog.alt_row, ALT, pace=0.04)
    yield 0.8
    dialog.apply()
    yield 1.4


def link(win):
    text = text_of(win)
    start = text.index("causeway")
    yield zoom_to(lines_rect(win, 0, len(text.split("\n")[0])), length=1.0, margin=0.04)
    buffer = win.editor.buffer
    buffer.select_range(buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(start + len("causeway")))
    yield 1.0
    format_(win, "link")
    yield 0.8
    yield from type_text(win, URL, pace=0.04)
    yield 1.2
    place(win, text_of(win).index("At low tide"))  # the link folds into a pill
    yield 1.4


def footnote(win):
    text = text_of(win)
    place(win, text.index("stone by stone.") + len("stone by stone."))
    yield 0.6
    format_(win, "footnote")
    yield 0.6
    yield from type_text(win, NOTE)
    yield 1.0
    place(win, text_of(win).index("At low tide"))  # and the note folds, too
    yield 1.4


def outlook(win):
    yield zoom_to(None, length=1.2)
    yield 1.0


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Pictures, links and footnotes are Markdown, too. Typecase keeps them out of your way.",
        "Bilder, Links und Fußnoten sind auch Markdown. Typecase hält sie dir aus dem Weg.",
        intro,
        say="Pictures, links and footnotes are Markdown, too. Type case keeps them out of your way.",
    ),
    Scene(
        "In your text they fold into small colored pills: yellow for pictures, blue for links, green for footnotes. "
        "Move the cursor onto one, and it opens up.",
        "Im Text klappen sie zu kleinen farbigen Pills zusammen: gelb für Bilder, blau für Links, grün für Fußnoten. "
        "Gehst du mit dem Cursor darauf, klappt die Pill auf.",
        pills,
    ),
    Scene(
        "To add a picture, click the image button, drag one in, or paste it. Typecase keeps a copy with the sheet, "
        "as an attachment.",
        "Für ein Bild klickst du auf den Bild-Knopf, ziehst eins hinein oder fügst es ein. Typecase legt eine Kopie "
        "als Anhang zum Blatt.",
        insert_image,
        say="To add a picture, click the image button, drag one in, or paste it. Type case keeps a copy with the "
            "sheet, as an attachment.",
    ),
    Scene(
        "Double-click it to set its size, alignment and caption, and a description for people who can't see it.",
        "Mit einem Doppelklick legst du Größe, Ausrichtung und Bildunterschrift fest, dazu eine Beschreibung für "
        "Menschen, die es nicht sehen können.",
        edit_image,
    ),
    Scene(
        "For a link, select a word and press Ctrl+K, then type or paste the address. Ctrl+click opens it in your "
        "browser.",
        "Für einen Link markierst du ein Wort und drückst Strg+K, dann tippst oder fügst du die Adresse ein. Mit "
        "Strg+Klick öffnest du ihn im Browser.",
        link,
        say="For a link, select a word and press Control K, then type or paste the address. Control click opens "
            "it in your browser.",
    ),
    Scene(
        "A footnote goes right where it belongs: press Ctrl+Alt+F and type the note. Or use the buttons in the bar.",
        "Eine Fußnote steht genau dort, wo sie hingehört: Drücke Strg+Alt+F und tippe die Anmerkung. Oder nimm die "
        "Knöpfe in der Leiste.",
        footnote,
        say="A footnote goes right where it belongs: press Control Alt F, and type the note. Or use the buttons "
            "in the bar.",
    ),
    Scene(
        "When you export, the picture gets its caption and the footnotes move to the bottom of the page.",
        "Beim Export bekommt das Bild seine Unterschrift, und die Fußnoten wandern an den Fuß der Seite.",
        outlook,
    ),
    Scene(
        "Everything stays plain text, and your writing stays easy to read.",
        "Alles bleibt reiner Text, und dein Text bleibt gut lesbar.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="images-links-footnotes",
    title="Images, links and footnotes",
    topic="Write",
    summary="Add pictures, links and footnotes, and see how they fold into pills that keep your text readable.",
    still=40,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
