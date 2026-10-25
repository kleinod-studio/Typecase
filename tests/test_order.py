import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.library import FOLDER_FILE, ordered_names, place, read_order, rename_in_order, scan, write_order


class OrderTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        for name in ("Chapter 10.md", "Chapter 2.md", "Chapter 1.md"):
            (self.root / name).write_text("x", encoding="utf-8")
        (self.root / "Notes").mkdir()

    def tearDown(self):
        self._dir.cleanup()

    def names(self, folder=None):
        return [node.path.name for node in scan(folder or self.root)]

    def test_default_order_without_file(self):
        self.assertEqual(self.names(), ["Notes", "Chapter 1.md", "Chapter 10.md", "Chapter 2.md"])
        self.assertFalse((self.root / FOLDER_FILE).exists())

    def test_manual_order_first_then_the_rest(self):
        write_order(self.root, ["Chapter 2.md", "Chapter 1.md", "gone.md"])
        self.assertEqual(self.names(), ["Chapter 2.md", "Chapter 1.md", "Notes", "Chapter 10.md"])

    def test_place_before_and_after(self):
        place(self.root / "Chapter 10.md", None)  # to the end
        self.assertEqual(self.names()[-1], "Chapter 10.md")
        place(self.root / "Chapter 2.md", self.root / "Chapter 1.md", after=True)
        self.assertEqual(self.names(), ["Notes", "Chapter 1.md", "Chapter 2.md", "Chapter 10.md"])
        place(self.root / "Notes", self.root / "Chapter 10.md", after=True)
        self.assertEqual(self.names(), ["Chapter 1.md", "Chapter 2.md", "Chapter 10.md", "Notes"])
        self.assertEqual(read_order(self.root), ["Chapter 1.md", "Chapter 2.md", "Chapter 10.md", "Notes"])

    def test_place_into_another_folder(self):
        (self.root / "Notes" / "Idea.md").write_text("x", encoding="utf-8")
        moved = place(self.root / "Chapter 2.md", self.root / "Notes" / "Idea.md")
        self.assertEqual(moved, self.root / "Notes" / "Chapter 2.md")
        self.assertEqual(self.names(self.root / "Notes"), ["Chapter 2.md", "Idea.md"])

    def test_rename_keeps_position(self):
        write_order(self.root, ["Chapter 2.md", "Chapter 1.md"])
        (self.root / "Chapter 2.md").rename(self.root / "Prologue.md")
        rename_in_order(self.root, "Chapter 2.md", "Prologue.md")
        self.assertEqual(self.names()[:2], ["Prologue.md", "Chapter 1.md"])

    def test_broken_file_is_ignored_and_other_keys_kept(self):
        (self.root / FOLDER_FILE).write_text("{kaputt", encoding="utf-8")
        self.assertEqual(read_order(self.root), [])
        self.assertEqual(ordered_names(self.root)[0], "Notes")
        (self.root / FOLDER_FILE).write_text(json.dumps({"icon": "book", "order": ["Chapter 1.md"]}), encoding="utf-8")
        write_order(self.root, ["Chapter 2.md"])
        data = json.loads((self.root / FOLDER_FILE).read_text(encoding="utf-8"))
        self.assertEqual(data, {"icon": "book", "order": ["Chapter 2.md"]})


if __name__ == "__main__":
    unittest.main()
