"""Explainer video: giving sheets and groups their own icon and color.

    python3 tools/video/icons-and-colors.py

Writes dist/videos/icons-and-colors/icons-and-colors.webm and .mp4, with English and German
subtitles. While it records, a Typecase window floats in the middle of the screen for
about a minute; leave it visible and don't touch it."""

import videokit
from actions import library_rows, menu_area, node, right_click, select, set_look, walk_to
from videokit import Scene, zoom_to

# --- The scenes -----------------------------------------------------------------


def opening(win):
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "02 The Storm")
    win.editor.focus_editor()


def intro(win):
    yield 3.2
    yield zoom_to(library_rows(win), length=1.6)
    yield 2.0


def open_dialog(win):
    yield 1.0
    right_click(win, "The Lighthouse Keeper")
    yield 0.3
    zoom_to(menu_area(win, "The Lighthouse Keeper"), length=0.9, margin=0.04)
    yield 2.0
    win.row_menu.popdown()
    win.activate_action("win.look", None)
    yield 0.4
    zoom_to(win.get_visible_dialog().get_child(), length=0.9, margin=0.05)


def pick_color(win):
    from typecase import looks

    yield 0.5
    dialog = win.get_visible_dialog()
    yield from walk_to(dialog.color_box, 0, 1 + looks.COLORS.index("purple"), pause=0.3)


def pick_icon(win):
    from typecase import looks

    dialog = win.get_visible_dialog()
    yield 0.3
    yield from walk_to(dialog.icon_box, 0, 1 + list(looks.ICON_NAMES).index("book"), pause=0.22)
    yield 1.2
    dialog.apply()
    yield 0.2
    zoom_to(library_rows(win), length=1.0)


def the_others(win):
    select(win, "02 The Storm")  # back to the chapter with the picture
    yield 0.8
    for row, icon, color in [
        ("Characters", "person", "teal"),
        ("Places", "place", "green"),
        ("Ideas", "idea", "yellow"),
        ("Open Questions", "question", "red"),
        ("02 The Storm", "star", "orange"),
    ]:
        set_look(win, row, icon, color)
        yield 1.0


def dark(win):
    from gi.repository import Adw

    zoom_to(None, length=1.2)
    yield 1.4
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    yield 2.6
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)


SCENES = [
    Scene(
        "This is Typecase, a calm writing app for Linux. Your library is a folder of plain Markdown files, "
        "and at first, every group and sheet looks the same.",
        "Das ist Typecase, eine ruhige Schreib-App für Linux. Deine Bibliothek ist ein Ordner mit ganz normalen "
        "Markdown-Dateien, und anfangs sehen alle Gruppen und Blätter gleich aus.",
        intro,
    ),
    Scene(
        "To make a group stand out, right-click it and choose Icon and Color.",
        "Damit eine Gruppe heraussticht, klickst du sie mit der rechten Maustaste an und wählst „Icon und Farbe“.",
        open_dialog,
    ),
    Scene(
        "Pick one of the nine accent colors from GNOME,",
        "Such dir eine der neun Akzentfarben von GNOME aus,",
        pick_color,
    ),
    Scene(
        "then one of twenty-eight icons. Apply, and the group shows them right away.",
        "und dann eines von achtundzwanzig Icons. Übernehmen, und die Gruppe zeigt beides sofort.",
        pick_icon,
        hold=0.4,
    ),
    Scene(
        "Give the other groups and sheets their own look, too. "
        "Characters, places, ideas and open questions now stand out at a glance.",
        "Gib auch den anderen Gruppen und Blättern ihr eigenes Aussehen. "
        "Figuren, Orte, Ideen und offene Fragen fallen jetzt auf einen Blick auf.",
        the_others,
    ),
    Scene(
        "The colors follow the light and dark style.",
        "Die Farben passen sich dem hellen und dunklen Stil an.",
        dark,
        hold=0.4,
    ),
    Scene(
        "And nothing is hidden away: a sheet keeps its icon and color in its front matter, a group in its own "
        "folder, so they travel along when you move, copy or sync them.",
        "Und nichts ist versteckt: Ein Blatt speichert Icon und Farbe in seinem Dateikopf, eine Gruppe in ihrem "
        "eigenen Ordner. So wandern sie mit, wenn du sie verschiebst, kopierst oder synchronisierst.",
    ),
]

VIDEO = videokit.Video(
    name="icons-and-colors",
    title="Icons and colors",
    topic="Organize your texts",
    summary="Give groups and sheets an icon and a color, so they stand out in your library at a glance.",
    still=32,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
