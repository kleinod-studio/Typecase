"""Builds export templates from a few settings, without GTK and without any AI.

The assistant in the preferences fills in the settings; this writes the template folder:
style.css and template.html for HTML and PDF, reference.docx for Word and template.json. The
settings are stored in template.json as well, so such a template can be opened and changed later.
Files are written to a hidden folder first and only then take the place of the template."""

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from gettext import gettext as _
from pathlib import Path

from . import docx_style
from .export_templates import BUILTIN_DIR, Template, read_folder

ASSETS = Path(__file__).resolve().parent / "template_assets"
SETTINGS_KEY = "assistant"

PAPERS = ("a4", "a5", "letter")
# Fonts that are there in the Flatpak; Word replaces them with their look-alikes if needed
SERIF_FONTS = ("Liberation Serif", "Caladea", "DejaVu Serif")
SANS_FONTS = ("Liberation Sans", "Carlito", "Noto Sans", "Cantarell", "DejaVu Sans")
FONTS = SERIF_FONTS + SANS_FONTS
PAGE_NUMBERS = ("none", "center", "right")
FIRST_LINE_INDENT_CM = 0.6
PARAGRAPH_GAP_PT = 8


@dataclass(frozen=True)
class Settings:
    name: str = ""
    paper: str = "a4"
    margin_top: float = 25
    margin_right: float = 25
    margin_bottom: float = 25
    margin_left: float = 25
    body_font: str = "Liberation Serif"
    body_size: float = 12
    line_spacing: float = 1.5
    first_line_indent: bool = False  # otherwise a gap between paragraphs
    justify: bool = False
    heading_font: str = "Liberation Sans"
    heading_center: bool = False
    chapters_on_new_page: bool = False
    page_numbers: str = "center"


def presets() -> dict[str, tuple[str, Settings]]:
    """Starting points: id → (label, settings)."""
    return {
        "text": (_("Plain Text"), Settings()),
        "manuscript": (_("Manuscript for an Editor"), Settings(
            margin_right=50, line_spacing=1.5, heading_font="Liberation Serif", first_line_indent=True,
            chapters_on_new_page=True, page_numbers="right",
        )),
        "thesis": (_("Thesis or Essay"), Settings(
            margin_left=30, justify=True, chapters_on_new_page=True,
        )),
        "novel": (_("Novel"), Settings(
            paper="a5", margin_top=20, margin_right=18, margin_bottom=22, margin_left=18, body_font="Caladea", body_size=10.5,
            line_spacing=1.3, first_line_indent=True, justify=True, heading_font="Caladea", heading_center=True,
            chapters_on_new_page=True,
        )),
        "report": (_("Report"), Settings(
            body_font="Carlito", body_size=11, line_spacing=1.25, heading_font="Carlito", page_numbers="right",
        )),
    }


def settings_of(template: Template) -> Settings | None:
    """The settings a template was built from; None for templates from elsewhere."""
    stored = template.info.get(SETTINGS_KEY)
    if not isinstance(stored, dict):
        return None
    values = {}
    for field in fields(Settings):
        value = stored.get(field.name)
        default = getattr(Settings(), field.name)
        numeric = isinstance(default, (int, float)) and not isinstance(default, bool)
        if numeric and isinstance(value, (int, float)) and not isinstance(value, bool):
            values[field.name] = float(value)
        elif isinstance(value, type(default)) and not numeric:
            values[field.name] = value
    settings = replace(Settings(), **values)
    # A file edited by hand must not bring in unknown choices
    return replace(
        settings,
        paper=settings.paper if settings.paper in PAPERS else "a4",
        body_font=settings.body_font if settings.body_font in FONTS else FONTS[0],
        heading_font=settings.heading_font if settings.heading_font in FONTS else FONTS[0],
        page_numbers=settings.page_numbers if settings.page_numbers in PAGE_NUMBERS else "center",
    )


def _font_stack(font: str) -> str:
    fallback = "serif" if font in SERIF_FONTS else "sans-serif"
    return f'"{font}", {fallback}'


def stylesheet(settings: Settings) -> str:
    """style.css: the look for HTML and PDF. Text rules apply to main, so the title block stays as it is."""
    align = "center" if settings.heading_center else "left"
    rules = [
        "/* Made with the Typecase template assistant. */",
        f"html {{ font-family: {_font_stack(settings.body_font)}; font-size: {settings.body_size:g}pt;"
        f" line-height: {settings.line_spacing:g}; color: #1f1f1f; background: #ffffff; }}",
        "body { max-width: 38em; margin: 3em auto; padding: 0 1.5em; }",
        "body.pdf { max-width: none; margin: 0; padding: 0; }",
        f".title-block {{ text-align: {align}; }}",
        ".title-block { margin-bottom: 2.5em; }",
        ".title { font-size: 2em; line-height: 1.2; margin: 0; }",
        ".subtitle { font-size: 1.25em; margin: 0.3em 0 0; }",
        ".author { margin: 0.8em 0 0; }",
        f".title, .subtitle, h1, h2, h3, h4, h5, h6 {{ font-family: {_font_stack(settings.heading_font)}; }}",
        f"h1, h2, h3, h4, h5, h6 {{ line-height: 1.25; margin: 1.6em 0 0.5em; text-align: {align}; break-after: avoid; }}",
        "h1 { font-size: 1.6em; } h2 { font-size: 1.3em; } h3 { font-size: 1.1em; } h4, h5, h6 { font-size: 1em; }",
        "main p { orphans: 3; widows: 3; }",
    ]
    if settings.first_line_indent:
        rules += ["main p { margin: 0; }", f"main p + p {{ text-indent: {FIRST_LINE_INDENT_CM}cm; }}"]
    else:
        rules.append(f"main p {{ margin: 0 0 {PARAGRAPH_GAP_PT}pt; }}")
    if settings.justify:
        rules.append("main p { text-align: justify; hyphens: auto; }")
    if settings.chapters_on_new_page:
        rules += [
            "main h1 { break-before: page; }",
            "main > h1:first-child { break-before: auto; }",
            # In a group with parts, the chapters are one level below their part.
            "main h1.part ~ h2 { break-before: page; }",
            "main h1.part + h2 { break-before: auto; }",
        ]
    if settings.page_numbers != "none":
        place = "bottom-center" if settings.page_numbers == "center" else "bottom-right"
        rules.append(f'@page {{ @{place} {{ content: counter(page); font-family: {_font_stack(settings.body_font)}; font-size: 9pt; }} }}')
    rules += [
        "a { color: inherit; }",
        ".underline { text-decoration: underline; }",
        "blockquote { margin: 1em 0; padding-left: 1em; border-left: 3px solid #d6d6d6; color: #5e5e5e; }",
        'code { font-family: "Liberation Mono", monospace; font-size: 0.9em; }',
        "pre { background: #f4f4f4; padding: 0.8em 1em; overflow-x: auto; break-inside: avoid; }",
        "hr { border: none; border-top: 1px solid #d6d6d6; margin: 2em 0; }",
        "img { max-width: 100%; }",
        "table { border-collapse: collapse; }",
        "th, td { border: 1px solid #d6d6d6; padding: 0.3em 0.6em; }",
    ]
    return "\n".join(rules) + "\n"


def _reference_docx(settings: Settings, output: Path) -> None:
    size = settings.body_size
    docx_style.apply(
        ASSETS / "reference-base.docx",
        output,
        body_font=settings.body_font,
        body_size=size,
        heading_font=settings.heading_font,
        heading_color="000000",
        heading_sizes=",".join(f"{size * factor:g}" for factor in (1.6, 1.3, 1.1)),
        heading_align="center" if settings.heading_center else "left",
        heading_bold=True,
        line_spacing=settings.line_spacing,
        paragraph_spacing=0 if settings.first_line_indent else PARAGRAPH_GAP_PT,
        first_line_indent=FIRST_LINE_INDENT_CM if settings.first_line_indent else None,
        align="justify" if settings.justify else "left",
        title_align="center" if settings.heading_center else "left",
        chapter_page_break=settings.chapters_on_new_page,
        paper=settings.paper,
        margins=f"{settings.margin_top:g},{settings.margin_right:g},{settings.margin_bottom:g},{settings.margin_left:g}",
        page_numbers=None if settings.page_numbers == "none" else settings.page_numbers,
    )


def write_files(settings: Settings, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    info = {
        "format": 1,
        "name": settings.name.strip(),
        "description": _("Made with the template assistant"),
        "pdf": {
            "paper": settings.paper,
            "margins_mm": {
                "top": settings.margin_top, "right": settings.margin_right,
                "bottom": settings.margin_bottom, "left": settings.margin_left,
            },
        },
        SETTINGS_KEY: asdict(settings),
    }
    (folder / "template.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(BUILTIN_DIR / "text" / "template.html", folder / "template.html")
    (folder / "style.css").write_text(stylesheet(settings), encoding="utf-8")
    _reference_docx(settings, folder / "reference.docx")


def new_id(name: str, user_dir: Path) -> str:
    """A folder name from the template's name that neither a built-in nor another template uses."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "template"
    taken = {folder.name for folder in BUILTIN_DIR.iterdir()}
    if user_dir.is_dir():
        taken |= {folder.name for folder in user_dir.iterdir()}
    candidate, number = slug, 2
    while candidate in taken:
        candidate, number = f"{slug}-{number}", number + 1
    return candidate


def save(settings: Settings, user_dir: Path, existing: Template | None = None) -> Template:
    """Creates a template in user_dir, or replaces existing once the new files are complete."""
    user_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".assistant-", dir=user_dir))
    try:
        folder = work / "template"
        write_files(settings, folder)
        read_folder(folder, builtin=False)  # the same check an imported template has to pass
        target = existing.path if existing is not None else user_dir / new_id(settings.name, user_dir)
        if target.exists():
            os.replace(target, work / "old")
        os.replace(folder, target)
        return read_folder(target, builtin=False)
    finally:
        shutil.rmtree(work, ignore_errors=True)
