"""Explainer video: export a whole group as one PDF, with a cover page, a table of contents and its
subgroups as parts.

    python3 tools/video/export-a-group.py

Writes dist/videos/export-a-group/export-a-group.webm and .mp4, with English and German subtitles.
Needs the installed Typecase Flatpak (for the export) and Papers (to show the result), which runs
with temporary settings of its own. While it records, a Typecase window floats in the middle of the
screen for about a minute and Papers opens over it; leave it visible and don't touch it.

Before it starts, the sample manuscript is split into two parts (subgroups), and the author in the
preferences is set. As in export-a-sheet.py, the file chooser is left out: the PDF is exported
beforehand, the way the dialog does it, and the dialog's toast opens it."""

import importlib.util
import random
import subprocess
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
# The helpers for exporting and for showing other apps over the recording
_spec = importlib.util.spec_from_file_location("export_a_sheet", HERE / "export-a-sheet.py")
sheet_video = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet_video)
press, area, temp, choose = sheet_video.press, sheet_video.area, sheet_video.temp, sheet_video.choose
bring_in, close, key_to, open_button = sheet_video.bring_in, sheet_video.close, sheet_video.key_to, sheet_video.open_button

BOOK = "The Lighthouse Keeper"
AUTHOR = "Ada Morrow"
PARTS = {"Part One: The Island": ("01 Arrival", "02 The Storm", "03 The Letter"),
         "Part Two: The Letter": ("04 Low Tide", "05 The Keeper's Log", "06 Fog")}
STATE = {}

# --- Helpers --------------------------------------------------------------------


def type_into(entry, text, pace=0.07, seed=4):
    """Types into an entry, over its text."""
    noise = random.Random(seed)
    entry.grab_focus()
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        yield pause + (pace * 0.6 if text[count - 1] == " " else 0)


def split_manuscript(manuscript):
    """Moves the chapters into two subgroups, the way the library does (attachments go along)."""
    from typecase import library

    for part, chapters in PARTS.items():
        folder = library.create_group(manuscript, part)
        for chapter in chapters:
            library.move(manuscript / f"{chapter}.md", folder)


def export_group(group, template, output):
    command = ["flatpak", "run", "--command=python3", "studio.kleinod.Typecase", str(HERE / "flatpak_group_export.py"),
               str(group), str(template), str(output), BOOK, AUTHOR, "title-page"]
    subprocess.run(command, check=True, capture_output=True)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import config, export_dialog

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    config.update(default_author=AUTHOR)
    manuscript = win.library_path / BOOK / "Manuscript"
    split_manuscript(manuscript)
    sheet_video.make_templates(config.TEMPLATES_DIR)
    work = temp("typecase-video-export-group-")
    sheet_video.make_templates(work / "templates")
    STATE["pdf"] = work / "Manuscript.pdf"
    export_group(manuscript, work / "templates" / "novel", STATE["pdf"])
    sheet_video.start_papers(STATE["pdf"], paged=True)
    win._reload(expand={win.library_path / BOOK, manuscript, *(manuscript / part for part in PARTS)})
    for group in ("Notes",):
        node(win, group)[1].set_expanded(True)
    select(win, "Manuscript")


def intro(win):
    yield 2.4


def open_dialog(win):
    yield 0.4
    win.activate_action("win.export", None)
    yield 0.8
    STATE["dialog"] = dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=1.0, factor=1.4)
    yield 1.4


def title(win):
    dialog = STATE["dialog"]
    yield from choose(dialog.format_row, "PDF")
    yield 0.3
    yield from choose(dialog.template_row, "Novel")
    yield 0.5
    yield from type_into(dialog.title_row, BOOK)
    yield 1.0


def structure(win):
    dialog = STATE["dialog"]
    yield 0.3
    yield from press(dialog.toc_row)
    dialog.toc_row.set_active(True)
    yield 0.7
    yield from press(dialog.cover_row)
    dialog.cover_row.set_active(True)
    yield 1.2


def parts(win):
    dialog = STATE["dialog"]
    yield 0.4
    yield from choose(dialog.parts_row, "With a Title Page")
    yield 1.8


def result(win):
    dialog = STATE["dialog"]
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.3
    win._on_exported(STATE["pdf"], None, [])
    yield 1.0
    yield from press(open_button(win))
    yield from bring_in("org.gnome.Papers", 1280, 720, sheet_video.X, sheet_video.Y)
    yield 2.6
    key_to("org.gnome.Papers", "Next")
    yield 2.4
    key_to("org.gnome.Papers", "Next")
    yield 2.0


def closing(win):
    close("org.gnome.Papers")
    yield 1.4


SCENES = [
    Scene(
        "A book is more than one sheet. Export a whole group as one document.",
        "Ein Buch ist mehr als ein Blatt. Exportiere eine ganze Gruppe als ein Dokument.",
        intro,
    ),
    Scene(
        "Select a group and press Ctrl+E. All its sheets are joined, in their order.",
        "Wähle eine Gruppe und drück Strg+E. Alle Blätter werden in ihrer Reihenfolge zusammengefügt.",
        open_dialog,
        say="Select a group and press Control E. All its sheets are joined, in their order.",
    ),
    Scene(
        "Give it a title. The author comes from the preferences.",
        "Gib ihm einen Titel. Der Autor kommt aus den Einstellungen.",
        title,
    ),
    Scene(
        "Turn on a table of contents and a cover page. In a PDF, the contents get page numbers.",
        "Schalte Inhaltsverzeichnis und Deckblatt ein. Im PDF bekommt das Inhaltsverzeichnis Seitenzahlen.",
        structure,
    ),
    Scene(
        "Subgroups become parts: one after another, each on a new page, or with a title page of its own.",
        "Untergruppen werden zu Teilen: fortlaufend, jeweils auf neuer Seite oder mit eigener Titelseite.",
        parts,
    ),
    Scene(
        "Export, and your book is ready: cover, contents, parts and chapters.",
        "Exportieren, und dein Buch ist fertig: Deckblatt, Inhalt, Teile und Kapitel.",
        result,
    ),
    Scene(
        "Write in sheets, share it as a book.",
        "In Blättern schreiben, als Buch teilen.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="export-a-group",
    title="Export a whole group",
    topic="Share",
    summary="Export all sheets of a group as one book, with a cover page, a table of contents and parts.",
    still=40,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
