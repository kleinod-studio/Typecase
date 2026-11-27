from gettext import gettext as _

from gi.repository import Adw, Gtk

from . import config, template_builder as builder
from .export_templates import FIELD_TYPES, MAX_FIELDS, TemplateError
from .template_builder import Settings


class TemplateDialog(Adw.Dialog):
    """Assistant for an export template: a starting point and a few settings, no CSS or AI needed.
    on_saved(template) reports the result. With template, its settings are opened for changing."""

    def __init__(self, on_saved, on_error, template=None):
        super().__init__(title=_("Edit Template") if template else _("New Template"), content_width=480, content_height=680)
        self._on_saved = on_saved
        self._on_error = on_error
        self._template = template
        self._presets = builder.presets()
        settings = builder.settings_of(template) if template else None

        page = Adw.PreferencesPage()
        start = Adw.PreferencesGroup()
        self.name_row = Adw.EntryRow(title=_("Name"))
        self.name_row.connect("changed", lambda _r: self._update_save())
        start.add(self.name_row)
        self.preset_row = Adw.ComboRow(
            title=_("Starting Point"),
            subtitle=_("Fills in the settings below"),
            model=Gtk.StringList.new([label for label, _s in self._presets.values()]),
            visible=template is None,
        )
        start.add(self.preset_row)
        page.add(start)

        sheet = Adw.PreferencesGroup(title=_("Page"))
        self.paper_row = self._combo(sheet, _("Paper"), [paper.upper() if paper != "letter" else _("Letter") for paper in builder.PAPERS])
        self.margin_rows = {}
        for side, label in (("top", _("Top Margin")), ("right", _("Right Margin")), ("bottom", _("Bottom Margin")), ("left", _("Left Margin"))):
            self.margin_rows[side] = self._spin(sheet, label, 0, 100, 1, 0, _("Millimeters"))
        self.numbers_row = self._combo(sheet, _("Page Numbers"), [_("None"), _("Bottom Center"), _("Bottom Right")])
        page.add(sheet)

        body = Adw.PreferencesGroup(title=_("Text"))
        self.body_font_row = self._combo(body, _("Font"), list(builder.FONTS))
        self.size_row = self._spin(body, _("Size"), 8, 24, 0.5, 1, _("Points"))
        self.spacing_row = self._spin(body, _("Line Spacing"), 1, 3, 0.05, 2)
        self.indent_row = self._combo(body, _("Paragraphs"), [_("Gap Between Paragraphs"), _("First-Line Indent")])
        self.justify_row = self._combo(body, _("Alignment"), [_("Left"), _("Justified")])
        page.add(body)

        headings = Adw.PreferencesGroup(title=_("Headings"))
        self.heading_font_row = self._combo(headings, _("Font"), list(builder.FONTS))
        self.center_row = self._combo(headings, _("Alignment"), [_("Left"), _("Centered")])
        self.chapters_row = Adw.SwitchRow(title=_("Chapters on a New Page"), subtitle=_("Every top-level heading starts a page"))
        headings.add(self.chapters_row)
        page.add(headings)

        # Fields: what sheets fill in for this template (a letter's sender, recipient, subject)
        self.fields_group = Adw.PreferencesGroup(
            title=_("Fields"),
            description=_("Sheets that use this template fill them in, in the properties pane. The export puts them below the title, in this order."),
        )
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add Field"), valign=Gtk.Align.CENTER, css_classes=["flat"])
        add.connect("clicked", lambda _b: self._add_field(focus=True))
        self.fields_group.set_header_suffix(add)
        self._add_field_button = add
        self._field_rows = []  # (row, key, type drop-down)
        page.add(self.fields_group)

        document = Adw.PreferencesGroup(title=_("Export"))
        self.structure_row = Adw.SwitchRow(
            title=_("Offer Contents and Cover Page"),
            subtitle=_("Switch off for letters and forms; then the title is left out as well"),
        )
        document.add(self.structure_row)
        page.add(document)

        self.save_button = Gtk.Button(label=_("Save") if template else _("Create"), css_classes=["suggested-action"])
        self.save_button.connect("clicked", lambda _b: self._save())
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda _b: self.close())
        bar = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        bar.pack_start(cancel)
        bar.pack_end(self.save_button)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(bar)
        self.set_child(view)
        self.set_default_widget(self.save_button)

        self._show(settings or self._presets["text"][1])
        if template:
            self.name_row.set_text(template.title)
            for key, label, kind in (settings.fields if settings else ()):
                self._add_field(key, label, kind)
        self.preset_row.connect("notify::selected", lambda *_a: self._apply_preset())
        self._update_save()

    @staticmethod
    def _combo(group, title, items) -> Adw.ComboRow:
        row = Adw.ComboRow(title=title, model=Gtk.StringList.new(items))
        group.add(row)
        return row

    @staticmethod
    def _spin(group, title, low, high, step, digits, subtitle=None) -> Adw.SpinRow:
        row = Adw.SpinRow.new_with_range(low, high, step)
        row.set_title(title)
        row.set_digits(digits)
        if subtitle:
            row.set_subtitle(subtitle)
        group.add(row)
        return row

    def _add_field(self, key="", label="", kind="text", focus=False):
        if len(self._field_rows) >= MAX_FIELDS:
            return
        row = Adw.EntryRow(title=_("Field Name"), text=label)
        types = Gtk.DropDown(
            model=Gtk.StringList.new([_("One Line"), _("Several Lines"), _("Date")]),
            valign=Gtk.Align.CENTER,
            tooltip_text=_("Kind of Field"),
        )
        types.set_selected(FIELD_TYPES.index(kind))
        row.add_suffix(types)
        up = Gtk.Button(icon_name="go-up-symbolic", tooltip_text=_("Move Up"), valign=Gtk.Align.CENTER, css_classes=["flat"])
        up.connect("clicked", lambda _b: self._move_field(row, -1))
        row.add_suffix(up)
        remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Remove Field"), valign=Gtk.Align.CENTER, css_classes=["flat"])
        remove.connect("clicked", lambda _b: self._remove_field(row))
        row.add_suffix(remove)
        self._field_rows.append((row, key, types))
        self.fields_group.add(row)
        self._add_field_button.set_sensitive(len(self._field_rows) < MAX_FIELDS)
        if focus:
            row.grab_focus()

    def _remove_field(self, row):
        self._field_rows = [entry for entry in self._field_rows if entry[0] is not row]
        self.fields_group.remove(row)
        self._add_field_button.set_sensitive(True)

    def _move_field(self, row, step):
        index = next(i for i, entry in enumerate(self._field_rows) if entry[0] is row)
        target = index + step
        if not 0 <= target < len(self._field_rows):
            return
        rows = self._field_rows
        rows[index], rows[target] = rows[target], rows[index]
        # A preferences group only appends, so the rows are put in again in their new order
        for entry in rows:
            self.fields_group.remove(entry[0])
        for entry in rows:
            self.fields_group.add(entry[0])
        row.grab_focus()

    def _apply_preset(self):
        self._show(list(self._presets.values())[self.preset_row.get_selected()][1])

    def _show(self, settings: Settings):
        self.paper_row.set_selected(builder.PAPERS.index(settings.paper))
        for side, row in self.margin_rows.items():
            row.set_value(getattr(settings, f"margin_{side}"))
        self.numbers_row.set_selected(builder.PAGE_NUMBERS.index(settings.page_numbers))
        self.body_font_row.set_selected(builder.FONTS.index(settings.body_font))
        self.size_row.set_value(settings.body_size)
        self.spacing_row.set_value(settings.line_spacing)
        self.indent_row.set_selected(1 if settings.first_line_indent else 0)
        self.justify_row.set_selected(1 if settings.justify else 0)
        self.heading_font_row.set_selected(builder.FONTS.index(settings.heading_font))
        self.center_row.set_selected(1 if settings.heading_center else 0)
        self.chapters_row.set_active(settings.chapters_on_new_page)
        self.structure_row.set_active(settings.structure)

    def settings(self) -> Settings:
        return Settings(
            name=self.name_row.get_text().strip(),
            paper=builder.PAPERS[self.paper_row.get_selected()],
            margin_top=self.margin_rows["top"].get_value(),
            margin_right=self.margin_rows["right"].get_value(),
            margin_bottom=self.margin_rows["bottom"].get_value(),
            margin_left=self.margin_rows["left"].get_value(),
            body_font=builder.FONTS[self.body_font_row.get_selected()],
            body_size=self.size_row.get_value(),
            line_spacing=round(self.spacing_row.get_value(), 2),
            first_line_indent=self.indent_row.get_selected() == 1,
            justify=self.justify_row.get_selected() == 1,
            heading_font=builder.FONTS[self.heading_font_row.get_selected()],
            heading_center=self.center_row.get_selected() == 1,
            chapters_on_new_page=self.chapters_row.get_active(),
            page_numbers=builder.PAGE_NUMBERS[self.numbers_row.get_selected()],
            fields=tuple(
                (key, row.get_text().strip(), FIELD_TYPES[types.get_selected()])
                for row, key, types in self._field_rows
                if row.get_text().strip()
            ),
            structure=self.structure_row.get_active(),
        )

    def _update_save(self):
        self.save_button.set_sensitive(bool(self.name_row.get_text().strip()))

    def _save(self):
        try:
            saved = builder.save(self.settings(), config.TEMPLATES_DIR, self._template)
        except (OSError, TemplateError) as error:
            self._on_error(str(error))
            return
        self.close()
        self._on_saved(saved)
