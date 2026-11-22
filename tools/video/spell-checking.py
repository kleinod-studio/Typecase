"""Explainer video: spell checking while you type, suggestions, your own words, a language per sheet.

    python3 tools/video/spell-checking.py

Writes dist/videos/spell-checking/spell-checking.webm and .mp4, with English and German subtitles.
While it records, a Typecase window floats in the middle of the screen for about a minute and a
half; leave it visible and don't touch it. Words added to the dictionary go to the recording's
own configuration, not yours. It needs the German and English dictionaries, and no French one."""

import random

import videokit
from actions import node, select
from videokit import Scene, zoom_to

TYPED = " That night the lamp in the lightouse burned until dawn, and Elias rowed over from Merrow."
GERMAN = "# Notiz\n\nDer Leuchtturm stand still im Nebel, und niemand kam."

# --- Helpers --------------------------------------------------------------------


def boolean(value):
    from gi.repository import GLib

    return GLib.Variant.new_boolean(value)


def text_of(win):
    buffer = win.editor.buffer
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)


def type_text(win, text, pace=0.06, seed=7):
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


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def press(button):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    button.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.35
    button.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    button.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def spell_button(win):
    from gi.repository import Gtk

    for widget in walk(win.format_bar):
        if isinstance(widget, Gtk.ToggleButton) and widget.get_action_name() == "win.spell-check":
            return widget
    raise LookupError("spell button")


def context_menu(win, word):
    """Right-clicks into `word`: the cursor goes there and the menu with the suggestions opens.
    The menu is taller than the space below the word and would be cut off; it opens beside the
    word instead, near the top of the window."""
    from gi.repository import Gdk, Graphene, Gtk

    editor = win.editor
    view = editor.view
    buffer = editor.buffer
    start = text_of(win).index(word)
    buffer.place_cursor(buffer.get_iter_at_offset(start + 2))
    editor.spell_adapter.update_corrections()
    view.activate_action("menu.popup", None)
    popover = next(w for w in walk(view) if isinstance(w, Gtk.PopoverMenu) and w.get_visible())
    popover.set_can_target(False)  # the real pointer, wherever it is, must not hover a row
    first = view.get_iter_location(buffer.get_iter_at_offset(start))
    last = view.get_iter_location(buffer.get_iter_at_offset(start + len(word)))
    x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, first.x, first.y)
    popover.set_position(Gtk.PositionType.RIGHT)
    target = Gdk.Rectangle()
    target.x, target.y, target.width, target.height = x, y, last.x - first.x, first.height
    popover.set_pointing_to(target)
    # Centered beside the word, its top would be cut off: move it down to just below the top edge
    _found, middle = view.compute_point(win, Graphene.Point().init(0, y + first.height / 2))
    corrections = editor.spell_adapter.get_checker().list_corrections(word)
    height = 481 + 32 * len(corrections)  # measured: the fixed rows and the shadow, then a row per suggestion
    popover.set_offset(0, round(16 - (middle.y - height / 2)))
    return popover


def unselect(popover):
    """A menu opened again keeps its last row selected; nothing should look chosen yet."""
    from gi.repository import Gtk

    for widget in walk(popover):
        widget.unset_state_flags(Gtk.StateFlags.SELECTED | Gtk.StateFlags.PRELIGHT)


def menu_item(popover, label):
    """The row of the menu that shows `label`, to hover it."""
    from gi.repository import Gtk

    for widget in walk(popover):
        if isinstance(widget, Gtk.Label) and widget.get_label() == label:
            row = widget
            while row.__gtype__.name != "GtkModelButton" and row.get_parent() is not None:  # GTK's menu row
                row = row.get_parent()
            return row
    raise LookupError(label)


def choose(popover, label):
    """Hovers a menu row and closes the menu, as a click on it would."""
    from gi.repository import Gtk

    row = menu_item(popover, label)
    for widget in walk(popover):
        widget.unset_state_flags(Gtk.StateFlags.PRELIGHT | Gtk.StateFlags.SELECTED)
    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    row.grab_focus()  # otherwise the menu's first row may keep the keyboard focus, and look chosen
    yield 0.8
    row.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    popover.popdown()


def set_language(win, code):
    win.inspector.lang_row.set_selected(win.inspector._choices["lang"].index(code))


def paragraph():
    """The sheet's paragraph, where the typing happens."""
    return (440, 160, 760, 140)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    win.lookup_action("spell-check").change_state(boolean(True))
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "05 The Keeper's Log")
    win.editor.focus_editor()
    buffer = win.editor.buffer
    end = buffer.get_end_iter()
    while end.backward_char() and end.get_char() == "\n":  # right after the paragraph, on its line
        pass
    end.forward_char()
    # The sample text spells "pencilled" the British way; the sheet is checked in US English.
    start = text_of(win).index("pencilled") + 2
    buffer.place_cursor(buffer.get_iter_at_offset(start))
    win.editor.spell_adapter.update_corrections()
    win.editor.view.activate_action("spelling.ignore", None)
    buffer.place_cursor(end)


def intro(win):
    yield 1.5


def underline(win):
    yield zoom_to(paragraph(), length=1.2, factor=1.4)
    yield 0.4
    yield from type_text(win, TYPED)
    yield 1.6
    yield zoom_to(None, length=0.8)  # the menu below would reach out of the picture


def suggestions(win):
    from gi.repository import GLib

    menu = context_menu(win, "lightouse")
    yield 0.05
    unselect(menu)
    yield 1.55
    yield from choose(menu, "lighthouse")
    win.editor.view.activate_action("spelling.correct", GLib.Variant.new_string("lighthouse"))
    yield 1.4


def dictionary(win):
    menu = context_menu(win, "Merrow")
    yield 0.05
    unselect(menu)
    yield 1.55
    yield from choose(menu, "Add to Dictionary")
    win.editor.view.activate_action("spelling.add", None)
    yield 1.4


def languages(win):
    yield zoom_to(None, length=1.0)
    select(win, "Notes")
    win.activate_action("win.new-sheet", None)
    yield 0.8
    yield from type_text(win, GERMAN, pace=0.05)
    yield 1.4
    win.inspector_split.set_show_sidebar(True)
    yield 1.4
    set_language(win, "de-DE")
    yield 2.2


def switch(win):
    button = spell_button(win)
    yield 0.6
    yield from press(button)
    win.lookup_action("spell-check").change_state(boolean(False))
    yield 1.8
    yield from press(button)
    win.lookup_action("spell-check").change_state(boolean(True))
    yield 1.2


def missing(win):
    yield 0.4
    set_language(win, "fr-FR")
    yield 3.0


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Typecase checks your spelling as you type. Everything happens on your computer, without the internet.",
        "Typecase prüft deine Rechtschreibung beim Tippen. Alles passiert auf deinem Computer, ganz ohne Internet.",
        intro,
        say="Type case checks your spelling as you type. Everything happens on your computer, without the "
            "internet.",
    ),
    Scene(
        "Misspelled words get a wavy red underline.",
        "Falsch geschriebene Wörter bekommen eine rote Wellenlinie.",
        underline,
    ),
    Scene(
        "Right-click the word for suggestions, and pick the right one.",
        "Ein Rechtsklick auf das Wort zeigt Vorschläge, und du wählst den richtigen.",
        suggestions,
    ),
    Scene(
        "Names and words of your own? Add them to the dictionary, and Typecase knows them from then on.",
        "Namen und eigene Wörter? Füge sie dem Wörterbuch hinzu, dann kennt Typecase sie ab sofort.",
        dictionary,
        say="Names and words of your own? Add them to the dictionary, and Type case knows them from then on.",
    ),
    Scene(
        "Each sheet is checked in its own language. Set it in the properties, or choose a default for all "
        "sheets in the preferences.",
        "Jedes Blatt wird in seiner eigenen Sprache geprüft. Du stellst sie in den Eigenschaften ein oder legst "
        "in den Einstellungen eine Vorgabe für alle Blätter fest.",
        languages,
    ),
    Scene(
        "Press F7 or the button in the bar to switch spell checking off and on. In focus mode, it stays off "
        "unless you switch it on there.",
        "Mit F7 oder dem Knopf in der Leiste schaltest du die Prüfung aus und wieder ein. Im Fokus-Modus bleibt "
        "sie aus, bis du sie dort einschaltest.",
        switch,
        say="Press F 7, or the button in the bar, to switch spell checking off and on. In focus mode, it stays "
            "off unless you switch it on there.",
    ),
    Scene(
        "If a dictionary is missing, Typecase tells you. Our website shows how to add more languages.",
        "Fehlt ein Wörterbuch, sagt Typecase dir Bescheid. Auf unserer Website steht, wie du weitere Sprachen "
        "hinzufügst.",
        missing,
        say="If a dictionary is missing, Type case tells you. Our website shows how to add more languages.",
    ),
    Scene(
        "Fewer typos, and nothing leaves your computer.",
        "Weniger Tippfehler, und nichts verlässt deinen Computer.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="spell-checking",
    title="Spell checking",
    topic="Write",
    summary="See misspelled words as you type, fix them from the right-click menu, and check each sheet in its "
            "own language.",
    still=12,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
