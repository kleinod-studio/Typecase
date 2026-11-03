from dataclasses import replace
from gettext import gettext as _

from gi.repository import Adw, Gtk

from . import images

WIDTHS = ("", "25%", "50%", "75%", "100%")


class ImageDialog(Adw.Dialog):
    """Size, alignment, alternative text and caption of an image; on_apply gets the changed image."""

    def __init__(self, image: images.Image, on_apply):
        super().__init__(title=_("Image"), content_width=420)
        self._image = image
        self._on_apply = on_apply

        # A size written by hand is offered as it is, so opening the dialog never changes it.
        self._widths = list(WIDTHS) + ([image.width] if image.width not in WIDTHS else [])
        labels = [_("Original Size"), _("Small"), _("Medium"), _("Large"), _("Full Width")] + self._widths[len(WIDTHS):]
        self.size_row = Adw.ComboRow(title=_("Size"), model=Gtk.StringList.new(labels))
        self.size_row.set_selected(self._widths.index(image.width))
        self._alignments = ("", *images.ALIGNMENTS)
        self.align_row = Adw.ComboRow(
            title=_("Alignment"),
            subtitle=_("Standard follows the template"),
            model=Gtk.StringList.new([_("Standard"), _("Left"), _("Center"), _("Right")]),
        )
        self.align_row.set_selected(self._alignments.index(image.align))
        layout = Adw.PreferencesGroup()
        layout.add(self.size_row)
        layout.add(self.align_row)

        self.caption_row = Adw.EntryRow(title=_("Caption"), text=image.caption, activates_default=True)
        captions = Adw.PreferencesGroup(description=_("Shown below the image in the export"))
        captions.add(self.caption_row)
        self.alt_row = Adw.EntryRow(title=_("Alternative Text"), text=image.alt, activates_default=True)
        descriptions = Adw.PreferencesGroup(description=_("Describes the image for people who cannot see it"))
        descriptions.add(self.alt_row)

        page = Adw.PreferencesPage()
        page.add(layout)
        page.add(captions)
        page.add(descriptions)

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

    def apply(self) -> None:
        self._on_apply(
            replace(
                self._image,
                width=self._widths[self.size_row.get_selected()],
                align=self._alignments[self.align_row.get_selected()],
                caption=self.caption_row.get_text().strip(),
                alt=self.alt_row.get_text().strip(),
            )
        )
        self.close()
