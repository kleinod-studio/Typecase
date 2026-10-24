"""Toggling Markdown formatting on and off, without GTK.

All functions take text and a selection (character positions) and return the new text
along with the new selection. That is easy to test; the editor merely applies the result."""

import re

# Inline: (characters before, characters after)
BOLD = ("**", "**")
ITALIC = ("*", "*")
STRIKE = ("~~", "~~")
CODE = ("`", "`")
UNDERLINE = ("<u>", "</u>")

_WORD_CHAR = re.compile(r"[\w'’-]")
_LINE_PREFIX = re.compile(r"^(?P<indent>[ \t]*)(?P<prefix>#{1,6}[ \t]+|[-*+][ \t]+|\d{1,9}[.)][ \t]+|>[ \t]?)?")

Result = tuple[str, int, int]  # new text, selection start, selection end


def toggle_inline(text: str, start: int, end: int, markers: tuple[str, str]) -> Result:
    """Wraps the selection in markers, or removes them if they are already there.
    Without a selection the word under the cursor is used; in the middle of whitespace the markers
    are inserted and the cursor is placed between them."""
    opening, closing = markers
    if start == end:
        start, end = _word_at(text, start)
        if start == end:
            return text[:start] + opening + closing + text[end:], start + len(opening), start + len(opening)

    selected = text[start:end]
    # The selection includes the markers themselves ("**bold**" selected)
    if len(selected) >= len(opening) + len(closing) and selected.startswith(opening) and selected.endswith(closing):
        if _is_wrapped(selected, 0 + len(opening), len(selected) - len(closing), markers):
            inner = selected[len(opening) : len(selected) - len(closing)]
            return text[:start] + inner + text[end:], start, start + len(inner)
    # The markers sit directly around the selection
    if _is_wrapped(text, start, end, markers):
        new = text[: start - len(opening)] + selected + text[end + len(closing) :]
        return new, start - len(opening), end - len(opening)
    return text[:start] + opening + selected + closing + text[end:], start + len(opening), end + len(opening)


def _is_wrapped(text: str, start: int, end: int, markers: tuple[str, str]) -> bool:
    """Are the markers immediately before and after the range? For * and ** the stars are counted,
    so that italic is not mistaken for bold (***both*** is both)."""
    opening, closing = markers
    if markers in (BOLD, ITALIC):
        before = len(text[:start]) - len(text[:start].rstrip("*"))
        after = len(text[end:]) - len(text[end:].lstrip("*"))
        stars = min(before, after)
        return stars >= 2 if markers == BOLD else stars in (1, 3)
    return text[max(0, start - len(opening)) : start] == opening and text[end : end + len(closing)] == closing


def _word_at(text: str, position: int) -> tuple[int, int]:
    start = position
    while start > 0 and _WORD_CHAR.match(text[start - 1]):
        start -= 1
    end = position
    while end < len(text) and _WORD_CHAR.match(text[end]):
        end += 1
    return start, end


# --- Paragraphs ------------------------------------------------------------


def toggle_lines(lines: list[str], first: int, last: int, kind: str) -> list[str]:
    """Paragraph format for lines first..last: "h1"–"h6", "paragraph" (plain text), "bullet",
    "numbered" or "quote". If all lines already have that format, it is removed."""
    out = list(lines)
    targets = [i for i in range(first, last + 1) if lines[i].strip() or first == last]
    wanted = _prefix_for(kind, 1)
    already = kind != "paragraph" and all(_current_kind(lines[i]) == kind for i in targets)
    number = 1
    for i in targets:
        match = _LINE_PREFIX.match(lines[i])
        indent, content = match["indent"], lines[i][match.end() :]
        if already or kind == "paragraph":
            out[i] = indent + content
        else:
            out[i] = indent + (_prefix_for(kind, number) if kind == "numbered" else wanted) + content
            number += 1
    return out


def _prefix_for(kind: str, number: int) -> str:
    if kind.startswith("h") and kind[1:].isdigit():
        return "#" * int(kind[1:]) + " "
    return {"bullet": "- ", "numbered": f"{number}. ", "quote": "> "}.get(kind, "")


def _current_kind(line: str) -> str:
    prefix = (_LINE_PREFIX.match(line)["prefix"] or "").strip()
    if prefix.startswith("#"):
        return f"h{len(prefix)}"
    if prefix in ("-", "*", "+"):
        return "bullet"
    if prefix[:1].isdigit():
        return "numbered"
    if prefix.startswith(">"):
        return "quote"
    return "paragraph"


# --- Inserting ----------------------------------------------------------------


def insert_link(text: str, start: int, end: int, placeholder_text: str, placeholder_url: str) -> Result:
    """Turns the selection into link text and then selects the URL so it can be typed over.
    If the selection is itself a URL, it becomes the URL and the link text is selected."""
    selected = text[start:end]
    if re.match(r"^(https?://|www\.)\S+$", selected):
        link = f"[{placeholder_text}]({selected})"
        return text[:start] + link + text[end:], start + 1, start + 1 + len(placeholder_text)
    label = selected or placeholder_text
    link = f"[{label}]({placeholder_url})"
    url_start = start + len(label) + 3
    if not selected:
        return text[:start] + link + text[end:], start + 1, start + 1 + len(label)
    return text[:start] + link + text[end:], url_start, url_start + len(placeholder_url)


def insert_code_block(text: str, start: int, end: int) -> Result:
    """Wraps the selected lines in ```; without a selection, an empty block with the cursor inside."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    if start == end and not text[line_start:line_end].strip():
        block = "```\n\n```"
        return text[:line_start] + block + text[line_end:], line_start + 4, line_start + 4
    inner = text[line_start:line_end]
    block = f"```\n{inner}\n```"
    return text[:line_start] + block + text[line_end:], line_start + 4, line_start + 4 + len(inner)
