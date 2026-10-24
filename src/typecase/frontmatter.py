"""Reading and changing the front matter (YAML) of a Markdown file, without GTK.

Principle: the front matter belongs to the user. Typecase only reads simple fields
(text, list) and, when writing, changes only the lines of the fields that have
changed. Everything else – unknown fields, comments, formatting – is preserved character
for character."""

import re

_OPEN = re.compile(r"\A---[ \t]*\r?\n")
_CLOSE = re.compile(r"^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.MULTILINE)
_KEY = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(.*?))?[ \t]*$")
_LIST_ITEM = re.compile(r"^[ \t]+-[ \t]+(.*?)[ \t]*$")
_NEEDS_QUOTES = re.compile(r"""^[\s\-?:,\[\]{}#&*!|>'"%@`]|[:#]\s|\s$|^$|^(?:true|false|null|yes|no|~)$""", re.IGNORECASE)


def split(text: str) -> tuple[str | None, str]:
    """Splits off the front matter. Returns (header including --- lines, rest) or (None, text)."""
    opening = _OPEN.match(text)
    if not opening:
        return None, text
    closing = _CLOSE.search(text, opening.end())
    if not closing:
        return None, text  # not closed: treat as normal text
    return text[: closing.end()], text[closing.end() :]


def join(header: str | None, body: str) -> str:
    return (header or "") + body


def parse(header: str | None) -> dict:
    """Simple fields of the header: text as str, lists as list[str]. Anything unknown is skipped."""
    if not header:
        return {}
    result = {}
    lines = _inner_lines(header)
    i = 0
    while i < len(lines):
        match = _KEY.match(lines[i].rstrip("\r"))
        i += 1
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if value is None or value == "":
            items = []
            while i < len(lines) and (item := _LIST_ITEM.match(lines[i].rstrip("\r"))):
                items.append(_unquote(item.group(1)))
                i += 1
            result[key] = items if items else ""
        elif value.startswith("[") and value.endswith("]"):
            result[key] = [_unquote(part) for part in _split_inline_list(value[1:-1])]
        else:
            result[key] = _unquote(_strip_comment(value))
    return result


def update(header: str | None, changes: dict) -> str | None:
    """Sets or removes fields (a value of None, "" or [] removes). Other lines stay unchanged.
    Returns None if no field is left afterwards and the header consisted only of Typecase fields."""
    newline = "\r\n" if header and "\r\n" in header else "\n"
    if header:
        opening = _OPEN.match(header).group(0)
        closing = _CLOSE.search(header, len(opening)).group(0)
        lines = _inner_lines(header)
    else:
        opening, lines, closing = "---" + newline, [], "---" + newline

    for key, value in changes.items():
        start, end = _field_span(lines, key)
        new_lines = [] if _empty(value) else _render(key, value)
        if start is None:
            lines.extend(new_lines)
        else:
            lines[start:end] = new_lines

    if not any(line.strip() for line in lines):
        return None
    return opening + "".join(line.rstrip("\r") + newline for line in lines) + closing


# --- internal ---------------------------------------------------------------


def _inner_lines(header: str) -> list[str]:
    opening = _OPEN.match(header)
    closing = _CLOSE.search(header, opening.end())
    inner = header[opening.end() : closing.start()]
    if not inner:
        return []
    return inner[:-1].split("\n") if inner.endswith("\n") else inner.split("\n")


def _field_span(lines: list[str], key: str) -> tuple[int | None, int | None]:
    """Line range of a field including its indented continuation lines (list items)."""
    for i, line in enumerate(lines):
        match = _KEY.match(line.rstrip("\r"))
        if match and match.group(1) == key:
            end = i + 1
            while end < len(lines) and lines[end][:1] in (" ", "\t") and lines[end].strip():
                end += 1
            return i, end
    return None, None


def _render(key: str, value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [f"{key}: [" + ", ".join(_quote(str(item)) for item in value) + "]"]
    return [f"{key}: {_quote(str(value))}"]


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, tuple)) and not value)


def _quote(value: str) -> str:
    if not _NEEDS_QUOTES.search(value) and "," not in value and "\n" not in value:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _strip_comment(value: str) -> str:
    if value[:1] in ('"', "'"):
        return value
    return re.sub(r"\s+#.*$", "", value)


def _split_inline_list(text: str) -> list[str]:
    parts, current, quote = [], "", None
    for char in text:
        if quote:
            current += char
            if char == quote:
                quote = None
        elif char in ('"', "'"):
            quote = char
            current += char
        elif char == ",":
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]
