"""Export-Vorlagen: lesen, als Datei packen und importieren, ohne GTK.

Eine Vorlage ist eine einzelne Datei mit der Endung .typecase-template. Technisch ist das ein
ZIP-Archiv (wie eine .docx-Datei) mit:

- template.json   Beschreibung (Pflicht), z. B. {"format": 1, "name": "Brief", "description": "…"}
                  Name und Beschreibung dürfen auch je Sprache angegeben werden:
                  {"name": {"en": "Letter", "de": "Brief"}}
- template.html   Pandoc-HTML-Vorlage für HTML und PDF (Pflicht, enthält $body$)
- style.css       Aussehen für HTML und PDF (optional)
- reference.docx  Formatvorlagen für Word (optional; sonst Pandocs Standard)
- weitere Dateien, z. B. Schriften oder ein Logo, auf die style.css mit url(…) verweist

Für das PDF kann template.json Papier und Ränder festlegen (sonst Papier nach Sprache, 25 mm):
  "pdf": {"paper": "a4", "margins_mm": {"top": 25, "right": 50, "bottom": 25, "left": 25}}

Importierte Vorlagen liegen entpackt im Datenordner der App; die mitgelieferten im Code."""

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path

EXTENSION = ".typecase-template"
FORMAT_VERSION = 1
BUILTIN_DIR = Path(__file__).resolve().parent / "templates"

PAPER_SIZES = {"a4": "iso_a4", "a5": "iso_a5", "a3": "iso_a3", "letter": "na_letter", "legal": "na_legal"}
DEFAULT_MARGIN_MM = 25
MAX_FILES = 200
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # entpackt


class TemplateError(Exception):
    """Vorlage ist unbrauchbar; die Meldung ist für den Nutzer gedacht."""


@dataclass(frozen=True)
class Template:
    id: str  # Ordnername, z. B. "text"
    path: Path
    builtin: bool
    info: dict

    @property
    def title(self) -> str:
        return localized(self.info.get("name")) or self.id

    @property
    def description(self) -> str:
        return localized(self.info.get("description"))

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

    @property
    def pdf_paper(self) -> str | None:
        """GTK-Papiername (z. B. "iso_a4") oder None für das Papier der Systemsprache."""
        pdf = self.info.get("pdf")
        paper = pdf.get("paper") if isinstance(pdf, dict) else None
        return PAPER_SIZES.get(paper.casefold()) if isinstance(paper, str) else None

    @property
    def pdf_margins_mm(self) -> dict[str, float]:
        """Seitenränder in Millimetern; Fehlendes oder Unsinniges wird zu 25 mm."""
        pdf = self.info.get("pdf")
        given = pdf.get("margins_mm") if isinstance(pdf, dict) else None
        given = given if isinstance(given, dict) else {}
        margins = {}
        for side in ("top", "right", "bottom", "left"):
            value = given.get(side)
            ok = isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100
            margins[side] = float(value) if ok else float(DEFAULT_MARGIN_MM)
        return margins


def localized(value) -> str:
    """Text aus template.json in der Sprache der Oberfläche (sonst Englisch, sonst den ersten)."""
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict) or not value:
        return ""
    for language in _ui_languages() + ["en"]:
        for key in (language, language.split("_")[0]):
            if isinstance(value.get(key), str):
                return value[key].strip()
    first = next(iter(value.values()))
    return first.strip() if isinstance(first, str) else ""


def _ui_languages() -> list[str]:
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        wanted = os.environ.get(variable)
        if wanted and not wanted.startswith(("C", "POSIX")):
            return [part.split(".")[0] for part in wanted.split(":") if part]
    return []


# --- Lesen ---------------------------------------------------------------------


def read_folder(folder: Path, builtin: bool) -> Template:
    """Prüft einen entpackten Vorlagenordner und liest seine Beschreibung."""
    info_file = folder / "template.json"
    if not info_file.is_file():
        raise TemplateError(_("The template description (template.json) is missing."))
    try:
        info = json.loads(info_file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TemplateError(_("The template description (template.json) cannot be read.")) from None
    if not isinstance(info, dict) or not localized(info.get("name")):
        raise TemplateError(_("The template has no name."))
    if not isinstance(info.get("format", FORMAT_VERSION), int) or info.get("format", FORMAT_VERSION) > FORMAT_VERSION:
        raise TemplateError(_("This template needs a newer version of Typecase."))
    html = folder / "template.html"
    if not html.is_file():
        raise TemplateError(_("The HTML template (template.html) is missing."))
    try:
        if "$body$" not in html.read_text(encoding="utf-8"):
            raise TemplateError(_("The HTML template does not contain $body$, so the text would be missing."))
    except UnicodeDecodeError:
        raise TemplateError(_("The HTML template (template.html) cannot be read.")) from None
    return Template(folder.name, folder, builtin, info)


def available(user_dir: Path | None) -> list[Template]:
    """Mitgelieferte und importierte Vorlagen. Kaputte Ordner werden übergangen."""
    found = []
    for base, builtin in ((BUILTIN_DIR, True), (user_dir, False)):
        if base is None or not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            if folder.is_dir() and not folder.name.startswith("."):
                try:
                    found.append(read_folder(folder, builtin))
                except TemplateError:
                    pass
    builtins = [t for t in found if t.builtin]
    others = sorted((t for t in found if not t.builtin), key=lambda t: t.title.casefold())
    return builtins + others


# --- Packen --------------------------------------------------------------------


def pack(template: Template, destination: Path) -> None:
    """Speichert eine Vorlage als .typecase-template-Datei (z. B. als Ausgangspunkt für eine eigene).
    Erst in eine temporäre Datei daneben, dann umbenennen."""
    temporary = destination.with_name(f".{destination.name}.typecase-tmp")
    try:
        # strict_timestamps=False: Dateien im Flatpak sind auf 1970 datiert, ZIP kennt erst 1980.
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            for file in sorted(template.path.rglob("*")):
                if file.is_file() and not file.is_symlink():
                    archive.write(file, file.relative_to(template.path).as_posix())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


# --- Importieren -----------------------------------------------------------------


def peek(file: Path) -> Template:
    """Entpackt zur Probe in einen temporären Ordner und prüft die Vorlage, ohne etwas zu installieren.
    Der Aufrufer bekommt die Beschreibung (z. B. für eine Rückfrage beim Ersetzen)."""
    with tempfile.TemporaryDirectory(prefix="typecase-template-") as work:
        folder = Path(work) / "template"
        _extract(file, folder)
        template = read_folder(folder, builtin=False)
        return Template(template_id(file, template.info), file, False, template.info)


def install(file: Path, user_dir: Path) -> Template:
    """Importiert eine .typecase-template-Datei nach user_dir/<id>. Eine vorhandene Vorlage mit
    derselben Kennung wird ersetzt – erst, wenn die neue vollständig entpackt und geprüft ist."""
    user_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".import-", dir=user_dir))
    try:
        folder = work / "template"
        _extract(file, folder)
        template = read_folder(folder, builtin=False)
        target = user_dir / template_id(file, template.info)
        if target.exists():
            old = work / "old"
            os.replace(target, old)
        os.replace(folder, target)
        return read_folder(target, builtin=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def template_id(file: Path, info: dict) -> str:
    """Kennung (Ordnername) aus dem Dateinamen; mitgelieferte Kennungen bleiben ihnen vorbehalten."""
    stem = file.name[: -len(EXTENSION)] if file.name.endswith(EXTENSION) else file.stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-") or re.sub(
        r"[^a-z0-9]+", "-", localized(info.get("name")).casefold()
    ).strip("-") or "template"
    builtin_ids = {folder.name for folder in BUILTIN_DIR.iterdir()} if BUILTIN_DIR.is_dir() else set()
    return f"{slug}-custom" if slug in builtin_ids else slug


def _extract(file: Path, folder: Path) -> None:
    """Entpackt mit Schutz: nichts außerhalb des Zielordners, keine Verknüpfungen, Größe begrenzt."""
    try:
        archive = zipfile.ZipFile(file)
    except (zipfile.BadZipFile, OSError):
        raise TemplateError(_("This is not a Typecase template file.")) from None
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_TOTAL_BYTES:
            raise TemplateError(_("The template is too large."))
        # Liegt alles in einem gemeinsamen Ordner (beim Packen mit einem Dateimanager üblich), diesen abziehen.
        names = [m.filename for m in members if not m.is_dir()]
        prefix = ""
        if names and "template.json" not in names:
            top = {name.split("/", 1)[0] for name in names}
            if len(top) == 1 and all("/" in name for name in names):
                prefix = top.pop() + "/"
        folder.mkdir(parents=True)
        root = folder.resolve()
        for member in members:
            name = member.filename[len(prefix) :] if member.filename.startswith(prefix) else member.filename
            if not name or member.is_dir():
                continue
            is_link = (member.external_attr >> 16) & 0o170000 == 0o120000
            target = (folder / name).resolve()
            if is_link or name.startswith("/") or root not in target.parents:
                raise TemplateError(_("The template contains files outside of its folder."))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)
