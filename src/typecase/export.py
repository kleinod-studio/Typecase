"""Exporting a sheet via Pandoc, without GTK.

Pandoc produces DOCX and HTML directly. For PDF, Pandoc produces HTML, which the editor then
prints to a PDF file with WebKit (HTML template with CSS, no LaTeX required).
How templates are structured is described in export_templates.py."""

import base64
import mimetypes
import re
import shutil
from pathlib import Path

from .export_templates import Template

FORMATS = ("pdf", "docx", "html")
EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}

# Markdown as in the editor: every line stays a line of its own.
INPUT_FORMAT = "markdown+hard_line_breaks"

_UNDERLINE = re.compile(r"<u>(.*?)</u>", re.DOTALL)
_FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".otf": "font/otf", ".ttf": "font/ttf"}
_CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")


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
) -> list[str]:
    """Command line for Pandoc; the text is passed via standard input.
    fmt "pdf" produces the intermediate HTML for PDF printing. header_file contains the CSS
    as a <style> block, so the HTML file needs no accompanying files. defaults are
    default values (author, language) for fields the front matter does not set itself."""
    args = [pandoc_path() or "pandoc", "--from", INPUT_FORMAT, "--output", str(output)]
    for key, value in (defaults or {}).items():
        if value:
            args += ["--metadata", f"{key}={value}"]
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
    return args


def style_header(template: Template) -> str:
    """The template's CSS as a <style> block for embedding. Fonts and images of the template that
    the CSS references with url(…) are embedded too: that way the HTML file is self-contained, and
    PDF printing finds them as well, even though it loads from the sheet's folder."""
    css = template.css.read_text(encoding="utf-8") if template.css.is_file() else ""
    css = _CSS_URL.sub(lambda match: _embed(template, match), css)
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
