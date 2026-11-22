"""Explainer video: focus mode, with typewriter scrolling, dimmed surroundings and settings of its own.

    python3 tools/video/focus-mode.py

Writes dist/videos/focus-mode/focus-mode.webm and .mp4, with English and German subtitles. While it
records, a Typecase window floats in the middle of the screen for about a minute and a half;
leave it visible and don't touch it. Focus mode would go full screen; the recording keeps the
window as it is."""

import random

import videokit
from actions import node, select
from videokit import HEIGHT, WIDTH, Scene, zoom_to

TYPED = ("\n\nShe found the matches where they had always been, in the tin above the stove. "
         "The flame caught on the second try, and the room grew warm and small around it.")

# --- Helpers --------------------------------------------------------------------


def boolean(value):
    from gi.repository import GLib

    return GLib.Variant.new_boolean(value)


def type_text(win, text, pace=0.06, seed=5):
    """Types like a person, a little unevenly, with short pauses after words and sentences."""
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


def cursor_into(win, words):
    """Puts the cursor at the end of the paragraph with `words`, as the arrow keys would."""
    view = win.editor.view
    buffer = win.editor.buffer
    text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
    end = text.index("\n", text.index(words))
    view._keyboard_moved = True  # typewriter scrolling follows the keyboard, not the mouse
    buffer.place_cursor(buffer.get_iter_at_offset(end))


def cursor_to_end(win):
    win.editor.view._keyboard_moved = True
    buffer = win.editor.buffer
    buffer.place_cursor(buffer.get_end_iter())


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def main_menu(win):
    from gi.repository import Gtk

    for widget in walk(win):
        if isinstance(widget, Gtk.MenuButton) and widget.get_primary():
            return widget
    raise LookupError("main menu")


def press(button):
    """Shows a button as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    button.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.35
    button.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    button.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def scroll_to(widget, length=1.0, above=24):
    """Scrolls the preferences smoothly until `widget` is near the top."""
    from gi.repository import Graphene, Gtk

    scrolled = widget.get_ancestor(Gtk.ScrolledWindow)
    adjustment = scrolled.get_vadjustment()
    _found, point = widget.compute_point(scrolled, Graphene.Point().init(0, 0))
    start = adjustment.get_value()
    target = min(start + point.y - above, adjustment.get_upper() - adjustment.get_page_size())
    frames = max(1, round(length * 30))
    for frame in range(1, frames + 1):
        u = frame / frames
        adjustment.set_value(start + (target - start) * u * u * (3 - 2 * u))
        yield 1 / 30


def text_middle():
    """The middle of the text column, where typewriter scrolling keeps the line."""
    return (WIDTH * 0.2, HEIGHT * 0.3, WIDTH * 0.6, HEIGHT * 0.4)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    win.fullscreen = lambda: None
    win.unfullscreen = lambda: None
    for group in ("The Lighthouse Keeper", "Manuscript"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()
    cursor_to_end(win)


def intro(win):
    yield 1.5


def enter(win):
    from gi.repository import Gtk

    menu = main_menu(win)
    popover = menu.get_popover()
    popover.set_position(Gtk.PositionType.BOTTOM)
    popover.set_offset(-130, 0)  # straight below the button, it would reach past the window
    yield zoom_to((WIDTH - 560, 0, 560, 400), length=0.8, factor=1.5)
    yield from press(menu)
    menu.popup()
    yield 1.8
    menu.popdown()
    yield zoom_to(None, length=0.6)
    win.lookup_action("focus-mode").change_state(boolean(True))
    win.editor.focus_editor()
    cursor_to_end(win)
    yield 1.0


def typewriter(win):
    zoom_to(text_middle(), length=2.0, factor=1.3)
    yield 0.6
    yield from type_text(win, TYPED)
    yield 0.6


def dim(win):
    yield zoom_to(None, length=1.2)
    yield 0.6
    cursor_into(win, "The lighthouse stood")
    yield 2.2
    cursor_to_end(win)
    yield 1.0


def pointer_watch(win, on):
    """Focus mode hides the header bar again when the pointer moves over the text; the real
    pointer, wherever it is, must not do that during the recording."""
    from gi.repository import Gtk

    controllers = win.content_view.observe_controllers()
    for index in range(controllers.get_n_items()):
        controller = controllers.get_item(index)
        if isinstance(controller, Gtk.EventControllerMotion):
            controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE if on else Gtk.PropagationPhase.NONE)


def tools(win):
    yield 1.2
    pointer_watch(win, False)
    win.content_view.set_reveal_top_bars(True)
    yield 2.6
    win.content_view.set_reveal_top_bars(False)
    pointer_watch(win, True)
    yield 0.6


def preferences(win):
    win.activate_action("win.preferences", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield from scroll_to(dialog.focus_same, length=1.4, above=120)
    yield 0.8
    dialog.focus_same.set_active(False)
    yield 1.0
    yield from scroll_to(dialog.focus_page.color_scheme, length=1.2, above=60)
    yield 0.6
    dialog.focus_page.color_scheme.set_selected(2)  # Dark
    yield 1.2
    dialog.focus_page._choose_theme("typecase-calm")
    yield 1.4
    yield from scroll_to(dialog.focus_typewriter, length=1.2, above=160)
    yield 1.6
    dialog.close()
    yield zoom_to(None, length=1.0)
    yield 1.0


def leave(win):
    yield 0.6
    win.lookup_action("focus-mode").change_state(boolean(False))
    yield 1.4


def closing(win):
    yield 1.0


SCENES = [
    Scene(
        "Sometimes you want nothing on screen but your text. That's what focus mode is for.",
        "Manchmal willst du nichts auf dem Bildschirm außer deinem Text. Dafür gibt es den Fokus-Modus.",
        intro,
    ),
    Scene(
        "Press Ctrl+Shift+Enter, or choose Focus Mode from the menu. The sidebar and toolbars step aside.",
        "Drücke Strg+Umschalt+Enter oder wähle „Fokus-Modus“ im Menü. Seitenleiste und Werkzeugleisten treten "
        "zur Seite.",
        enter,
        say="Press Control Shift Enter, or choose Focus Mode from the menu. The sidebar and toolbars step aside.",
    ),
    Scene(
        "As you type, the line you're writing stays in the middle of the screen, like on a typewriter. Your eyes "
        "don't have to wander.",
        "Beim Tippen bleibt die Zeile, an der du schreibst, in der Mitte, wie bei einer Schreibmaschine. Deine "
        "Augen müssen nicht wandern.",
        typewriter,
    ),
    Scene(
        "Everything except the paragraph you're working on fades into the background.",
        "Alles außer dem Absatz, an dem du gerade arbeitest, tritt in den Hintergrund.",
        dim,
    ),
    Scene(
        "The formatting bar stays at hand. Move the pointer to the top edge, and the header bar comes back.",
        "Die Formatierungsleiste bleibt griffbereit. Fährst du mit dem Mauszeiger an den oberen Rand, kommt die "
        "Kopfleiste zurück.",
        tools,
    ),
    Scene(
        "In the preferences, focus mode can have its own font, size and theme, like a dark one just for writing. "
        "You can also switch off typewriter scrolling and dimming there.",
        "In den Einstellungen bekommt der Fokus-Modus auf Wunsch eigene Schrift, Größe und ein eigenes Thema, "
        "etwa ein dunkles nur zum Schreiben. Dort kannst du auch Schreibmaschinen-Scrollen und Abdunkeln "
        "ausschalten.",
        preferences,
    ),
    Scene(
        "Press Escape to leave focus mode. Everything is back where it was.",
        "Drücke Escape, um den Fokus-Modus zu verlassen. Alles ist wieder da, wo es war.",
        leave,
    ),
    Scene(
        "Just you and your text.",
        "Nur du und dein Text.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="focus-mode",
    title="Focus mode",
    topic="Write",
    summary="Hide everything but your text, with typewriter scrolling, dimmed surroundings and settings of its own.",
    still=28,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
