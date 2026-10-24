"""Full-text search across the library, without GTK."""

import re
from dataclasses import dataclass
from pathlib import Path

from .fileio import read_text
from .library import Node, scan

SNIPPET_BEFORE = 40
SNIPPET_AFTER = 90
_WHITESPACE = re.compile(r"\s+")


@dataclass
class Hit:
    path: Path
    name: str
    group: str  # group relative to the library, "" for the root folder
    count: int  # matches in the text
    offset: int  # character position of the first match in the text, -1 if only the name matches
    snippet: str  # text excerpt around the first match, single line
    snippet_match: tuple[int, int]  # position of the match within the excerpt


class LibrarySearch:
    """Searches sheets for a term (case-insensitively).

    File contents are cached and only re-read when the file has changed;
    that way the search stays smooth while typing, even with 1,000 sheets."""

    def __init__(self):
        self._cache: dict[Path, tuple[float, int, str]] = {}

    def search(self, root: Path, query: str, overrides: dict[Path, str] | None = None) -> list[Hit]:
        """overrides: contents that are newer than the file (the sheet open in the editor)."""
        query = query.strip()
        if not query:
            return []
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        overrides = overrides or {}

        name_hits, text_hits = [], []
        for node in _sheets(scan(root)):
            text = overrides.get(node.path)
            if text is None:
                text = self._read(node.path)
            matches = list(pattern.finditer(text)) if text else []
            name_match = pattern.search(node.name) is not None
            if not matches and not name_match:
                continue
            group = str(node.path.parent.relative_to(root)) if node.path.parent != root else ""
            if matches:
                snippet, where = _snippet(text, matches[0].start(), matches[0].end())
                hit = Hit(node.path, node.name, group, len(matches), matches[0].start(), snippet, where)
            else:
                hit = Hit(node.path, node.name, group, 0, -1, _first_line(text), (0, 0))
            (name_hits if name_match else text_hits).append(hit)
        return name_hits + text_hits

    def _read(self, path: Path) -> str:
        try:
            stat = path.stat()
            cached = self._cache.get(path)
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return cached[2]
            text = read_text(path)
        except (OSError, UnicodeDecodeError):
            return ""
        self._cache[path] = (stat.st_mtime, stat.st_size, text)
        return text


def _sheets(nodes: list[Node]):
    for node in nodes:
        if node.is_group:
            yield from _sheets(node.children)
        else:
            yield node


def _snippet(text: str, start: int, end: int) -> tuple[str, tuple[int, int]]:
    """Excerpt from the line of the match, whitespace collapsed, with … where it is cut off."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    a = max(line_start, start - SNIPPET_BEFORE)
    b = min(line_end, end + SNIPPET_AFTER)
    before = _WHITESPACE.sub(" ", text[a:start]).lstrip()
    after = _WHITESPACE.sub(" ", text[end:b]).rstrip()
    prefix = "…" if a > line_start else ""
    suffix = "…" if b < line_end else ""
    match_start = len(prefix) + len(before)
    snippet = prefix + before + text[start:end] + after + suffix
    return snippet, (match_start, match_start + end - start)


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return " ".join(line.split())[: SNIPPET_BEFORE + SNIPPET_AFTER]
    return ""
