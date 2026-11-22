"""Explainer video: export a sheet as a PDF and as a Word document, and open the results.

    python3 tools/video/export-a-sheet.py

Writes dist/videos/export/export.webm and .mp4, with English and German subtitles. Needs the
installed Typecase Flatpak (it brings Pandoc and WeasyPrint for the exports), Papers for the PDF
and the ONLYOFFICE Flatpak for the Word document. Both apps run with temporary settings of their
own, so your own settings and recent files stay untouched. While it records, a Typecase window
floats in the middle of the screen for about a minute, and the two apps open over it; leave it all
visible and don't touch it.

The file chooser of the export dialog is left out (it would show your own folders): the files are
exported beforehand, the way the dialog does it, and the dialog's toast opens them."""

import atexit
import base64
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import videokit
from actions import node, select
from videokit import Scene, zoom_to

HERE = Path(__file__).resolve().parent
SHEET = "The Lighthouse Keeper/Manuscript/02 The Storm.md"
X, Y = 260, 224  # the recording region, as videokit places the Typecase window
SPECIAL = "special:typecase-video"  # apps start here, hidden, until they are in place
OPENED = {}  # what opening() prepared: folders, files, window classes
TEMPS = []

# --- Helpers --------------------------------------------------------------------


def walk(widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        yield from walk(child)
        child = child.get_next_sibling()


def press(widget):
    """Shows a button or row as hovered and pressed, the way a click looks."""
    from gi.repository import Gtk

    widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
    yield 0.45
    widget.set_state_flags(Gtk.StateFlags.ACTIVE, False)
    yield 0.15
    widget.unset_state_flags(Gtk.StateFlags.ACTIVE | Gtk.StateFlags.PRELIGHT)


def area(win, widget, margin=24):
    _found, bounds = widget.compute_bounds(win)
    return (bounds.get_x() - margin, bounds.get_y() - margin, bounds.get_width() + 2 * margin, bounds.get_height() + 2 * margin)


def temp(prefix):
    folder = Path(tempfile.mkdtemp(prefix=prefix, dir=Path.home() / ".cache"))
    TEMPS.append(folder)
    return folder


def hyprctl(*args):
    return subprocess.run(["hyprctl", *args], capture_output=True, text=True).stdout


def window_of(cls):
    for client in json.loads(hyprctl("-j", "clients")):
        if client["class"] == cls:
            return client
    return None


def hidden_start(cls, command, env=None):
    """Starts an app on a hidden workspace, floating, so that it can be put in place unseen."""
    rule = f"typecase-video-{cls.lower().replace('.', '-')}"
    hyprctl("eval", f'hl.window_rule({{ name = "{rule}", match = {{ class = "{cls}" }}, float = true, workspace = "{SPECIAL} silent", no_initial_focus = true, suppress_event = "activate activatefocus" }})')
    OPENED.setdefault("rules", []).append(rule)
    subprocess.Popen(command, env={**os.environ, **(env or {})}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def bring_in(cls, width, height, x, y):
    """Sizes and places the hidden window, then shows it on the current workspace."""
    for _ in range(80):
        client = window_of(cls)
        if client:
            break
        yield 0.25
    else:
        raise LookupError(f"no window of {cls}")
    address = client["address"]
    hyprctl("dispatch", f'hl.dsp.window.resize({{ x = {width}, y = {height}, window = "address:{address}" }})')
    hyprctl("dispatch", f'hl.dsp.window.move({{ x = {x}, y = {y}, window = "address:{address}" }})')
    yield 0.2
    workspace = json.loads(hyprctl("-j", "activeworkspace"))["id"]
    hyprctl("dispatch", f'hl.dsp.window.move({{ workspace = "{workspace}", window = "address:{address}" }})')


def key_to(cls, key):
    """Focuses the window of cls and presses a key in it, only if it really has the focus."""
    client = window_of(cls)
    if not client:
        return
    hyprctl("dispatch", f'hl.dsp.focus({{ window = "address:{client["address"]}" }})')
    active = json.loads(hyprctl("-j", "activewindow") or "{}")
    if active.get("class") == cls:
        subprocess.run(["wtype", "-k", key], check=False)


def close(cls):
    client = window_of(cls)
    if client:
        hyprctl("dispatch", f'hl.dsp.window.close({{ window = "address:{client["address"]}" }})')


@atexit.register
def clean_up():
    for cls in ("org.gnome.Papers", "ONLYOFFICE"):
        close(cls)
    for rule in OPENED.get("rules", []):
        hyprctl("eval", f'hl.window_rule({{ name = "{rule}", enabled = false }})')
    for folder in TEMPS:
        shutil.rmtree(folder, ignore_errors=True)


def make_templates(folder):
    """The two templates of the video, made from the assistant's presets."""
    from typecase import template_builder

    presets = template_builder.presets()
    template_builder.save(replace(presets["novel"][1], name="Novel", page_numbers="center"), folder)
    template_builder.save(replace(presets["manuscript"][1], name="Manuscript for an Editor"), folder)


def export(sheet, template, fmt, output, cover=False):
    """Exports in the installed Typecase Flatpak, which brings Pandoc and WeasyPrint."""
    command = ["flatpak", "run", "--command=python3", "studio.kleinod.Typecase", str(HERE / "flatpak_export.py"),
               str(sheet), str(template), fmt, str(output)]
    subprocess.run(command + (["--cover"] if cover else []), check=True, capture_output=True)


def start_papers(pdf, paged=False):
    """paged: turn two pages at a time with Page Down, starting with pages 1 and 2 side by side."""
    home = temp("typecase-video-papers-")
    settings = home / "cfg" / "glib-2.0" / "settings"
    settings.mkdir(parents=True)
    # Two pages side by side, whole pages, no sidebar
    paging = "continuous=false\ndual-page-odd-left=true\n" if paged else ""
    (settings / "keyfile").write_text(
        f"[org/gnome/papers/default]\nshow-sidebar=false\ndual-page=true\nsizing-mode='fit-page'\n{paging}\n"
        "[org/gnome/papers]\nnight-mode=false\n"
    )
    env = {"XDG_CONFIG_HOME": str(home / "cfg"), "XDG_DATA_HOME": str(home / "data"), "XDG_STATE_HOME": str(home / "state"),
           "XDG_CACHE_HOME": str(home / "cache"), "GSETTINGS_BACKEND": "keyfile", "GIO_USE_VFS": "local",
           "ADW_DEBUG_COLOR_SCHEME": "prefer-light", "LANGUAGE": "en"}
    hidden_start("org.gnome.Papers", ["papers", str(pdf)], env)


def start_onlyoffice(docx):
    home = temp("typecase-video-onlyoffice-")
    (home / "cfg" / "onlyoffice").mkdir(parents=True)
    appdata = {"username": "Ada Morrow", "langid": "en-US", "uitheme": "theme-light", "editorwindowmode": False,
               "spellcheckdetect": "auto", "usegpu": True, "useai": False, "restart": False, "country": "us"}
    encoded = base64.b64encode(json.dumps(appdata).encode()).decode()
    (home / "cfg" / "onlyoffice" / "DesktopEditors.conf").write_text(
        f'[General]\nappdata="@ByteArray({encoded})"\neditorWindowMode=false\ntitlebar=custom\n'
    )
    # Flatpak sets the XDG folders itself, so they are set again inside the sandbox. Without the
    # session bus the editor can't read the system's dark style and stays light.
    inner = (f"export XDG_CONFIG_HOME={home}/cfg XDG_DATA_HOME={home}/data XDG_CACHE_HOME={home}/cache "
             "LANGUAGE=en LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 GTK_THEME=Adwaita GTK_USE_PORTAL=0 "
             "DBUS_SESSION_BUS_ADDRESS=unix:path=/nonexistent; exec /app/bin/desktopeditors --force-scale=2 \"$1\"")
    hidden_start("ONLYOFFICE", ["flatpak", "run", "--command=sh", "org.onlyoffice.desktopeditors", "-c", inner, "sh", str(docx)])


def open_button(win):
    """The Open button of the export toast."""
    from gi.repository import Gtk

    for widget in walk(win.toasts):
        if isinstance(widget, Gtk.Button) and widget.get_label() == "Open":
            return widget
    raise LookupError("Open")


def choose(row, title):
    titles = [row.get_model().get_string(i) for i in range(row.get_model().get_n_items())]
    yield from press(row)
    row.set_selected(titles.index(title))


# --- The scenes -----------------------------------------------------------------


def opening(win):
    from typecase import config, export_dialog

    # Outside the Flatpak WeasyPrint is missing; the dialog would say so under PDF.
    export_dialog.pdf_available = lambda: True
    make_templates(config.TEMPLATES_DIR)
    sheet = win.library_path / SHEET
    work = temp("typecase-video-export-")
    make_templates(work / "templates")
    folders = {path.name: path for path in (work / "templates").iterdir() if path.is_dir() and not path.name.startswith(".")}
    out = work / "out"
    out.mkdir()
    OPENED["pdf"], OPENED["docx"] = out / "02 The Storm.pdf", out / "02 The Storm.docx"
    export(sheet, folders["novel"], "pdf", OPENED["pdf"], cover=True)
    export(sheet, folders["manuscript-for-an-editor"], "docx", OPENED["docx"])
    start_papers(OPENED["pdf"])
    start_onlyoffice(OPENED["docx"])
    for group in ("The Lighthouse Keeper", "Manuscript", "Notes"):
        node(win, group)[1].set_expanded(True)
    select(win, "02 The Storm")
    win.editor.focus_editor()


def intro(win):
    yield 2.0


def open_dialog(win):
    yield 0.6
    win.activate_action("win.export", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    OPENED["dialog"] = dialog
    yield zoom_to(area(win, dialog, margin=30), length=1.0, factor=1.4)
    yield 1.0


def format_pdf(win):
    dialog = OPENED["dialog"]
    yield 0.4
    yield from choose(dialog.format_row, "PDF")
    yield 1.6


def template(win):
    dialog = OPENED["dialog"]
    yield 0.4
    yield from choose(dialog.template_row, "Novel")
    yield 1.6


def cover(win):
    dialog = OPENED["dialog"]
    yield 0.4
    yield from press(dialog.cover_row)
    dialog.cover_row.set_active(True)
    yield 1.4


def export_pdf(win):
    dialog = OPENED["dialog"]
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.4
    win._on_exported(OPENED["pdf"], None, [])
    yield 1.2
    yield from press(open_button(win))
    yield from bring_in("org.gnome.Papers", 1280, 720, X, Y)
    yield 3.4


def export_word(win):
    close("org.gnome.Papers")
    yield 1.0
    win.activate_action("win.export", None)
    yield 0.8
    dialog = win.get_visible_dialog()
    yield zoom_to(area(win, dialog, margin=30), length=0.8, factor=1.4)
    yield from choose(dialog.format_row, "Word Document (DOCX)")
    yield 0.6
    yield from choose(dialog.template_row, "Manuscript for an Editor")
    yield 0.8
    yield from press(dialog.export_button)
    dialog.close()
    yield zoom_to(None, length=0.8)
    yield 0.4
    win._on_exported(OPENED["docx"], None, [])
    yield 1.2
    yield from press(open_button(win))
    # The window has a frame of its own around the editor, so it is a little larger than the region
    yield from bring_in("ONLYOFFICE", 1334, 773, X - 27, Y - 24)
    yield 3.0


def closing(win):
    close("ONLYOFFICE")
    yield 1.2


SCENES = [
    Scene(
        "When your text is ready, share it: as a PDF, a Word document or a web page.",
        "Ist dein Text fertig, teilst du ihn: als PDF, als Word-Dokument oder als Webseite.",
        intro,
    ),
    Scene(
        "Press Ctrl+E, or choose Export from the menu.",
        "Drück Strg+E oder wähle „Exportieren“ im Menü.",
        open_dialog,
        say="Press Control E, or choose Export from the menu.",
    ),
    Scene(
        "Choose a format. A PDF is for reading and printing.",
        "Wähle ein Format. Ein PDF ist zum Lesen und Drucken.",
        format_pdf,
    ),
    Scene(
        "A template sets the look: fonts, margins and page numbers. You can make your own.",
        "Eine Vorlage bestimmt das Aussehen: Schriften, Ränder und Seitenzahlen. Du kannst auch eigene machen.",
        template,
    ),
    Scene(
        "Add a cover page or a table of contents, if you like.",
        "Wenn du magst, kommt ein Deckblatt oder ein Inhaltsverzeichnis dazu.",
        cover,
    ),
    Scene(
        "Click Export, choose where to save it, and open the result.",
        "Klick auf „Exportieren“, wähle, wo es gespeichert wird, und öffne das Ergebnis.",
        export_pdf,
    ),
    Scene(
        "A Word document is for an editor or a publisher. They can work in it right away, with comments and tracked changes.",
        "Ein Word-Dokument ist für Lektorat oder Verlag. Dort kann man sofort darin arbeiten, mit Kommentaren und Änderungsverfolgung.",
        export_word,
    ),
    Scene(
        "Write in plain text, share it in style.",
        "In reinem Text schreiben, schön gestaltet teilen.",
        closing,
        hold=0.5,
    ),
]

VIDEO = videokit.Video(
    name="export",
    title="Export",
    topic="Share",
    summary="Export a sheet as a PDF or a Word document with a template, and open the result.",
    still=24,
)

if __name__ == "__main__":
    videokit.run(VIDEO, SCENES, before=opening)
