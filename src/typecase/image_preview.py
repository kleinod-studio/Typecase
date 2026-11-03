import re
from gettext import gettext as _
from pathlib import Path

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gsk, Gtk, Pango

from . import images

UPDATE_DELAY_MS = 150
MAX_HEIGHT = 560
MAX_DECODED_WIDTH = 1600  # large photos are loaded smaller, so writing stays fluid
PLACEHOLDER_HEIGHT = 44
GAP = 12  # between text and image, and between images on one line
PILL_ICON = 16
PILL_PADDING = 8
_CAPTION_MARKUP = re.compile(r"[*_`~\\]")


class _Picture:
    def __init__(self, image: images.Image, file: Path | None):
        self.image = image
        self.file = file
        self.texture = None
        self.problem = None  # text shown instead of the image
        self.size = (0, 0)  # width and height in the editor
        self.offset = 0


class _Line:
    """A line of text with images below it; the mark keeps its place while typing."""

    def __init__(self, mark, number: int, only_images: bool):
        self.mark = mark
        self.number = number
        self.only_images = only_images  # its text can fold into a pill
        self.pictures: list[_Picture] = []
        self.gap = 0


class ImagePreviews:
    """Shows the images of a sheet below their lines, in the editor.

    The text itself is never touched: a text tag leaves free space below the line, and the text
    view paints the image into that space (no widgets or special characters in the buffer, so
    nothing can end up in the file). Loading happens in the background.

    A line with nothing but images folds into a small pill, again with tags only. It unfolds while
    the caret or the selection is on it, so the text can be edited and copied as usual, and a
    button on the image opens its dialog. The first character stays (transparent, below the pill),
    since a line without any visible character would have no height and no room below it."""

    def __init__(self, view, buffer, sheet):
        """sheet: returns the path of the open sheet, or None."""
        self.view = view
        self.buffer = buffer
        self.sheet = sheet
        self.lines: list[_Line] = []
        self.on_edit = None  # the edit button was clicked
        self._stay_folded = False  # right after inserting or editing, until the caret moves
        self._hidden = buffer.create_tag(None, invisible=True)
        # Not quite 0: Pango takes an alpha of exactly 0 for "not set" and draws solid text.
        self._transparent = buffer.create_tag(None, foreground_rgba=Gdk.RGBA(0, 0, 0, 0.005))
        self._button = Gtk.Button(
            icon_name="document-edit-symbolic",
            tooltip_text=_("Edit Image…"),
            css_classes=["osd", "circular"],
            focus_on_click=False,
            visible=False,
        )
        self._button.update_property([Gtk.AccessibleProperty.LABEL], [_("Edit Image…")])
        self._button.connect("clicked", lambda _b: self.on_edit and self.on_edit())
        view.add_overlay(self._button, 0, 0)
        self._timer = 0
        self._tags: dict[int, object] = {}  # one tag per height
        self._sizes: dict[tuple, tuple[int, int] | None] = {}  # natural sizes by file and date
        self._textures: dict[tuple, object] = {}
        self._loading: set[tuple] = set()
        self._width = 0
        buffer.connect("changed", self._on_changed)
        buffer.connect("mark-set", self._on_mark_set)

    def _on_changed(self, _buffer):
        self._stay_folded = False
        self._apply_folding()
        self.queue_update()

    def _on_mark_set(self, buffer, _where, mark):
        if self.lines and mark in (buffer.get_insert(), buffer.get_selection_bound()):
            self._stay_folded = False
            self._apply_folding()

    def fold_caret_line(self) -> None:
        """Keeps the caret's line folded for now, for example after inserting an image."""
        self._stay_folded = True
        self._apply_folding()

    def queue_update(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(UPDATE_DELAY_MS, self._on_timer)

    def _on_timer(self):
        self._timer = 0
        self.update()
        return GLib.SOURCE_REMOVE

    def stop(self) -> None:
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def width_changed(self) -> None:
        """The text column got wider or narrower: images follow it (after this layout pass)."""
        width = self._available()
        if width != self._width and self.lines:
            GLib.idle_add(self.update)
        self._width = width

    def _available(self) -> int:
        return max(0, self.view.get_width() - self.view.get_left_margin() - self.view.get_right_margin())

    def update(self) -> bool:
        """Finds the images in the text and makes room for them."""
        sheet = self.sheet()
        buffer = self.buffer
        found = images.in_text(buffer.get_text(*buffer.get_bounds(), True)) if sheet is not None else []
        lines = buffer.get_text(*buffer.get_bounds(), True).split("\n") if found else []
        by_line: dict[int, list[images.Image]] = {}
        for number, image in found:
            if not images.is_remote(image.address):
                by_line.setdefault(number, []).append(image)

        for line in self.lines:
            buffer.delete_mark(line.mark)
        self.lines = []
        available = self._available() or 600
        for number, line_images in by_line.items():
            _found, start = buffer.get_iter_at_line(number)
            line = _Line(buffer.create_mark(None, start, True), number, images.only_images(lines[number]))
            for image in line_images:
                line.pictures.append(self._picture(image, sheet.parent, available))
            line.gap = sum(p.size[1] + GAP for p in line.pictures) + GAP // 2
            self.lines.append(line)
        self._apply_gaps()
        self._apply_folding()
        self.view.queue_draw()
        return False

    def _picture(self, image: images.Image, folder: Path, available: int) -> _Picture:
        file = images.resolve(image.address, folder)
        picture = _Picture(image, file)
        key = self._key(file)
        natural = None
        if key is None:
            picture.problem = _("Image not found: %s") % Path(image.address).name
        else:
            natural = self._natural_size(key)
            if natural is None:
                picture.problem = _("No preview for this image: %s") % Path(image.address).name
        if picture.problem:
            picture.size = (available, PLACEHOLDER_HEIGHT)
            return picture
        picture.offset, width, height = images.preview_size(image, natural, available, MAX_HEIGHT)
        picture.size = (width, height)
        picture.texture = self._textures.get(key)
        if picture.texture is None:
            self._load(key)
        return picture

    @staticmethod
    def _key(file: Path | None) -> tuple | None:
        try:
            status = file.stat()
        except (OSError, AttributeError):
            return None
        return (str(file), status.st_mtime_ns) if file.is_file() else None

    def _natural_size(self, key: tuple) -> tuple[int, int] | None:
        if key not in self._sizes:
            _format, width, height = GdkPixbuf.Pixbuf.get_file_info(key[0])
            self._sizes[key] = (width, height) if _format is not None and width > 0 and height > 0 else None
        return self._sizes[key]

    def _load(self, key: tuple) -> None:
        if key in self._loading:
            return
        self._loading.add(key)
        Gio.File.new_for_path(key[0]).read_async(GLib.PRIORITY_LOW, None, self._on_opened, key)

    def _on_opened(self, file, result, key):
        try:
            stream = file.read_finish(result)
        except GLib.Error:
            self._loaded(key, None)
            return
        width = min(self._sizes[key][0], MAX_DECODED_WIDTH)
        GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(stream, width, -1, True, None, self._on_decoded, key)

    def _on_decoded(self, _source, result, key):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(result)
        except GLib.Error:
            self._loaded(key, None)
            return
        # Photos often store their rotation separately; it can swap width and height.
        turned = pixbuf.apply_embedded_orientation()
        pixbuf = turned if turned is not None else pixbuf
        self._loaded(key, Gdk.Texture.new_for_pixbuf(pixbuf))

    def _loaded(self, key: tuple, texture) -> None:
        self._loading.discard(key)
        if texture is None:
            self._sizes[key] = None
        else:
            self._textures[key] = texture
            width, height = self._sizes[key]
            if (width > height) != (texture.get_width() > texture.get_height()):
                self._sizes[key] = (height, width)
        self.update()

    def _apply_gaps(self) -> None:
        """Makes room below the lines with images. Only what differs is touched: changing a tag
        lays its text out anew, which must not happen to the whole sheet while typing."""
        buffer = self.buffer
        spacing = self.view.get_pixels_below_lines()
        wanted = {line.number: line.gap + spacing for line in self.lines}
        for height in wanted.values():
            if height not in self._tags:
                self._tags[height] = buffer.create_tag(None, pixels_below_lines=height)
        correct = set()
        for height, tag in self._tags.items():
            for start, end in self._runs(tag):
                first, last = buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end)
                if first.starts_line() and last.ends_line() and first.get_line() == last.get_line() and wanted.get(first.get_line()) == height:
                    correct.add(first.get_line())
                else:
                    buffer.remove_tag(tag, first, last)
        for number, height in wanted.items():
            if number in correct:
                continue
            _found, first = buffer.get_iter_at_line(number)
            last = first.copy()
            if not last.ends_line():
                last.forward_to_line_end()
            buffer.apply_tag(self._tags[height], first, last)
        used = set(wanted.values())
        for height in [height for height in self._tags if height not in used]:
            buffer.get_tag_table().remove(self._tags.pop(height))

    def _open_lines(self) -> tuple[int, int]:
        """The lines that stay unfolded: from the caret to the other end of the selection."""
        buffer = self.buffer
        one = buffer.get_iter_at_mark(buffer.get_insert()).get_line()
        other = buffer.get_iter_at_mark(buffer.get_selection_bound()).get_line()
        return min(one, other), max(one, other)

    def _apply_folding(self) -> None:
        buffer = self.buffer
        hidden, transparent = set(), set()
        first_open, last_open = self._open_lines()
        for line in self.lines:
            start = buffer.get_iter_at_mark(line.mark)
            number = start.get_line()
            is_open = first_open <= number <= last_open and not (self._stay_folded and first_open == last_open)
            if not line.only_images or is_open:
                continue
            if not start.starts_line():
                continue  # the text just changed; the coming update looks at it again
            offset = start.get_offset()
            end = start.copy()
            if not end.ends_line():
                end.forward_to_line_end()
            transparent.add((offset, offset + 1))
            hidden.add((offset + 1, end.get_offset()))
        self._set_runs(self._hidden, hidden)
        self._set_runs(self._transparent, transparent)
        self.view.queue_draw()
        self._queue_place_button()

    def _set_runs(self, tag, wanted: set[tuple[int, int]]) -> None:
        buffer = self.buffer
        current = set(self._runs(tag))
        for start, end in current - wanted:
            buffer.remove_tag(tag, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end))
        for start, end in wanted - current:
            buffer.apply_tag(tag, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end))

    def _queue_place_button(self) -> None:
        # After the layout has followed the change.
        GLib.idle_add(self._place_button)

    def _place_button(self):
        """The edit button sits on the first image of the caret's line, once that line is open."""
        first_open, last_open = self._open_lines()
        for line, picture, x, y in self._rectangles():
            number = self.buffer.get_iter_at_mark(line.mark).get_line()
            if first_open == last_open == number and not self._stay_folded:
                size = self._button.get_width() or 34
                self.view.move_overlay(self._button, max(self.view.get_left_margin(), x + picture.size[0] - size - 6), y + 6)
                self._button.set_visible(True)
                return False
        self._button.set_visible(False)
        return False

    def _runs(self, tag) -> list[tuple[int, int]]:
        runs = []
        position = self.buffer.get_start_iter()
        start = 0 if position.has_tag(tag) else None
        while position.forward_to_tag_toggle(tag):
            if position.starts_tag(tag):
                start = position.get_offset()
            elif start is not None:
                runs.append((start, position.get_offset()))
                start = None
        return runs

    def _rectangles(self):
        """Every picture with its place, in the coordinates of the text."""
        left = self.view.get_left_margin()
        spacing = self.view.get_pixels_below_lines()
        for line in self.lines:
            last = self.buffer.get_iter_at_mark(line.mark)
            if not last.ends_line():
                last.forward_to_line_end()
            y, height = self.view.get_line_yrange(last)
            top = y + height - line.gap - spacing + GAP // 2
            for picture in line.pictures:
                yield line, picture, left + picture.offset, top
                top += picture.size[1] + GAP

    def _is_folded(self, line: _Line) -> bool:
        return self.buffer.get_iter_at_mark(line.mark).has_tag(self._transparent)

    def _pill(self, line: _Line):
        """Text and place of a folded line's pill."""
        image = line.pictures[0].image
        label = _CAPTION_MARKUP.sub("", image.caption) or Path(image.address).name
        layout = self.view.create_pango_layout(label)
        layout.set_attributes(Pango.AttrList.from_string("0 -1 scale 0.85"))
        left = self.view.get_left_margin()
        y, _height = self.view.get_line_yrange(self.buffer.get_iter_at_mark(line.mark))
        row = self.view.get_iter_location(self.buffer.get_iter_at_mark(line.mark)).height
        width = min(layout.get_pixel_size()[0] + PILL_ICON + 3 * PILL_PADDING, max(self._available(), 1))
        layout.set_width(int(max(width - PILL_ICON - 3 * PILL_PADDING, 1)) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        return layout, Graphene.Rect().init(left, y, width, row)

    def _snapshot_pill(self, snapshot, line: _Line) -> None:
        layout, rect = self._pill(line)
        fill = self.view.get_color()
        fill.alpha = 0.1
        rounded = Gsk.RoundedRect()
        rounded.init_from_rect(rect, rect.get_height() / 2)
        snapshot.push_rounded_clip(rounded)
        snapshot.append_color(fill, rect)
        snapshot.pop()
        color = self.view.get_color()
        color.alpha = 0.75
        icon = Gtk.IconTheme.get_for_display(self.view.get_display()).lookup_icon(
            "image-x-generic-symbolic", None, PILL_ICON, self.view.get_scale_factor(), Gtk.TextDirection.NONE, 0
        )
        snapshot.save()
        snapshot.translate(Graphene.Point().init(rect.get_x() + PILL_PADDING, rect.get_y() + (rect.get_height() - PILL_ICON) / 2))
        icon.snapshot_symbolic(snapshot, PILL_ICON, PILL_ICON, [color])
        snapshot.restore()
        snapshot.save()
        text_height = layout.get_pixel_size()[1]
        snapshot.translate(Graphene.Point().init(rect.get_x() + PILL_ICON + 2 * PILL_PADDING, rect.get_y() + (rect.get_height() - text_height) / 2))
        snapshot.append_layout(layout, color)
        snapshot.restore()

    def over_image(self, x: float, y: float) -> bool:
        """Whether a place in the view is on a pill or a picture: they react to clicks."""
        if self.picture_at(x, y) is not None:
            return True
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        for line in self.lines:
            if self._is_folded(line):
                rect = self._pill(line)[1]
                if rect.contains_point(Graphene.Point().init(bx, by)):
                    return True
        return False

    def snapshot(self, snapshot) -> None:
        visible = self.view.get_visible_rect()
        for line in self.lines:
            if self._is_folded(line):
                self._snapshot_pill(snapshot, line)
        for _line, picture, x, y in self._rectangles():
            width, height = picture.size
            if y + height < visible.y or y > visible.y + visible.height:
                continue
            rect = Graphene.Rect().init(x, y, width, height)
            if picture.texture is not None:
                snapshot.append_texture(picture.texture, rect)
            elif picture.problem:
                self._snapshot_problem(snapshot, picture, rect)
            else:
                color = self.view.get_color()
                color.alpha = 0.06
                snapshot.append_color(color, rect)

    def _snapshot_problem(self, snapshot, picture, rect) -> None:
        color = self.view.get_color()
        color.alpha = 0.25
        rounded = Gsk.RoundedRect()
        rounded.init_from_rect(rect, 6)
        snapshot.append_border(rounded, [1, 1, 1, 1], [color, color, color, color])
        layout = self.view.create_pango_layout(picture.problem)
        layout.set_width(int(max(rect.get_width() - 24, 1)) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        color = self.view.get_color()
        color.alpha = 0.7
        snapshot.save()
        text_height = layout.get_pixel_size()[1]
        point = Graphene.Point().init(rect.get_x() + 12, rect.get_y() + (rect.get_height() - text_height) / 2)
        snapshot.translate(point)
        snapshot.append_layout(layout, color)
        snapshot.restore()

    def picture_at(self, x: float, y: float) -> tuple[int, images.Image] | None:
        """(line, image) of the picture at a place in the view, or None."""
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        for line, picture, left, top in self._rectangles():
            width, height = picture.size
            if left <= bx < left + width and top <= by < top + height:
                return self.buffer.get_iter_at_mark(line.mark).get_line(), picture.image
        return None

    def pictures_loaded(self) -> bool:
        """Whether everything has been loaded (for the tests)."""
        return not self._loading and not self._timer
