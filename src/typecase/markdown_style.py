"""Erkennt Markdown-Auszeichnung zeilenweise, ohne GTK.

Liefert für eine Zeile Bereiche (start, ende, tag), die der Editor mit Text-Tags gestaltet.
Syntaxzeichen bekommen das Tag "syntax" und werden gedimmt; der Text dazwischen wird
fett, kursiv, als Überschrift usw. gesetzt. Mehrzeilig ist nur der Codeblock (```)."""

import re

Span = tuple[int, int, str]

FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)[ \t]*([\w+#.-]*)")
_HEADING = re.compile(r"^(#{1,6})([ \t]+|$)")
_RULE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE = re.compile(r"^[ \t]*(?:>[ \t]?)+")
_LIST = re.compile(r"^([ \t]*)([-*+]|\d{1,9}[.)])([ \t]+)(\[[ xX]\][ \t]+)?")

_CODE = re.compile(r"(`+)(.+?)\1")
_IMAGE_OR_LINK = re.compile(r"(!?\[)([^\]\n]+)(\]\([^)\s]*(?:[ \t]+\"[^\"]*\")?\))")
_STRONG_EMPHASIS = re.compile(r"(\*\*\*|___)(?=\S)(.+?)(?<=\S)\1")
_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_EMPHASIS = re.compile(r"(?<![\w*])(\*|_)(?=[^\s*_])(.+?)(?<=[^\s*_])\1(?![\w*])")
_STRIKE = re.compile(r"(~~)(?=\S)(.+?)(?<=\S)~~")
_UNDERLINE = re.compile(r"(<u>)(.+?)(</u>)", re.IGNORECASE)  # Markdown kennt kein Unterstreichen; HTML-Behelf

_MASK = "\x00"  # verdeckt schon vergebene Zeichen vor den folgenden Mustern


def fence_language(line: str) -> str:
    """Sprache hinter dem öffnenden Zaun ("```python" -> "python"), sonst ""."""
    match = FENCE.match(line)
    return match.group(2).lower() if match else ""


def line_spans(line: str, in_code_block: bool) -> list[Span]:
    """Gestaltung einer Zeile. in_code_block: Zeile liegt zwischen zwei ```-Zäunen."""
    if FENCE.match(line):
        return [(0, len(line), "syntax")] if line else []
    if in_code_block:
        return [(0, len(line), "codeblock")] if line else []
    if _RULE.match(line):
        return [(0, len(line), "syntax")]

    heading = _HEADING.match(line)
    if heading:
        level = len(heading.group(1))
        spans = [(0, heading.end(), "syntax")]
        if heading.end() < len(line):
            spans.append((heading.end(), len(line), f"h{level}"))
        return spans + _inline(line, heading.end())

    spans: list[Span] = []
    start = 0
    quote = _QUOTE.match(line)
    if quote:
        spans.append((0, quote.end(), "syntax"))
        if quote.end() < len(line):
            spans.append((quote.end(), len(line), "quote"))
        start = quote.end()

    item = _LIST.match(line, start) if start == 0 else _LIST.match(line[start:])
    if item:
        offset = start
        marker_end = offset + item.end(3)
        spans.append((offset + item.start(2), offset + item.end(2), "list-marker"))
        if item.group(4):
            spans.append((marker_end, offset + item.end(4), "syntax"))
        start = offset + item.end()

    return spans + _inline(line, start)


def _inline(line: str, start: int) -> list[Span]:
    spans: list[Span] = []
    text = list(line)
    for i in range(start):
        text[i] = _MASK

    def masked() -> str:
        return "".join(text)

    def hide(a: int, b: int):
        for i in range(a, b):
            text[i] = _MASK

    for match in _CODE.finditer(masked()):
        ticks = len(match.group(1))
        spans += [
            (match.start(), match.start() + ticks, "syntax"),
            (match.start() + ticks, match.end() - ticks, "code"),
            (match.end() - ticks, match.end(), "syntax"),
        ]
        hide(match.start(), match.end())

    for match in _IMAGE_OR_LINK.finditer(masked()):
        spans += [
            (match.start(1), match.end(1), "syntax"),
            (match.start(2), match.end(2), "link"),
            (match.start(3), match.end(3), "syntax"),
        ]
        hide(match.start(1), match.end(1))
        hide(match.start(3), match.end(3))

    for match in _UNDERLINE.finditer(masked()):
        spans += [
            (match.start(1), match.end(1), "syntax"),
            (match.start(2), match.end(2), "underline"),
            (match.start(3), match.end(3), "syntax"),
        ]
        hide(match.start(1), match.end(1))
        hide(match.start(3), match.end(3))

    for pattern, tags in [
        (_STRONG_EMPHASIS, ("bold", "italic")),
        (_STRONG, ("bold",)),
        (_EMPHASIS, ("italic",)),
        (_STRIKE, ("strike",)),
    ]:
        for match in pattern.finditer(masked()):
            width = len(match.group(1))
            inner = (match.start() + width, match.end() - width)
            spans.append((match.start(), inner[0], "syntax"))
            spans.append((inner[1], match.end(), "syntax"))
            spans += [(inner[0], inner[1], tag) for tag in tags]
            hide(match.start(), inner[0])
            hide(inner[1], match.end())

    return spans
