import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.frontmatter import parse, update
from typecase.goal import GoalIndex, fraction, parse_goal


class GoalTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_goal("1500"), 1500)
        self.assertEqual(parse_goal(" 1.500 "), 1500)
        self.assertEqual(parse_goal("1 500"), 1500)

    def test_parse_rejects(self):
        for value in (None, "", "0", "-5", "viel", "12.5k", ["1000"], "99999999"):
            self.assertIsNone(parse_goal(value), value)

    def test_fraction(self):
        self.assertEqual(fraction(250, 1000), 0.25)
        self.assertEqual(fraction(1500, 1000), 1.0)
        self.assertEqual(fraction(10, None), 0.0)

    def test_roundtrip_through_header(self):
        header = update(None, {"goal": 1500})
        self.assertEqual(header, "---\ngoal: 1500\n---\n")
        self.assertEqual(parse_goal(parse(header)["goal"]), 1500)
        self.assertIsNone(update(header, {"goal": None}))

    def test_index_reads_files_and_notices_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder) / "a.md"
            sheet.write_text("---\ngoal: 10\n---\n# Titel\n\nDrei kleine Wörter.\n", encoding="utf-8")
            index = GoalIndex()
            self.assertEqual(index.progress_of(sheet), (4, 10))
            sheet.write_text("Kein Ziel mehr, dafür längerer Text.\n", encoding="utf-8")
            self.assertIsNone(index.progress_of(sheet))
            self.assertIsNone(index.progress_of(Path(folder) / "fehlt.md"))


if __name__ == "__main__":
    unittest.main()
