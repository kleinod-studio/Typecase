"""Explainer video: a group's sheets as cards with their notes, to plan and reorder a story.

    python3 tools/video/cards-view.py

Writes dist/videos/cards/cards.webm and .mp4, with English and German subtitles. While it records,
a Typecase window floats in the middle of the screen for about a minute; leave it visible and don't
touch it. Before it starts, the sample chapters and characters get short notes, so that the cards
have something to show. (The file is not called cards.py: that name belongs to the title cards.)"""

import random

import videokit
from actions import node, select
from videokit import Scene, zoom_to

NOTES = {
    "The Lighthouse Keeper/Manuscript/01 Arrival": "Ada arrives. The island, the tower, her father's log.",
    "The Lighthouse Keeper/Manuscript/02 The Storm": "The storm. Ada keeps the light. A small light on the water.",
    "The Lighthouse Keeper/Manuscript/03 The Letter": "The stranger: Elias. The letter she was told to keep closed.",
    "The Lighthouse Keeper/Manuscript/04 Low Tide": "The causeway shows. Ada and Elias walk out to the old wreck.",
    "The Lighthouse Keeper/Manuscript/05 The Keeper's Log": "The stars in the margin. What did her father count?",
    "The Lighthouse Keeper/Characters/Ada Morrow": "Stubborn, careful, never asks for help.",
    "The Lighthouse Keeper/Characters/Elias": "Knows more about the island than he says.",
    "The Lighthouse Keeper/Places/Skerry Island": "112 steps. The light turns every ten seconds.",
}
TYPED = "Fog for three days. Elias wants to leave, Ada won't let him."

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def type_buffer(buffer, text, pace=0.055, seed=6):
    """Types at the cursor like a person, a little unevenly."""
    noise = random.Random(seed)
    for char in text:
        buffer.insert_at_cursor(char)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        if char == " ":
            pause += pace * 0.6
        elif char in ",.":
            pause += pace * 3
        yield pause


def press(widget):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def cards_toggle(win):
    """The button of the Cards toggle in the header bar."""
    from gi.repository import Gtk

    for widget in walk(win.group_mode):
        if isinstance(widget, Gtk.Label) and widget.get_label() == "Cards":
            button = widget
            while not isinstance(button, Gtk.Button) and button.get_parent() is not None:
                button = button.get_parent()
            return button
    raise LookupError("Cards")


def card(win, stem):
    return next(card for card in win.group_view.cards.cards if card.path.stem == stem)


def area(win, widget, margin=24):
    _found, bounds = widget.compute_bounds(win)
    return (bounds.get_x() - margin, bounds.get_y() - margin, bounds.get_width() + 2 * margin, bounds.get_height() + 2 * margin)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase.cards import save_notes

    for sheet, notes in NOTES.items():
        save_notes(win.library_path / f"{sheet}.md", "", notes)
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 2.0


def switch(win):
    select(win, "Manuscript")
    yield 1.4
    yield from press(cards_toggle(win))
    win.group_mode.set_active_name("cards")
    yield 2.4


def one_card(win):
    yield zoom_to(area(win, card(win, "02 The Storm")), length=1.0, factor=1.5)
    yield 3.4
    yield zoom_to(None, length=0.8)


def write(win):
    notes = card(win, "06 Fog").notes
    notes.grab_focus()
    yield 0.6
    yield from type_buffer(notes.get_buffer(), TYPED)
    yield 1.4


def reorder(win):
    target = card(win, "05 The Keeper's Log")
    target.notes.grab_focus()
    yield 1.0
    win.group_view.cards.move_step(target, -1)
    yield 2.6


def subgroups(win):
    select(win, "The Lighthouse Keeper")
    yield 1.2
    yield from press(cards_toggle(win))
    win.group_mode.set_active_name("cards")
    yield 2.8


def open_sheet(win):
    title = card(win, "Elias").title
    yield from press(title)
    title.emit("clicked")
    yield 2.2


def remembered(win):
    select(win, "Manuscript")
    yield 2.6


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Before you write, you plan. Cards show your story at a glance.",
        "Bevor du schreibst, planst du. Karten zeigen deine Geschichte auf einen Blick.",
        intro,
    ),
    Scene(
        "Select a group and click Cards, or press Ctrl+Alt+C. Each sheet becomes a card.",
        "Wähle eine Gruppe und klicke auf „Karten“, oder drücke Strg+Alt+C. Jedes Blatt wird zu einer Karte.",
        switch,
        say="Select a group and click Cards, or press Control Alt C. Each sheet becomes a card.",
    ),
    Scene(
        "A card shows the title, status and keywords of its sheet, its word count, and your notes.",
        "Eine Karte zeigt Titel, Status und Schlagwörter des Blatts, seine Wortzahl und deine Notizen.",
        one_card,
    ),
    Scene(
        "Write your notes right on the card. They're saved with the sheet.",
        "Du schreibst deine Notizen direkt auf die Karte. Sie werden mit dem Blatt gespeichert.",
        write,
    ),
    Scene(
        "Drag a card to change the order of your sheets, or use Alt and the arrow keys.",
        "Ziehe eine Karte, um die Reihenfolge deiner Blätter zu ändern, oder nimm Alt und die Pfeiltasten.",
        reorder,
    ),
    Scene(
        "A group with subgroups shows a block of cards for each.",
        "Eine Gruppe mit Untergruppen zeigt für jede einen eigenen Block Karten.",
        subgroups,
    ),
    Scene(
        "Click a title to open the sheet and write.",
        "Ein Klick auf einen Titel öffnet das Blatt zum Schreiben.",
        open_sheet,
    ),
    Scene(
        "Typecase remembers which groups you like to see as cards.",
        "Typecase merkt sich, welche Gruppen du als Karten sehen willst.",
        remembered,
        say="Type case remembers which groups you like to see as cards.",
    ),
    Scene(
        "Plan with cards, write with words.",
        "Mit Karten planen, mit Worten schreiben.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="cards",
    title="Cards",
    topic="Plot",
    summary="See the sheets of a group as cards with their notes, write on them, and change the order of your story.",
    still=12,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
