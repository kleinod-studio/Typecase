import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.search import LibrarySearch


class SearchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Roman").mkdir()
        (self.root / "Roman" / "Kapitel.md").write_text("Es war einmal ein Drache.\nDer DRACHE schlief.\n")
        (self.root / "Drachenkunde.md").write_text("Nichts Passendes hier.")
        (self.root / "Notiz.md").write_text("Einkaufen")
        self.search = LibrarySearch()

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_text_case_insensitive_with_count(self):
        hits = self.search.search(self.root, "drache")
        by_name = {hit.name: hit for hit in hits}
        kapitel = by_name["Kapitel"]
        self.assertEqual((kapitel.count, kapitel.group, kapitel.offset), (2, "Roman", 18))
        start, end = kapitel.snippet_match
        self.assertEqual(kapitel.snippet[start:end], "Drache")

    def test_name_matches_come_first(self):
        names = [hit.name for hit in self.search.search(self.root, "drache")]
        self.assertEqual(names, ["Drachenkunde", "Kapitel"])
        self.assertEqual(self.search.search(self.root, "drache")[0].offset, -1)

    def test_empty_query_and_no_match(self):
        self.assertEqual(self.search.search(self.root, "   "), [])
        self.assertEqual(self.search.search(self.root, "Einhorn"), [])

    def test_special_characters_are_literal(self):
        (self.root / "Code.md").write_text("Preis: 3.50 (netto)")
        self.assertEqual([h.name for h in self.search.search(self.root, "(netto)")], ["Code"])
        self.assertEqual(self.search.search(self.root, "3x50"), [])

    def test_override_for_open_sheet(self):
        path = self.root / "Notiz.md"
        hits = self.search.search(self.root, "Milch", overrides={path: "Einkaufen: Milch"})
        self.assertEqual([h.name for h in hits], ["Notiz"])

    def test_cache_notices_changes(self):
        self.assertEqual(self.search.search(self.root, "Milch"), [])
        path = self.root / "Notiz.md"
        path.write_text("Einkaufen: Milch und Brot")
        later = time.time() + 5
        os.utime(path, (later, later))
        self.assertEqual([h.name for h in self.search.search(self.root, "Milch")], ["Notiz"])

    def test_snippet_is_shortened_around_match(self):
        long_line = "Wort " * 40 + "Ziel" + " Ende" * 40
        (self.root / "Lang.md").write_text(long_line)
        hit = self.search.search(self.root, "Ziel")[0]
        self.assertTrue(hit.snippet.startswith("…") and hit.snippet.endswith("…"))
        start, end = hit.snippet_match
        self.assertEqual(hit.snippet[start:end], "Ziel")
        self.assertLess(len(hit.snippet), 150)


if __name__ == "__main__":
    unittest.main()
