"""Schlagwörter aus den Dateiköpfen sammeln und die Bibliothek danach filtern, ohne GTK."""

from pathlib import Path

from . import frontmatter
from .fileio import read_text
from .library import Node


class KeywordIndex:
    """Liest die Schlagwörter (Feld "keywords") der Blätter und merkt sie sich, bis sich eine Datei ändert."""

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
        """Alle Schlagwörter mit der Zahl ihrer Blätter, alphabetisch. Groß-/Kleinschreibung zählt
        nicht; angezeigt wird die Schreibweise, die zuerst vorkommt."""
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
    """Nur Blätter, für die keep(blatt) gilt, und die Gruppen auf dem Weg dorthin."""
    result = []
    for node in nodes:
        if node.is_group:
            children = filter_nodes(node.children, keep)
            if children:
                result.append(Node(node.name, node.path, children))
        elif keep(node):
            result.append(node)
    return result
