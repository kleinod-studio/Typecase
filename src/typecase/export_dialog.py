import os
import shutil
import tempfile
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from . import config, export, export_templates

PAGE_MARGIN_MM = 25


def format_name(fmt: str) -> str:
    return {"pdf": _("PDF"), "docx": _("Word Document (DOCX)"), "html": _("Web Page (HTML)")}[fmt]


class ExportDialog(Adw.Dialog):
    """Format und Vorlage wählen, dann Speicherort. Das Ergebnis meldet on_done(Pfad oder None, Fehlertext)."""

    def __init__(self, text: str, sheet_path: Path, title: str | None, defaults: dict, on_done):
        super().__init__(title=_("Export"), content_width=420)
        self._text = text
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
            return  # abgebrochen
        output = Path(file.get_path())
        config.update(export_folder=str(output.parent))
        self.export_button.set_sensitive(False)
        template = self._templates[self.template_row.get_selected()]
        config.update(export_template=template.id)
        run_export(self._text, self.fmt, template, output, self._sheet_path, self._title, self._defaults, self._finished)

    def _finished(self, output: Path | None, error: str | None):
        self.close()
        self._on_done(output, error)


def run_export(text, fmt, template, output: Path, sheet_path: Path, title, defaults, on_done):
    """Exportiert im Hintergrund. Geschrieben wird erst in eine temporäre Datei; erst wenn alles
    geklappt hat, ersetzt sie das Ziel. Ein Fehler hinterlässt also nie eine halbe Datei."""
    if export.pandoc_path() is None:
        on_done(None, _("Pandoc is not installed."))
        return
    work = Path(tempfile.mkdtemp(prefix="typecase-export-"))

    def done(path, error):
        shutil.rmtree(work, ignore_errors=True)
        on_done(path, error)

    header = work / "style.html"
    header.write_text(export.style_header(template), encoding="utf-8")
    pandoc_output = work / ("document.html" if fmt == "pdf" else "document" + export.EXTENSIONS[fmt])
    args = export.pandoc_args(fmt, template, pandoc_output, None if title else sheet_path.stem, header, defaults)
    # Relative Bildpfade im Text beziehen sich auf den Ordner des Blatts.
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
            _print_pdf(pandoc_output, sheet_path.parent, output, work, done)
        else:
            _move_into_place(pandoc_output, output, done)

    process.communicate_utf8_async(export.prepare_markdown(text), None, on_pandoc)


def _move_into_place(source: Path, output: Path, done):
    """Erst neben das Ziel kopieren, dann umbenennen: so entsteht das Ziel in einem Schritt."""
    try:
        temporary = output.with_name(f".{output.name}.typecase-tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, output)
    except OSError as error:
        done(None, error.strerror or str(error))
        return
    done(output, None)


def _webkit():
    try:
        import gi

        gi.require_version("WebKit", "6.0")
        from gi.repository import WebKit
    except (ImportError, ValueError):
        return None
    return WebKit


def pdf_available() -> bool:
    return _webkit() is not None


def _print_pdf(html: Path, base_dir: Path, output: Path, work: Path, done):
    """Lädt das HTML in eine unsichtbare WebKit-Ansicht und druckt es ohne Dialog in eine PDF-Datei."""
    WebKit = _webkit()
    if WebKit is None:
        done(None, _("PDF export needs WebKitGTK 6.0."))
        return

    view = WebKit.WebView()
    settings = view.get_settings()
    settings.set_enable_javascript(False)  # nur Text und CSS; nichts aus dem Dokument ausführen
    pdf = work / "document.pdf"
    holder = {"view": view}  # bis zum Ende festhalten, sonst räumt Python die Ansicht weg

    def on_load(web_view, event):
        if event != WebKit.LoadEvent.FINISHED:
            return
        print_settings = Gtk.PrintSettings()
        # Der Datei-"Drucker" heißt so, wie GTK ihn in der Sprache der Oberfläche nennt.
        print_settings.set_printer(GLib.dgettext("gtk40", "Print to File"))
        print_settings.set(Gtk.PRINT_SETTINGS_OUTPUT_FILE_FORMAT, "pdf")
        print_settings.set(Gtk.PRINT_SETTINGS_OUTPUT_URI, Gio.File.new_for_path(str(pdf)).get_uri())
        page_setup = Gtk.PageSetup()
        page_setup.set_paper_size(Gtk.PaperSize.new(Gtk.PaperSize.get_default()))
        for setter in (page_setup.set_top_margin, page_setup.set_bottom_margin, page_setup.set_left_margin, page_setup.set_right_margin):
            setter(PAGE_MARGIN_MM, Gtk.Unit.MM)
        operation = WebKit.PrintOperation.new(web_view)
        operation.set_print_settings(print_settings)
        operation.set_page_setup(page_setup)
        holder["operation"] = operation

        def on_finished(_op):
            failed = holder.get("failed")
            holder.clear()
            if failed:
                return  # schon gemeldet
            if pdf.is_file():
                _move_into_place(pdf, output, done)
            else:
                done(None, _("The PDF could not be created."))

        def on_failed(_op, error):
            holder["failed"] = True
            done(None, error.message)

        operation.connect("failed", on_failed)
        operation.connect("finished", on_finished)
        operation.print_()

    def on_load_failed(_view, _event, _uri, error):
        holder.clear()
        done(None, error.message)
        return True

    view.connect("load-changed", on_load)
    view.connect("load-failed", on_load_failed)
    view.load_html(html.read_text(encoding="utf-8"), Gio.File.new_for_path(str(base_dir)).get_uri() + "/")
