from gi.repository import Gdk, GLib, Graphene, Gsk, Gtk, Pango

from .markdown_style import FENCE, link_spans, note_definition, note_spans
from .markdown_styler import FOOTNOTE_SCALE

UPDATE_DELAY_MS = 150
PADDING = 6  # around the text of a pill
ICON_SIZE = 16
ROOM = PADDING + ICON_SIZE + PADDING // 2  # for the icon, at the start of a pill
ICONS = {"image": "image-x-generic-symbolic", "link": "typecase-link-symbolic", "note": "typecase-footnote-symbolic"}

# Tints behind the text, which keeps the theme's color. Soft enough for light and dark themes.
TINTS = {
    "image": (0.96, 0.78, 0.07, 0.28),
    "link": (0.21, 0.52, 0.89, 0.24),
    "note": (0.2, 0.75, 0.42, 0.24),
    "calm": (0.5, 0.5, 0.5, 0.16),  # focus mode: no colors to distract
}


def tint(kind: str, calm: bool) -> Gdk.RGBA:
    red, green, blue, alpha = TINTS["calm" if calm else kind]
    return Gdk.RGBA(red, green, blue, alpha)


def tag_runs(buffer, tag) -> list[tuple[int, int]]:
    """Where a tag lies in the buffer, as (start, end) offsets."""
    runs = []
    position = buffer.get_start_iter()
    start = 0 if position.has_tag(tag) else None
    while position.forward_to_tag_toggle(tag):
        if position.starts_tag(tag):
            start = position.get_offset()
        elif start is not None:
            runs.append((start, position.get_offset()))
            start = None
    return runs


def set_tag_runs(buffer, tag, wanted: set[tuple[int, int]]) -> None:
    """Puts a tag exactly on these ranges. Only what differs is touched: changing a tag lays its
    text out anew, which must not happen to a whole sheet while typing."""
    current = set(tag_runs(buffer, tag))
    for start, end in current - wanted:
        buffer.remove_tag(tag, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end))
    for start, end in wanted - current:
        buffer.apply_tag(tag, buffer.get_iter_at_offset(start), buffer.get_iter_at_offset(end))


def snapshot_icon(view, snapshot, kind: str, x: float, y: float, color: Gdk.RGBA) -> None:
    icon = Gtk.IconTheme.get_for_display(view.get_display()).lookup_icon(
        ICONS[kind], None, ICON_SIZE, view.get_scale_factor(), Gtk.TextDirection.NONE, 0
    )
    snapshot.save()
    snapshot.translate(Graphene.Point().init(x, y))
    icon.snapshot_symbolic(snapshot, ICON_SIZE, ICON_SIZE, [color])
    snapshot.restore()


class _Pill:
    """A link or footnote: marks at its start and end, and around its text. While folded, its first
    character stays in place, transparent and spaced out, to make room for the icon."""

    def __init__(self, buffer, kind: str, offset: int, span: tuple[int, int, int, int]):
        start, text_start, text_end, end = (buffer.get_iter_at_offset(offset + value) for value in span)
        self.kind = kind
        self.marks = [buffer.create_mark(None, place, True) for place in (start, text_start, text_end, end)]
        self.folded = False
        self.wide = False  # at the start of a row, where only half of the spacing takes effect
        self.note = ""  # what a reference like [^1] stands for, shown on hover
        self.label = text_start.get_text(text_end) if kind == "note" and span[1] == span[0] + 2 else ""

    def offsets(self, buffer) -> list[int]:
        return [buffer.get_iter_at_mark(mark).get_offset() for mark in self.marks]


class TextPills:
    """Links and footnotes in the running text as tinted pills with an icon, their markup folded away.

    Like the images (see image_preview), this only uses text tags and painting below the text; the
    text itself stays untouched. A pill unfolds while the caret touches it or a selection covers
    it, so it can be edited, and copying always takes the whole Markdown.

    Hidden text must never come with space below its line: GTK 4.24 aborts when it is asked for a
    position there. So all spacing in the editor lies above the lines."""

    def __init__(self, view, buffer):
        self.view = view
        self.buffer = buffer
        self.calm = False
        self.pills: list[_Pill] = []
        self._timer = 0
        self._hidden = buffer.create_tag(None, invisible=True)
        # A folded link reads like the other pills: muted text, no underline. It looks like a link
        # again, in the theme's color, while it is open for editing.
        self._muted = buffer.create_tag(None, underline=Pango.Underline.NONE)
        # In a pill, a note has the size of the text around it: rows of smaller text would be
        # lower, and the pill uneven. (Text tags multiply their scales.)
        self._note_size = buffer.create_tag(None, scale=1 / FOOTNOTE_SCALE)
        self._color = None
        self._anchors: dict[int, object] = {}  # one tag per width of the room they make
        self._measure_idle = 0
        buffer.connect("changed", lambda _b: self.queue_update())
        buffer.connect("mark-set", self._on_mark_set)

    def set_text_color(self, color: Gdk.RGBA) -> None:
        muted = color.copy()
        muted.alpha *= 0.75
        self._color = muted
        self._muted.props.foreground_rgba = muted

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

    def _on_mark_set(self, buffer, _where, mark):
        if self.pills and mark in (buffer.get_insert(), buffer.get_selection_bound()):
            self._apply_folding()

    def update(self) -> None:
        """Finds the links and footnotes in the text."""
        buffer = self.buffer
        for pill in self.pills:
            for mark in pill.marks:
                buffer.delete_mark(mark)
        self.pills = []
        offset = 0
        in_code_block = False
        definitions = {}
        for line in buffer.get_text(*buffer.get_bounds(), True).split("\n"):
            if FENCE.match(line):
                in_code_block = not in_code_block
            elif not in_code_block and ("[" in line or "<" in line or "http" in line or "www." in line):
                definition = note_definition(line)
                if definition is not None:
                    definitions[definition[0]] = definition[1]
                found = [("link", span) for span in link_spans(line)] + [("note", span) for span in note_spans(line)]
                self.pills += [_Pill(buffer, kind, offset, span) for kind, span in sorted(found, key=lambda item: item[1])]
            offset += len(line) + 1
        for pill in self.pills:
            pill.note = definitions.get(pill.label, "")
        self._apply_folding()
        self.view.queue_draw()

    def _room(self, pill: _Pill, first_character: str) -> int:
        """Letter spacing that gives the first character the width of the icon."""
        spacing = max(ROOM - self.view.text_width(first_character), 1)
        return 2 * spacing if pill.wide else spacing

    def queue_measure(self) -> None:
        if not self._measure_idle:
            self._measure_idle = GLib.idle_add(self._measure)

    def _measure(self):
        """Pango applies only half of the letter spacing at the start and end of a row, and where
        a row breaks is known only after the layout. So the room is checked and corrected here."""
        self._measure_idle = 0
        changed = False
        for pill in self.pills:
            if pill.folded:
                width = self.view.char_area(self.buffer.get_iter_at_mark(pill.marks[0])).width
                wide = width < ROOM - 2 if not pill.wide else width <= ROOM + 4
                if wide != pill.wide:
                    pill.wide = wide
                    changed = True
        if changed:
            self._apply_folding()
        return GLib.SOURCE_REMOVE

    def _anchor_tag(self, spacing: int):
        if spacing not in self._anchors:
            # Not quite 0: Pango takes an alpha of exactly 0 for "not set" and draws solid text.
            self._anchors[spacing] = self.buffer.create_tag(
                None, foreground_rgba=Gdk.RGBA(0, 0, 0, 0.005), letter_spacing=spacing * Pango.SCALE
            )
        return self._anchors[spacing]

    def _apply_folding(self) -> None:
        buffer = self.buffer
        caret = buffer.get_iter_at_mark(buffer.get_insert()).get_offset()
        other = buffer.get_iter_at_mark(buffer.get_selection_bound()).get_offset()
        first, last = min(caret, other), max(caret, other)
        hidden, muted, notes = set(), set(), set()
        anchors: dict[int, set] = {spacing: set() for spacing in self._anchors}
        for pill in self.pills:
            start, text_start, text_end, end = pill.offsets(buffer)
            pill.folded = not (start <= last and first <= end) and end > start
            if not pill.folded:
                continue  # the caret touches it, or the selection covers it
            character = buffer.get_iter_at_offset(start).get_char()
            anchors.setdefault(self._room(pill, character), set()).add((start, start + 1))
            if text_start < text_end:
                muted.add((max(text_start, start + 1), text_end))
                if pill.kind == "note":
                    notes.add((text_start, text_end))
            if start + 1 < text_start:
                hidden.add((start + 1, text_start))
            if text_end < end:
                hidden.add((text_end, end))
        set_tag_runs(buffer, self._hidden, hidden)
        set_tag_runs(buffer, self._muted, muted)
        set_tag_runs(buffer, self._note_size, notes)
        for spacing, runs in anchors.items():
            set_tag_runs(buffer, self._anchor_tag(spacing), runs)
        self.queue_measure()

    def _rows(self, start, end):
        """The parts of a range of visible text on each row of the display, as rectangles."""
        view = self.view
        position = start.copy()
        while True:
            stop = position.copy()
            view.forward_display_line_end(stop)
            if stop.compare(end) >= 0 or stop.compare(position) <= 0:
                stop = end.copy()
            last = stop.copy()
            last.backward_char()
            left, right = view.char_area(position), view.char_area(last)
            yield left.x, left.y, max(right.x + right.width - left.x, 1), left.height
            if stop.compare(end) >= 0:
                return
            following = stop.copy()
            if not view.forward_display_line(following):
                return
            if not view.starts_display_line(following):
                view.backward_display_line_start(following)
            if following.compare(stop) <= 0 or following.compare(end) >= 0:
                return
            position = following

    def _pill_rectangles(self, pill: _Pill):
        buffer = self.buffer
        start, text_start, text_end, end = pill.offsets(buffer)
        if not pill.folded and text_start >= text_end:
            return []
        first = buffer.get_iter_at_offset(start if pill.folded else text_start)
        rows = list(self._rows(first, buffer.get_iter_at_offset(text_end)))
        pills = [(x - PADDING, y, width + 2 * PADDING, height) for x, y, width, height in rows]
        if pill.folded:  # the first row starts with the room for the icon
            x, y, width, height = rows[0]
            pills[0] = (x, y, width + PADDING, height)
        return pills

    def snapshot(self, snapshot) -> None:
        buffer = self.buffer
        visible = self.view.get_visible_rect()
        color = self._color or self.view.get_color()
        for pill in self.pills:
            start, _text_start, text_end, end = pill.offsets(buffer)
            if self.view.char_area(buffer.get_iter_at_offset(start)).y > visible.y + visible.height:
                break
            if self.view.char_area(buffer.get_iter_at_offset(end)).y + 40 < visible.y:
                continue
            fill = tint(pill.kind, self.calm)
            rectangles = self._pill_rectangles(pill)
            for x, y, width, height in rectangles:
                rect = Graphene.Rect().init(x, y, width, height)
                rounded = Gsk.RoundedRect()
                rounded.init_from_rect(rect, height / 2)
                snapshot.push_rounded_clip(rounded)
                snapshot.append_color(fill, rect)
                snapshot.pop()
            if pill.folded and rectangles:
                x, y, _width, height = rectangles[0]
                snapshot_icon(self.view, snapshot, pill.kind, x + PADDING, y + (height - ICON_SIZE) / 2, color)

    def note_at(self, x: float, y: float) -> str | None:
        """What a folded reference to a footnote at a place in the view stands for, or None."""
        bx, by = self.view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, int(x), int(y))
        point = Graphene.Point().init(bx, by)
        for pill in self.pills:
            if pill.note and pill.folded:
                for left, top, width, height in self._pill_rectangles(pill):
                    if Graphene.Rect().init(left, top, width, height).contains_point(point):
                        return pill.note
        return None

    def is_folded(self, pill: _Pill) -> bool:
        """Whether its markup is hidden right now (for the tests)."""
        return pill.folded
