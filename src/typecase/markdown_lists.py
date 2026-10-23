import re

_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)]|>)(?P<space>[ \t]+)(?P<box>\[[ xX]\][ \t]+)?")


def on_enter(line: str, column: int) -> tuple[str, str] | None:
    """Entscheidet, was die Eingabetaste in einer Zeile mit Listenzeichen tut.

    Liefert ("continue", Präfix) für die neue Zeile, ("end", "") wenn der leere Listenpunkt
    die Liste beendet, oder None, wenn die Zeile keine Liste ist oder der Cursor im
    Listenzeichen steht (dann gilt der normale Zeilenumbruch)."""
    match = _ITEM.match(line)
    if match is None or column < match.end():
        return None
    if line[match.end() :].strip() == "":
        return ("end", "")

    marker = match["marker"]
    if marker[0].isdigit():
        marker = f"{int(marker[:-1]) + 1}{marker[-1]}"
    box = "[ ]" + match["box"][3:] if match["box"] else ""
    return ("continue", f"{match['indent']}{marker}{match['space']}{box}")


# --- Nummerieren und Einrücken ----------------------------------------------

INDENT = "    "  # eine Ebene; reicht nach CommonMark für "- " und "1. "
_LIST_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d{1,9}[.)])[ \t]+")
_NUMBERED = re.compile(r"^(?P<indent>[ \t]*)(?P<number>\d{1,9})(?P<delim>[.)])(?=[ \t])")


def _width(line: str) -> int:
    """Einrückung in Spalten (Tab = 4)."""
    width = 0
    for char in line:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            break
    return width


def _blank(line: str) -> bool:
    return line.strip() == ""


def _set_number(line: str, number: int) -> str:
    match = _NUMBERED.match(line)
    return f"{match['indent']}{number}{match['delim']}{line[match.end():]}"


def _previous_number(lines: list[str], index: int, width: int) -> int | None:
    """Nummer des vorherigen Listenpunkts auf derselben Ebene, None wenn es keinen gibt."""
    for i in range(index - 1, -1, -1):
        line = lines[i]
        if _blank(line) or _width(line) < width:
            return None
        if _width(line) == width:
            match = _NUMBERED.match(line)
            return int(match["number"]) if match else None
    return None


def renumber(lines: list[str], index: int, restart: bool = False) -> list[str]:
    """Nummeriert die nummerierte Liste fortlaufend, in der Zeile index steht.

    Betrachtet wird nur die Ebene dieser Zeile; tiefer eingerückte Zeilen dazwischen
    (Unterpunkte, Fortsetzungen) werden übersprungen. Die erste Nummer bleibt erhalten,
    außer restart=True, dann beginnt die Liste bei 1."""
    if not _NUMBERED.match(lines[index]):
        return lines
    width = _width(lines[index])

    start = index
    for i in range(index - 1, -1, -1):
        line = lines[i]
        if _blank(line) or _width(line) < width:
            break
        if _width(line) == width:
            if not _NUMBERED.match(line):
                break
            start = i

    out = list(lines)
    number = 1 if restart else int(_NUMBERED.match(lines[start])["number"])
    for i in range(start, len(out)):
        line = out[i]
        if _blank(line) or _width(line) < width:
            break
        if _width(line) == width:
            if not _NUMBERED.match(line):
                break
            out[i] = _set_number(line, number)
            number += 1
    return out


def change_indent(lines: list[str], index: int, direction: int) -> list[str] | None:
    """Rückt einen Listenpunkt um eine Ebene ein (direction=1) oder aus (-1) und nummeriert
    beide betroffenen Ebenen neu. None, wenn die Zeile kein Listenpunkt ist oder nicht weiter
    ausgerückt werden kann."""
    line = lines[index]
    item = _LIST_ITEM.match(line)
    if item is None:
        return None
    indent = item["indent"]
    if direction > 0:
        new_indent = indent + INDENT
    elif indent.endswith("\t"):
        new_indent = indent[:-1]
    elif indent:
        stripped = indent.rstrip(" ")
        new_indent = indent[: max(len(stripped), len(indent) - len(INDENT))]
    else:
        return None

    old_width = _width(line)
    out = list(lines)
    out[index] = new_indent + line[len(indent) :]
    new_width = _width(out[index])

    if _NUMBERED.match(out[index]):
        previous = _previous_number(out, index, new_width)
        out[index] = _set_number(out[index], previous + 1 if previous else 1)
        out = renumber(out, index)

    # Die zurückgelassene Ebene: der nächste Punkt dort zählt ab jetzt richtig weiter.
    for i in range(index + 1, len(out)):
        other = out[i]
        if _blank(other) or _width(other) < min(old_width, new_width):
            break
        if _width(other) == old_width:
            if _NUMBERED.match(other):
                out = renumber(out, i, restart=direction < 0)
            break
    return out
