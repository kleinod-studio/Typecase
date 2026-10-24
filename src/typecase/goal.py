"""A sheet's writing goal (field "goal" in the front matter: number of words), without GTK."""

from pathlib import Path

from . import frontmatter
from .fileio import read_text
from .textstats import count_words

MAX_GOAL = 1_000_000
DEFAULT_GOAL = 1000  # suggested value when a goal is switched on


def parse_goal(value) -> int | None:
    """Word goal from the front matter; None if none is set or the value is unreadable.
    Thousands separators as dots and spaces ("1.500", "1 500") are tolerated."""
    if not isinstance(value, str):
        return None
    digits = value.strip().replace(".", "").replace(",", "").replace(" ", "").replace(" ", "")
    if not digits.isdigit():
        return None
    goal = int(digits)
    return goal if 0 < goal <= MAX_GOAL else None


def fraction(words: int, goal: int | None) -> float:
    """Fraction of the goal between 0 and 1 (beyond the goal it stays at 1)."""
    if not goal:
        return 0.0
    return max(0.0, min(1.0, words / goal))


class GoalIndex:
    """Reads the word goal and word count of sheets (for the rings in the library) and caches them
    until a file changes."""

    def __init__(self):
        self._cache: dict[Path, tuple[float, int, tuple[int, int] | None]] = {}

    def progress_of(self, path: Path) -> tuple[int, int] | None:
        """(words, goal), or None if the sheet has no goal."""
        try:
            stat = path.stat()
            cached = self._cache.get(path)
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return cached[2]
            header, body = frontmatter.split(read_text(path))
        except (OSError, UnicodeDecodeError):
            return None
        goal = parse_goal(frontmatter.parse(header).get("goal"))
        result = (count_words(body), goal) if goal else None
        self._cache[path] = (stat.st_mtime, stat.st_size, result)
        return result
