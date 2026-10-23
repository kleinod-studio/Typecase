"""Schreibziel eines Blatts (Feld "goal" im Dateikopf: Anzahl Wörter), ohne GTK."""

from pathlib import Path

from . import frontmatter
from .fileio import read_text
from .textstats import count_words

MAX_GOAL = 1_000_000
DEFAULT_GOAL = 1000  # Vorschlag, wenn man ein Ziel einschaltet


def parse_goal(value) -> int | None:
    """Wortziel aus dem Dateikopf; None, wenn keins gesetzt oder der Wert unlesbar ist.
    Tausenderpunkte und -leerzeichen ("1.500", "1 500") werden toleriert."""
    if not isinstance(value, str):
        return None
    digits = value.strip().replace(".", "").replace(",", "").replace(" ", "").replace(" ", "")
    if not digits.isdigit():
        return None
    goal = int(digits)
    return goal if 0 < goal <= MAX_GOAL else None


def fraction(words: int, goal: int | None) -> float:
    """Anteil des Ziels zwischen 0 und 1 (darüber hinaus bleibt es bei 1)."""
    if not goal:
        return 0.0
    return max(0.0, min(1.0, words / goal))


class GoalIndex:
    """Liest Wortziel und Wortzahl der Blätter (für die Ringe in der Bibliothek) und merkt sie sich,
    bis sich eine Datei ändert."""

    def __init__(self):
        self._cache: dict[Path, tuple[float, int, tuple[int, int] | None]] = {}

    def progress_of(self, path: Path) -> tuple[int, int] | None:
        """(Wörter, Ziel) oder None, wenn das Blatt kein Ziel hat."""
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
