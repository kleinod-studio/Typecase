from gettext import gettext as _

from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from . import config, export_templates


def _system_font_family() -> str:
    name = Gtk.Settings.get_default().props.gtk_font_name or "Sans"
    return Pango.FontDescription.from_string(name).get_family()


class _ProfilePage(Adw.PreferencesPage):
    """Eine Rubrik mit Schrift, Textblock und Stil für ein Profil (Editor oder Fokus-Modus)."""

    def __init__(self, profile: str, title: str, icon_name: str, on_change, intro: Adw.PreferencesGroup | None = None):
        super().__init__(title=title, icon_name=icon_name, name=profile)
        self.profile = profile
        self._on_change = on_change
        self._loading = True
        current = config.settings(profile)
        self.groups: list[Adw.PreferencesGroup] = []
        if intro is not None:
            self.add(intro)  # steht über den übrigen Gruppen

        # Schrift
        font_group = self._group(_("Font"))
        self.system_font = Adw.SwitchRow(
            title=_("Use System Font"),
            subtitle=_("The same font as the rest of the desktop"),
            active=current["editor_font"] is None,
        )
        font_group.add(self.system_font)

        self.font_button = Gtk.FontDialogButton(
            dialog=Gtk.FontDialog(title=_("Choose Font")),
            level=Gtk.FontLevel.FAMILY,
            valign=Gtk.Align.CENTER,
        )
        # Nur die Familie zeigen (Größe hat eine eigene Zeile); ohne eigene Schrift die des Systems.
        family = current["editor_font"] or _system_font_family()
        self.font_button.set_font_desc(Pango.FontDescription.from_string(family))
        font_row = Adw.ActionRow(title=_("Font"))
        font_row.add_suffix(self.font_button)
        font_row.set_activatable_widget(self.font_button)
        self.system_font.bind_property(
            "active", font_row, "sensitive", GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN
        )
        font_group.add(font_row)

        low, high = config.FONT_SIZE_RANGE
        self.font_size = Adw.SpinRow.new_with_range(low, high, 1)
        self.font_size.set_title(_("Font Size"))
        self.font_size.set_subtitle(_("In points"))
        self.font_size.set_value(current["editor_font_size"])
        font_group.add(self.font_size)

        # Textblock
        text_group = self._group(_("Text Block"))
        low, high = config.LINE_WIDTH_RANGE
        self.line_width = Adw.SpinRow.new_with_range(low, high, 5)
        self.line_width.set_title(_("Line Width"))
        self.line_width.set_subtitle(_("Maximum characters per line; the text stays centered"))
        self.line_width.set_value(current["line_width"])
        text_group.add(self.line_width)

        self.line_spacing = Adw.ComboRow(
            title=_("Line Spacing"),
            model=Gtk.StringList.new([_("Compact"), _("Normal"), _("Relaxed")]),
            selected=config.LINE_SPACINGS.index(current["line_spacing"]),
        )
        text_group.add(self.line_spacing)

        # Darstellung
        look_group = self._group(_("Appearance"))
        self.color_scheme = Adw.ComboRow(
            title=_("Style"),
            model=Gtk.StringList.new([_("Follow System"), _("Light"), _("Dark")]),
            selected=config.COLOR_SCHEMES.index(current["color_scheme"]),
        )
        look_group.add(self.color_scheme)

        reset_group = self._group(None)
        reset = Gtk.Button(label=_("Restore Defaults"), halign=Gtk.Align.CENTER, css_classes=["pill"])
        reset.connect("clicked", lambda _b: self.reset())
        reset_group.add(reset)

        for widget, signal in [
            (self.system_font, "notify::active"),
            (self.font_button, "notify::font-desc"),
            (self.font_size, "notify::value"),
            (self.line_width, "notify::value"),
            (self.line_spacing, "notify::selected"),
            (self.color_scheme, "notify::selected"),
        ]:
            widget.connect(signal, lambda *_args: self.save())
        self._loading = False

    def _group(self, title: str | None) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=title) if title else Adw.PreferencesGroup()
        self.add(group)
        self.groups.append(group)
        return group

    def save(self):
        if self._loading:
            return
        font = None
        if not self.system_font.get_active() and self.font_button.get_font_desc() is not None:
            font = self.font_button.get_font_desc().get_family()
        config.update_profile(
            self.profile,
            {
                "editor_font": font,
                "editor_font_size": int(self.font_size.get_value()),
                "line_width": int(self.line_width.get_value()),
                "line_spacing": config.LINE_SPACINGS[self.line_spacing.get_selected()],
                "color_scheme": config.COLOR_SCHEMES[self.color_scheme.get_selected()],
            },
        )
        self._on_change()

    def reset(self):
        defaults = config.SETTINGS_DEFAULTS
        self._loading = True
        self.system_font.set_active(True)
        self.font_size.set_value(defaults["editor_font_size"])
        self.line_width.set_value(defaults["line_width"])
        self.line_spacing.set_selected(config.LINE_SPACINGS.index(defaults["line_spacing"]))
        self.color_scheme.set_selected(config.COLOR_SCHEMES.index(defaults["color_scheme"]))
        self._loading = False
        self.save()


class _SheetsPage(Adw.PreferencesPage):
    """Voreinstellungen für die Meta-Informationen der Blätter (nicht in die Dateien geschrieben)."""

    def __init__(self, apply):
        super().__init__(title=_("Sheets"), icon_name="document-properties-symbolic", name="sheets")
        self._apply = apply
        defaults = config.sheet_defaults()
        group = Adw.PreferencesGroup(
            title=_("Defaults"),
            description=_("Used for every sheet that does not set its own value, for example when exporting. They are not written into your files."),
        )
        self.add(group)
        self.author = Adw.EntryRow(title=_("Author"), text=defaults["author"] or "")
        self.author.connect("changed", lambda row: self._save())
        group.add(self.author)
        from .inspector import language_name

        self.lang = Adw.ComboRow(
            title=_("Language"),
            model=Gtk.StringList.new([language_name(code) for code in config.LANGUAGES]),
            selected=config.LANGUAGES.index(defaults["lang"]) if defaults["lang"] in config.LANGUAGES else 0,
        )
        self.lang.connect("notify::selected", lambda *_a: self._save())
        group.add(self.lang)

    def _save(self):
        config.update(default_author=self.author.get_text().strip() or None, default_lang=config.LANGUAGES[self.lang.get_selected()])
        self._apply()


class _TemplatesPage(Adw.PreferencesPage):
    """Export-Vorlagen: importieren (.typecase-template), als Datei speichern, entfernen."""

    def __init__(self, toast):
        super().__init__(title=_("Templates"), icon_name="folder-templates-symbolic", name="templates")
        self._toast = toast
        self.group = Adw.PreferencesGroup(
            title=_("Export Templates"),
            description=_(
                "Choose a template when exporting. To build your own, save a template as a file and use it as a starting point."
            ),
        )
        self.import_button = Gtk.Button(label=_("Import…"), css_classes=["flat"], valign=Gtk.Align.CENTER)
        self.import_button.connect("clicked", lambda _b: self._choose_import())
        self.group.set_header_suffix(self.import_button)
        self.add(self.group)
        self._rows: list[Gtk.Widget] = []
        self.refresh()

    def refresh(self):
        for row in self._rows:
            self.group.remove(row)
        self._rows = []
        for template in export_templates.available(config.TEMPLATES_DIR):
            row = Adw.ActionRow(title=template.title, subtitle=template.description or "")
            if template.builtin:
                row.add_suffix(Gtk.Label(label=_("Built-in"), css_classes=["dim-label", "caption"], valign=Gtk.Align.CENTER))
            save = Gtk.Button(
                icon_name="document-save-symbolic", tooltip_text=_("Save as File…"), css_classes=["flat"], valign=Gtk.Align.CENTER
            )
            save.connect("clicked", lambda _b, t=template: self._choose_save(t))
            row.add_suffix(save)
            if not template.builtin:
                remove = Gtk.Button(
                    icon_name="user-trash-symbolic", tooltip_text=_("Remove"), css_classes=["flat"], valign=Gtk.Align.CENTER
                )
                remove.connect("clicked", lambda _b, t=template: self._remove(t))
                row.add_suffix(remove)
            self.group.add(row)
            self._rows.append(row)

    # --- Importieren ------------------------------------------------------------

    def _file_filter(self) -> Gio.ListStore:
        file_filter = Gtk.FileFilter(name=_("Typecase Templates"))
        file_filter.add_suffix(export_templates.EXTENSION.lstrip("."))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        return filters

    def _choose_import(self):
        dialog = Gtk.FileDialog(title=_("Import Template"), filters=self._file_filter())
        dialog.open(self.get_root(), None, self._on_import_chosen)

    def _on_import_chosen(self, dialog, result):
        try:
            path = Path(dialog.open_finish(result).get_path())
        except GLib.Error:
            return  # abgebrochen
        try:
            candidate = export_templates.peek(path)
        except export_templates.TemplateError as error:
            self._error(_("Template Not Imported"), str(error))
            return
        existing = {t.id: t for t in export_templates.available(config.TEMPLATES_DIR) if not t.builtin}
        if candidate.id not in existing:
            self._install(path)
            return
        alert = Adw.AlertDialog(
            heading=_("Replace Template?"),
            body=_("A template “%s” is already installed. It will be replaced by the new file.") % existing[candidate.id].title,
        )
        alert.add_response("cancel", _("Cancel"))
        alert.add_response("replace", _("Replace"))
        alert.set_response_appearance("replace", Adw.ResponseAppearance.DESTRUCTIVE)
        alert.connect("response", lambda _a, response: response == "replace" and self._install(path))
        alert.present(self)

    def _install(self, path: Path):
        try:
            template = export_templates.install(path, config.TEMPLATES_DIR)
        except (export_templates.TemplateError, OSError) as error:
            self._error(_("Template Not Imported"), str(error))
            return
        self.refresh()
        self._toast(_("Template “%s” imported") % template.title)

    # --- Speichern und Entfernen ----------------------------------------------

    def _choose_save(self, template):
        dialog = Gtk.FileDialog(title=_("Save Template"), initial_name=template.title + export_templates.EXTENSION)
        dialog.save(self.get_root(), None, lambda d, r: self._on_save_chosen(d, r, template))

    def _on_save_chosen(self, dialog, result, template):
        try:
            path = Path(dialog.save_finish(result).get_path())
        except GLib.Error:
            return
        try:
            export_templates.pack(template, path)
        except OSError as error:
            self._error(_("Template Not Saved"), error.strerror or str(error))
            return
        self._toast(_("Saved “%s”") % path.name)

    def _remove(self, template):
        # In den Papierkorb, nicht endgültig: versehentlich Entferntes lässt sich zurückholen.
        try:
            Gio.File.new_for_path(str(template.path)).trash(None)
        except GLib.Error as error:
            self._error(_("Template Not Removed"), error.message)
            return
        self.refresh()
        self._toast(_("Template “%s” moved to the trash") % template.title)

    def _error(self, heading: str, body: str):
        alert = Adw.AlertDialog(heading=heading, body=body)
        alert.add_response("close", _("Close"))
        alert.present(self)


class PreferencesDialog(Adw.PreferencesDialog):
    """Einstellungen im GNOME-Stil: Änderungen wirken sofort und werden gleich gespeichert.

    Zwei Rubriken: der normale Editor und der Fokus-Modus. Der Fokus-Modus übernimmt
    zunächst die Einstellungen des Editors; erst wenn das abgeschaltet ist, gelten seine eigenen."""

    def __init__(self, apply):
        super().__init__(title=_("Preferences"))
        self._apply = apply

        intro = Adw.PreferencesGroup(
            description=_("Focus mode hides the sidebar and toolbars and shows only your text, full screen.")
        )
        self.focus_same = Adw.SwitchRow(
            title=_("Use Editor Settings"),
            subtitle=_("Switch off to give focus mode its own font, size and style"),
            active=config.focus_uses_editor_settings(),
        )
        intro.add(self.focus_same)

        self.editor_page = _ProfilePage("editor", _("Editor"), "document-edit-symbolic", apply)
        self.focus_page = _ProfilePage("focus", _("Focus Mode"), "view-fullscreen-symbolic", apply, intro)
        self.sheets_page = _SheetsPage(apply)
        self.add(self.editor_page)
        self.add(self.focus_page)
        self.add(self.sheets_page)
        self.templates_page = _TemplatesPage(lambda text: self.add_toast(Adw.Toast(title=text)))
        self.add(self.templates_page)

        for group in self.focus_page.groups:
            self.focus_same.bind_property(
                "active", group, "sensitive", GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN
            )
        self.focus_same.connect("notify::active", self._on_focus_same_changed)

        tools = Adw.PreferencesGroup(title=_("Tools"))
        self.format_bar = Adw.SwitchRow(
            title=_("Formatting Bar"),
            subtitle=_("Buttons below the text for bold, lists, headings and more"),
            active=config.load().get("format_bar") is not False,
        )
        self.format_bar.connect("notify::active", self._on_format_bar_changed)
        tools.add(self.format_bar)
        self.underline_caret = Adw.SwitchRow(
            title=_("Underline Cursor"),
            subtitle=_("Show the text cursor as a line below the character instead of a vertical bar"),
            active=config.load().get("underline_caret") is not False,
        )
        self.underline_caret.connect(
            "notify::active", lambda row, _p: (config.update(underline_caret=row.get_active()), self._apply())
        )
        tools.add(self.underline_caret)
        self.editor_page.add(tools)

        # Eigene Werkzeug-Einstellung im Fokus-Modus (unabhängig von "Einstellungen des Editors übernehmen").
        focus_tools = Adw.PreferencesGroup(title=_("Tools"))
        self.focus_format_bar = Adw.SwitchRow(
            title=_("Show Formatting Bar"),
            subtitle=_("When off, it appears when you move the pointer to the bottom edge"),
            active=config.load().get("focus_format_bar") is not False,
        )
        self.focus_format_bar.connect("notify::active", self._on_focus_format_bar_changed)
        focus_tools.add(self.focus_format_bar)
        for key, title, subtitle in [
            ("focus_typewriter", _("Typewriter Scrolling"), _("Keep the line you are writing in the middle of the screen")),
            ("focus_dim", _("Dim Surroundings"), _("Fade everything except the paragraph you are writing")),
        ]:
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=config.load().get(key) is not False)
            row.connect("notify::active", lambda r, _p, k=key: (config.update(**{k: r.get_active()}), self._apply()))
            focus_tools.add(row)
            setattr(self, key, row)
        self.focus_page.add(focus_tools)

    def _on_focus_format_bar_changed(self, *_args):
        config.update(focus_format_bar=self.focus_format_bar.get_active())
        self._apply()

    def _on_format_bar_changed(self, *_args):
        config.update(format_bar=self.format_bar.get_active())
        self._apply()

    def _on_focus_same_changed(self, *_args):
        config.update(focus_same_as_editor=self.focus_same.get_active())
        self._apply()
