import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.keywords import KeywordIndex, filter_nodes
from typecase.library import scan


def sheet(path: Path, keywords: str | None, body: str = "Text"):
    header = f"---\nkeywords: {keywords}\n---\n" if keywords is not None else ""
    path.write_text(header + body, encoding="utf-8")


class KeywordTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Roman" / "Teil 1").mkdir(parents=True)
        (self.root / "Notizen").mkdir()
        sheet(self.root / "Roman" / "Teil 1" / "Kapitel.md", "[Roman, Entwurf]")
        sheet(self.root / "Roman" / "Plan.md", "[roman]")
        sheet(self.root / "Notizen" / "Einkauf.md", "Alltag")
        sheet(self.root / "Ohne.md", None)
        self.index = KeywordIndex()

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary_counts_case_insensitive(self):
        self.assertEqual(self.index.summary(scan(self.root)), [("Alltag", 1), ("Entwurf", 1), ("Roman", 2)])

    def test_filter_keeps_groups_on_the_way(self):
        nodes = filter_nodes(scan(self.root), lambda node: self.index.has(node.path, "ROMAN"))
        self.assertEqual([n.name for n in nodes], ["Roman"])
        roman = nodes[0]
        self.assertEqual([c.name for c in roman.children], ["Teil 1", "Plan"])
        self.assertEqual([c.name for c in roman.children[0].children], ["Kapitel"])

    def test_no_match(self):
        self.assertEqual(filter_nodes(scan(self.root), lambda node: self.index.has(node.path, "Lyrik")), [])

    def test_cache_notices_changes(self):
        path = self.root / "Ohne.md"
        self.assertEqual(self.index.keywords_of(path), [])
        sheet(path, "[Neu]")
        later = time.time() + 5
        os.utime(path, (later, later))
        self.assertEqual(self.index.keywords_of(path), ["Neu"])

    def test_unreadable_file(self):
        (self.root / "Kaputt.md").write_bytes(b"\xff\xfe kaputt")
        self.assertEqual(self.index.keywords_of(self.root / "Kaputt.md"), [])


if __name__ == "__main__":
    unittest.main()
