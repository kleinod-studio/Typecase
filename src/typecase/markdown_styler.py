import re

from gi.repository import Gdk, GLib, GtkSource, Pango

from .markdown_style import FENCE, fence_language, line_spans

_FENCE_LINES = re.compile(r"^[ \t]{0,3}(?:```|~~~).*$", re.MULTILINE)

# Gängige Kurznamen hinter ``` auf die Sprach-IDs von GtkSourceView abbilden.
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
    """Gestaltet Markdown im Puffer mit Text-Tags und hält sie beim Tippen aktuell.

    Nach einer Änderung werden nur die betroffenen Zeilen neu gestaltet (im Leerlauf,
    damit das Tippen nie wartet). Nur wenn ein Codeblock-Zaun (```) dazukommt oder
    wegfällt, wird alles neu gestaltet, weil sich dann die Zeilen darunter ändern.

    Codeblöcke mit Sprachangabe (```python) werden mit den Sprachregeln und Farben von
    GtkSourceView eingefärbt; code_blocks liefert dem Textfeld die Zeilen für den Rahmen."""

    def __init__(self, buffer):
        self.buffer = buffer
        self.tags = {}
        # (Zeile öffnender Zaun, letzte Zeile, geschlossen?); ein offener Block reicht bis zum Textende
        self.code_blocks: list[tuple[int, int, bool]] = []
        self.on_blocks_changed = None  # Rückruf, damit das Textfeld den Rahmen neu zeichnet

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
        tag("codeblock", family="monospace")
        tag("link", underline=Pango.Underline.SINGLE)
        tag("list-marker")
        tag("syntax")

        self._source_tags: dict[tuple, object] = {}  # Farben aus GtkSourceView, je Stil ein Tag
        self._highlighter = GtkSource.Buffer()
        self._languages = GtkSource.LanguageManager.get_default()

        self._dirty_start = buffer.create_mark(None, buffer.get_start_iter(), True)
        self._dirty_end = buffer.create_mark(None, buffer.get_start_iter(), False)
        self._dirty = False
        self._idle = 0
        self._fence_count = 0
        self.dark = False
        self.set_dark(False)

        buffer.connect_after("insert-text", self._on_insert)
        buffer.connect_after("delete-range", self._on_delete)

    def set_dark(self, dark: bool):
        self.dark = dark
        accent = "#78aeed" if dark else "#1c71d8"
        self.tags["syntax"].props.foreground_rgba = _rgba("rgba(255,255,255,0.35)" if dark else "rgba(0,0,0,0.35)")
        self.tags["code"].props.background_rgba = _rgba("rgba(255,255,255,0.06)" if dark else "rgba(0,0,0,0.05)")
        self.tags["link"].props.foreground_rgba = _rgba(accent)
        self.tags["list-marker"].props.foreground_rgba = _rgba(accent)
        if self.buffer.get_char_count():
            self.restyle_all()  # Syntaxfarben kommen aus dem (hellen/dunklen) Farbschema

    def restyle_all(self):
        self._cancel_idle()
        self._dirty = False
        text = self._text(self.buffer.get_start_iter(), self.buffer.get_end_iter())
        self._update_blocks(text)
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
        """Merkt sich die Zeilen aller Codeblöcke (ein offener Block reicht bis zum Ende)."""
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
            self.on_blocks_changed()  # auch bei gleichen Zeilen: Höhen können sich geändert haben

    # --- Gestalten -----------------------------------------------------------

    def _restyle_lines(self, first: int, last: int):
        buffer = self.buffer
        start = self._line_start(first)
        end = self._line_start(last)
        if not end.ends_line():
            end.forward_to_line_end()

        before = self._text(buffer.get_start_iter(), start)
        in_code = len(_FENCE_LINES.findall(before)) % 2 == 1

        for tag in list(self.tags.values()) + list(self._source_tags.values()):
            buffer.remove_tag(tag, start, end)

        offset = start.get_offset()
        for line in self._text(start, end).split("\n"):
            for a, b, name in line_spans(line, in_code):
                if a < b:
                    buffer.apply_tag(self.tags[name], buffer.get_iter_at_offset(offset + a), buffer.get_iter_at_offset(offset + b))
            if FENCE.match(line):
                in_code = not in_code
            offset += len(line) + 1

        for open_line, last_line, closed in self.code_blocks:
            if open_line <= last and last_line >= first:
                self._highlight_block(open_line, last_line, closed)

    def _highlight_block(self, open_line: int, last_line: int, closed: bool):
        """Färbt den Inhalt eines Codeblocks über einen unsichtbaren GtkSourceView-Puffer ein."""
        buffer = self.buffer
        language = self._language(fence_language(self._text(self._line_start(open_line), self._line_end(open_line))))
        content_last = last_line - 1 if closed else last_line
        if content_last <= open_line:
            return
        start, end = self._line_start(open_line + 1), self._line_end(content_last)
        for tag in self._source_tags.values():
            buffer.remove_tag(tag, start, end)  # alte Farben weg, auch wenn die Sprache entfernt wurde
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

    def _language(self, name: str):
        if not name:
            return None
        return self._languages.get_language(_LANGUAGE_ALIASES.get(name, name))

    def _source_tag(self, tags):
        """Übersetzt die Stil-Tags des unsichtbaren Puffers in eigene Tags (Farbe, fett, kursiv)."""
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
