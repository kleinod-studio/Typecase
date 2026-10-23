from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk, Pango

from . import config


class PreferencesDialog(Adw.PreferencesDialog):
    """Einstellungen im GNOME-Stil: Änderungen wirken sofort und werden gleich gespeichert."""

    def __init__(self, apply):
        super().__init__(title=_("Preferences"))
        self._apply = apply  # Rückruf: Einstellungen auf Fenster und Editor anwenden
        current = config.settings()

        page = Adw.PreferencesPage(title=_("Editor"), icon_name="document-edit-symbolic")
        self.add(page)

        # Schrift
        font_group = Adw.PreferencesGroup(title=_("Font"))
        page.add(font_group)

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
        family = current["editor_font"] or Pango.FontDescription.from_string(
            Gtk.Settings.get_default().props.gtk_font_name or "Sans"
        ).get_family()
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
        text_group = Adw.PreferencesGroup(title=_("Text Block"))
        page.add(text_group)

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
        look_group = Adw.PreferencesGroup(title=_("Appearance"))
        page.add(look_group)
        self.color_scheme = Adw.ComboRow(
            title=_("Style"),
            model=Gtk.StringList.new([_("Follow System"), _("Light"), _("Dark")]),
            selected=config.COLOR_SCHEMES.index(current["color_scheme"]),
        )
        look_group.add(self.color_scheme)

        reset_group = Adw.PreferencesGroup()
        page.add(reset_group)
        reset = Gtk.Button(label=_("Restore Defaults"), halign=Gtk.Align.CENTER, css_classes=["pill"])
        reset.connect("clicked", lambda _b: self._reset())
        reset_group.add(reset)

        for widget, signal in [
            (self.system_font, "notify::active"),
            (self.font_button, "notify::font-desc"),
            (self.font_size, "notify::value"),
            (self.line_width, "notify::value"),
            (self.line_spacing, "notify::selected"),
            (self.color_scheme, "notify::selected"),
        ]:
            widget.connect(signal, lambda *_args: self._save())

    def _save(self):
        font = None
        if not self.system_font.get_active() and self.font_button.get_font_desc() is not None:
            font = self.font_button.get_font_desc().get_family()
        config.update(
            editor_font=font,
            editor_font_size=int(self.font_size.get_value()),
            line_width=int(self.line_width.get_value()),
            line_spacing=config.LINE_SPACINGS[self.line_spacing.get_selected()],
            color_scheme=config.COLOR_SCHEMES[self.color_scheme.get_selected()],
        )
        self._apply()

    def _reset(self):
        defaults = config.SETTINGS_DEFAULTS
        self.system_font.set_active(True)
        self.font_size.set_value(defaults["editor_font_size"])
        self.line_width.set_value(defaults["line_width"])
        self.line_spacing.set_selected(config.LINE_SPACINGS.index(defaults["line_spacing"]))
        self.color_scheme.set_selected(config.COLOR_SCHEMES.index(defaults["color_scheme"]))
        self._save()
