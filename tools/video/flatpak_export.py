"""Exports one sheet the way Typecase's export dialog does, with a template folder, optionally with
a cover page. Runs inside the installed Typecase Flatpak, which brings Pandoc and WeasyPrint
(export.py calls it):

    flatpak run --command=python3 studio.kleinod.Typecase flatpak_export.py SHEET TEMPLATE_FOLDER FORMAT OUTPUT [--cover]

FORMAT is pdf or docx. For a feature the installed Flatpak does not have yet, it also runs with the
development version: TYPECASE_CODE=src .venv/bin/python flatpak_export.py … (Pandoc on the PATH)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CODE = str(Path(os.environ.get("TYPECASE_CODE", "/app/share/typecase")).resolve())
sys.path.insert(0, CODE)
from typecase import export, export_templates  # noqa: E402
from typecase.frontmatter import parse, split  # noqa: E402

sheet, folder, fmt, output = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
cover = "--cover" in sys.argv[5:]
template = export_templates.read_folder(folder, builtin=False)
text = sheet.read_text(encoding="utf-8")
if hasattr(export, "with_fields"):  # template fields, as the export dialog fills them in
    text = export.with_fields(text, template)
title = parse(split(text)[0]).get("title")
defaults = {"author": None, "lang": None, "date": export.export_date()}
if fmt == "docx" and not cover:
    defaults.pop("date")
work = Path(tempfile.mkdtemp(prefix="typecase-export-"))
header = work / "style.html"
header.write_text(export.style_header(template, pdf=fmt == "pdf"), encoding="utf-8")
pandoc_output = work / ("document.html" if fmt == "pdf" else "document.docx")
args = export.pandoc_args(fmt, template, pandoc_output, None if title else sheet.stem, header, defaults, cover=cover)
subprocess.run(args, input=export.prepare_markdown(text), text=True, cwd=sheet.parent, check=True)
if fmt == "pdf":
    pandoc_output.write_text(export.with_empty_alt(pandoc_output.read_text(encoding="utf-8")), encoding="utf-8")
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    paper = Gtk.PaperSize.new(template.pdf_paper or "iso_a4")
    margins = template.pdf_margins_mm
    subprocess.run(
        [sys.executable, "-m", "typecase.pdf_render", str(pandoc_output), str(sheet.parent), str(output),
         "--paper-mm", f"{paper.get_width(Gtk.Unit.MM):.2f},{paper.get_height(Gtk.Unit.MM):.2f}",
         "--margins-mm", ",".join(str(margins[side]) for side in ("top", "right", "bottom", "left"))],
        env={"PYTHONPATH": CODE, "PATH": "/app/bin:/usr/bin"}, check=True,
    )
else:
    export.style_aligned_images(pandoc_output)
    if cover:
        export.hide_first_page_footer(pandoc_output)
    output.write_bytes(pandoc_output.read_bytes())
print("done", output, flush=True)
