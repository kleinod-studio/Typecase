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


def validate_name(name: str) -> str:
    """Gibt den bereinigten Namen zurück oder wirft ValueError, wenn er als Datei- oder Ordnername nicht taugt."""
    name = name.strip()
    if not name or name in (".", "..") or name.startswith(".") or "/" in name or "\0" in name:
        raise ValueError(name)
    return name


def sheet_filename(name: str) -> str:
    name = validate_name(name)
    return name if name.lower().endswith(".md") else name + ".md"


def unique_path(folder: Path, base: str, suffix: str = "") -> Path:
    """Liefert einen noch freien Pfad: 'Base', dann 'Base 2', 'Base 3' …"""
    candidate = folder / f"{base}{suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{base} {number}{suffix}"
        number += 1
    return candidate


def create_sheet(folder: Path, base: str) -> Path:
    path = unique_path(folder, base, ".md")
    # "x" schlägt fehl, statt eine inzwischen entstandene Datei zu überschreiben.
    with open(path, "x", encoding="utf-8"):
        pass
    return path


def create_group(folder: Path, base: str) -> Path:
    path = unique_path(folder, base)
    path.mkdir()
    return path


def rename(path: Path, new_name: str) -> Path:
    """Benennt ein Blatt (Endung .md bleibt) oder eine Gruppe um. Wirft ValueError bei ungültigem Namen
    und FileExistsError, wenn das Ziel schon existiert. Ein bestehendes Ziel wird nie überschrieben."""
    new_name = sheet_filename(new_name) if path.is_file() else validate_name(new_name)
    target = path.with_name(new_name)
    if target == path:
        return path
    if target.exists() and not _same_file(target, path):
        raise FileExistsError(str(target))
    # Reine Groß-/Kleinschreibung auf Dateisystemen ohne Unterscheidung wird von rename() sauber erledigt.
    path.rename(target)
    return target


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return False
