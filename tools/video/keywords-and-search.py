"""Explainer video: keywords and the keyword filter, full-text search, find and replace in a sheet.

    python3 tools/video/keywords-and-search.py

Writes dist/videos/keywords-and-search/keywords-and-search.webm and .mp4, with English and German
subtitles. While it records, a Typecase window floats in the middle of the screen for about a
minute and a half; leave it visible and don't touch it."""

import random

import videokit
from actions import node, select
from videokit import Scene, zoom_to

KEYWORDS = "draft, chapter, storm"
QUERY = "lamp"
REPLACEMENT = "lantern"

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def type_into(entry, text, pace=0.07, seed=4):
    """Types into an entry, over what it held."""
    noise = random.Random(seed)
    entry.grab_focus()
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if text[count - 1] == " ":
            pause += pace * 0.6
        elif text[count - 1] == ",":
            pause += pace * 2
        yield pause


def press(widget):
    """Shows a button or row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def button_with(root, label):
    from gi.repository import Gtk

    for widget in walk(root):
        if isinstance(widget, Gtk.Button) and widget.get_label() == label:
            return widget
    raise LookupError(label)


def keyword_row(win, keyword):
    """The row of the keyword list that shows `keyword`."""
    for row in walk(win.keyword_list):
        if getattr(row, "keyword", "") == keyword:
            return row
    raise LookupError(keyword)


def sidebar():
    """The library column, as a rectangle in the window."""
    return (0, 0, 460, 720)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "04 Low Tide")
    win.editor.focus_editor()


def intro(win):
    yield 1.8


def add_keywords(win):
    win.inspector_split.set_show_sidebar(True)
    yield 1.4
    row = win.inspector.keywords_row
    yield zoom_to(row, length=1.0, factor=1.4)
    yield 0.4
    yield from type_into(row, KEYWORDS)
    yield 1.2
    win.editor.flush()  # the filter reads the keywords from the file
    yield 0.4


def filter_(win):
    yield zoom_to(None, length=1.0)
    win.inspector_split.set_show_sidebar(False)
    win.editor.focus_editor()
    yield 0.6
    yield from press(win.keyword_button)
    win.keyword_button.popup()
    yield 1.6
    row = keyword_row(win, "draft")
    yield from press(row)
    win.keyword_list.emit("row-activated", row)
    yield 1.0
    yield zoom_to(sidebar(), length=1.0, factor=1.3)
    yield 2.2


def show_all(win):
    yield from press(button_with(win.filter_banner, "Show All"))
    win.set_keyword_filter(None)
    yield 1.4
    yield zoom_to(None, length=0.8)


def search(win):
    win.activate_action("win.search", None)
    yield 0.8
    yield from type_into(win.search_entry, QUERY, pace=0.16)
    yield 0.6
    yield zoom_to(sidebar(), length=1.0, factor=1.3)
    yield 2.4


def open_hit(win):
    hit = next(row for row in walk(win.results) if getattr(row, "hit", None) and row.hit.path.stem == "02 The Storm")
    yield from press(hit)
    yield zoom_to(None, length=0.8)
    win.results.emit("row-activated", hit)
    yield 2.6


def replace(win):
    win.search_bar.set_search_mode(False)
    win.activate_action("win.replace", None)
    yield 0.8
    bar = win.find_bar
    yield from type_into(bar.replace_entry, REPLACEMENT)
    yield 0.8
    yield from press(button_with(bar, "Replace All"))
    bar.replace_all()
    yield 2.4


def closing(win):
    win.find_bar.set_search_mode(False)
    yield 1.0


SCENES = [
    Scene(
        "The more you write, the more you need to find again. Keywords and search help you.",
        "Je mehr du schreibst, desto mehr musst du wiederfinden. Schlagwörter und Suche helfen dir dabei.",
        intro,
    ),
    Scene(
        "Give a sheet keywords in its properties, separated by commas.",
        "In den Eigenschaften gibst du einem Blatt Schlagwörter, durch Kommas getrennt.",
        add_keywords,
    ),
    Scene(
        "The keyword button filters your library. Only the matching sheets stay.",
        "Der Schlagwort-Knopf filtert deine Bibliothek. Nur die passenden Blätter bleiben stehen.",
        filter_,
    ),
    Scene(
        "Show All brings everything back.",
        "Mit „Alle anzeigen“ ist alles wieder da.",
        show_all,
    ),
    Scene(
        "Ctrl+Shift+F searches the text of all sheets, as you type.",
        "Mit Strg+Umschalt+F durchsuchst du den Text aller Blätter, schon während du tippst.",
        search,
        say="Control Shift F searches the text of all sheets, as you type.",
    ),
    Scene(
        "Pick a result, and the sheet opens right at the spot.",
        "Wähle einen Treffer, und das Blatt öffnet sich genau an der Stelle.",
        open_hit,
    ),
    Scene(
        "Ctrl+F finds words in the open sheet. Ctrl+H replaces them, one by one or all at once.",
        "Strg+F findet Wörter im offenen Blatt. Strg+H ersetzt sie, einzeln oder alle auf einmal.",
        replace,
        say="Control F finds words in the open sheet. Control H replaces them, one by one, or all at once.",
    ),
    Scene(
        "Everything in its place, and found in a moment.",
        "Alles an seinem Platz und im Nu gefunden.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="keywords-and-search",
    title="Keywords and search",
    topic="Organize",
    summary="Tag sheets with keywords, filter your library by them, search all your text and replace words in a "
            "sheet.",
    still=30,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
