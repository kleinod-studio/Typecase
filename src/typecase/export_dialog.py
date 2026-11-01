import os
import shutil
import sys
import tempfile
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from . import config, export, export_templates, pdf_render

def format_name(fmt: str) -> str:
    return {"pdf": _("PDF"), "docx": _("Word Document (DOCX)"), "html": _("Web Page (HTML)")}[fmt]


class ExportDialog(Adw.Dialog):
    """Choose format and template, then the location. The result is reported via on_done(path or None, error text)."""

    def __init__(
        self,
        text: str,
        sheet_path: Path,
        title: str | None,
        defaults: dict,
        on_done,
        editable_title: bool = False,
        page_break_text: str | None = None,
    ):
        """page_break_text: for a group with subgroups, the same text with a new page for every subgroup."""
        super().__init__(title=_("Export"), content_width=420)
        self._text = text
        self._page_break_text = page_break_text
        self._editable_title = editable_title
        self._sheet_path = sheet_path
        self._title = title
        self._defaults = defaults
        self._on_done = on_done
        self._templates = export_templates.available(config.TEMPLATES_DIR)
        saved = config.load()

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        self.format_row = Adw.ComboRow(title=_("Format"), model=Gtk.StringList.new([format_name(f) for f in export.FORMATS]))
        last = saved.get("export_format")
        self.format_row.set_selected(export.FORMATS.index(last) if last in export.FORMATS else 0)
        group.add(self.format_row)
        self.template_row = Adw.ComboRow(
            title=_("Template"),
            subtitle=_("Import more templates in the preferences"),
            model=Gtk.StringList.new([t.title for t in self._templates]),
        )
        ids = [t.id for t in self._templates]
        if saved.get("export_template") in ids:
            self.template_row.set_selected(ids.index(saved["export_template"]))
        group.add(self.template_row)
        # Exporting a group: its sheets have no common front matter, so the title is asked here.
        self.title_row = Adw.EntryRow(title=_("Title"), text=title or "", visible=editable_title)
        group.add(self.title_row)
        self.page_break_row = Adw.SwitchRow(
            title=_("Start Each Subgroup on a New Page"),
            active=saved.get("export_page_breaks") is not False,
            visible=page_break_text is not None,
        )
        group.add(self.page_break_row)
        page.add(group)

        self.export_button = Gtk.Button(label=_("Export…"), css_classes=["suggested-action", "pill"], halign=Gtk.Align.CENTER)
        self.export_button.connect("clicked", lambda _b: self._choose_file())
        button_group = Adw.PreferencesGroup()
        button_group.add(self.export_button)
        page.add(button_group)

        view = Adw.ToolbarView(content=page)
        view.add_top_bar(Adw.HeaderBar())
        self.set_child(view)
        self.set_default_widget(self.export_button)
        self.format_row.connect("notify::selected", lambda *_a: self._check_format())
        self._check_format()

    def _check_format(self):
        """Tells right away when a format cannot be exported here (PDF without WeasyPrint)."""
        missing = self.fmt == "pdf" and not pdf_available()
        self.format_row.set_subtitle(pdf_missing_text() if missing else "")
        self.export_button.set_sensitive(not missing)

    @property
    def fmt(self) -> str:
        return export.FORMATS[self.format_row.get_selected()]

    def _choose_file(self):
        fmt = self.fmt
        config.update(export_format=fmt)
        dialog = Gtk.FileDialog(title=_("Export"), initial_name=self._sheet_path.stem + export.EXTENSIONS[fmt])
        folder = config.load().get("export_folder")
        if not (folder and Path(folder).is_dir()):
            folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOCUMENTS) or GLib.get_home_dir()
        dialog.set_initial_folder(Gio.File.new_for_path(folder))
        dialog.save(self.get_root(), None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return  # canceled
        output = Path(file.get_path())
        config.update(export_folder=str(output.parent))
        self.export_button.set_sensitive(False)
        template = self._templates[self.template_row.get_selected()]
        config.update(export_template=template.id)
        text, title = self._text, self._title
        if self._page_break_text is not None:
            config.update(export_page_breaks=self.page_break_row.get_active())
            if self.page_break_row.get_active():
                text = self._page_break_text
        if self._editable_title:
            title = self.title_row.get_text().strip() or None
            text = export.with_title(text, title)
        run_export(text, self.fmt, template, output, self._sheet_path, title, self._defaults, self._finished)

    def _finished(self, output: Path | None, error: str | None):
        self.close()
        self._on_done(output, error)


def run_export(text, fmt, template, output: Path, sheet_path: Path, title, defaults, on_done):
    """Exports in the background. Output goes to a temporary file first; only once everything has
    worked does it replace the target. So an error never leaves a half-written file behind."""
    if export.pandoc_path() is None:
        on_done(None, _("Pandoc is not installed."))
        return
    if fmt == "docx":
        # Pandoc writes a "date" as its own paragraph under the title in Word files. The export date
        # is only meant for HTML templates that ask for $date$; a date set in the sheet stays.
        defaults = {key: value for key, value in defaults.items() if key != "date"}
    work = Path(tempfile.mkdtemp(prefix="typecase-export-"))

    def done(path, error):
        shutil.rmtree(work, ignore_errors=True)
        on_done(path, error)

    header = work / "style.html"
    header.write_text(export.style_header(template, pdf=fmt == "pdf"), encoding="utf-8")
    pandoc_output = work / ("document.html" if fmt == "pdf" else "document" + export.EXTENSIONS[fmt])
    args = export.pandoc_args(fmt, template, pandoc_output, None if title else sheet_path.stem, header, defaults)
    # Relative image paths in the text refer to the sheet's folder.
    launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
    launcher.set_cwd(str(sheet_path.parent))
    try:
        process = launcher.spawnv(args)
    except GLib.Error as error:
        done(None, error.message)
        return

    def on_pandoc(proc, result):
        try:
            _ok, _stdout, stderr = proc.communicate_utf8_finish(result)
        except GLib.Error as error:
            done(None, error.message)
            return
        if not proc.get_successful() or not pandoc_output.is_file():
            done(None, (stderr or "").strip() or _("Pandoc could not convert the text."))
            return
        if fmt == "pdf":
            _print_pdf(pandoc_output, sheet_path.parent, output, work, template, done)
        else:
            _move_into_place(pandoc_output, output, done)

    process.communicate_utf8_async(export.prepare_markdown(text), None, on_pandoc)


def _move_into_place(source: Path, output: Path, done):
    """Copy next to the target first, then rename: that way the target appears in a single step."""
    try:
        temporary = output.with_name(f".{output.name}.typecase-tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, output)
    except OSError as error:
        done(None, error.strerror or str(error))
        return
    done(output, None)


def pdf_missing_text() -> str:
    # Translators: shown when the system lacks the program for PDF export (only outside the Flatpak)
    return _("PDF export needs WeasyPrint, which is not installed. The Flatpak version of Typecase includes it.")


def pdf_available() -> bool:
    return pdf_render.available()


def _print_pdf(html: Path, base_dir: Path, output: Path, work: Path, template, done):
    """Lays out the HTML as PDF pages with WeasyPrint, in a process of its own."""
    if not pdf_available():
        done(None, pdf_missing_text())
        return
    # The template sets paper and margins; if unspecified, paper by system language and 25 mm margins.
    paper = Gtk.PaperSize.new(template.pdf_paper or Gtk.PaperSize.get_default())
    margins = template.pdf_margins_mm
    pdf = work / "document.pdf"
    args = [
        sys.executable, "-m", "typecase.pdf_render", str(html), str(base_dir), str(pdf),
        "--paper-mm", f"{paper.get_width(Gtk.Unit.MM):.2f},{paper.get_height(Gtk.Unit.MM):.2f}",
        "--margins-mm", ",".join(str(margins[side]) for side in ("top", "right", "bottom", "left")),
    ]
    launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDERR_PIPE)
    package_root = str(Path(__file__).resolve().parent.parent)  # where "typecase" can be imported from
    launcher.setenv("PYTHONPATH", os.pathsep.join(filter(None, [package_root, os.environ.get("PYTHONPATH")])), True)
    try:
        process = launcher.spawnv(args)
    except GLib.Error as error:
        done(None, error.message)
        return

    def on_finished(proc, result):
        try:
            _ok, _stdout, stderr = proc.communicate_utf8_finish(result)
        except GLib.Error as error:
            done(None, error.message)
            return
        if proc.get_successful() and pdf.is_file():
            _move_into_place(pdf, output, done)
        else:
            lines = (stderr or "").strip().splitlines()
            done(None, lines[-1] if lines else _("The PDF could not be created."))

    process.communicate_utf8_async(None, None, on_finished)
