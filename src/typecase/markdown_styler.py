import re

from gi.repository import Gdk, GLib, Pango

from .markdown_style import line_spans, FENCE

_FENCE_LINES = re.compile(r"^[ \t]{0,3}(?:```|~~~)", re.MULTILINE)


def _rgba(spec: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(spec)
    return color


class MarkdownStyler:
    """Gestaltet Markdown im Puffer mit Text-Tags und hält sie beim Tippen aktuell.

    Nach einer Änderung werden nur die betroffenen Zeilen neu gestaltet (im Leerlauf,
    damit das Tippen nie wartet). Nur wenn ein Codeblock-Zaun (```) dazukommt oder
    wegfällt, wird alles neu gestaltet, weil sich dann die Zeilen darunter ändern."""

    def __init__(self, buffer):
        self.buffer = buffer
        self.tags = {}

        def tag(name, **props):
            self.tags[name] = buffer.create_tag(f"md-{name}", **props)

        # Reihenfolge = Priorität: spätere Tags gewinnen (Syntax-Dimmen zuletzt).
        tag("h1", scale=1.6, weight=Pango.Weight.BOLD)
        tag("h2", scale=1.35, weight=Pango.Weight.BOLD)
        tag("h3", scale=1.15, weight=Pango.Weight.BOLD)
        for level in (4, 5, 6):
            tag(f"h{level}", weight=Pango.Weight.BOLD)
        tag("bold", weight=Pango.Weight.BOLD)
        tag("italic", style=Pango.Style.ITALIC)
        tag("strike", strikethrough=True)
        tag("quote", style=Pango.Style.ITALIC)
        tag("code", family="monospace")
        tag("link", underline=Pango.Underline.SINGLE)
        tag("list-marker")
        tag("syntax")

        self._dirty_start = buffer.create_mark(None, buffer.get_start_iter(), True)
        self._dirty_end = buffer.create_mark(None, buffer.get_start_iter(), False)
        self._dirty = False
        self._idle = 0
        self._fence_count = 0
        self.set_dark(False)

        buffer.connect_after("insert-text", self._on_insert)
        buffer.connect_after("delete-range", self._on_delete)

    def set_dark(self, dark: bool):
        accent = "#78aeed" if dark else "#1c71d8"
        self.tags["syntax"].props.foreground_rgba = _rgba("rgba(255,255,255,0.35)" if dark else "rgba(0,0,0,0.35)")
        self.tags["code"].props.background_rgba = _rgba("rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.05)")
        self.tags["link"].props.foreground_rgba = _rgba(accent)
        self.tags["list-marker"].props.foreground_rgba = _rgba(accent)

    def restyle_all(self):
        self._cancel_idle()
        self._dirty = False
        self._fence_count = len(_FENCE_LINES.findall(self._text(self.buffer.get_start_iter(), self.buffer.get_end_iter())))
        self._restyle_lines(0, self.buffer.get_line_count() - 1)

    # --- Änderungen verfolgen -----------------------------------------------

    def _on_insert(self, _buffer, location, text, _length):
        last = location.get_line()
        self._mark_dirty(last - text.count("\n"), last)

    def _on_delete(self, _buffer, start, _end):
        self._mark_dirty(start.get_line(), start.get_line())

    def _mark_dirty(self, first: int, last: int):
        buffer = self.buffer
        if self._dirty:
            first = min(first, buffer.get_iter_at_mark(self._dirty_start).get_line())
            last = max(last, buffer.get_iter_at_mark(self._dirty_end).get_line())
        buffer.move_mark(self._dirty_start, self._line_start(max(first, 0)))
        buffer.move_mark(self._dirty_end, self._line_start(last))
        self._dirty = True
        if not self._idle:
            self._idle = GLib.idle_add(self._on_idle)

    def _on_idle(self):
        self._idle = 0
        if not self._dirty:
            return GLib.SOURCE_REMOVE
        self._dirty = False
        buffer = self.buffer
        fences = len(_FENCE_LINES.findall(self._text(buffer.get_start_iter(), buffer.get_end_iter())))
        if fences != self._fence_count:
            self._fence_count = fences
            self._restyle_lines(0, buffer.get_line_count() - 1)
        else:
            self._restyle_lines(
                buffer.get_iter_at_mark(self._dirty_start).get_line(),
                buffer.get_iter_at_mark(self._dirty_end).get_line(),
            )
        return GLib.SOURCE_REMOVE

    def _cancel_idle(self):
        if self._idle:
            GLib.source_remove(self._idle)
            self._idle = 0

    # --- Gestalten -----------------------------------------------------------

    def _restyle_lines(self, first: int, last: int):
        buffer = self.buffer
        start = self._line_start(first)
        end = self._line_start(last)
        if not end.ends_line():
            end.forward_to_line_end()

        before = self._text(buffer.get_start_iter(), start)
        in_code = len(_FENCE_LINES.findall(before)) % 2 == 1

        for tag in self.tags.values():
            buffer.remove_tag(tag, start, end)

        offset = start.get_offset()
        for line in self._text(start, end).split("\n"):
            for a, b, name in line_spans(line, in_code):
                if a < b:
                    buffer.apply_tag(self.tags[name], buffer.get_iter_at_offset(offset + a), buffer.get_iter_at_offset(offset + b))
            if FENCE.match(line):
                in_code = not in_code
            offset += len(line) + 1

    def _line_start(self, line: int):
        found, it = self.buffer.get_iter_at_line(line)
        return it if found else self.buffer.get_end_iter()

    def _text(self, a, b) -> str:
        return self.buffer.get_text(a, b, True)
