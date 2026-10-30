import re

from gi.repository import Gdk, GLib, GtkSource, Pango

from .markdown_style import FENCE, fence_language, line_spans, list_text_start

_FENCE_LINES = re.compile(r"^[ \t]{0,3}(?:```|~~~).*$", re.MULTILINE)
_BARE_ADDRESS = re.compile(r"\b(?:https?://|www\.)\S+|\b[\w.+-]+@[\w-]+\.[\w.-]+")
# Spans that the spell checker skips: code, code blocks, Markdown marks and link targets.
_NO_SPELL_CHECK = {"code", "codeblock", "syntax"}
# libspelling skips text with GtkSourceView's "no-spell-check" context class; since Typecase styles
# Markdown itself (no GtkSourceView language), it marks those regions with a tag of that name.
NO_SPELL_CHECK_TAG = "gtksourceview:context-classes:no-spell-check"

# Map common short names after ``` to GtkSourceView's language IDs.
_LANGUAGE_ALIASES = {
    "py": "python3",
    "python": "python3",
    "js": "js",
    "javascript": "js",
    "ts": "typescript",
    "sh": "sh",
    "bash": "sh",
    "shell": "sh",
    "zsh": "sh",
    "c++": "cpp",
    "cs": "c-sharp",
    "csharp": "c-sharp",
    "rs": "rust",
    "md": "markdown",
    "yml": "yaml",
    "html": "html",
    "xml": "xml",
}


def _rgba(spec: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(spec)
    return color


class MarkdownStyler:
    """Styles Markdown in the buffer with text tags and keeps them up to date while typing.

    After a change only the affected lines are restyled (when idle, so that typing
    never has to wait). Only when a code block fence (```) is added or removed is
    everything restyled, because then the lines below it change.

    Code blocks with a language (```python) are highlighted with GtkSourceView's language
    rules and colors; code_blocks gives the text view the lines for the frame."""

    def __init__(self, buffer):
        self.buffer = buffer
        self.tags = {}
        # (line of opening fence, last line, closed?); an open block extends to the end of the text
        self.code_blocks: list[tuple[int, int, bool]] = []
        self.on_blocks_changed = None  # callback so the text view redraws the frame
        # Width in pixels of a piece of text in the editor's font (set by the text view). With it,
        # wrapped lines of a list item line up with its text instead of with the marker.
        self.measure = None
        self._indent_tags: dict[int, object] = {}  # one hanging-indent tag per width

        def tag(name, **props):
            self.tags[name] = buffer.create_tag(f"md-{name}", **props)

        # Order = priority: later tags win (syntax dimming last).
        tag("h1", scale=1.6, weight=Pango.Weight.BOLD)
        tag("h2", scale=1.35, weight=Pango.Weight.BOLD)
        tag("h3", scale=1.15, weight=Pango.Weight.BOLD)
        for level in (4, 5, 6):
            tag(f"h{level}", weight=Pango.Weight.BOLD)
        tag("bold", weight=Pango.Weight.BOLD)
        tag("italic", style=Pango.Style.ITALIC)
        tag("strike", strikethrough=True)
        tag("underline", underline=Pango.Underline.SINGLE)
        tag("quote", style=Pango.Style.ITALIC)
        tag("code", family="monospace")
        tag("codeblock", family="monospace")
        tag("link", underline=Pango.Underline.SINGLE)
        tag("list-marker")
        tag("syntax")
        self.no_spell_check = buffer.create_tag(NO_SPELL_CHECK_TAG)

        self._source_tags: dict[tuple, object] = {}  # colors from GtkSourceView, one tag per style
        self._highlighter = GtkSource.Buffer()
        self._languages = GtkSource.LanguageManager.get_default()

        self._dirty_start = buffer.create_mark(None, buffer.get_start_iter(), True)
        self._dirty_end = buffer.create_mark(None, buffer.get_start_iter(), False)
        self._dirty = False
        self._idle = 0
        self._fence_count = 0
        self.palette: dict | None = None  # colors of the editor theme (see themes.palette)

        buffer.connect_after("insert-text", self._on_insert)
        buffer.connect_after("delete-range", self._on_delete)

    def set_palette(self, palette: dict):
        """Colors from the editor theme; the code highlighting follows the buffer's style scheme."""
        self.palette = palette
        self.tags["syntax"].props.foreground_rgba = palette["syntax"]
        self.tags["code"].props.background_rgba = palette["code"]
        self.tags["link"].props.foreground_rgba = palette["link"]
        self.tags["list-marker"].props.foreground_rgba = palette["list-marker"]
        for level in range(1, 7):
            tag = self.tags[f"h{level}"]
            if palette["heading"] is not None:
                tag.props.foreground_rgba = palette["heading"]
            else:
                tag.props.foreground_set = False
        if self.buffer.get_char_count():
            self.restyle_all()  # code colors come from the style scheme

    def restyle_all(self):
        self._cancel_idle()
        self._dirty = False
        text = self._text(self.buffer.get_start_iter(), self.buffer.get_end_iter())
        self._update_blocks(text)
        self._restyle_lines(0, self.buffer.get_line_count() - 1)

    # --- Tracking changes --------------------------------------------------

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
        fences_before = self._fence_count
        self._update_blocks(self._text(buffer.get_start_iter(), buffer.get_end_iter()))
        if self._fence_count != fences_before:
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

    def _update_blocks(self, text: str):
        """Remembers the lines of all code blocks (an open block extends to the end)."""
        fences = []
        line, position = 0, 0
        for match in _FENCE_LINES.finditer(text):
            line += text.count("\n", position, match.start())
            position = match.start()
            fences.append(line)
        self._fence_count = len(fences)
        last_line = text.count("\n")
        blocks = [
            (fences[i], fences[i + 1], True) if i + 1 < len(fences) else (fences[i], last_line, False)
            for i in range(0, len(fences), 2)
        ]
        if blocks != self.code_blocks:
            self.code_blocks = blocks
        if self.on_blocks_changed:
            self.on_blocks_changed()  # even if the lines are the same: heights may have changed

    # --- Styling -------------------------------------------------------------

    def _restyle_lines(self, first: int, last: int):
        buffer = self.buffer
        start = self._line_start(first)
        end = self._line_start(last)
        if not end.ends_line():
            end.forward_to_line_end()

        before = self._text(buffer.get_start_iter(), start)
        in_code = len(_FENCE_LINES.findall(before)) % 2 == 1

        for tag in [*self.tags.values(), *self._source_tags.values(), *self._indent_tags.values(), self.no_spell_check]:
            buffer.remove_tag(tag, start, end)

        offset = start.get_offset()
        for line in self._text(start, end).split("\n"):
            for a, b, name in line_spans(line, in_code):
                if a < b:
                    first_iter, last_iter = buffer.get_iter_at_offset(offset + a), buffer.get_iter_at_offset(offset + b)
                    buffer.apply_tag(self.tags[name], first_iter, last_iter)
                    if name in _NO_SPELL_CHECK:
                        buffer.apply_tag(self.no_spell_check, first_iter, last_iter)
            for match in _BARE_ADDRESS.finditer(line):  # web and mail addresses are no words
                buffer.apply_tag(self.no_spell_check, buffer.get_iter_at_offset(offset + match.start()), buffer.get_iter_at_offset(offset + match.end()))
            text_start = None if in_code or self.measure is None else list_text_start(line)
            if text_start is not None:
                tag = self._indent_tag(self.measure(line[:text_start]))
                buffer.apply_tag(tag, buffer.get_iter_at_offset(offset), buffer.get_iter_at_offset(offset + len(line)))
            if FENCE.match(line):
                in_code = not in_code
            offset += len(line) + 1

        for open_line, last_line, closed in self.code_blocks:
            if open_line <= last and last_line >= first:
                self._highlight_block(open_line, last_line, closed)

    def _highlight_block(self, open_line: int, last_line: int, closed: bool):
        """Highlights the content of a code block via an invisible GtkSourceView buffer."""
        buffer = self.buffer
        language = self._language(fence_language(self._text(self._line_start(open_line), self._line_end(open_line))))
        content_last = last_line - 1 if closed else last_line
        if content_last <= open_line:
            return
        start, end = self._line_start(open_line + 1), self._line_end(content_last)
        for tag in self._source_tags.values():
            buffer.remove_tag(tag, start, end)  # remove old colors, even if the language was removed
        if language is None:
            return
        code = self._text(start, end)

        hidden = self._highlighter
        hidden.set_style_scheme(buffer.get_style_scheme())
        hidden.set_language(language)
        hidden.set_text(code)
        hidden.ensure_highlight(hidden.get_start_iter(), hidden.get_end_iter())

        base = start.get_offset()
        position = hidden.get_start_iter()
        while not position.is_end():
            following = position.copy()
            if not following.forward_to_tag_toggle(None):
                following = hidden.get_end_iter()
            tag = self._source_tag(position.get_tags())
            if tag is not None:
                buffer.apply_tag(
                    tag,
                    buffer.get_iter_at_offset(base + position.get_offset()),
                    buffer.get_iter_at_offset(base + following.get_offset()),
                )
            position = following

    def _indent_tag(self, width: int):
        """A negative indent leaves the first line where it is and moves the wrapped lines in."""
        if width not in self._indent_tags:
            self._indent_tags[width] = self.buffer.create_tag(None, indent=-width)
        return self._indent_tags[width]

    def _language(self, name: str):
        if not name:
            return None
        return self._languages.get_language(_LANGUAGE_ALIASES.get(name, name))

    def _source_tag(self, tags):
        """Translates the style tags of the invisible buffer into our own tags (color, bold, italic)."""
        foreground, bold, italic = None, False, False
        for tag in tags:
            if tag.props.foreground_set:
                foreground = tag.props.foreground_rgba.to_string()
            if tag.props.weight_set and tag.props.weight >= Pango.Weight.BOLD:
                bold = True
            if tag.props.style_set and tag.props.style == Pango.Style.ITALIC:
                italic = True
        if foreground is None and not bold and not italic:
            return None
        key = (foreground, bold, italic)
        if key not in self._source_tags:
            props = {}
            if foreground:
                props["foreground_rgba"] = _rgba(foreground)
            if bold:
                props["weight"] = Pango.Weight.BOLD
            if italic:
                props["style"] = Pango.Style.ITALIC
            self._source_tags[key] = self.buffer.create_tag(None, **props)
        return self._source_tags[key]

    def _line_start(self, line: int):
        found, it = self.buffer.get_iter_at_line(line)
        return it if found else self.buffer.get_end_iter()

    def _line_end(self, line: int):
        it = self._line_start(line)
        if not it.ends_line():
            it.forward_to_line_end()
        return it

    def _text(self, a, b) -> str:
        return self.buffer.get_text(a, b, True)
