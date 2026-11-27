"""Comments in a sheet, without GTK.

Comments are notes to yourself while revising. They are written in CriticMarkup, so the sheet
stays a plain Markdown file that other tools can read:

    The storm {==cracked the lamp==}{>>too dramatic?<<} last night.
    {>>A paragraph is missing here.<<}

{==…==} marks a passage, {>>…<<} holds the comment on it; a comment may also stand alone. A
marked passage without a comment is allowed too. Comments stay within one paragraph, and
markup inside code (code spans and code blocks) is left alone. The export leaves comments out
and keeps the marked passages as plain text."""

import re
from dataclasses import dataclass

from .markdown_style import FENCE

# Any text up to the next blank line: comments do not reach into the next paragraph.
_IN_PARAGRAPH = r"(?:(?!\n[ \t]*\n).)*?"
_COMMENT = re.compile(
    r"\{==(?P<marked>" + _IN_PARAGRAPH + r")==\}(?:[ \t]*\{>>(?P<after>" + _IN_PARAGRAPH + r")<<\})?"
    r"|\{>>(?P<alone>" + _IN_PARAGRAPH + r")<<\}",
    re.DOTALL,
)
_CODE_SPAN = re.compile(r"(`+)(?:(?!\n[ \t]*\n).)+?\1", re.DOTALL)
_MASK = "\x00"
_GONE = "\x01"  # stands in for a removed comment until lines left empty are dropped
_EMPTY_LINE = re.compile(r"^[ \t" + _GONE + r"]*" + _GONE + r"[ \t" + _GONE + r"]*(?:\n|$)", re.MULTILINE)

Range = tuple[int, int]


@dataclass(frozen=True)
class Comment:
    """A comment in a text: start and end cover all of its markup. marked is the range of the
    marked passage, note the range of the comment's text; either may be None."""

    start: int
    end: int
    marked: Range | None
    note: Range | None

    def note_text(self, text: str) -> str:
        return text[self.note[0] : self.note[1]].strip() if self.note else ""


def _masked(text: str) -> str:
    """The text with code blocks and code spans hidden, at the same positions."""
    chars = list(text)
    position, fenced = 0, False
    for line in text.splitlines(keepends=True):
        fence = FENCE.match(line)
        if fenced or fence:
            chars[position : position + len(line)] = _MASK * len(line)
        if fence:
            fenced = not fenced
        position += len(line)
    masked = "".join(chars)
    return _CODE_SPAN.sub(lambda match: _MASK * len(match.group(0)), masked)


def find(text: str) -> list[Comment]:
    """All comments in text, in order."""
    found = []
    for match in _COMMENT.finditer(_masked(text)):
        if match.group("alone") is not None:
            found.append(Comment(match.start(), match.end(), None, match.span("alone")))
        else:
            note = match.span("after") if match.group("after") is not None else None
            found.append(Comment(match.start(), match.end(), match.span("marked"), note))
    return found


def strip(text: str) -> str:
    """The text without comments: marked passages stay as plain text, and a line that held
    nothing but comments disappears, so paragraphs stay as they were."""
    comments = find(text)
    if not comments:
        return text
    pieces, position = [], 0
    for comment in comments:
        pieces.append(text[position : comment.start])
        pieces.append(text[comment.marked[0] : comment.marked[1]] if comment.marked else _GONE)
        position = comment.end
    pieces.append(text[position:])
    result = _EMPTY_LINE.sub("", "".join(pieces))
    return result.replace(_GONE, "")
