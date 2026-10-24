"""Export templates: reading, packing as a file and importing, without GTK.

A template is a single file with the extension .typecase-template. Technically it is a
ZIP archive (like a .docx file) containing:

- template.json   description (required), e.g. {"format": 1, "name": "Letter", "description": "…"}
                  Name and description may also be given per language:
                  {"name": {"en": "Letter", "de": "Brief"}}
- template.html   Pandoc HTML template for HTML and PDF (required, contains $body$)
- style.css       appearance for HTML and PDF (optional)
- reference.docx  styles for Word (optional; otherwise Pandoc's default)
- further files, e.g. fonts or a logo, that style.css references with url(…)

For PDF, template.json can set paper and margins (otherwise paper by language, 25 mm):
  "pdf": {"paper": "a4", "margins_mm": {"top": 25, "right": 50, "bottom": 25, "left": 25}}

Imported templates are stored unpacked in the app's data folder; the built-in ones live in the code."""

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
MAX_TOTAL_BYTES = 50 * 1024 * 1024  # unpacked


class TemplateError(Exception):
    """The template is unusable; the message is meant for the user."""


@dataclass(frozen=True)
class Template:
    id: str  # folder name, e.g. "text"
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
        """GTK paper name (e.g. "iso_a4"), or None for the paper of the system language."""
        pdf = self.info.get("pdf")
        paper = pdf.get("paper") if isinstance(pdf, dict) else None
        return PAPER_SIZES.get(paper.casefold()) if isinstance(paper, str) else None

    @property
    def pdf_margins_mm(self) -> dict[str, float]:
        """Page margins in millimeters; missing or nonsensical values become 25 mm."""
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
    """Text from template.json in the interface language (otherwise English, otherwise the first one)."""
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


# --- Reading -------------------------------------------------------------------


def read_folder(folder: Path, builtin: bool) -> Template:
    """Checks an unpacked template folder and reads its description."""
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
    """Built-in and imported templates. Broken folders are skipped."""
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


# --- Packing -------------------------------------------------------------------


def pack(template: Template, destination: Path) -> None:
    """Saves a template as a .typecase-template file (e.g. as a starting point for your own).
    Writes to a temporary file next to it first, then renames it."""
    temporary = destination.with_name(f".{destination.name}.typecase-tmp")
    try:
        # strict_timestamps=False: files in the Flatpak are dated 1970, but ZIP only starts at 1980.
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            for file in sorted(template.path.rglob("*")):
                if file.is_file() and not file.is_symlink():
                    archive.write(file, file.relative_to(template.path).as_posix())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


# --- Importing -------------------------------------------------------------------


def peek(file: Path) -> Template:
    """Test-unpacks into a temporary folder and checks the template without installing anything.
    The caller gets the description (e.g. to ask for confirmation before replacing)."""
    with tempfile.TemporaryDirectory(prefix="typecase-template-") as work:
        folder = Path(work) / "template"
        _extract(file, folder)
        template = read_folder(folder, builtin=False)
        return Template(template_id(file, template.info), file, False, template.info)


def install(file: Path, user_dir: Path) -> Template:
    """Imports a .typecase-template file into user_dir/<id>. An existing template with the
    same ID is replaced – but only once the new one is fully unpacked and checked."""
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
    """ID (folder name) from the file name; the IDs of built-in templates are reserved for them."""
    stem = file.name[: -len(EXTENSION)] if file.name.endswith(EXTENSION) else file.stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-") or re.sub(
        r"[^a-z0-9]+", "-", localized(info.get("name")).casefold()
    ).strip("-") or "template"
    builtin_ids = {folder.name for folder in BUILTIN_DIR.iterdir()} if BUILTIN_DIR.is_dir() else set()
    return f"{slug}-custom" if slug in builtin_ids else slug


def _extract(file: Path, folder: Path) -> None:
    """Unpacks safely: nothing outside the target folder, no symlinks, limited size."""
    try:
        archive = zipfile.ZipFile(file)
    except (zipfile.BadZipFile, OSError):
        raise TemplateError(_("This is not a Typecase template file.")) from None
    with archive:
        members = archive.infolist()
        if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_TOTAL_BYTES:
            raise TemplateError(_("The template is too large."))
        # If everything is inside one common folder (usual when zipping with a file manager), strip it.
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
