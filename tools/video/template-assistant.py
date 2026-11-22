"""Explainer video: make an export template with the assistant, use it, and change it later.

    python3 tools/video/template-assistant.py

Writes dist/videos/template-assistant/template-assistant.webm and .mp4, with English and German
subtitles. Needs the installed Typecase Flatpak (for the export) and Papers (to show the result),
which runs with temporary settings of its own. While it records, a Typecase window floats in the
middle of the screen for about a minute and Papers opens over it; leave it visible and don't touch it.

As in export-a-sheet.py, the file chooser is left out: the PDF is exported beforehand with the same
settings the assistant ends up with, and the dialog's toast opens it."""

import importlib.util
import os
import random
from dataclasses import replace
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

os.environ["LC_NUMERIC"] = "en_US.UTF-8"  # decimal points in the spin rows, as an English user sees them
HERE = Path(__file__).resolve().parent
# The helpers for exporting and for showing other apps over the recording
_spec = importlib.util.spec_from_file_location("export_a_sheet", HERE / "export-a-sheet.py")
sheet_video = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet_video)
press, area, temp, choose, walk = sheet_video.press, sheet_video.area, sheet_video.temp, sheet_video.choose, sheet_video.walk
bring_in, close, open_button = sheet_video.bring_in, sheet_video.close, sheet_video.open_button

NAME = "Paperback"
SHEET = "The Lighthouse Keeper/Manuscript/01 Arrival.md"
CHANGES = {"body_font": "DejaVu Serif", "body_size": 11, "margin_top": 24}  # what the video changes after the preset
STATE = {}

# --- Helpers --------------------------------------------------------------------


def type_into(entry, text, pace=0.07, seed=5):
    """Types into an entry, over its text."""
    noise = random.Random(seed)
    entry.grab_focus()
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        pause = pace * (1 + noise.uniform(-0.35, 0.35))
        yield pause + (pace * 0.6 if text[count - 1] == " " else 0)


def spin_to(row, value, steps=None, pace=0.12):
    """Counts a spin row up or down to value, the way clicking its buttons does."""
    yield from press(row)
    start = row.get_value()
    steps = steps or max(1, round(abs(value - start) / row.get_adjustment().get_step_increment()))
    for step in range(1, steps + 1):
        row.set_value(start + (value - start) * step / steps)
        yield pace


def scroll_to(dialog, widget, length=0.9):
    """Scrolls the dialog's page smoothly until widget is in its upper part."""
    from gi.repository import Gtk

    scrolled = next(w for w in walk(dialog) if isinstance(w, Gtk.ScrolledWindow))
    adjustment = scrolled.get_vadjustment()
    _found, bounds = widget.compute_bounds(scrolled)
    start = adjustment.get_value()
    target = min(start + bounds.get_y() - 40, adjustment.get_upper() - adjustment.get_page_size())
    frames = int(length * 30)
    for frame in range(1, frames + 1):
        t = frame / frames
        adjustment.set_value(start + (target - start) * (3 * t * t - 2 * t * t * t))
        yield 1 / 30


def open_templates(win):
    win.activate_action("win.preferences", None)
    yield 0.8
    STATE["prefs"] = prefs = win.get_visible_dialog()
    prefs.set_visible_page(prefs.templates_page)
    yield 0.6


def edit_button(prefs):
    from gi.repository import Gtk

    for widget in walk(prefs.templates_page):
        if isinstance(widget, Gtk.Button) and widget.get_tooltip_text() == "Edit":
            return widget
    raise LookupError("Edit")


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import export_dialog, template_builder

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    work = temp("typecase-video-template-")
    novel = template_builder.presets()["novel"][1]
    template_builder.save(replace(novel, name=NAME, **CHANGES), work / "templates")
    folder = next(path for path in (work / "templates").iterdir() if path.is_dir() and not path.name.startswith("."))
    STATE["pdf"] = work / "01 Arrival.pdf"
    sheet_video.export(win.library_path / SHEET, folder, "pdf", STATE["pdf"])
    sheet_video.start_papers(STATE["pdf"], paged=True)
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "01 Arrival")
    win.editor.focus_editor()


def intro(win):
    yield 2.2


def new_template(win):
    yield 0.4
    yield from open_templates(win)
    yield 0.6
    yield from press(STATE["prefs"].templates_page.new_button)
    STATE["prefs"].templates_page._open_assistant()
    yield 0.8
    STATE["dialog"] = win.get_visible_dialog()
    yield 1.0


def starting_point(win):
    dialog = STATE["dialog"]
    yield from type_into(dialog.name_row, NAME)
    yield 0.6
    yield from choose(dialog.preset_row, "Novel")
    yield 2.2


def adjust(win):
    dialog = STATE["dialog"]
    yield 0.3
    yield from spin_to(dialog.margin_rows["top"], CHANGES["margin_top"])
    yield 0.6
    yield from scroll_to(dialog, dialog.body_font_row)
    yield 0.3
    yield from choose(dialog.body_font_row, CHANGES["body_font"])
    yield 0.6
    yield from spin_to(dialog.size_row, CHANGES["body_size"])
    yield 1.2


def create(win):
    dialog = STATE["dialog"]
    yield from press(dialog.save_button)
    dialog._save()
    yield 2.8


def use_it(win):
    STATE["prefs"].close()
    yield 0.6
    win.activate_action("win.export", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=0.8, factor=1.4)
    yield from choose(dialog.format_row, "PDF")
    yield 0.5
    yield from choose(dialog.template_row, NAME)
    yield 0.8
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.3
    win._on_exported(STATE["pdf"], None, [])
    yield 1.0
    yield from press(open_button(win))
    yield from bring_in("org.gnome.Papers", 1280, 720, sheet_video.X, sheet_video.Y)
    yield 4.0


def edit_later(win):
    close("org.gnome.Papers")
    yield 1.0
    yield from open_templates(win)
    button = edit_button(STATE["prefs"])
    yield from press(button)
    button.emit("clicked")
    yield 0.8
    dialog = win.get_visible_dialog()
    yield from scroll_to(dialog, dialog.spacing_row)
    yield 0.3
    yield from spin_to(dialog.spacing_row, 1.4, pace=0.15)
    yield 0.8
    yield from press(dialog.save_button)
    dialog._save()
    yield 2.0


def closing(win):
    STATE["prefs"].close()
    yield 1.6


SCENES = [
    Scene(
        "Give your exports a look of your own. No code needed.",
        "Gib deinen Exporten ein eigenes Aussehen. Ganz ohne Code.",
        intro,
    ),
    Scene(
        "Open the preferences with Ctrl+Comma. Under Templates, choose New.",
        "Öffne die Einstellungen mit Strg+Komma. Unter Vorlagen wählst du Neu.",
        new_template,
        say="Open the preferences with Control Comma. Under Templates, choose New.",
    ),
    Scene(
        "Name it and pick a starting point. It fills in every setting.",
        "Gib ihr einen Namen und wähle einen Ausgangspunkt. Er füllt alle Einstellungen aus.",
        starting_point,
    ),
    Scene(
        "Then change what you like: paper, margins, fonts, page numbers.",
        "Dann änderst du, was du möchtest: Papier, Ränder, Schriften, Seitenzahlen.",
        adjust,
    ),
    Scene(
        "Create it. One template for PDF, Word and HTML.",
        "Erstellen. Eine Vorlage für PDF, Word und HTML.",
        create,
    ),
    Scene(
        "Choose it when you export.",
        "Wähle sie beim Exportieren.",
        use_it,
    ),
    Scene(
        "Change it any time with the pencil button.",
        "Mit dem Stift änderst du sie jederzeit.",
        edit_later,
    ),
    Scene(
        "Your book, your look.",
        "Dein Buch, dein Aussehen.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="template-assistant",
    title="Template assistant",
    topic="Share",
    summary="Make your own export template from a starting point and a few settings, use it, and change it later.",
    still=20,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
