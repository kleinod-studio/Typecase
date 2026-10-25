from gettext import gettext as _

from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource, Pango

from . import config, export_templates, themes


def _system_font_family() -> str:
    name = Gtk.Settings.get_default().props.gtk_font_name or "Sans"
    return Pango.FontDescription.from_string(name).get_family()


def _section_heading(page: Adw.PreferencesPage, title: str, description: str | None = None, separator: bool = False):
    """A large heading that divides a preferences page into clearly separate parts."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    if separator:
        box.append(Gtk.Separator(margin_bottom=18))
    box.append(Gtk.Label(label=title, xalign=0, css_classes=["title-2"]))
    if description:
        box.append(Gtk.Label(label=description, xalign=0, wrap=True, css_classes=["dim-label"]))
    group = Adw.PreferencesGroup()
    group.add(box)
    page.add(group)


class _ProfileSection:
    """Font, text block and style for one profile (editor or focus mode), as groups on a page."""

    def __init__(self, page: Adw.PreferencesPage, profile: str, on_change):
        self.page = page
        self.profile = profile
        self._on_change = on_change
        self._loading = True
        current = config.settings(profile)
        self.groups: list[Adw.PreferencesGroup] = []

        # Font
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
        # Only show the family (size has its own row); without a custom font, the system font.
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

        # Text block
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

        # Appearance
        look_group = self._group(_("Appearance"))
        self.color_scheme = Adw.ComboRow(
            title=_("Style"),
            model=Gtk.StringList.new([_("Follow System"), _("Light"), _("Dark")]),
            selected=config.COLOR_SCHEMES.index(current["color_scheme"]),
        )
        look_group.add(self.color_scheme)
        # Editor theme: preview tiles as in GNOME Text Editor, showing the variant for the current style.
        self._theme = current["editor_theme"]
        self.theme_box = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            min_children_per_line=2,
            max_children_per_line=5,
            column_spacing=12,
            row_spacing=12,
            margin_top=12,
        )
        look_group.add(self.theme_box)
        self.refresh_themes()

        reset_group = self._group(None)
        self.reset_group = reset_group
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
        self.page.add(group)
        self.groups.append(group)
        return group

    def refresh_themes(self):
        """(Re)builds the theme tiles, e.g. after an import or when the style turns dark."""
        self.theme_box.remove_all()
        self._previews: dict[str, GtkSource.StyleSchemePreview] = {}
        dark = Adw.StyleManager.get_default().get_dark()
        known = False
        for theme in themes.available():
            preview = GtkSource.StyleSchemePreview(scheme=themes.scheme(theme.id, dark), tooltip_text=theme.name)
            preview.update_property([Gtk.AccessibleProperty.LABEL], [theme.name])
            preview.connect("activate", lambda _p, theme_id=theme.id: self._choose_theme(theme_id))
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            tile.append(preview)
            tile.append(Gtk.Label(label=theme.name, ellipsize=3, css_classes=["caption"]))
            self.theme_box.append(tile)
            self._previews[theme.id] = preview
            known = known or theme.id == self._theme
        if not known:
            self._theme = themes.DEFAULT  # e.g. an imported theme that was removed
        self._previews[self._theme].set_selected(True)

    def _choose_theme(self, theme_id: str):
        for key, preview in self._previews.items():
            preview.set_selected(key == theme_id)
        self._theme = theme_id
        self.save()

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
                "editor_theme": self._theme,
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
        self._choose_theme(defaults["editor_theme"])  # saves


class _SheetsPage(Adw.PreferencesPage):
    """Defaults for sheet metadata (not written into the files)."""

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
    """Export templates: import (.typecase-template), save as a file, remove."""

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

    # --- Importing --------------------------------------------------------------

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
            return  # canceled
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

    # --- Saving and removing -------------------------------------------------

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
        # Into the trash, not permanently: something removed by accident can be restored.
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


THEMES_GUIDE = "https://kleinod.studio/typecase/themes/"


class _ThemesGroup(Adw.PreferencesGroup):
    """Editor themes: save a built-in one as a starting point, import GtkSourceView style schemes
    (.xml, e.g. from GNOME Text Editor), remove imported ones."""

    def __init__(self, on_change, toast):
        super().__init__(
            title=_("Editor Themes"),
            description=_("Import more themes as style scheme files (.xml), the format of GNOME Text Editor. Import the light and the dark variant to get both."),
        )
        self._on_change = on_change
        self._toast = toast
        button = Gtk.Button(label=_("Import…"), css_classes=["flat"], valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: self._choose())
        self.set_header_suffix(button)
        self._rows: list[Gtk.Widget] = []
        self.refresh()

    def refresh(self):
        for row in self._rows:
            self.remove(row)
        self._rows = []
        for theme in themes.available():
            variants = _("Light and dark") if theme.light != theme.dark else _("One variant for light and dark")
            row = Adw.ActionRow(title=theme.name, subtitle=variants)
            if theme.builtin:
                row.add_suffix(Gtk.Label(label=_("Built-in"), css_classes=["dim-label", "caption"], valign=Gtk.Align.CENTER))
                save = Gtk.Button(
                    icon_name="document-save-symbolic", tooltip_text=_("Save as File…"), css_classes=["flat"], valign=Gtk.Align.CENTER
                )
                save.connect("clicked", lambda _b, t=theme: self._choose_save(t))
                row.add_suffix(save)
            else:
                remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Remove"), css_classes=["flat"], valign=Gtk.Align.CENTER)
                remove.connect("clicked", lambda _b, t=theme: self._remove(t))
                row.add_suffix(remove)
            self.add(row)
            self._rows.append(row)
        # The guide on the website (opens the browser; Typecase itself stays offline).
        guide = Adw.ActionRow(title=_("How to Build Your Own Theme"), activatable=True)
        guide.add_suffix(Gtk.Image(icon_name="adw-external-link-symbolic"))
        guide.connect("activated", lambda _r: Gtk.UriLauncher(uri=THEMES_GUIDE).launch(self.get_root(), None, None))
        self.add(guide)
        self._rows.append(guide)

    def _choose_save(self, theme):
        """Both variants of a built-in theme as files to edit; they import next to the original."""
        dialog = Gtk.FileDialog(title=_("Save Theme"))
        dialog.select_folder(self.get_root(), None, lambda d, r: self._on_save_chosen(d, r, theme))

    def _on_save_chosen(self, dialog, result, theme):
        try:
            folder = Path(dialog.select_folder_finish(result).get_path())
        except (GLib.Error, TypeError):
            return  # canceled
        try:
            # Translators: file and theme name of a built-in theme saved as a starting point
            files = themes.save_builtin(theme.id, folder, _("%(name)s (custom)") % {"name": theme.name})
        except OSError as error:
            alert = Adw.AlertDialog(heading=_("Theme Not Saved"), body=error.strerror or str(error))
            alert.add_response("close", _("Close"))
            alert.present(self)
            return
        self._toast(_("Saved %s") % " · ".join(f"“{path.name}”" for path in files))

    def _choose(self):
        file_filter = Gtk.FileFilter(name=_("Style Schemes"))
        file_filter.add_suffix("xml")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(file_filter)
        dialog = Gtk.FileDialog(title=_("Import Theme"), filters=filters)
        dialog.open_multiple(self.get_root(), None, self._on_chosen)

    def _on_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return  # canceled
        imported = []
        for i in range(files.get_n_items()):
            path = Path(files.get_item(i).get_path())
            try:
                themes.install(path)
            except (themes.ThemeError, OSError) as error:
                alert = Adw.AlertDialog(heading=_("Theme Not Imported"), body=f"{path.name}: {error}")
                alert.add_response("close", _("Close"))
                alert.present(self)
                continue
            imported.append(path.name)
        if imported:
            self.refresh()
            self._on_change()
            self._toast(_("Imported %s") % ", ".join(imported))

    def _remove(self, theme):
        # Into the trash, like templates: something removed by accident can be restored.
        try:
            for path in theme.files:
                Gio.File.new_for_path(str(path)).trash(None)
        except GLib.Error as error:
            alert = Adw.AlertDialog(heading=_("Theme Not Removed"), body=error.message)
            alert.add_response("close", _("Close"))
            alert.present(self)
        themes.rescan()
        self.refresh()
        self._on_change()
        self._toast(_("Theme “%s” moved to the trash") % theme.name)


class PreferencesDialog(Adw.PreferencesDialog):
    """Preferences in GNOME style: changes take effect immediately and are saved right away.

    The "Editor" page covers the normal editor and, set apart below it, focus mode. Focus mode
    initially uses the editor's settings; only when that is switched off do its own settings
    apply (and appear)."""

    def __init__(self, apply):
        super().__init__(title=_("Preferences"))
        self._apply = apply

        # One page for both editors: the normal editor on top, focus mode below, clearly set apart.
        page = Adw.PreferencesPage(title=_("Writing"), icon_name="document-edit-symbolic", name="editor")
        _section_heading(page, _("Editor"), _("How your text looks while you write as usual."))
        self.editor_page = _ProfileSection(page, "editor", apply)
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
        page.add(tools)
        self.themes_group = _ThemesGroup(self._themes_changed, lambda text: self.add_toast(Adw.Toast(title=text)))
        page.add(self.themes_group)
        self._editor_reset(page)

        _section_heading(
            page,
            _("Focus Mode"),
            _("Focus mode hides the sidebar and toolbars and shows only your text, full screen."),
            separator=True,
        )
        same_group = Adw.PreferencesGroup()
        self.focus_same = Adw.SwitchRow(
            title=_("Use Editor Settings"),
            subtitle=_("Switch off to give focus mode its own font, size and style"),
            active=config.focus_uses_editor_settings(),
        )
        same_group.add(self.focus_same)
        page.add(same_group)
        self.focus_page = _ProfileSection(page, "focus", apply)
        # Its own font and style only matter when it doesn't use the editor's: hidden until then.
        for group in self.focus_page.groups:
            self.focus_same.bind_property(
                "active", group, "visible", GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.INVERT_BOOLEAN
            )
        self.focus_same.connect("notify::active", self._on_focus_same_changed)
        # The tiles show the light or dark variant, whichever the style currently uses.
        style = Adw.StyleManager.get_default()
        handler = style.connect("notify::dark", lambda *_a: [section.refresh_themes() for section in (self.editor_page, self.focus_page)])
        self.connect("closed", lambda _d: style.disconnect(handler))

        # Separate tool settings in focus mode (independent of "Use Editor Settings").
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
        page.add(focus_tools)
        self.add(page)

        self.sheets_page = _SheetsPage(apply)
        self.add(self.sheets_page)
        self.templates_page = _TemplatesPage(lambda text: self.add_toast(Adw.Toast(title=text)))
        self.add(self.templates_page)

    def _themes_changed(self):
        for section in (self.editor_page, self.focus_page):
            section.refresh_themes()
            section.save()  # a removed theme falls back to the default
        self._apply()

    def _editor_reset(self, page):
        """"Restore Defaults" for the editor sits after its tools, before the focus mode part."""
        group = self.editor_page.reset_group
        page.remove(group)
        page.add(group)

    def _on_focus_format_bar_changed(self, *_args):
        config.update(focus_format_bar=self.focus_format_bar.get_active())
        self._apply()

    def _on_format_bar_changed(self, *_args):
        config.update(format_bar=self.format_bar.get_active())
        self._apply()

    def _on_focus_same_changed(self, *_args):
        config.update(focus_same_as_editor=self.focus_same.get_active())
        self._apply()
