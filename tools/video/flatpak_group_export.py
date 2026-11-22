"""Exports a whole group as one PDF the way Typecase's export dialog does, with a table of contents,
a cover page and its subgroups as parts. Runs inside the installed Typecase Flatpak, which brings
Pandoc and WeasyPrint (export-a-group.py calls it):

    flatpak run --command=python3 studio.kleinod.Typecase flatpak_group_export.py GROUP TEMPLATE_FOLDER OUTPUT TITLE AUTHOR PARTS

PARTS is continuous, new-page or title-page."""
import sys
from pathlib import Path

sys.path.insert(0, "/app/share/typecase")
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib  # noqa: E402

from typecase import export, export_templates  # noqa: E402
from typecase.export_dialog import run_export  # noqa: E402
from typecase.keywords import sheets as all_sheets  # noqa: E402
from typecase.library import scan  # noqa: E402

group, folder, output, title, author, parts = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), *sys.argv[4:7]
template = export_templates.read_folder(folder, builtin=False)
sheets = [sheet.path for sheet in all_sheets(scan(group))]
text = export.with_title(export.combine_sheets(sheets, group, parts), title)
defaults = {"author": author, "lang": None, "date": export.export_date()}
loop = GLib.MainLoop()
result = {}


def done(path, error, missing):
    result.update(path=path, error=error)
    loop.quit()


run_export(text, "pdf", template, output, group / f"{group.name}.md", title, defaults, done, toc_title="Contents", cover=True)
loop.run()
if result["error"]:
    sys.exit(result["error"])
print("done", result["path"], flush=True)
