#!/usr/bin/env python3
"""Check a template folder and pack it into a .typecase-template file.

Runs the same checks Typecase runs when importing (so a file that passes here imports cleanly)
plus a few extra warnings for things that would silently look wrong. Standard library only.

Usage:
    python3 build_template.py <template-folder> <output.typecase-template>

The file name becomes the template's id in Typecase, so name it after the template,
e.g. "Lektorat.typecase-template" or "Business Letter.typecase-template".
"""

import json
import re
import sys
import zipfile
from pathlib import Path

FORMAT_VERSION = 1
PAPERS = {"a3", "a4", "a5", "letter", "legal"}
MAX_FILES = 200
MAX_TOTAL_BYTES = 50 * 1024 * 1024
CSS_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""")


def check(folder: Path) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    info_file = folder / "template.json"
    info = {}
    if not info_file.is_file():
        errors.append("template.json is missing.")
    else:
        try:
            info = json.loads(info_file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"template.json is not valid JSON: {error}")
        if not isinstance(info, dict):
            errors.append("template.json must contain a JSON object.")
            info = {}
    name = info.get("name")
    if isinstance(name, dict):
        if not any(isinstance(v, str) and v.strip() for v in name.values()):
            errors.append('template.json: "name" has no text.')
        elif "en" not in name:
            warnings.append('template.json: add an English name ("en") as a fallback for other languages.')
    elif not (isinstance(name, str) and name.strip()):
        errors.append('template.json: "name" is required (a string or {"en": ..., "de": ...}).')
    version = info.get("format", FORMAT_VERSION)
    if not isinstance(version, int) or version > FORMAT_VERSION:
        errors.append(f'template.json: "format" must be {FORMAT_VERSION}.')
    pdf = info.get("pdf", {})
    if not isinstance(pdf, dict):
        errors.append('template.json: "pdf" must be an object.')
        pdf = {}
    paper = pdf.get("paper")
    if paper is not None and (not isinstance(paper, str) or paper.casefold() not in PAPERS):
        warnings.append(f'template.json: unknown paper "{paper}" (Typecase falls back to the system paper). Use one of {sorted(PAPERS)}.')
    margins = pdf.get("margins_mm", {})
    if not isinstance(margins, dict):
        warnings.append('template.json: "margins_mm" should be an object like {"top": 25, ...}.')
        margins = {}
    for side, value in margins.items():
        if side not in ("top", "right", "bottom", "left"):
            warnings.append(f'template.json: unknown margin "{side}".')
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            warnings.append(f'template.json: margin "{side}" must be a number of millimetres between 0 and 100 (falls back to 25).')

    html_file = folder / "template.html"
    if not html_file.is_file():
        errors.append("template.html is missing.")
    else:
        try:
            html = html_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("template.html is not UTF-8 text.")
            html = ""
        if html and "$body$" not in html:
            errors.append("template.html does not contain $body$ — the text would be missing from the export.")
        if html and "header-includes" not in html:
            warnings.append("template.html has no $for(header-includes)$$header-includes$$endfor$ in <head>, so style.css will NOT be applied.")
        if html and re.search(r"<script", html, re.IGNORECASE):
            warnings.append("template.html contains <script>; scripts are not run for PDF and should be avoided.")

    css_file = folder / "style.css"
    if css_file.is_file():
        css = css_file.read_text(encoding="utf-8", errors="replace")
        for match in CSS_URL.finditer(css):
            reference = match.group(2).strip()
            if re.match(r"^(data:|[a-z]+://|#)", reference, re.IGNORECASE):
                if reference.lower().startswith(("http:", "https:")):
                    warnings.append(f"style.css loads {reference} from the internet; Typecase never downloads anything, so it will be missing.")
                continue
            target = (folder / reference).resolve()
            if folder.resolve() not in target.parents:
                warnings.append(f"style.css refers to {reference}, which is outside the template folder; it will be missing.")
            elif not target.is_file():
                errors.append(f"style.css refers to {reference}, but that file is not in the template.")
    else:
        warnings.append("No style.css — HTML and PDF will use the browser's plain default look.")

    docx = folder / "reference.docx"
    if docx.is_file():
        try:
            with zipfile.ZipFile(docx) as archive:
                if "word/styles.xml" not in archive.namelist():
                    errors.append("reference.docx is not a valid Word document (word/styles.xml missing).")
        except zipfile.BadZipFile:
            errors.append("reference.docx is not a valid Word document.")
    else:
        warnings.append("No reference.docx — Word exports will use Pandoc's default styles.")

    files = [p for p in folder.rglob("*") if p.is_file() or p.is_symlink()]
    if any(p.is_symlink() for p in files):
        errors.append("The folder contains symbolic links; Typecase rejects them. Copy the real files in.")
    if len(files) > MAX_FILES:
        errors.append(f"Too many files ({len(files)}; at most {MAX_FILES}).")
    total = sum(p.stat().st_size for p in files if p.is_file())
    if total > MAX_TOTAL_BYTES:
        errors.append(f"Too large ({total // 1024 // 1024} MB; at most 50 MB).")
    return errors, warnings


def pack(folder: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for file in sorted(folder.rglob("*")):
            if file.is_file() and not file.is_symlink() and not file.name.startswith("."):
                archive.write(file, file.relative_to(folder).as_posix())


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    folder, output = Path(sys.argv[1]), Path(sys.argv[2])
    if not output.name.endswith(".typecase-template"):
        output = output.with_name(output.name + ".typecase-template")
    errors, warnings = check(folder)
    for message in warnings:
        print(f"warning: {message}")
    for message in errors:
        print(f"ERROR: {message}")
    if errors:
        print("Not packed. Fix the errors above and run again.")
        return 1
    pack(folder, output)
    print(f"Packed {output} ({output.stat().st_size // 1024 + 1} KB). Import it in Typecase: Preferences → Templates → Import…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
