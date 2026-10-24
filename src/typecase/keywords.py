"""Collecting keywords from the front matter and filtering the library by them, without GTK."""

from pathlib import Path

from . import frontmatter
from .fileio import read_text
from .library import Node


class KeywordIndex:
    """Reads the keywords (field "keywords") of sheets and caches them until a file changes."""

    def __init__(self):
        self._cache: dict[Path, tuple[float, int, list[str]]] = {}

    def keywords_of(self, path: Path) -> list[str]:
        try:
            stat = path.stat()
            cached = self._cache.get(path)
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return cached[2]
            header, _body = frontmatter.split(read_text(path))
        except (OSError, UnicodeDecodeError):
            return []
        value = frontmatter.parse(header).get("keywords", [])
        keywords = [value] if isinstance(value, str) else list(value)
        keywords = [word.strip() for word in keywords if word.strip()]
        self._cache[path] = (stat.st_mtime, stat.st_size, keywords)
        return keywords

    def summary(self, nodes: list[Node]) -> list[tuple[str, int]]:
        """All keywords with the number of their sheets, sorted alphabetically. Case does not
        matter; the spelling that occurs first is the one shown."""
        counts: dict[str, list] = {}
        for sheet in sheets(nodes):
            for word in {w.casefold(): w for w in self.keywords_of(sheet.path)}.values():
                entry = counts.setdefault(word.casefold(), [word, 0])
                entry[1] += 1
        return sorted(((word, count) for word, count in counts.values()), key=lambda item: item[0].casefold())

    def has(self, path: Path, keyword: str) -> bool:
        wanted = keyword.casefold()
        return any(word.casefold() == wanted for word in self.keywords_of(path))


def sheets(nodes: list[Node]):
    for node in nodes:
        if node.is_group:
            yield from sheets(node.children)
        else:
            yield node


def filter_nodes(nodes: list[Node], keep) -> list[Node]:
    """Only sheets for which keep(sheet) holds, plus the groups on the way to them."""
    result = []
    for node in nodes:
        if node.is_group:
            children = filter_nodes(node.children, keep)
            if children:
                result.append(Node(node.name, node.path, children))
        elif keep(node):
            result.append(node)
    return result
