from dataclasses import dataclass
from pathlib import Path


@dataclass
class Node:
    """Ein Eintrag der Bibliothek: eine Gruppe (Ordner, mit children) oder ein Blatt (.md-Datei)."""

    name: str
    path: Path
    children: list["Node"] | None = None

    @property
    def is_group(self) -> bool:
        return self.children is not None


def scan(root: Path) -> list[Node]:
    """Liest einen Ordner ein: Gruppen zuerst, dann Blätter, jeweils alphabetisch.
    Versteckte Einträge und verlinkte Ordner werden übersprungen."""
    groups: list[Node] = []
    sheets: list[Node] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir() and not entry.is_symlink():
            groups.append(Node(entry.name, entry, scan(entry)))
        elif entry.is_file() and entry.suffix.lower() == ".md":
            sheets.append(Node(entry.stem, entry))

    def by_name(node: Node) -> str:
        return node.name.casefold()

    return sorted(groups, key=by_name) + sorted(sheets, key=by_name)
