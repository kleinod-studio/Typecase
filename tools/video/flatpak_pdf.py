"""Exports one sheet as an A5 PDF with the "Novel" template, the way Typecase does. Runs inside the
installed Typecase Flatpak, which brings Pandoc and WeasyPrint (tour.py calls it):

    flatpak run --command=python3 studio.kleinod.Typecase flatpak_pdf.py SHEET WORK_FOLDER OUTPUT.pdf"""
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, "/app/share/typecase")
from typecase import export, template_builder  # noqa: E402

sheet, folder, output = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
folder.mkdir(parents=True, exist_ok=True)
_label, settings = template_builder.presets()["novel"]
template = template_builder.save(replace(settings, name="Novel", page_numbers="center"), folder)
header = folder / "style.html"
header.write_text(export.style_header(template, pdf=True), encoding="utf-8")
html = folder / "document.html"
defaults = {"author": None, "lang": None, "date": export.export_date()}
args = export.pandoc_args("pdf", template, html, None, header, defaults)
subprocess.run(args, input=export.prepare_markdown(sheet.read_text(encoding="utf-8")), text=True, cwd=sheet.parent, check=True)
if hasattr(export, "with_empty_alt"):
    html.write_text(export.with_empty_alt(html.read_text(encoding="utf-8")), encoding="utf-8")
margins = template.pdf_margins_mm
subprocess.run(
    [sys.executable, "-m", "typecase.pdf_render", str(html), str(sheet.parent), str(output),
     "--paper-mm", "148,210", "--margins-mm", ",".join(str(margins[s]) for s in ("top", "right", "bottom", "left"))],
    env={"PYTHONPATH": "/app/share/typecase", "PATH": "/app/bin:/usr/bin"}, check=True,
)
print("done", output, flush=True)
