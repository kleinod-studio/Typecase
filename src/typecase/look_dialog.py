from gettext import gettext as _

from gi.repository import Adw, Gtk

from . import looks


def color_class(color: str | None) -> list[str]:
    """CSS classes that give an icon one of the library colors (see window._install_css)."""
    return [f"look-{color}"] if color else []


class LookDialog(Adw.Dialog):
    """Icon and color of a sheet or group in the library; on_apply gets the chosen looks.Look."""

    def __init__(self, look: looks.Look, is_group: bool, on_apply):
        super().__init__(title=_("Icon and Color"), content_width=420)
        self._on_apply = on_apply
        self._is_group = is_group

        self._colors = [None, *looks.COLORS]
        self.color_box = self._flow_box(len(looks.COLORS) + 1)
        for color in self._colors:
            swatch = Gtk.Box(css_classes=["look-swatch", f"look-swatch-{color}" if color else "look-swatch-standard"])
            swatch.set_size_request(24, 24)
            self._add_child(self.color_box, swatch, color_label(color))
        self.color_box.select_child(self.color_box.get_child_at_index(self._colors.index(look.color)))

        self._icons = [None, *looks.ICON_NAMES]
        self.icon_box = self._flow_box(7)
        self._images: list[Gtk.Image] = []
        for icon in self._icons:
            image = Gtk.Image(icon_name=looks.Look(icon).icon_name(is_group), pixel_size=24)
            self._images.append(image)
            self._add_child(self.icon_box, image, looks.icon_label(icon) if icon else _("Standard"))
        self.icon_box.select_child(self.icon_box.get_child_at_index(self._icons.index(look.icon)))
        self.color_box.connect("selected-children-changed", lambda _b: self._show_color())
        self._show_color()

        colors = Adw.PreferencesGroup(title=_("Color"))
        colors.add(self.color_box)
        icons = Adw.PreferencesGroup(title=_("Icon"))
        icons.add(self.icon_box)
        page = Adw.PreferencesPage()
        page.add(colors)
        page.add(icons)

        self.apply_button = Gtk.Button(label=_("Apply"), css_classes=["suggested-action"])
        self.apply_button.connect("clicked", lambda _b: self.apply())
        header = Adw.HeaderBar(show_end_title_buttons=False, show_start_title_buttons=False)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)
        header.pack_end(self.apply_button)
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self.set_default_widget(self.apply_button)

    @staticmethod
    def _flow_box(columns: int) -> Gtk.FlowBox:
        # Arrow keys move between the choices, Enter or a click picks one.
        return Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.BROWSE,
            min_children_per_line=columns,
            max_children_per_line=columns,
            homogeneous=True,
            column_spacing=4,
            row_spacing=4,
            css_classes=["look-choices"],
        )

    @staticmethod
    def _add_child(box: Gtk.FlowBox, widget: Gtk.Widget, label: str):
        widget.set_halign(Gtk.Align.CENTER)
        widget.set_valign(Gtk.Align.CENTER)
        child = Gtk.FlowBoxChild(child=widget, tooltip_text=label)
        child.update_property([Gtk.AccessibleProperty.LABEL], [label])
        box.append(child)

    def _selected(self, box: Gtk.FlowBox, values: list):
        chosen = box.get_selected_children()
        return values[chosen[0].get_index()] if chosen else None

    def _show_color(self):
        """The icons are shown in the chosen color."""
        classes = color_class(self._selected(self.color_box, self._colors))
        for image in self._images:
            image.set_css_classes(classes)

    @property
    def look(self) -> looks.Look:
        return looks.Look(self._selected(self.icon_box, self._icons), self._selected(self.color_box, self._colors))

    def apply(self) -> None:
        self._on_apply(self.look)
        self.close()


def color_label(color: str | None) -> str:
    return looks.color_label(color) if color else _("Standard")
