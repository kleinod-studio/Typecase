"""Export eines Blatts über Pandoc, ohne GTK.

DOCX und HTML erzeugt Pandoc direkt. Für PDF erzeugt Pandoc HTML, das der Editor anschließend
mit WebKit in eine PDF-Datei druckt (HTML-Vorlage mit CSS, kein LaTeX nötig).

Eine Vorlage ist ein Ordner mit:
- template.html  Pandoc-HTML-Vorlage (für HTML und PDF)
- style.css      Aussehen (für HTML und PDF)
- reference.docx Formatvorlagen für DOCX (optional; ohne nimmt Pandoc seine Standardvorlage)"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

FORMATS = ("pdf", "docx", "html")
EXTENSIONS = {"pdf": ".pdf", "docx": ".docx", "html": ".html"}
BUILTIN_TEMPLATES = Path(__file__).resolve().parent / "templates"

# Markdown wie im Editor: jede Zeile bleibt eine eigene Zeile.
INPUT_FORMAT = "markdown+hard_line_breaks"

_UNDERLINE = re.compile(r"<u>(.*?)</u>", re.DOTALL)


@dataclass(frozen=True)
class Template:
    name: str  # Ordnername, z. B. "text"
    path: Path

    @property
    def html(self) -> Path:
        return self.path / "template.html"

    @property
    def css(self) -> Path:
        return self.path / "style.css"

    @property
    def reference_docx(self) -> Path | None:
        docx = self.path / "reference.docx"
        return docx if docx.is_file() else None


def templates() -> list[Template]:
    """Mitgelieferte Vorlagen; eigene Vorlagen aus der Bibliothek kommen später dazu."""
    if not BUILTIN_TEMPLATES.is_dir():
        return []
    return [
        Template(folder.name, folder)
        for folder in sorted(BUILTIN_TEMPLATES.iterdir())
        if folder.is_dir() and (folder / "template.html").is_file()
    ]


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
    """CSS der Vorlage als <style>-Block zum Einbetten."""
    css = template.css.read_text(encoding="utf-8") if template.css.is_file() else ""
    return "<style>\n" + css.replace("</style", "<\\/style") + "\n</style>\n"
