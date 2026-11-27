"""Markdown tables (pipe tables), without GTK.

A table is a header row, a separator row and any number of body rows, with cells divided by
"|". The colons in the separator set each column's alignment:

    | Name  | Town    | Age |
    |:------|:-------:|----:|
    | Anna  | Hamburg |  34 |

The pipes at the start and end of a row are optional. Like Pandoc, which does the export, a
table starts a block (at the start of the text, after a blank line or a heading) and ends at
the first line without a pipe. A "|" inside `code` or written as "\\|" divides no cells.

Tidying pads the cells so the columns line up in a font of fixed width. It never drops text:
a row with more cells than the separator has columns gets the table a column more (Pandoc
would leave those cells out of the export), and short rows are filled with empty cells."""

import re
import unicodedata
from dataclasses import dataclass

from .markdown_style import FENCE

LEFT, CENTER, RIGHT = "left", "center", "right"

_SEPARATOR_CELL = re.compile(r"\A[ \t]*(:?)-+(:?)[ \t]*\Z")
_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}([ \t]|$)")
_INDENT = re.compile(r"^[ \t]{0,3}(?=\S)")


@dataclass
class Table:
    rows: list[list[str]]  # header first, then the body; cells without the spaces around them
    aligns: list[str | None]  # one per column of the separator: LEFT, CENTER, RIGHT or None

    @property
    def columns(self) -> int:
        return max([len(self.aligns), *(len(row) for row in self.rows)])


def pipe_positions(line: str) -> list[int]:
    """Where the line has pipes that divide cells (not inside `code`, not written as \\|)."""
    positions = []
    i = 0
    while i < len(line):
        char = line[i]
        if char == "\\":
            i += 2
            continue
        if char == "`":
            ticks = len(line[i:]) - len(line[i:].lstrip("`"))
            close = line.find("`" * ticks, i + ticks)
            while close != -1 and line[close + ticks : close + ticks + 1] == "`":  # a longer run
                close = line.find("`" * ticks, close + ticks + 1)
            if close != -1:
                i = close + ticks
                continue
            i += ticks
            continue
        if char == "|":
            positions.append(i)
        i += 1
    return positions


def is_row(line: str) -> bool:
    """Whether the line can be a row of a table: it has a dividing pipe and is no code."""
    return bool(_INDENT.match(line)) and bool(pipe_positions(line))


def cell_spans(line: str) -> list[tuple[int, int]]:
    """The cells of a row as (start, end) of their text, without the spaces around it. A pipe at
    the start or end of the row opens or closes the row; it adds no empty cell."""
    pipes = pipe_positions(line)
    bounds = [-1, *pipes, len(line)]
    spans = []
    for a, b in zip(bounds, bounds[1:]):
        start, end = a + 1, b
        while start < end and line[start] in " \t":
            start += 1
        while end > start and line[end - 1] in " \t":
            end -= 1
        spans.append((start, end))
    if pipes and not line[: pipes[0]].strip():
        spans.pop(0)
    if pipes and not line[pipes[-1] + 1 :].strip() and spans:
        spans.pop()
    return spans


def cells(line: str) -> list[str]:
    return [line[a:b] for a, b in cell_spans(line)]


def separator_aligns(line: str) -> list[str | None] | None:
    """The alignments if the line is a separator row ("|:--|--:|"), otherwise None."""
    if not is_row(line):
        return None
    parts = cells(line)
    if not parts:
        return None
    aligns = []
    for part in parts:
        match = _SEPARATOR_CELL.match(part)
        if not match:
            return None
        left, right = bool(match.group(1)), bool(match.group(2))
        aligns.append(CENTER if left and right else RIGHT if right else LEFT if left else None)
    return aligns


def find(lines: list[str]) -> list[tuple[int, int]]:
    """The tables in the text's lines as (first line, last line), both included. Tables in code
    blocks don't count."""
    tables = []
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            in_code = not in_code
            i += 1
            continue
        starts_block = i == 0 or not lines[i - 1].strip() or bool(_HEADING.match(lines[i - 1]))
        if (
            not in_code
            and starts_block
            and i + 1 < len(lines)
            and is_row(line)
            and separator_aligns(lines[i + 1]) is not None
        ):
            last = i + 1
            while last + 1 < len(lines) and is_row(lines[last + 1]) and not FENCE.match(lines[last + 1]):
                last += 1
            tables.append((i, last))
            i = last + 1
            continue
        i += 1
    return tables


def table_at(lines: list[str], line: int) -> tuple[int, int] | None:
    """The table the line belongs to, as (first line, last line), or None."""
    for first, last in find(lines):
        if first <= line <= last:
            return first, last
        if first > line:
            break
    return None


def parse(lines: list[str]) -> Table:
    """The table in these lines (header, separator, body), as find() returns them."""
    rows = [cells(lines[0]), *(cells(line) for line in lines[2:])]
    return Table(rows, separator_aligns(lines[1]) or [])


def width(text: str) -> int:
    """How many columns the text takes in a font of fixed width (wide characters take two)."""
    total = 0
    for char in text:
        if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf"):
            continue
        total += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return total


def render(table: Table) -> list[str]:
    """The table as tidy lines: every row has all columns, padded so the pipes line up."""
    count = table.columns
    rows = [row + [""] * (count - len(row)) for row in table.rows]
    aligns = table.aligns + [None] * (count - len(table.aligns))
    widths = [max(3, *(width(row[c]) for row in rows)) for c in range(count)]

    def line(row: list[str]) -> str:
        return "| " + " | ".join(_pad(text, widths[c], aligns[c]) for c, text in enumerate(row)) + " |"

    separator = "|" + "|".join(_separator_cell(widths[c], aligns[c]) for c in range(count)) + "|"
    return [line(rows[0]), separator, *(line(row) for row in rows[1:])]


def gaps(lines: list[str], width_of=None) -> list[list[tuple[int, float]]]:
    """Where the editor widens a table's rows so their pipes line up, without changing the text:
    for every row, (offset of the character before a pipe, extra width). width_of(text, row)
    measures a piece of a row (row 0 is the header); by default in characters of fixed width."""
    measure = width_of or (lambda text, _row: width(text))
    rows = []
    for number, line in enumerate(lines):
        pipes = pipe_positions(line)
        if pipes and not line[: pipes[0]].strip():
            pipes = pipes[1:]  # the leading pipe belongs to the first piece
        pieces, start = [], 0
        for pipe in pipes:
            pieces.append((pipe, measure(line[start:pipe], number)))
            start = pipe + 1
        rows.append(pieces)
    columns = [0.0] * max((len(pieces) for pieces in rows), default=0)
    for pieces in rows:
        for column, (_pipe, size) in enumerate(pieces):
            columns[column] = max(columns[column], size)
    return [
        [(pipe - 1, columns[column] - size) for column, (pipe, size) in enumerate(pieces) if pipe > 0 and columns[column] > size]
        for pieces in rows
    ]


def tidy(lines: list[str]) -> list[str]:
    """The table's lines tidied (see render())."""
    return render(parse(lines))


EMPTY_CELL = "  "  # the caret goes between the spaces; the editor lines up the columns itself


def empty_row(count: int) -> str:
    """A row of empty cells, short so that typing in a cell pushes no spaces ahead of it."""
    return "|" + f"{EMPTY_CELL}|" * count


def new(header: list[str], body_rows: int = 2) -> list[str]:
    """The lines of a new table with these column titles and empty body rows."""
    head = render(Table([list(header)], [None] * len(header)))
    return head + [empty_row(len(header))] * body_rows


def _pad(text: str, size: int, align: str | None) -> str:
    space = size - width(text)
    if align == RIGHT:
        return " " * space + text
    if align == CENTER:
        return " " * (space // 2) + text + " " * (space - space // 2)
    return text + " " * space


def _separator_cell(size: int, align: str | None) -> str:
    dashes = size + 2  # the cell's text has a space on either side
    if align == CENTER:
        return ":" + "-" * (dashes - 2) + ":"
    if align == RIGHT:
        return "-" * (dashes - 1) + ":"
    if align == LEFT:
        return ":" + "-" * (dashes - 1)
    return "-" * dashes


def cell_index(line: str, column: int) -> int:
    """Which cell of the row the caret (in characters from the line start) is in. A caret right
    before a pipe is still in the cell to its left; before the leading pipe, in the first cell."""
    pipes = pipe_positions(line)
    index = sum(1 for pipe in pipes if pipe < column)
    if pipes and not line[: pipes[0]].strip():
        index -= 1  # the leading pipe opens the row
    return max(index, 0)


def move(
    lines: list[str], row: int, column: int, forward: bool, tidy: bool = False
) -> tuple[list[str], int, int, int] | None:
    """Tab and Shift+Tab in a table: the next or previous cell, from the cell at (row, column)
    (row 0 is the header, 1 the separator). Returns the lines and the row, start and end of that
    cell's text, to select. Tab in the last cell adds an empty row, and a short row gets the cell
    it lacks; otherwise the text stays as it is, unless tidy is set. Shift+Tab in the first cell
    returns None."""
    table = parse(lines)
    count = table.columns
    if row == 1:  # the separator: between the header and the first body row
        index = count - 1 if forward else count
        row = 0
    else:
        index = min(cell_index(lines[row], column), count - 1)
    position = (0 if row == 0 else row - 1) * count + index + (1 if forward else -1)
    if position < 0:
        return None
    content_rows = len(table.rows)
    if position >= content_rows * count:
        table.rows.append([""] * count)
        position = content_rows * count
    target_row = position // count
    target_row = target_row + 1 if target_row else 0  # skip the separator
    target = position % count
    if tidy:
        result = render(table)
    else:
        result = list(lines) if target_row < len(lines) else [*lines, empty_row(count)]
        result[target_row] = _with_cells(result[target_row], target + 1)
    spans = cell_spans(result[target_row])
    start, end = spans[target]
    if start == end:  # an empty cell: the caret after the space that follows the pipe
        line = result[target_row]
        while start > 0 and line[start - 1] in " \t":
            start -= 1
        start = end = min(start + 1, end) if start > 0 else start
    return result, target_row, start, end


def _with_cells(line: str, count: int) -> str:
    """The row with at least this many cells; missing ones are added empty at the end."""
    missing = count - len(cell_spans(line))
    if missing <= 0:
        return line
    pipes = pipe_positions(line)
    if not pipes or line[pipes[-1] + 1 :].strip():
        line = line.rstrip() + " |"  # close the last cell
    return line.rstrip() + f"{EMPTY_CELL}|" * missing


def insert(text: str, start: int, end: int, header: list[str]) -> tuple[str, int, int]:
    """Inserts a new table as a paragraph of its own below the selection (or the caret's line),
    with the first column title selected, ready to be typed over."""
    from .formatting import insert_block

    block = "\n".join(new(header))
    new_text, after, _after = insert_block(text, end, block)
    first = after - len(block) + 2
    return new_text, first, first + len(header[0])


def tidy_at(lines: list[str], row: int, column: int) -> tuple[list[str], int]:
    """Tidies the table and returns where the caret goes in the given row: at the end of the
    text of the cell it was in (at the row's start on the separator)."""
    tidied = tidy(lines)
    if row == 1:
        return tidied, 0
    spans = cell_spans(tidied[row])
    return tidied, spans[min(cell_index(lines[row], column), len(spans) - 1)][1]


def _split(line: str) -> tuple[bool, list[str], bool]:
    """A row as (leading pipe?, the cells as typed, spaces included, trailing pipe?)."""
    pipes = pipe_positions(line)
    leading = bool(pipes) and not line[: pipes[0]].strip()
    trailing = bool(pipes) and not line[pipes[-1] + 1 :].strip() and (len(pipes) > 1 or not leading)
    bounds = [-1, *pipes, len(line)]
    raw = [line[a + 1 : b] for a, b in zip(bounds, bounds[1:])]
    if leading:
        raw = raw[1:]
    if trailing:
        raw = raw[:-1]
    return leading, raw, trailing


def _join(leading: bool, raw: list[str], trailing: bool) -> str:
    return ("|" if leading else "") + "|".join(raw) + ("|" if trailing else "")


def add_row(lines: list[str], row: int, below: bool) -> tuple[list[str], int]:
    """A row of empty cells above or below the given one; above the header or below the
    separator, it becomes the first row of the body. Returns the lines and the new row."""
    place = row + 1 if below else row
    place = max(place, 2)
    return lines[:place] + [empty_row(parse(lines).columns)] + lines[place:], place


def remove_row(lines: list[str], row: int) -> list[str] | None:
    """The table without a row of its body; None for the header and the separator."""
    if row < 2:
        return None
    return lines[:row] + lines[row + 1 :]


def add_column(lines: list[str], index: int) -> list[str]:
    """An empty column at this place (0 = in front of the first); every row gets its cell, the
    separator its dashes. Short rows are filled up first, so the cells stay in their columns."""
    count = parse(lines).columns
    result = []
    for number, line in enumerate(lines):
        leading, raw, trailing = _split(_with_cells(line, count) if number != 1 else line)
        if not trailing and number != 1 and raw:
            raw[-1] = raw[-1].rstrip() + " "  # "a | b" gets its closing pipe as "a | b |"
        while len(raw) < count:
            raw.append("---" if number == 1 else EMPTY_CELL)
        if index == 0 and not leading and number != 1 and raw:
            raw[0] = " " + raw[0].lstrip()  # "a | b" gets its new first cell as "  | a | b"
        raw.insert(min(index, len(raw)), "---" if number == 1 else EMPTY_CELL)
        result.append(_join(leading, raw, True))
    return result


def remove_column(lines: list[str], index: int) -> list[str] | None:
    """The table without the column at this place; None if it is the only one."""
    if parse(lines).columns < 2:
        return None
    result = []
    for line in lines:
        leading, raw, trailing = _split(line)
        if index < len(raw):
            del raw[index]
        if len(raw) == 1 and not (leading or trailing):  # a row needs a pipe to stay in the table
            leading = trailing = True
            raw = [raw[0] if set(raw[0].strip()) <= set(":-") else f" {raw[0].strip()} "]
        result.append(_join(leading, raw, trailing))
    return result


def cell_place(line: str, index: int) -> int:
    """Where the caret goes to type in a cell of the row: the end of its text, or for an empty
    cell, after the space that follows its pipe."""
    spans = cell_spans(line)
    start, end = spans[min(index, len(spans) - 1)]
    if start == end:
        while start > 0 and line[start - 1] in " \t":
            start -= 1
        return min(start + 1, end) if start > 0 else start
    return end
