"""Export eines Blatts über Pandoc, ohne GTK.

DOCX und HTML erzeugt Pandoc direkt. Für PDF erzeugt Pandoc HTML, das der Editor anschließend
mit WebKit in eine PDF-Datei druckt (HTML-Vorlage mit CSS, kein LaTeX nötig).
Wie Vorlagen aufgebaut sind, steht in export_templates.py."""

import base64
import mimetypes
import re
import shutil
from pathlib import Path

from .export_templates import Template

FORMATS = ("pdf", "docx", "html")
EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}

# Markdown wie im Editor: jede Zeile bleibt eine eigene Zeile.
INPUT_FORMAT = "markdown+hard_line_breaks"

_UNDERLINE = re.compile(r"<u>(.*?)</u>", re.DOTALL)
_FONT_TYPES = {".woff2": "font/woff2", ".woff": "font/woff", ".otf": "font/otf", ".ttf": "font/ttf"}
_CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")


def pandoc_path() -> str | None:
    return shutil.which("pandoc")


def prepare_markdown(text: str) -> str:
    """Typecase-Eigenheiten in Pandoc-Markdown übersetzen: Unterstreichen ist bei uns <u>…</u>,
    Pandoc kennt dafür [Text]{.underline} (rohes HTML ginge in DOCX verloren)."""
    return _UNDERLINE.sub(lambda m: "[" + m.group(1) + "]{.underline}", text)


def pandoc_args(
    fmt: str,
    template: Template,
    output: Path,
    fallback_title: str | None,
    header_file: Path | None = None,
    defaults: dict | None = None,
) -> list[str]:
    """Befehlszeile für Pandoc; der Text kommt über die Standardeingabe.
    fmt "pdf" erzeugt die HTML-Zwischenstufe für den PDF-Druck. header_file enthält das CSS
    als <style>-Block, damit die HTML-Datei ohne Begleitdateien auskommt. defaults sind
    Voreinstellungen (Autor, Sprache) für Felder, die der Dateikopf nicht selbst setzt."""
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
            # Fenstertitel der HTML-Seite, wenn der Dateikopf keinen Titel hat; im Text erscheint er nicht.
            args += ["--metadata", "pagetitle=" + fallback_title]
        if header_file is not None:
            args += ["--include-in-header", str(header_file)]
        if fmt == "pdf":
            args += ["--variable", "pdf"]  # die Vorlage kann Bildschirm- und Druckfassung unterscheiden
    return args


def style_header(template: Template) -> str:
    """CSS der Vorlage als <style>-Block zum Einbetten. Schriften und Bilder der Vorlage, auf die
    das CSS mit url(…) verweist, werden mit eingebettet: So ist die HTML-Datei vollständig, und
    der PDF-Druck findet sie auch, obwohl er vom Ordner des Blatts aus lädt."""
    css = template.css.read_text(encoding="utf-8") if template.css.is_file() else ""
    css = _CSS_URL.sub(lambda match: _embed(template, match), css)
    return "<style>\n" + css.replace("</style", "<\\/style") + "\n</style>\n"


def _embed(template: Template, match: re.Match) -> str:
    reference = match.group(2).strip()
    if re.match(r"^(data:|[a-z]+://|#)", reference, re.IGNORECASE):
        return match.group(0)
    file = (template.path / reference).resolve()
    if template.path.resolve() not in file.parents or not file.is_file():
        return match.group(0)  # außerhalb der Vorlage oder nicht vorhanden: unverändert lassen
    mime = mimetypes.guess_type(file.name)[0] or _FONT_TYPES.get(file.suffix.lower(), "application/octet-stream")
    return f"url('data:{mime};base64,{base64.b64encode(file.read_bytes()).decode('ascii')}')"
