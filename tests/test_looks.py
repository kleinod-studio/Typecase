import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import looks  # noqa: E402
from typecase.library import FOLDER_FILE, write_order  # noqa: E402


class LookTests(unittest.TestCase):
    def test_unknown_values_are_the_standard(self):
        self.assertEqual(looks.Look.of(" Star ", "ORANGE"), looks.Look("star", "orange"))
        self.assertEqual(looks.Look.of("rocket", "#ff0000"), looks.Look())
        self.assertEqual(looks.Look.of(["star"], 3), looks.Look())

    def test_icon_names(self):
        self.assertEqual(looks.Look().icon_name(False), looks.DEFAULT_SHEET_ICON)
        self.assertEqual(looks.Look().icon_name(True), looks.DEFAULT_GROUP_ICON)
        self.assertEqual(looks.Look("heart").icon_name(True), "emote-love-symbolic")

    def test_every_icon_has_a_label(self):
        for name in looks.ICON_NAMES:
            self.assertNotEqual(looks.icon_label(name), name)
        for color in looks.COLORS:
            self.assertNotEqual(looks.color_label(color), color)

    def test_sheet_look_in_front_matter(self):
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder, "A.md")
            sheet.write_text("---\ntitle: A\n---\nText.\n", encoding="utf-8")
            looks.set_for_sheet(sheet, looks.Look("star", "orange"))
            self.assertEqual(sheet.read_text(encoding="utf-8"), "---\ntitle: A\nicon: star\ncolor: orange\n---\nText.\n")
            self.assertEqual(looks.LookIndex().of_sheet(sheet), looks.Look("star", "orange"))
            looks.set_for_sheet(sheet, looks.Look())
            self.assertEqual(sheet.read_text(encoding="utf-8"), "---\ntitle: A\n---\nText.\n")

    def test_sheet_without_front_matter(self):
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder, "B.md")
            sheet.write_text("Text.\n", encoding="utf-8")
            looks.set_for_sheet(sheet, looks.Look(None, "teal"))
            self.assertEqual(sheet.read_text(encoding="utf-8"), "---\ncolor: teal\n---\nText.\n")
            looks.set_for_sheet(sheet, looks.Look())
            self.assertEqual(sheet.read_text(encoding="utf-8"), "Text.\n")

    def test_group_look_keeps_the_order(self):
        with tempfile.TemporaryDirectory() as folder:
            group = Path(folder)
            looks.set_for_group(group, looks.Look("book", "purple"))
            self.assertEqual(looks.of_group(group), looks.Look("book", "purple"))
            write_order(group, ["b.md", "a.md"])
            looks.set_for_group(group, looks.Look("book"))
            data = json.loads((group / FOLDER_FILE).read_text(encoding="utf-8"))
            self.assertEqual(data, {"icon": "book", "order": ["b.md", "a.md"]})
            looks.set_for_group(group, looks.Look())
            self.assertEqual(json.loads((group / FOLDER_FILE).read_text(encoding="utf-8")), {"order": ["b.md", "a.md"]})

    def test_standard_removes_an_otherwise_empty_folder_file(self):
        with tempfile.TemporaryDirectory() as folder:
            group = Path(folder)
            looks.set_for_group(group, looks.Look(None, "red"))
            looks.set_for_group(group, looks.Look())
            self.assertFalse((group / FOLDER_FILE).exists())


if __name__ == "__main__":
    unittest.main()
