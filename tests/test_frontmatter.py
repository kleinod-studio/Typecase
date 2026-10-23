import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.frontmatter import join, parse, split, update

SAMPLE = """---
title: Der Drache
author: "Sascha W."
keywords: [Roman, "Teil 1, Entwurf"]
aliases:
  - Fridolin
  - Drache
cssclass: wide   # von Obsidian
---
# Kapitel eins

Text.
"""


class SplitTest(unittest.TestCase):
    def test_split_and_join_roundtrip(self):
        header, body = split(SAMPLE)
        self.assertTrue(header.startswith("---\n") and header.endswith("---\n"))
        self.assertEqual(body, "# Kapitel eins\n\nText.\n")
        self.assertEqual(join(header, body), SAMPLE)

    def test_no_header(self):
        self.assertEqual(split("# Titel\n---\nText"), (None, "# Titel\n---\nText"))
        self.assertEqual(split("---\nnie geschlossen"), (None, "---\nnie geschlossen"))
        self.assertEqual(split(""), (None, ""))

    def test_header_only_and_crlf(self):
        self.assertEqual(split("---\ntitle: x\n---"), ("---\ntitle: x\n---", ""))
        header, body = split("---\r\ntitle: x\r\n---\r\nText")
        self.assertEqual((parse(header), body), ({"title": "x"}, "Text"))


class ParseTest(unittest.TestCase):
    def test_fields(self):
        header, _ = split(SAMPLE)
        data = parse(header)
        self.assertEqual(data["title"], "Der Drache")
        self.assertEqual(data["author"], "Sascha W.")
        self.assertEqual(data["keywords"], ["Roman", "Teil 1, Entwurf"])
        self.assertEqual(data["aliases"], ["Fridolin", "Drache"])
        self.assertEqual(data["cssclass"], "wide")

    def test_empty(self):
        self.assertEqual(parse(None), {})
        self.assertEqual(parse("---\n---\n"), {})


class UpdateTest(unittest.TestCase):
    def test_changes_only_touched_lines(self):
        header, body = split(SAMPLE)
        new = update(header, {"title": "Neuer Titel"})
        self.assertEqual(new, header.replace("title: Der Drache", "title: Neuer Titel"))

    def test_add_and_remove(self):
        header, _ = split(SAMPLE)
        new = update(header, {"status": "draft", "aliases": None})
        self.assertIn("status: draft\n---\n", new)
        self.assertNotIn("aliases", new)
        self.assertNotIn("Fridolin", new)
        self.assertIn("cssclass: wide   # von Obsidian", new)

    def test_new_header_and_removal_of_last_field(self):
        created = update(None, {"created": "2026-10-23"})
        self.assertEqual(created, "---\ncreated: 2026-10-23\n---\n")
        self.assertIsNone(update(created, {"created": ""}))
        self.assertIsNone(update(None, {"title": None}))

    def test_quoting_roundtrip(self):
        tricky = ['Teil 1, Entwurf', 'Zitat "hier"', "key: value", "# kein Kommentar", "yes", "  Leer"]
        header = update(None, {"keywords": tricky, "title": 'Er sagte: "Hallo"'})
        data = parse(header)
        self.assertEqual(data["keywords"], tricky)
        self.assertEqual(data["title"], 'Er sagte: "Hallo"')

    def test_keeps_crlf(self):
        header, _ = split("---\r\ntitle: x\r\n---\r\nText")
        self.assertEqual(update(header, {"author": "A"}), "---\r\ntitle: x\r\nauthor: A\r\n---\r\n")


if __name__ == "__main__":
    unittest.main()
