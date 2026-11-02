"""Exporting a sheet via Pandoc, without GTK.

Pandoc produces DOCX and HTML directly. For PDF, Pandoc produces HTML, which WeasyPrint then
lays out as pages (HTML template with CSS, no LaTeX required; see pdf_render.py).
How templates are structured is described in export_templates.py."""

import base64
import datetime
import locale
import mimetypes
import os
import re
import shutil
import zipfile
from pathlib import Path

from . import frontmatter
from .export_templates import Template
from .fileio import read_text

FORMATS = ("pdf", "docx", "html")
EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}

# Markdown as in the editor: every line stays a line of its own.
INPUT_FORMAT = "markdown+hard_line_breaks"

_UNDERLINE = re.compile(r"<u>(.*?)</u>", re.DOTALL)
_FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".otf": "font/otf", ".ttf": "font/ttf"}
_CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")
FOOTNOTE_FILTER = Path(__file__).resolve().parent / "filters" / "page-footnotes.lua"
STRUCTURE_FILTER = Path(__file__).resolve().parent / "filters" / "structure.lua"
TOC_DEPTH = 2  # parts and chapters, or chapters and sections

# Defaults for the cover page, table of contents and parts, before the template's CSS so a
# template can restyle them. They apply to HTML and PDF.
BASE_CSS = """\
.cover { text-align: center; margin: 4em 0; }
.cover .title { font-size: 2em; font-weight: bold; line-height: 1.2; }
.cover .subtitle { font-size: 1.25em; margin-top: 0.4em; }
.cover .author { margin-top: 2em; }
.cover .date { margin-top: 0.5em; }
.toc { margin: 2em 0; }
.toc .toc-title { font-size: 1.3em; font-weight: bold; margin-bottom: 0.8em; }
.toc ul { list-style: none; padding-left: 0; margin: 0; }
.toc ul ul { padding-left: 1.5em; }
.toc li { margin: 0.25em 0; }
.toc a { color: inherit; text-decoration: none; }
"""

# PDF pages: footnotes at the bottom of their page, called by a small raised number; the cover,
# the contents and the title page of a part each on pages of their own, without a page number;
# page numbers in the table of contents.
PDF_BASE_CSS = """\
.cover { page: cover; break-after: page; margin: 0; padding-top: 30vh; }
@page cover { @top-center { content: none; } @bottom-center { content: none; } @bottom-right { content: none; } }
.toc { break-after: page; margin-top: 0; }
.toc a::after { content: leader(". ") target-counter(attr(href url), page); }
.part.new-page { break-before: page; }
.part.title-page { page: part; break-before: page; break-after: page; padding-top: 30vh; text-align: center; }
@page part { @top-center { content: none; } @bottom-center { content: none; } @bottom-right { content: none; } }
.footnote { float: footnote; font-size: 0.85em; }
::footnote-call { content: counter(footnote); vertical-align: super; font-size: 0.65em; line-height: 0; }
::footnote-marker { content: counter(footnote) "\\00a0\\00a0"; }
@page { @footnote { margin-top: 1em; padding-top: 0.5em; border-top: 0.5pt solid #bbbbbb; } }
"""


def export_date(today: datetime.date | None = None, time_locale: str | None = None, language: str | None = None) -> str:
    """Today's date for $date$ in templates, written the way the user's language writes dates.
    Without the system's locale data (a Flatpak whose locale extension lacks the language runs in
    C.UTF-8), %x would give "10/24/26"; then fall back to a format chosen by the UI language."""
    today = today or datetime.date.today()
    if time_locale is None:
        time_locale = locale.setlocale(locale.LC_TIME)
    if not time_locale.startswith(("C", "POSIX")):
        return today.strftime("%x")
    if language is None:
        language = os.environ.get("LANGUAGE") or os.environ.get("LANG") or ""
    language = language.split(":")[0].split(".")[0]
    if language.startswith("de"):
        return today.strftime("%d.%m.%Y")
    if language in ("en_US", "en"):
        return today.strftime("%m/%d/%Y")
    if language.startswith("en"):
        return today.strftime("%d/%m/%Y")
    return today.isoformat()


# Breaks for Word, as raw OpenXML that only the DOCX writer keeps. In HTML and PDF, CSS classes
# on the part headings do the same (see BASE_CSS), so no empty element can cause a blank page.
DOCX_PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'

PARTS = ("continuous", "new-page", "title-page")  # how the parts (subgroups) of a group begin
_FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")
_ATX = re.compile(r"^(#{1,6})(?=[ \t]|$)")
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>#|~^])")


def shift_headings(text: str, levels: int) -> str:
    """Moves every heading down by levels (# becomes ##), up to level 6; code blocks stay as they are."""
    if levels <= 0:
        return text
    lines = text.split("\n")
    in_code = False
    for index, line in enumerate(lines):
        if _FENCE.match(line):
            in_code = not in_code
        elif not in_code:
            heading = _ATX.match(line)
            if heading:
                level = min(len(heading.group(1)) + levels, 6)
                lines[index] = "#" * level + line[heading.end():]
    return "\n".join(lines)


def combine_sheets(paths: list[Path], group: Path | None = None, parts: str = "continuous") -> str:
    """Joins sheets into one Markdown text for exporting a group: each sheet's text without its
    front matter, in the given order, separated by a blank line. Unreadable files are skipped.

    With subgroups, each one becomes a part: its name is a heading of the level of its depth
    (class "part"), and the headings of its sheets move down below it. Sheets directly in the
    group keep their levels. parts: "new-page" starts each part on a new page, "title-page"
    gives its name a page of its own."""
    nested = group is not None and has_subgroups(paths)
    blocks = []
    named: set[tuple[str, ...]] = set()
    for path in paths:
        try:
            _header, body = frontmatter.split(read_text(path))
        except (OSError, UnicodeDecodeError):
            continue
        body = body.strip("\n")
        depth = len(path.parent.relative_to(group).parts) if nested else 0
        if nested:
            folders = path.parent.relative_to(group).parts
            for level in range(1, len(folders) + 1):
                if folders[:level] not in named:
                    named.add(folders[:level])
                    blocks += _part_heading(folders[level - 1], level, parts, blocks)
        if body.strip():
            blocks.append(shift_headings(body, depth))
    return "\n\n".join(blocks) + "\n"


def _part_heading(name: str, level: int, parts: str, blocks: list[str]) -> list[str]:
    """The heading that opens a part, with Word page breaks around it as the mode asks; none at
    the very start and none twice in a row (a part that directly follows another one's title page)."""
    classes = {"continuous": ".part", "new-page": ".part .new-page", "title-page": ".part .title-page"}[parts]
    heading = f"{'#' * level} {_MARKDOWN_SPECIAL.sub(r'\\\1', name)} {{{classes}}}"
    before = [] if parts == "continuous" or not blocks or blocks[-1] == DOCX_PAGE_BREAK else [DOCX_PAGE_BREAK]
    after = [DOCX_PAGE_BREAK] if parts == "title-page" else []
    return before + [heading] + after


def has_subgroups(paths: list[Path]) -> bool:
    """Whether the sheets of a group come from more than one folder."""
    return len({path.parent for path in paths}) > 1


def hide_first_page_footer(docx: Path) -> None:
    """Keeps the cover of a Word file free of page numbers: "different first page" in the last
    section's settings. Word's schema wants titlePg before the few elements listed here."""
    temporary = docx.with_suffix(".tmp")
    with zipfile.ZipFile(docx) as source, zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                data = _with_title_page(data.decode("utf-8")).encode("utf-8")
            target.writestr(item, data)
    os.replace(temporary, docx)


def _with_title_page(xml: str) -> str:
    start = xml.rfind("<w:sectPr")
    end = xml.find("</w:sectPr>", start)
    if start < 0 or end < 0 or "<w:titlePg" in xml[start:end]:
        return xml  # no section settings, so no footer either
    later = [xml.find(tag, start, end) for tag in ("<w:textDirection", "<w:bidi", "<w:rtlGutter", "<w:docGrid")]
    position = min((found for found in later if found >= 0), default=end)
    return xml[:position] + "<w:titlePg/>" + xml[position:]


def with_title(text: str, title: str | None) -> str:
    """Puts a title into the front matter of a (front-matter-less) text, for the template's title block."""
    title = (title or "").strip()
    return frontmatter.join(frontmatter.update(None, {"title": title}), text) if title else text


def pandoc_path() -> str | None:
    return shutil.which("pandoc")


def prepare_markdown(text: str) -> str:
    """Translate Typecase specifics into Pandoc Markdown: we write underline as <u>…</u>,
    Pandoc uses [text]{.underline} for that (raw HTML would get lost in DOCX)."""
    return _UNDERLINE.sub(lambda m: "[" + m.group(1) + "]{.underline}", text)


def pandoc_args(
    fmt: str,
    template: Template,
    output: Path,
    fallback_title: str | None,
    header_file: Path | None = None,
    defaults: dict | None = None,
    toc_title: str | None = None,
    cover: bool = False,
) -> list[str]:
    """Command line for Pandoc; the text is passed via standard input.
    fmt "pdf" produces the intermediate HTML for PDF printing. header_file contains the CSS
    as a <style> block, so the HTML file needs no accompanying files. defaults are
    default values (author, language) for fields the front matter does not set itself.
    toc_title: put a table of contents with this heading in front of the text; cover: a cover page."""
    args = [pandoc_path() or "pandoc", "--from", INPUT_FORMAT, "--output", str(output)]
    for key, value in (defaults or {}).items():
        if value:
            args += ["--metadata", f"{key}={value}"]
    if toc_title or cover:
        args += ["--lua-filter", str(STRUCTURE_FILTER)]
        if toc_title:
            args += ["--metadata", f"typecase-toc={TOC_DEPTH}", "--metadata", f"typecase-toc-title={toc_title}"]
        if cover:
            args += ["--metadata", "typecase-cover=true"]
    if fmt == "docx":
        args += ["--to", "docx"]
        if template.reference_docx:
            args += ["--reference-doc", str(template.reference_docx)]
    else:
        args += ["--to", "html5", "--standalone", "--template", str(template.html)]
        if fallback_title:
            # Window title of the HTML page if the front matter has no title; it does not appear in the text.
            args += ["--metadata", "pagetitle=" + fallback_title]
        if header_file is not None:
            args += ["--include-in-header", str(header_file)]
        if fmt == "pdf":
            args += ["--variable", "pdf"]  # lets the template tell the screen and print versions apart
            # Footnotes stay in place for the page layout; no line wrapping, since inside a
            # footnote WeasyPrint would keep Pandoc's source line breaks.
            args += ["--lua-filter", str(FOOTNOTE_FILTER), "--wrap", "none"]
    return args


def style_header(template: Template, pdf: bool = False) -> str:
    """The template's CSS as a <style> block for embedding. Fonts and images of the template that
    the CSS references with url(…) are embedded too: that way the HTML file is self-contained, and
    PDF printing finds them as well, even though it loads from the sheet's folder."""
    css = template.css.read_text(encoding="utf-8") if template.css.is_file() else ""
    css = _CSS_URL.sub(lambda match: _embed(template, match), css)
    css = BASE_CSS + (PDF_BASE_CSS if pdf else "") + "\n" + css
    return "<style>\n" + css.replace("</style", "<\\/style") + "\n</style>\n"


def _embed(template: Template, match: re.Match) -> str:
    reference = match.group(2).strip()
    if re.match(r"^(data:|[a-z]+://|#)", reference, re.IGNORECASE):
        return match.group(0)
    file = (template.path / reference).resolve()
    if template.path.resolve() not in file.parents or not file.is_file():
        return match.group(0)  # outside the template or missing: leave unchanged
    mime = mimetypes.guess_type(file.name)[0] or _FONT_TYPES.get(file.suffix.lower(), "application/octet-stream")
    return f"url('data:{mime};base64,{base64.b64encode(file.read_bytes()).decode('ascii')}')"
