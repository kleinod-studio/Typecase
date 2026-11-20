"""A short tour of Typecase without narration, cut to a piece of music: from the first sentence
to the finished page.

    python3 tools/video/tour.py MUSIC.mp3

The music is not part of the repository (keep its license in mind); the scenes are timed to
the bars of "Cinematic" by AtlasAudio (Pixabay, 1:26, about 99 bpm). Another piece needs
other bar times below. Writes dist/videos/tour/tour.webm and .mp4. While it records, a
Typecase window floats in the middle of the screen for about 80 seconds; leave it visible and
don't touch it.

The pages in the export scene are made with the installed Typecase Flatpak (it brings Pandoc
and WeasyPrint) and kept in ~/.cache/typecase-video/tour-pages.png."""

import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cards
import videokit
from actions import library_rows, node, select, set_look
from videokit import Scene, at, zoom_to

BAR, FIRST_BEAT = 2.4145, 0.24  # of the music, in seconds
BEAT = BAR / 4


def bar(number: int) -> float:
    """When bar `number` of the music begins, in seconds of the video."""
    return FIRST_BEAT + number * BAR


PAGES = videokit.TOOLS / "tour-pages.png"
FIRST = "When the fog lifted, Ada climbed the hundred and twelve steps to the lamp."
SECOND = "\n\nSomewhere out there, someone would **see** it."

# The focus mode has its own look: big letters on paper, the line kept in the middle.
SETTINGS = {
    "focus_same_as_editor": False,
    "focus_editor_font_size": 30,
    "focus_line_width": 32,
    "focus_editor_theme": "typecase-paper",
    "focus_color_scheme": "light",
    "focus_typewriter": True,
    "focus_dim": False,
    "focus_format_bar": False,
}


# --- Helpers ------------------------------------------------------------------------


def cursor_line(win, height=44):
    """The line with the cursor across the text column, as a rectangle in the window."""
    from gi.repository import Graphene, Gtk

    view = win.editor.view
    buffer = view.get_buffer()
    place = view.get_iter_location(buffer.get_iter_at_mark(buffer.get_insert()))
    x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, place.x, place.y + place.height / 2)
    _found, point = view.compute_point(win, Graphene.Point().init(x, y))
    _found, bounds = view.compute_bounds(win)
    return (bounds.get_x(), point.y - height / 2, bounds.get_width(), height)


def type_text(win, text, begin, end, seed=7):
    """Types `text` into the sheet between `begin` and `end` seconds of the scene, letter by
    letter, a little unevenly, with short pauses after words and longer ones after commas."""
    noise = random.Random(seed)
    weights = []
    for char in text:
        weight = 1.0 + noise.uniform(-0.35, 0.35)
        if char == " ":
            weight += 0.6
        elif char in ",.":
            weight += 2.2
        elif char == "\n":
            weight += 1.5
        weights.append(weight)
    step = (end - begin) / sum(weights)
    moment = begin
    buffer = win.editor.buffer
    for char, weight in zip(text, weights):
        yield at(moment)
        buffer.insert_at_cursor(char)
        moment += weight * step


def editor_area(win):
    _found, bounds = win.editor.view.compute_bounds(win)
    return (bounds.get_x(), bounds.get_y(), bounds.get_width(), bounds.get_height())


def theme(win, name, scheme="light"):
    from typecase import config

    config.update(editor_theme=name, color_scheme=scheme)
    win.apply_settings()


def boolean(value):
    from gi.repository import GLib

    return GLib.Variant.new_boolean(value)


def expand(win, *groups):
    for group in groups:
        node(win, group)[1].set_expanded(True)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    # Focus mode would go full screen; the recording needs the window as it is.
    win.fullscreen = lambda: None
    win.unfullscreen = lambda: None
    expand(win, "The Lighthouse Keeper", "Manuscript")
    select(win, "07 The Light")
    win.lookup_action("focus-mode").change_state(boolean(True))
    win.editor.focus_editor()


def first_line(win):
    """Close on the empty page; the first sentence is typed while the picture slowly widens."""
    zoom_to(cursor_line(win), length=0.01, factor=1.5)
    yield at(FADE_IN + 0.4)
    zoom_to(cursor_line(win), length=10.5, factor=1.3)
    yield from type_text(win, FIRST, FADE_IN + 0.8, scene_length(0) - 0.6)


def second_line(win):
    zoom_to(None, length=2.4)
    yield from type_text(win, SECOND, 1.4, 8.4, seed=11)


def leave_focus(win):
    win.lookup_action("focus-mode").change_state(boolean(False))
    yield 0


def picture(win):
    """The first picture shown in the sheet, as a rectangle in the window (or the text area)."""
    from gi.repository import Graphene, Gtk

    view = win.editor.view
    for _line, shown, left, top in win.editor.previews._rectangles():
        x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, left, top)
        _found, point = view.compute_point(win, Graphene.Point().init(x, y))
        width, height = shown.size
        return (point.x, point.y, width, height)
    return editor_area(win)


def storm(win):
    """One move of the camera: close to the picture in the text, then over to the library,
    where it stays for the next scene."""
    select(win, "02 The Storm")
    yield at(1.0)  # the picture has been loaded by then
    zoom_to(picture(win), length=3.0, margin=0.08)
    yield at(scene_length(3) - 2.2)
    zoom_to(library_rows(win), length=2.2, factor=1.3)


LOOKS = [
    ("The Lighthouse Keeper", "book", "purple"),
    ("Characters", "person", "teal"),
    ("Places", "place", "green"),
    ("Notes", "idea", "yellow"),
    ("Letters", "mail", "orange"),
    ("Thesis", "science", "blue"),
]


def organize(win):
    """Icons and colors on the beat, a chapter moved up two places, then the keyword filter."""
    for beat, (row, icon, color) in enumerate(LOOKS):
        yield at(beat * BEAT + 0.15)
        set_look(win, row, icon, color)
    yield at(6 * BEAT)
    select(win, "07 The Light")
    for beat in (7, 8):
        yield at(beat * BEAT)
        win.activate_action("move-up", None)
    yield at(10 * BEAT)
    win.set_keyword_filter("chapter")


def plot(win):
    win.set_keyword_filter(None)
    zoom_to(None, length=1.0)
    yield at(2 * BEAT)
    expand(win, "The Lighthouse Keeper")
    select(win, "Manuscript")
    yield at(3 * BEAT)
    win.lookup_action("cards").change_state(boolean(True))
    yield at(4 * BEAT)
    zoom_to(win.group_view, length=2.0, margin=0.0, factor=1.15)
    for beat in (6, 8):
        yield at(beat * BEAT)
        board = win.group_view.cards
        card = next(card for card in board.cards if card.path.stem.startswith("04"))
        board.move_step(card, -1)


def share(win):
    from typecase import template_builder
    from typecase.template_dialog import TemplateDialog

    zoom_to(None, length=0.8)
    dialog = TemplateDialog(lambda *_a: None, lambda *_a: None)
    dialog.present(win)
    yield at(0.8)
    zoom_to(dialog.get_child(), length=1.2, margin=0.04)
    for number in range(1, len("Novel") + 1):
        yield at(1.4 + number * 0.22)
        dialog.name_row.set_text("Novel"[:number])
    yield at(3.6)
    dialog.preset_row.set_selected(list(template_builder.presets()).index("novel"))
    yield at(8.4)  # the printed pages cover the picture by now
    dialog.force_close()
    zoom_to(None, length=0.3)


THEMES = [
    ("typecase-paper", "light"),
    ("typecase-solarized", "light"),
    ("typecase-calm", "light"),
    ("typecase-paper", "dark"),
    ("typecase-solarized", "dark"),
]


def looks_change(win):
    select(win, "02 The Storm")
    for number, (name, scheme) in enumerate(THEMES, start=1):
        yield at(number * 2 * BEAT)
        theme(win, name, scheme)


USES = [("01 Arrival", "Novels."), ("1 Introduction", "Theses."), ("Dear Mira", "Letters."), ("Ideas", "Notes.")]


def uses(win):
    theme(win, "typecase-standard", "light")
    expand(win, "Thesis", "Letters", "Notes")
    for number, (sheet, _caption) in enumerate(USES):
        yield at(number * BAR)
        select(win, sheet)
        zoom_to(editor_area(win), length=0.01, margin=0.02, factor=1.18)
        zoom_to(editor_area(win), length=BAR - 0.1, margin=0.02, factor=1.1)
    yield at(4 * BAR)
    zoom_to(None, length=1.6)


# Scene starts in seconds of the video, on the bars of the music; the recording cross-fades in
# from the intro card half a second before the first one.
FADE_IN = videokit.FADE
STARTS = [bar(2) - FADE_IN, bar(7), bar(11), bar(12), bar(15), bar(18), bar(21), bar(25), bar(28)]
END = bar(33) + videokit.FADE  # the closing card cross-fades in over the last half second


def scene_length(index):
    return (STARTS[1:] + [END])[index] - STARTS[index]


def caption(text, begin, end):
    return (text, begin, end)


SCENES = [
    Scene("", "", steps=first_line),
    Scene("", "", steps=second_line, overlays=[caption("Write.", 1.2, 9.2)]),
    Scene("", "", steps=leave_focus),
    Scene("", "", steps=storm),
    Scene("", "", steps=organize, overlays=[caption("Organize.", 0.3, 7.0)]),
    Scene("", "", steps=plot, overlays=[caption("Plot.", 1.8, 7.0)]),
    Scene("", "", steps=share, overlays=[(PAGES, 4.83, 9.66), caption("Share.", 5.3, 9.4)]),
    Scene("", "", steps=looks_change, overlays=[caption("Make it yours.", 1.0, 6.9)]),
    Scene("", "", steps=uses, overlays=[caption(text, number * BAR + 0.3, (number + 1) * BAR - 0.2)
                                        for number, (_sheet, text) in enumerate(USES)]),
]
for index, scene in enumerate(SCENES):
    scene.length = scene_length(index)

VIDEO = videokit.Video(
    name="tour",
    title="A tour of Typecase",
    topic="Get started",
    summary="A short tour through Typecase, from the first sentence to the finished page.",
    still=33,
    credit="Music: “Cinematic” by AtlasAudio, from Pixabay",
    credit_url="https://pixabay.com/music/",
)


def make_pages():
    """The first page of "02 The Storm" as the Novel template prints it (once, then cached)."""
    if PAGES.exists():
        return
    import demo_library

    with tempfile.TemporaryDirectory(dir=Path.home() / ".cache") as temp:
        temp = Path(temp)
        library = demo_library.build(temp / "lib", "en")
        sheet = library / "The Lighthouse Keeper" / "Manuscript" / "02 The Storm.md"
        # the template prints the title from the metadata; the heading would say it twice
        lines = sheet.read_text(encoding="utf-8").split("\n")
        heading = next(i for i, line in enumerate(lines) if line.startswith("# "))
        del lines[heading:heading + 2]
        sheet.write_text("\n".join(lines), encoding="utf-8")
        pdf = temp / "storm.pdf"
        subprocess.run(["flatpak", "run", "--command=python3", "studio.kleinod.Typecase",
                        str(videokit.HERE / "flatpak_pdf.py"), str(sheet), str(temp / "export"), str(pdf)], check=True)
        subprocess.run(["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", "1", str(pdf), str(temp / "page")], check=True)
        images = sorted(temp.glob("page-*.png"))
        PAGES.parent.mkdir(parents=True, exist_ok=True)
        cards.pages(images, PAGES)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    music = Path(sys.argv[1])
    if shutil.which("flatpak") is None or shutil.which("pdftoppm") is None:
        sys.exit("flatpak and pdftoppm are needed for the export scene.")
    make_pages()
    videokit.run_music(VIDEO, SCENES, music, before=opening, settings=SETTINGS, extras=True, intro=bar(2))
