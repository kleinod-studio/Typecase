import re

_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[-*+]|\d{1,9}[.)]|>)(?P<space>[ \t]+)(?P<box>\[[ xX]\][ \t]+)?")


def on_enter(line: str, column: int) -> tuple[str, str] | None:
    """Decides what the Enter key does in a line with a list marker.

    Returns ("continue", prefix) for the new line, ("end", "") if the empty list item
    ends the list, or None if the line is not a list item or the cursor is inside the
    list marker (then the normal line break applies)."""
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


# --- Numbering and indenting -----------------------------------------------

INDENT = "    "  # one level; per CommonMark enough for "- " and "1. "
_LIST_ITEM = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d{1,9}[.)])[ \t]+")
_NUMBERED = re.compile(r"^(?P<indent>[ \t]*)(?P<number>\d{1,9})(?P<delim>[.)])(?=[ \t])")


def _width(line: str) -> int:
    """Indentation in columns (tab = 4)."""
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
    """Number of the previous list item on the same level, None if there is none."""
    for i in range(index - 1, -1, -1):
        line = lines[i]
        if _blank(line) or _width(line) < width:
            return None
        if _width(line) == width:
            match = _NUMBERED.match(line)
            return int(match["number"]) if match else None
    return None


def renumber(lines: list[str], index: int, restart: bool = False) -> list[str]:
    """Renumbers consecutively the numbered list that contains line index.

    Only the level of this line is considered; more deeply indented lines in between
    (sub-items, continuations) are skipped. The first number is kept,
    unless restart=True, in which case the list starts at 1."""
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
    """Indents a list item by one level (direction=1) or outdents it (-1) and renumbers
    both affected levels. None if the line is not a list item or cannot be outdented
    any further."""
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

    # The level left behind: from now on the next item there continues counting correctly.
    for i in range(index + 1, len(out)):
        other = out[i]
        if _blank(other) or _width(other) < min(old_width, new_width):
            break
        if _width(other) == old_width:
            if _NUMBERED.match(other):
                out = renumber(out, i, restart=direction < 0)
            break
    return out
