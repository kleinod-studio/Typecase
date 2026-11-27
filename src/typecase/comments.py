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


# --- Editing (text and selection in, new text and selection out, like formatting.py) ---------

Result = tuple[str, int, int]


def at(text: str, start: int, end: int | None = None) -> Comment | None:
    """The comment that a position, or a selection, touches."""
    end = start if end is None else end
    return next((comment for comment in find(text) if comment.start <= end and start <= comment.end), None)


def caret_in(comment: Comment) -> int:
    """Where the caret goes to write the comment: at the end of its text."""
    return comment.note[1] if comment.note else comment.end


def add(text: str, start: int, end: int) -> Result:
    """Comments on the selection: marks it and puts the caret into the new, empty comment. Without
    a selection, the comment stands alone at the caret. In a comment already, the caret goes into
    it (a marked passage without one gets its comment)."""
    existing = at(text, start, end)
    if existing is not None:
        if existing.note is None:
            text = text[: existing.end] + "{>><<}" + text[existing.end :]
            return text, existing.end + 3, existing.end + 3
        place = caret_in(existing)
        return text, place, place
    passage = text[start:end]
    # A comment stays within one paragraph, and the marking leaves out spaces at its edges.
    if passage.strip() and not re.search(r"\n[ \t]*\n", passage):
        start += len(passage) - len(passage.lstrip())
        end -= len(passage) - len(passage.rstrip())
        new = text[:start] + "{==" + text[start:end] + "==}{>><<}" + text[end:]
        place = end + 9
        return new, place, place
    new = text[:end] + "{>><<}" + text[end:]
    return new, end + 3, end + 3


def remove(text: str, position: int) -> Result | None:
    """Removes the comment at the caret; its marked passage stays as plain text. None if there is none."""
    comment = at(text, position)
    if comment is None:
        return None
    kept = text[comment.marked[0] : comment.marked[1]] if comment.marked else ""
    start, end = comment.start, comment.end
    if not kept:  # a comment alone: a space before it goes too, or the whole line if that was all
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        line_end = len(text) if line_end == -1 else line_end
        if not text[line_start:start].strip() and not text[end:line_end].strip():
            start, end = line_start, min(line_end + 1, len(text))
        elif text[start - 1 : start] == " " and text[end : end + 1] in (" ", "\n", ""):
            start -= 1
    return text[:start] + kept + text[end:], start + len(kept), start + len(kept)


def neighbour(text: str, position: int, forward: bool = True) -> int | None:
    """Where the caret goes in the next (or previous) comment, around the end if need be. None
    without comments."""
    found = find(text)
    if not found:
        return None
    places = [caret_in(comment) for comment in found]
    if forward:
        return next((place for place in places if place > position), places[0])
    return next((place for place in reversed(places) if place < position), places[-1])


def for_word(text: str, author: str) -> str:
    """The text with its comments as Pandoc's comment spans, which become comments in the margin of
    a Word document: the marked passage is what they comment on."""
    found = find(text)
    if not found:
        return text
    pieces, position = [], 0
    for number, comment in enumerate(found):
        note = re.sub(r"([\[\]\\])", r"\\\1", comment.note_text(text))
        name = author.replace("\\", "\\\\").replace('"', '\\"')
        passage = text[comment.marked[0] : comment.marked[1]] if comment.marked else ""
        pieces.append(text[position : comment.start])
        pieces.append(
            f'[{note}]{{.comment-start id="{number}" author="{name}"}}{passage}[]{{.comment-end id="{number}"}}'
        )
        position = comment.end
    pieces.append(text[position:])
    return "".join(pieces)
