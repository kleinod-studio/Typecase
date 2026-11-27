"""Explainer video: a letter with template fields. A sheet picks the built-in letter template, its
fields are filled in, the PDF puts them where a window envelope expects them, and the assistant
adds fields to a template of your own.

    python3 tools/video/template-fields.py

Writes dist/videos/template-fields/template-fields.webm and .mp4, with English and German subtitles.
Needs Papers (to show the result), which runs with temporary settings of its own. The PDF is made
beforehand with the development version (.venv with WeasyPrint, Pandoc on the PATH), as long as the
installed Flatpak has no template fields yet. While it records, a Typecase window floats in the
middle of the screen for about a minute and Papers opens over it; leave it visible and don't touch it.

As in export-a-sheet.py, the file chooser is left out: the dialog's toast opens the PDF made beforehand."""

import importlib.util
import os
import random
import subprocess
from pathlib import Path

import videokit
from actions import select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
_spec = importlib.util.spec_from_file_location("export_a_sheet", HERE / "export-a-sheet.py")
sheet_video = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet_video)
press, area, temp, choose, walk = sheet_video.press, sheet_video.area, sheet_video.temp, sheet_video.choose, sheet_video.walk
bring_in, close, open_button = sheet_video.bring_in, sheet_video.close, sheet_video.open_button

GROUP, SHEET = "Letters", "To the Harbour Office"
LETTER = (
    "Dear Mr. Hale,\n\n"
    "The storm last week cracked the mantle of the main lamp. I have fitted the spare one, but it will not "
    "last the winter.\n\n"
    "Could you send two new mantles with the next supply boat? The station's fund will cover the cost.\n\n"
    "Kind regards,  \nAda Morrow\n"
)
FIELDS = {
    "sender": "Ada Morrow\nSkerry Island Lighthouse\nSkerry Island\n\nada.morrow@example.com",
    "recipient": "Harbour Office\nAttn. Mr. Tom Hale\n1 Quay Street\nPort Elwyn",
    "place": "Skerry Island",
    "subject": "Two new lamp mantles",
}
TEMPLATE = "Invoice"
STATE = {}

# --- Helpers --------------------------------------------------------------------


def _pause(char, pace, noise):
    return pace * (1 + noise.uniform(-0.35, 0.35)) + (pace * 0.8 if char in " \n" else 0)


def type_into(entry, text, pace=0.06, seed=5):
    noise = random.Random(seed)
    entry.grab_focus()
    for count in range(1, len(text) + 1):
        entry.set_text(text[:count])
        entry.set_position(count)
        yield _pause(text[count - 1], pace, noise)


def type_lines(row, text, pace=0.035, seed=8):
    """Types into a field of several lines (a text view inside the row)."""
    from gi.repository import Gtk

    view = next(w for w in walk(row) if isinstance(w, Gtk.TextView))
    view.grab_focus()
    buffer, noise = view.get_buffer(), random.Random(seed)
    for char in text:
        buffer.insert_at_cursor(char)
        yield _pause(char, pace, noise)


def scroll_to(scrolled_in, widget, length=0.8, top=30):
    """Scrolls smoothly until widget is near the top of the scrolled window it sits in."""
    from gi.repository import Gtk

    scrolled = widget.get_ancestor(Gtk.ScrolledWindow) or next(w for w in walk(scrolled_in) if isinstance(w, Gtk.ScrolledWindow))
    adjustment = scrolled.get_vadjustment()
    _found, bounds = widget.compute_bounds(scrolled)
    start = adjustment.get_value()
    target = max(0, min(start + bounds.get_y() - top, adjustment.get_upper() - adjustment.get_page_size()))
    frames = int(length * 30)
    for frame in range(1, frames + 1):
        t = frame / frames
        adjustment.set_value(start + (target - start) * (3 * t * t - 2 * t * t * t))
        yield 1 / 30


def inspector_button(win):
    from gi.repository import Gtk

    for widget in walk(win):
        if isinstance(widget, Gtk.ToggleButton) and widget.get_action_name() == "win.inspector" and widget.get_mapped():
            return widget
    raise LookupError("properties button")


def inspector_area(win):
    _found, bounds = win.inspector.compute_bounds(win)
    return (bounds.get_x() - 40, bounds.get_y(), bounds.get_width() + 40, bounds.get_height())


def field_row(win, number):
    return win.inspector._field_rows[number]


def export_pdf(sheet: Path, output: Path):
    """The PDF the dialog's toast opens, made with the development version (see the docstring)."""
    from typecase import export_templates

    letter = export_templates.BUILTIN_DIR / "letter"
    # English dates, as an English user gets them
    env = {**os.environ, "TYPECASE_CODE": str(ROOT / "src"), "LC_ALL": "en_US.UTF-8", "LANGUAGE": "en"}
    subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), str(HERE / "flatpak_export.py"), str(sheet), str(letter), "pdf", str(output)],
        check=True, capture_output=True, env=env,
    )


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import export_dialog, frontmatter

    export_dialog.pdf_available = lambda: True  # outside the Flatpak WeasyPrint is missing
    folder = win.library_path / GROUP
    folder.mkdir(exist_ok=True)
    (folder / f"{SHEET}.md").write_text("---\nlanguage: en\n---\n" + LETTER, encoding="utf-8")
    # The PDF of the finished letter, as the scenes will fill it in
    work = temp("typecase-video-fields-")
    filled = work / f"{SHEET}.md"
    filled.write_text(frontmatter.join(frontmatter.update(None, {"language": "en", "template": "letter", **FIELDS}), LETTER), encoding="utf-8")
    STATE["pdf"] = work / f"{SHEET}.pdf"
    export_pdf(filled, STATE["pdf"])
    sheet_video.start_papers(STATE["pdf"])
    win.inspector.stack.set_visible_child_name("details")
    win._reload(select_path=folder / f"{SHEET}.md")
    select(win, SHEET)
    win._open_selected()  # the reload only selects it
    win.editor.focus_editor()


def intro(win):
    yield 2.2


def choose_template(win):
    yield 0.4
    yield from press(inspector_button(win))
    win.inspector_split.set_show_sidebar(True)
    yield 1.0
    yield zoom_to(inspector_area(win), length=1.0, factor=1.4)
    yield from scroll_to(win.inspector, win.inspector.template_row, top=12)
    yield 0.4
    yield from choose(win.inspector.template_row, "Letter (DIN 5008)")
    yield 1.6


def fill_in(win):
    yield 0.3
    yield from type_lines(field_row(win, 0), FIELDS["sender"])
    yield 0.4
    yield from scroll_to(win.inspector, field_row(win, 1), top=12)
    yield from type_lines(field_row(win, 1), FIELDS["recipient"], seed=9)
    yield 0.4
    yield from scroll_to(win.inspector, field_row(win, 2), top=60)
    yield from type_into(field_row(win, 2), FIELDS["place"])
    yield 0.3
    yield from type_into(field_row(win, 4), FIELDS["subject"], seed=6)
    yield 1.0


def date(win):
    from gi.repository import Gtk

    row = field_row(win, 3)
    yield 0.4
    row.set_state_flags(Gtk.StateFlags.PRELIGHT, False)  # shown as hovered: its subtitle names the day of the export
    yield 2.2
    row.unset_state_flags(Gtk.StateFlags.PRELIGHT)
    yield 0.4


def just_the_letter(win):
    yield zoom_to(None, length=0.9)
    yield 0.3
    win.inspector_split.set_show_sidebar(False)
    win.editor.focus_editor()
    yield 2.0


def wait_for_dialog(win, limit=3.0):
    """Yields until a dialog is shown on win, for at most limit seconds."""
    waited = 0.0
    while win.get_visible_dialog() is None and waited < limit:
        yield 0.1
        waited += 0.1


def export_it(win):
    win.editor.focus_editor()
    win.activate_action("win.export", None)
    yield from wait_for_dialog(win)
    if win.get_visible_dialog() is None:
        win._export()  # the action did not open it
        yield from wait_for_dialog(win)
    yield 0.4
    dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=0.8, factor=1.4)
    yield from choose(dialog.format_row, "PDF")
    yield 1.2  # the template is the sheet's own, already chosen
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.3
    win._on_exported(STATE["pdf"], None, [])
    yield 1.0
    yield from press(open_button(win))
    yield from bring_in("org.gnome.Papers", 1280, 720, sheet_video.X, sheet_video.Y)
    yield 5.0


def own_fields(win):
    close("org.gnome.Papers")
    yield 1.0
    win.activate_action("win.preferences", None)
    yield 0.8
    prefs = STATE["prefs"] = win.get_visible_dialog()
    prefs.set_visible_page(prefs.templates_page)
    yield 0.6
    yield from press(prefs.templates_page.new_button)
    prefs.templates_page._open_assistant()
    yield 0.8
    dialog = STATE["dialog"] = win.get_visible_dialog()
    yield from type_into(dialog.name_row, TEMPLATE)
    yield 0.4
    yield from scroll_to(dialog, dialog.fields_group, length=1.0)
    for label, kind in (("Invoice number", 0), ("Client", 1)):
        yield from press(dialog._add_field_button)
        dialog._add_field()
        yield 0.3
        row, _key, types = dialog._field_rows[-1]
        yield from type_into(row, label)
        if kind:
            yield from press(types)
            types.set_selected(kind)
        yield 0.4
    yield from scroll_to(dialog, dialog.structure_row, length=0.6, top=200)
    yield from press(dialog.structure_row)
    dialog.structure_row.set_active(False)
    yield 1.0
    yield from press(dialog.save_button)
    dialog._save()
    yield 1.4


def closing(win):
    STATE["prefs"].close()
    win.editor.focus_editor()
    yield 1.6


SCENES = [
    Scene(
        "Letters, invoices, forms: some texts need more than a title.",
        "Briefe, Rechnungen, Formulare: Manche Texte brauchen mehr als einen Titel.",
        intro,
    ),
    Scene(
        "Open the properties and choose a template. A letter template comes with Typecase.",
        "Öffne die Eigenschaften und wähle eine Vorlage. Eine Briefvorlage bringt Typecase mit.",
        choose_template,
        say="Open the properties and choose a template. A letter template comes with Type case.",
    ),
    Scene(
        "Its fields appear right below. Fill in sender, recipient and subject.",
        "Ihre Felder erscheinen gleich darunter. Trag Absender, Empfänger und Betreff ein.",
        fill_in,
    ),
    Scene(
        "Leave the date empty, and the export uses today's.",
        "Lass das Datum leer, dann nimmt der Export den heutigen Tag.",
        date,
    ),
    Scene(
        "The editor keeps just your letter.",
        "Im Editor steht nur dein Brief.",
        just_the_letter,
    ),
    Scene(
        "Export as PDF. Everything sits where a window envelope expects it.",
        "Als PDF exportieren. Alles sitzt dort, wo ein Fensterumschlag es erwartet.",
        export_it,
    ),
    Scene(
        "Your own templates can ask for fields too. Add them in the template assistant.",
        "Auch eigene Vorlagen können nach Feldern fragen. Du legst sie im Vorlagen-Assistenten an.",
        own_fields,
    ),
    Scene(
        "You write the letter. Typecase does the rest.",
        "Du schreibst den Brief. Den Rest macht Typecase.",
        closing,
        say="You write the letter. Type case does the rest.",
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="template-fields",
    title="Letters and template fields",
    topic="Share",
    summary="Choose the letter template for a sheet, fill in its fields, export a letter for window envelopes, and add fields to your own templates.",
    still=30,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
