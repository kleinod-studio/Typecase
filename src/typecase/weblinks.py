"""Links kept with a sheet, without GTK.

Besides files, a sheet can keep links to web pages, for research or sources. They are stored in
the front matter field "links", one Markdown link per item, so any editor can read them:

    links:
      - "[Tide tables](https://example.org/tides)"
      - https://en.wikipedia.org/wiki/Lighthouse

The title is optional. Only web addresses (http and https) count as links; other items in the
field are kept as they are, since the front matter belongs to the user. The export leaves links
out, like the notes."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

FIELD = "links"
_MARKDOWN = re.compile(r"\A\[(?P<title>(?:\\.|[^\]\\])*)\]\((?P<address>[^\s()]*)\)\Z")
_SCHEME = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True)
class WebLink:
    address: str
    title: str = ""

    def label(self) -> str:
        """The title, or else the address's host (without "www.")."""
        if self.title:
            return self.title
        host = urlsplit(self.address).hostname or self.address
        return host.removeprefix("www.")


def normalized(address: str) -> str | None:
    """A web address as it is stored, or None if it is none: "www." gets "https://" in front,
    spaces and parentheses are encoded (they would end the Markdown link)."""
    address = address.strip()
    if not address:
        return None
    if not _SCHEME.match(address):
        if not re.match(r"\A[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}(?:[/:?#]|\Z)", address):
            return None
        address = "https://" + address  # "www.example.org", "example.org/page"
    address = address.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
    try:
        parts = urlsplit(address)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname or re.search(r"\s", address):
        return None
    return address


def parse(item: str) -> WebLink | None:
    """The link an item of the field stands for, or None if it is no web link."""
    item = item.strip()
    match = _MARKDOWN.match(item)
    if match:
        address = normalized(match.group("address"))
        title = re.sub(r"\\(.)", r"\1", match.group("title")).strip()
        return WebLink(address, title) if address else None
    address = normalized(item) if _SCHEME.match(item) else None
    return WebLink(address) if address else None


def to_item(link: WebLink) -> str:
    """The item for the field: a Markdown link, or the bare address without a title."""
    if not link.title:
        return link.address
    title = re.sub(r"([\[\]\\])", r"\\\1", link.title)
    return f"[{title}]({link.address})"


def items(value) -> list[str]:
    """The field's items from the parsed front matter (a single text counts as one)."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [value] if isinstance(value, str) and value.strip() else []


def links(field: list[str]) -> list[tuple[int, WebLink]]:
    """The web links among the field's items, with their place in it."""
    return [(index, link) for index, item in enumerate(field) if (link := parse(item)) is not None]


def make(address: str, title: str = "") -> WebLink | None:
    """A link from what was typed in, or None if the address is no web address."""
    address = normalized(address)
    return WebLink(address, " ".join(title.split())) if address else None


def add(field: list[str], link: WebLink) -> list[str]:
    """The field with the link at the end. A link to the same address is replaced instead (it
    takes the new title, if there is one), so the list has no doubles."""
    for index, existing in links(field):
        if existing.address == link.address:
            return replace(field, index, WebLink(link.address, link.title or existing.title))
    return field + [to_item(link)]


def replace(field: list[str], index: int, link: WebLink) -> list[str]:
    return field[:index] + [to_item(link)] + field[index + 1 :]


def remove(field: list[str], index: int) -> list[str]:
    return field[:index] + field[index + 1 :]
