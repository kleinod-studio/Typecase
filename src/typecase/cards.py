"""What a card in the card view shows, and saving a card's notes – without GTK.

A card edits only the "notes" field of a sheet. When saving, the file is read again and only
that field is replaced, so the text and every other field stay exactly as they are on disk."""

import shutil
import time
from dataclasses import dataclass, field
from gettext import gettext as _
from pathlib import Path

from . import frontmatter
from .fileio import atomic_write_text, read_text
from .goal import parse_goal
from .library import unique_path
from .textstats import count_characters, count_words


@dataclass
class CardData:
    notes: str = ""
    status: str = ""
    keywords: list[str] = field(default_factory=list)
    words: int = 0
    characters: int = 0
    goal: int | None = None


def notes_of(data: dict) -> str:
    """The notes from parsed front matter as one text (a list is read line by line)."""
    value = data.get("notes", "")
    return (value if isinstance(value, str) else "\n".join(value)).strip("\n")


def read_card(path: Path) -> CardData:
    """Reads what a card shows. Raises OSError or UnicodeDecodeError."""
    header, body = frontmatter.split(read_text(path))
    data = frontmatter.parse(header)
    keywords = data.get("keywords", [])
    keywords = [keywords] if isinstance(keywords, str) else list(keywords)
    status = data.get("status", "")
    return CardData(
        notes=notes_of(data),
        status=status if isinstance(status, str) else "",
        keywords=[word.strip() for word in keywords if word.strip()],
        words=count_words(body),
        characters=count_characters(body),
        goal=parse_goal(data.get("goal")),
    )


def save_notes(path: Path, base: str, notes: str) -> Path | None:
    """Writes notes into the sheet's front matter. base is the notes as they were when the card
    read them. If the notes on disk have been changed elsewhere since then, that version is kept
    as a copy next to the sheet first, and its path is returned. A sheet deleted in the meantime
    is recreated with just the notes. Raises OSError or UnicodeDecodeError."""
    try:
        text = read_text(path)
    except FileNotFoundError:
        text = None
    header, body = frontmatter.split(text or "")
    on_disk = notes_of(frontmatter.parse(header))
    copy = None
    if text is not None and on_disk not in (base.strip("\n"), notes.strip("\n")):
        stamp = time.strftime("%Y-%m-%d %H.%M")
        copy = unique_path(path.parent, _("%(name)s (conflict %(date)s)") % {"name": path.stem, "date": stamp}, ".md")
        shutil.copyfile(path, copy)
    atomic_write_text(path, frontmatter.join(frontmatter.update(header, {"notes": notes}), body))
    return copy
