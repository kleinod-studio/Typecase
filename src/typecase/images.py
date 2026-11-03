"""Images in the Markdown text, without GTK.

An image is plain Pandoc Markdown, so a sheet stays readable and exportable without Typecase:

    ![Caption](<.attachments/Chapter 1/photo.png>){.center width=50% alt="What it shows"}

The text in square brackets is the caption shown in the export, "alt" the description for people
who cannot see the image. Size and alignment are optional. Attributes Typecase does not know are
kept as they are."""

import base64
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

ALIGNMENTS = ("left", "center", "right")
SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

IMAGE = re.compile(
    r"!\[(?P<caption>(?:[^\[\]\n\\]|\\.|\[[^\[\]\n]*\])*)\]"
    r"\((?P<target><[^<>\n]*>|[^()\s]*)(?P<title>[ \t]+\"(?:[^\"\\\n]|\\.)*\")?\)"
    r"(?P<attributes>\{[^{}\n]*\})?"
)
_ATTRIBUTE = re.compile(r"\.(?P<class>[\w-]+)|(?P<key>[\w-]+)=(?P<value>\"(?:[^\"\\]|\\.)*\"|[^\s}]+)|(?P<other>\S+)")
_FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")
_INLINE_CODE = re.compile(r"(`+).+?\1")
_REMOTE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_CAPTION_SPECIAL = re.compile(r"([\\\[\]])")
_ESCAPED = re.compile(r"\\(.)")


@dataclass
class Image:
    address: str  # as a file name: no brackets, no percent encoding
    caption: str = ""
    alt: str = ""
    width: str = ""  # for example "50%"
    align: str = ""  # one of ALIGNMENTS, or empty for what the template does
    title: str = ""  # the rest as written, kept unchanged
    others: list[str] = field(default_factory=list)
    start: int = 0  # position in the line
    end: int = 0


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in SUFFIXES


def _parse(match: re.Match) -> Image:
    target = match["target"]
    if target.startswith("<"):
        target = target[1:-1]
    image = Image(
        address=unquote(target),
        caption=_ESCAPED.sub(r"\1", match["caption"]),
        title=match["title"] or "",
        start=match.start(),
        end=match.end(),
    )
    for item in _ATTRIBUTE.finditer((match["attributes"] or "{}")[1:-1]):
        if item["class"] in ALIGNMENTS and not image.align:
            image.align = item["class"]
        elif item["key"] == "width" and not image.width:
            image.width = item["value"].strip('"')
        elif item["key"] == "alt" and not image.alt:
            value = item["value"]
            image.alt = _ESCAPED.sub(r"\1", value[1:-1]) if value.startswith('"') else value
        else:
            image.others.append(item.group(0))
    return image


def _code_ranges(line: str) -> list[tuple[int, int]]:
    return [match.span() for match in _INLINE_CODE.finditer(line)]


def in_line(line: str) -> list[Image]:
    """The images of a line that is not inside a code block; those in `code` do not count."""
    code = _code_ranges(line)
    return [
        _parse(match) for match in IMAGE.finditer(line)
        if not any(start <= match.start() < end for start, end in code)
    ]


def in_text(text: str) -> list[tuple[int, Image]]:
    """All images of a text as (line number, image), without those in code."""
    found = []
    if "![" not in text:
        return found
    in_code_block = False
    for number, line in enumerate(text.split("\n")):
        if _FENCE.match(line):
            in_code_block = not in_code_block
        elif not in_code_block and "![" in line:
            found += [(number, image) for image in in_line(line)]
    return found


def to_markdown(image: Image) -> str:
    caption = " ".join(_CAPTION_SPECIAL.sub(r"\\\1", image.caption).split())
    parts = [f".{image.align}"] if image.align else []
    if image.width:
        parts.append(f"width={image.width}")
    if image.alt.strip():
        alt = " ".join(image.alt.split()).replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'alt="{alt}"')
    parts += image.others
    attributes = "{" + " ".join(parts) + "}" if parts else ""
    return f"![{caption}]({_target(image.address)}{image.title}){attributes}"


def _target(address: str) -> str:
    """An address as written in the text; angle brackets allow spaces and parentheses."""
    written = address.replace("%", "%25").replace("<", "%3C").replace(">", "%3E")
    return f"<{written}>" if re.search(r"[\s()]", written) else written


def _map_addresses(text: str, change) -> str:
    """Replaces the address of every image, outside of code; change returns the new address or None."""
    if "![" not in text:
        return text
    lines = text.split("\n")
    in_code_block = False
    for number, line in enumerate(lines):
        if _FENCE.match(line):
            in_code_block = not in_code_block
        elif not in_code_block and "![" in line:
            code = _code_ranges(line)

            def replaced(match: re.Match) -> str:
                if any(start <= match.start() < end for start, end in code):
                    return match.group(0)
                target = match["target"][1:-1] if match["target"].startswith("<") else match["target"]
                address = change(unquote(target))
                if address is None:
                    return match.group(0)
                begin, end = match.span("target")
                offset = match.start()
                return match.group(0)[: begin - offset] + _target(address) + match.group(0)[end - offset :]

            lines[number] = IMAGE.sub(replaced, line)
    return "\n".join(lines)


def is_remote(address: str) -> bool:
    return bool(_REMOTE.match(address))


def resolve(address: str, folder: Path) -> Path | None:
    """The file of an image in a sheet in folder; None if it is not a local file."""
    return None if not address or is_remote(address) else folder / address


def retarget(text: str, old_folder: str, new_folder: str) -> str:
    """After a sheet was renamed: images in its old attachments folder point to the new one."""
    prefix = old_folder + "/"
    return _map_addresses(
        text, lambda address: new_folder + "/" + address[len(prefix) :] if address.startswith(prefix) else None
    )


def with_absolute_paths(text: str, folder: Path) -> str:
    """For texts combined from several folders: relative paths would lose their meaning."""
    return _map_addresses(
        text,
        lambda address: str(folder / address) if address and not is_remote(address) and not address.startswith("/") else None,
    )


def embedded(text: str, folder: Path) -> str:
    """Local images as part of the text (data: addresses), for a web page without extra files.
    A file that cannot be read stays as it is, so the export still works."""

    def as_data(address: str) -> str | None:
        file = resolve(address, folder)
        if file is None:
            return None
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        try:
            return f"data:{mime};base64,{base64.b64encode(file.read_bytes()).decode('ascii')}"
        except OSError:
            return None

    return _map_addresses(text, as_data)


def only_images(line: str) -> bool:
    """Whether a line holds nothing but images."""
    return "![" in line and not IMAGE.sub("", line).strip()


def uses_file(text: str, name: str) -> bool:
    return any(Path(image.address).name == name for _line, image in in_text(text))


def plain_text(text: str) -> str:
    """The text with images reduced to their captions: addresses and attributes are no words."""
    return IMAGE.sub(lambda match: match["caption"], text)


def preview_size(image: Image, natural: tuple[int, int], available: int, max_height: int) -> tuple[int, int, int]:
    """Where an image goes in the editor: (x offset, width, height), for its natural size in pixels
    and the width of the text. The size follows the export as far as a text column can."""
    width, height = natural
    wanted = width
    if image.width.endswith("%"):
        try:
            wanted = round(available * float(image.width[:-1]) / 100)
        except ValueError:
            pass
    elif image.width.endswith("px"):
        try:
            wanted = round(float(image.width[:-2]))
        except ValueError:
            pass
    wanted = max(1, min(wanted, available))
    shown = max(1, round(height * wanted / max(width, 1)))
    if shown > max_height:
        wanted = max(1, round(wanted * max_height / shown))
        shown = max_height
    offset = {"center": (available - wanted) // 2, "right": available - wanted}.get(image.align, 0)
    return max(0, offset), wanted, shown

