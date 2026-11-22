"""Explainer video: why Typecase writes in Markdown, the few characters it needs, the formatting
bar and the shortcuts.

    python3 tools/video/markdown.py

Writes dist/videos/markdown/markdown.webm and .mp4, with English and German subtitles. While it
records, a Typecase window floats in the middle of the screen for about a minute and a half;
leave it visible and don't touch it."""

import random

import videokit
from actions import node, select
from videokit import Scene, zoom_to

# --- Helpers --------------------------------------------------------------------


def editor(win):
    return win.editor


def type_text(win, text, pace=0.07, seed=3):
    """Types like a person, a little unevenly; Enter goes through the editor, so lists continue."""
    noise = random.Random(seed)
    buffer = editor(win).buffer
    for char in text:
        if char == "\n":
            if not editor(win)._continue_list():
                buffer.insert_at_cursor("\n")
            yield pace * 4
            continue
        buffer.insert_at_cursor(char)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if char == " ":
            pause += pace * 0.6
        elif char in ",.:":
            pause += pace * 3
        yield pause


def select_word(win, word):
    """Selects the last place of `word` in the sheet, as a double-click would."""
    buffer = editor(win).buffer
    text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
    start = text.rindex(word)
    buffer.select_range(buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(start + len(word)))


def cursor_to_end(win):
    buffer = editor(win).buffer
    buffer.place_cursor(buffer.get_end_iter())


def bar_button(win, kind):
    """The button of the formatting bar for `kind` (bold, italic …)."""
    child = win.format_bar.get_first_child()
    while child is not None:
        target = child.get_action_target_value() if hasattr(child, "get_action_target_value") else None
        if target is not None and target.get_string() == kind:
            return child
        child = child.get_next_sibling()
    raise LookupError(kind)


def heading_button(win):
    from gi.repository import Gtk

    child = win.format_bar.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.MenuButton):
            return child
        child = child.get_next_sibling()
    raise LookupError("heading")


def press(button):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    button.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.35
    button.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    button.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def text_area(win):
    """The upper part of the text column, where the writing happens (the text runs down to
    about 60 % of the window by the end)."""
    width, height = win.get_width(), win.get_height()
    return (width * 0.27, 0, width * 0.6, height * 0.62)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    node(win, "Notes")[1].set_expanded(True)
    select(win, "Notes")
    win.activate_action("win.new-sheet", None)


def intro(win):
    yield 1.5
    zoom_to(text_area(win), length=12.0, margin=0.04)  # slowly, through the next scene


def why(win):
    yield 1.0


def no_learning(win):
    yield 0.5


def headings(win):
    yield from type_text(win, "# The Keeper\n\n")
    yield 0.8
    yield from type_text(win, "## His Nights\n\n")


def bold_italic(win):
    yield from type_text(win, "Every night he climbed the stairs, **storm** or *quiet*.\n\n")


def lists(win):
    yield from type_text(win, "He kept three things in order:\n\n- the lamp\nthe logbook\nthe stove")
    yield 0.6


def formatting_bar(win):
    from gi.repository import GLib

    yield zoom_to(None, length=1.0)
    select_word(win, "logbook")
    yield 1.2
    yield from press(bar_button(win, "bold"))
    win.activate_action("win.format", GLib.Variant.new_string("bold"))
    yield 1.2
    cursor_to_end(win)
    yield from type_text(win, "\n\n\nNight Log")
    yield 0.6
    from gi.repository import Gtk

    button = heading_button(win)
    button.get_popover().set_position(Gtk.PositionType.TOP)  # below the window, it would not be recorded
    yield from press(button)
    button.popup()
    yield 1.4
    button.popdown()
    win.activate_action("win.format", GLib.Variant.new_string("h2"))
    yield 1.0


def shortcuts(win):
    from gi.repository import GLib

    yield zoom_to(text_area(win), length=1.0, margin=0.04)
    select_word(win, "stairs")
    yield 1.0
    win.activate_action("win.format", GLib.Variant.new_string("italic"))
    yield 1.0
    cursor_to_end(win)


def closing(win):
    yield 0.5
    yield zoom_to(None, length=1.2)


SCENES = [
    Scene(
        "Typecase writes in Markdown: plain text with a few characters for formatting.",
        "Typecase schreibt in Markdown: ganz normaler Text mit ein paar Zeichen zum Formatieren.",
        intro,
        say="Type case writes in Markdown: plain text, with a few characters for formatting.",
    ),
    Scene(
        "Why? Your texts stay ordinary text files. Any app on any computer can open them, today and in twenty "
        "years. And you write without fiddling with layout: the look comes later, when you export to PDF or "
        "Word.",
        "Warum? Deine Texte bleiben ganz normale Textdateien. Jede App auf jedem Computer kann sie öffnen, heute "
        "und in zwanzig Jahren. Und du schreibst, ohne am Layout herumzubasteln: Das Aussehen kommt später, beim "
        "Export als PDF oder Word.",
        why,
    ),
    Scene(
        "You don't have to learn the characters first. Here are the few you need.",
        "Du musst die Zeichen nicht vorher lernen. Hier sind die wenigen, die du brauchst.",
        no_learning,
    ),
    Scene(
        "A hash sign starts a heading, two of them a smaller one.",
        "Ein Rautenzeichen beginnt eine Überschrift, zwei eine kleinere.",
        headings,
    ),
    Scene(
        "Two asterisks around a word make it bold, one makes it italic. The characters stay, but fade into the "
        "background.",
        "Zwei Sternchen um ein Wort machen es fett, eines kursiv. Die Zeichen bleiben, treten aber in den "
        "Hintergrund.",
        bold_italic,
    ),
    Scene(
        "A dash starts a list. Press Enter, and the next item begins by itself.",
        "Ein Minus beginnt eine Liste. Drücke Enter, und der nächste Punkt beginnt von selbst.",
        lists,
    ),
    Scene(
        "Rather not type the characters? Select a word and use the bar at the bottom. It also turns a line into "
        "a heading.",
        "Du möchtest die Zeichen lieber nicht tippen? Markiere ein Wort und nimm die Leiste unten. Sie macht auch "
        "aus einer Zeile eine Überschrift.",
        formatting_bar,
    ),
    Scene(
        "Or use the keyboard: Ctrl+B for bold, Ctrl+I for italic, Ctrl+1 to 3 for headings.",
        "Oder nimm die Tastatur: Strg+B für fett, Strg+I für kursiv, Strg+1 bis 3 für Überschriften.",
        shortcuts,
        say="Or use the keyboard: Control B for bold, Control I for italic, Control one to three for headings.",
    ),
    Scene(
        "That's all you need. Everything else is just writing.",
        "Mehr brauchst du nicht. Alles andere ist einfach Schreiben.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="markdown",
    title="Markdown and the formatting bar",
    topic="Write",
    summary="Why Typecase writes in Markdown, the few characters you need, and how to format without them.",
    still=50,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
