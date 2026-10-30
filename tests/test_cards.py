import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.cards import read_card, save_notes


class CardsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.sheet = self.folder / "Chapter.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_read_card(self):
        self.sheet.write_text(
            "---\nstatus: draft\nkeywords: [Plot, Anna]\ngoal: 100\nnotes: |-\n  First idea\n  Second idea\n---\nThree words here.\n",
            encoding="utf-8",
        )
        card = read_card(self.sheet)
        self.assertEqual(card.notes, "First idea\nSecond idea")
        self.assertEqual(card.status, "draft")
        self.assertEqual(card.keywords, ["Plot", "Anna"])
        self.assertEqual((card.words, card.goal), (3, 100))

    def test_read_card_without_front_matter(self):
        self.sheet.write_text("Just text.\n", encoding="utf-8")
        card = read_card(self.sheet)
        self.assertEqual((card.notes, card.status, card.keywords, card.goal), ("", "", [], None))

    def test_save_keeps_text_and_other_fields(self):
        self.sheet.write_text("---\ntitle: A # comment\nnotes: old\n---\nBody\n", encoding="utf-8")
        self.assertIsNone(save_notes(self.sheet, "old", "new\nline"))
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "---\ntitle: A # comment\nnotes: |-\n  new\n  line\n---\nBody\n")

    def test_save_takes_the_text_fresh_from_disk(self):
        self.sheet.write_text("Body\n", encoding="utf-8")
        self.sheet.write_text("Body written meanwhile\n", encoding="utf-8")  # e.g. by another program
        save_notes(self.sheet, "", "idea")
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "---\nnotes: idea\n---\nBody written meanwhile\n")

    def test_removing_the_notes_removes_an_empty_header(self):
        self.sheet.write_text("---\nnotes: idea\n---\nBody\n", encoding="utf-8")
        save_notes(self.sheet, "idea", "")
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "Body\n")

    def test_notes_changed_elsewhere_are_kept_as_a_copy(self):
        self.sheet.write_text("---\nnotes: theirs\n---\nBody\n", encoding="utf-8")
        copy = save_notes(self.sheet, "original", "mine")
        self.assertIsNotNone(copy)
        self.assertEqual(copy.read_text(encoding="utf-8"), "---\nnotes: theirs\n---\nBody\n")
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "---\nnotes: mine\n---\nBody\n")

    def test_same_change_elsewhere_is_no_conflict(self):
        self.sheet.write_text("---\nnotes: mine\n---\nBody\n", encoding="utf-8")
        self.assertIsNone(save_notes(self.sheet, "original", "mine"))
        self.assertEqual(len(list(self.folder.iterdir())), 1)

    def test_deleted_sheet_is_recreated_with_the_notes(self):
        self.assertIsNone(save_notes(self.sheet, "idea", "idea and more"))
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "---\nnotes: idea and more\n---\n")


if __name__ == "__main__":
    unittest.main()
