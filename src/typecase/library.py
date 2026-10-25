import json
from dataclasses import dataclass
from pathlib import Path

from .fileio import atomic_write_text

# Per-folder settings of the library, written only where needed (for now: the manual order).
# A hidden JSON file keeps the file names untouched and travels along with sync tools.
FOLDER_FILE = ".typecase.json"


@dataclass
class Node:
    """An entry in the library: a group (folder, with children) or a sheet (.md file)."""

    name: str
    path: Path
    children: list["Node"] | None = None

    @property
    def is_group(self) -> bool:
        return self.children is not None


def scan(root: Path) -> list[Node]:
    """Reads a folder: groups first, then sheets, each sorted alphabetically – unless the folder
    has a manual order (see read_order), which then comes first. Hidden entries and symlinked
    folders are skipped."""
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

    return _apply_order(root, sorted(groups, key=by_name) + sorted(sheets, key=by_name))


def _apply_order(folder: Path, nodes: list[Node]) -> list[Node]:
    """Entries named in the folder's manual order come first, in that order; everything else
    (new or never sorted) follows in the default order. Names that no longer exist are ignored."""
    order = read_order(folder)
    if not order:
        return nodes
    position = {name: index for index, name in enumerate(order)}
    listed = sorted((n for n in nodes if n.path.name in position), key=lambda n: position[n.path.name])
    return listed + [n for n in nodes if n.path.name not in position]


def _read_folder_file(folder: Path) -> dict:
    try:
        data = json.loads((folder / FOLDER_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def read_order(folder: Path) -> list[str]:
    """The manual order of a folder: file and folder names (e.g. "Chapter 1.md", "Notes")."""
    order = _read_folder_file(folder).get("order", [])
    return [name for name in order if isinstance(name, str)] if isinstance(order, list) else []


def write_order(folder: Path, names: list[str]) -> None:
    """Stores the manual order atomically; other keys in the file are kept."""
    data = _read_folder_file(folder)
    data["order"] = names
    atomic_write_text(folder / FOLDER_FILE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def ordered_names(folder: Path) -> list[str]:
    """The names of a folder's entries in the order the library shows them."""
    return [node.path.name for node in scan(folder)] if folder.is_dir() else []


def place(item: Path, anchor: Path | None, after: bool = False) -> Path:
    """Moves a sheet or group next to anchor (before it, or after it) and stores the new order.
    Without an anchor the item goes to the end of its folder. If anchor is in another folder,
    the item is moved there first (same rules as move()). Returns the item's new path."""
    folder = anchor.parent if anchor is not None else item.parent
    if item.parent != folder:
        item = move(item, folder)
    names = [name for name in ordered_names(folder) if name != item.name]
    if anchor is None or anchor.name not in names:
        names.append(item.name)
    else:
        names.insert(names.index(anchor.name) + (1 if after else 0), item.name)
    write_order(folder, names)
    return item


def rename_in_order(folder: Path, old_name: str, new_name: str) -> None:
    """Keeps a renamed entry at its place in the manual order (if the folder has one)."""
    order = read_order(folder)
    if old_name in order:
        write_order(folder, [new_name if name == old_name else name for name in order])


def validate_name(name: str) -> str:
    """Returns the cleaned-up name, or raises ValueError if it is not usable as a file or folder name."""
    name = name.strip()
    if not name or name in (".", "..") or name.startswith(".") or "/" in name or "\0" in name:
        raise ValueError(name)
    return name


def sheet_filename(name: str) -> str:
    name = validate_name(name)
    return name if name.lower().endswith(".md") else name + ".md"


def unique_path(folder: Path, base: str, suffix: str = "") -> Path:
    """Returns a path that is still free: 'Base', then 'Base 2', 'Base 3' …"""
    candidate = folder / f"{base}{suffix}"
    number = 2
    while candidate.exists():
        candidate = folder / f"{base} {number}{suffix}"
        number += 1
    return candidate


def create_sheet(folder: Path, base: str) -> Path:
    path = unique_path(folder, base, ".md")
    # "x" fails instead of overwriting a file that has appeared in the meantime.
    with open(path, "x", encoding="utf-8"):
        pass
    return path


def create_group(folder: Path, base: str) -> Path:
    path = unique_path(folder, base)
    path.mkdir()
    return path


def rename(path: Path, new_name: str) -> Path:
    """Renames a sheet (the .md extension stays) or a group. Raises ValueError for an invalid name
    and FileExistsError if the target already exists. An existing target is never overwritten."""
    new_name = sheet_filename(new_name) if path.is_file() else validate_name(new_name)
    target = path.with_name(new_name)
    if target == path:
        return path
    if target.exists() and not _same_file(target, path):
        raise FileExistsError(str(target))
    # A case-only change on case-insensitive file systems is handled cleanly by rename().
    path.rename(target)
    return target


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except OSError:
        return False


def move(path: Path, folder: Path) -> Path:
    """Moves a sheet or a group into another folder. Raises ValueError if a group would be moved
    into itself, and FileExistsError if something with the same name already exists at the
    target. An existing target is never overwritten."""
    target = folder / path.name
    if target == path:
        return path
    if path.is_dir() and (folder == path or path in folder.parents):
        raise ValueError(str(folder))
    if target.exists():
        raise FileExistsError(str(target))
    path.rename(target)
    return target


def all_groups(nodes: list[Node]) -> list[Path]:
    """All groups (folders) of the library, in sidebar order."""
    groups: list[Path] = []
    for node in nodes:
        if node.is_group:
            groups.append(node.path)
            groups.extend(all_groups(node.children))
    return groups
