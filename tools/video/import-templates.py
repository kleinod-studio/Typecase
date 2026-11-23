"""Explainer video: import a template file, share one as a file, and export with it.

    python3 tools/video/import-templates.py

Writes dist/videos/import-templates/import-templates.webm and .mp4, with English and German
subtitles. Needs the installed Typecase Flatpak (for the export) and Papers (to show the result),
which runs with temporary settings of its own. While it records, a Typecase window floats in the
middle of the screen for about a minute and Papers opens over it; leave it visible and don't touch it.

The file choosers are left out (they would show your own folders): the template file is made
beforehand and imported the way the Import button does it after the file is chosen."""

import importlib.util
import json
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("export_a_sheet", HERE / "export-a-sheet.py")
sheet_video = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet_video)
press, area, temp, choose, walk = sheet_video.press, sheet_video.area, sheet_video.temp, sheet_video.choose, sheet_video.walk
bring_in, close, open_button = sheet_video.bring_in, sheet_video.close, sheet_video.open_button

NAME = "Double-Spaced Draft"
DESCRIPTION = "Wide margins and double spacing, for notes by hand"
SHEET = "The Lighthouse Keeper/Manuscript/03 The Letter.md"
STATE = {}

# --- Helpers --------------------------------------------------------------------


def make_template_file(work):
    """A template file as someone else would send it: made with the assistant's builder, with a
    description of its own and without the assistant's settings."""
    from typecase import export_templates, template_builder
    from typecase.template_builder import Settings

    settings = Settings(name=NAME, margin_left=35, margin_right=35, body_font="DejaVu Sans", body_size=11,
                        line_spacing=2.0, heading_font="DejaVu Sans", page_numbers="right")
    template = template_builder.save(settings, work / "made")
    info_file = template.path / "template.json"
    info = json.loads(info_file.read_text(encoding="utf-8"))
    info["description"] = DESCRIPTION
    info.pop(template_builder.SETTINGS_KEY, None)
    info_file.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    file = work / f"{NAME}{export_templates.EXTENSION}"
    export_templates.pack(export_templates.read_folder(template.path, builtin=False), file)
    return template.path, file


def row_of(prefs, title):
    from gi.repository import Adw

    for widget in walk(prefs.templates_page):
        if isinstance(widget, Adw.ActionRow) and widget.get_title() == title:
            return widget
    raise LookupError(title)


def button_in(row, tooltip):
    from gi.repository import Gtk

    for widget in walk(row):
        if isinstance(widget, Gtk.Button) and widget.get_tooltip_text() == tooltip:
            return widget
    raise LookupError(tooltip)


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import export_dialog

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    work = temp("typecase-video-import-")
    folder, STATE["file"] = make_template_file(work)
    STATE["pdf"] = work / "03 The Letter.pdf"
    sheet_video.export(win.library_path / SHEET, folder, "pdf", STATE["pdf"])
    sheet_video.start_papers(STATE["pdf"])
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "03 The Letter")
    win.editor.focus_editor()


def intro(win):
    yield 2.2


def import_it(win):
    yield 0.4
    win.activate_action("win.preferences", None)
    yield 0.8
    STATE["prefs"] = prefs = win.get_visible_dialog()
    prefs.set_visible_page(prefs.templates_page)
    yield 1.0
    yield from press(prefs.templates_page.import_button)
    yield 0.6
    prefs.templates_page._install(STATE["file"])
    yield 2.4


def where_from(win):
    row = row_of(STATE["prefs"], NAME)
    yield zoom_to(area(win, row, margin=40), length=1.0, factor=1.5)
    yield 4.2


def share(win):
    row = row_of(STATE["prefs"], NAME)
    yield 0.4
    yield from press(button_in(row, "Save as File…"))
    yield 2.4
    yield zoom_to(None, length=0.8)
    yield 0.4


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


def closing(win):
    close("org.gnome.Papers")
    yield 1.4


SCENES = [
    Scene(
        "Need a special layout? Import a template file.",
        "Du brauchst ein besonderes Layout? Importiere eine Vorlagen-Datei.",
        intro,
    ),
    Scene(
        "In the preferences, under Templates, choose Import.",
        "In den Einstellungen wählst du unter Vorlagen „Importieren“.",
        import_it,
    ),
    Scene(
        "Template files end in .typecase-template. Someone can make one for you, or Claude with the Typecase skill.",
        "Vorlagen-Dateien enden auf .typecase-template. Jemand kann dir eine machen, oder Claude mit dem Typecase-Skill.",
        where_from,
        say="Template files end in dot typecase template. Someone can make one for you, or Claude with the Typecase skill.",
    ),
    Scene(
        "Share your own templates the same way: save one as a file.",
        "Eigene Vorlagen teilst du genauso: als Datei speichern.",
        share,
    ),
    Scene(
        "Choose it when you export.",
        "Wähle sie beim Exportieren.",
        use_it,
    ),
    Scene(
        "Any look, one file away.",
        "Jedes Aussehen, nur eine Datei entfernt.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="import-templates",
    title="Import templates",
    topic="Share",
    summary="Import a template file, made by someone else or by Claude with the Typecase skill, and share your own.",
    still=12,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
