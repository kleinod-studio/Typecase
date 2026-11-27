import re

from . import comments
from .images import plain_text

# A word: letters/digits, possibly joined by a hyphen or apostrophe ("e-mail", "don't").
# This way Markdown characters such as #, *, - or > do not count as words.
_WORD = re.compile(r"\w+(?:[-'’]\w+)*")
# Numbers at the start of numbered list items ("1. ", "12) ") are Markdown, not text.
_LIST_NUMBER = re.compile(r"^[ \t]*(?:>[ \t]*)*\d{1,9}[.)][ \t]+", re.MULTILINE)


def _counted(text: str) -> str:
    """What counts: no comments, and images only by their captions."""
    return plain_text(comments.strip(text))


def count_words(text: str) -> int:
    return sum(1 for _match in _WORD.finditer(_LIST_NUMBER.sub("", _counted(text))))


def count_characters(text: str) -> int:
    """Characters including spaces, excluding line breaks."""
    text = _counted(text)
    return len(text) - text.count("\n") - text.count("\r")
