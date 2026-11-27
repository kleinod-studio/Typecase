import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import frontmatter, weblinks
from typecase.weblinks import WebLink


class AddressTest(unittest.TestCase):
    def test_web_addresses(self):
        self.assertEqual(weblinks.normalized(" https://example.org/tides "), "https://example.org/tides")
        self.assertEqual(weblinks.normalized("http://example.org"), "http://example.org")

    def test_without_scheme_gets_https(self):
        self.assertEqual(weblinks.normalized("www.example.org"), "https://www.example.org")
        self.assertEqual(weblinks.normalized("example.org/page?a=1"), "https://example.org/page?a=1")

    def test_spaces_and_parentheses_are_encoded(self):
        self.assertEqual(
            weblinks.normalized("https://en.wikipedia.org/wiki/Bell_(instrument)"),
            "https://en.wikipedia.org/wiki/Bell_%28instrument%29",
        )
        self.assertEqual(weblinks.normalized("https://example.org/a b"), "https://example.org/a%20b")

    def test_no_web_address(self):
        for text in ("", "  ", "hello", "Notes 1.5", "file:///home/ada/x.md", "mailto:ada@example.org",
                     "javascript:alert(1)", "https://", "ftp://example.org"):
            self.assertIsNone(weblinks.normalized(text), text)


class ItemTest(unittest.TestCase):
    def test_markdown_link(self):
        self.assertEqual(weblinks.parse("[Tide tables](https://example.org/tides)"), WebLink("https://example.org/tides", "Tide tables"))

    def test_bare_address(self):
        self.assertEqual(weblinks.parse("https://example.org"), WebLink("https://example.org"))

    def test_other_items_are_no_links(self):
        self.assertIsNone(weblinks.parse("just a note"))
        self.assertIsNone(weblinks.parse("[Title](not an address)"))
        self.assertIsNone(weblinks.parse("example.org"), "a bare item needs its scheme")

    def test_round_trip(self):
        for link in (WebLink("https://example.org/a", "Notes [draft] \\ old"), WebLink("https://example.org")):
            self.assertEqual(weblinks.parse(weblinks.to_item(link)), link)

    def test_label(self):
        self.assertEqual(WebLink("https://example.org", "Tides").label(), "Tides")
        self.assertEqual(WebLink("https://www.example.org/page").label(), "example.org")

    def test_make(self):
        self.assertEqual(weblinks.make("www.example.org", "  Tide   tables "), WebLink("https://www.example.org", "Tide tables"))
        self.assertIsNone(weblinks.make("no address", "Title"))


class FieldTest(unittest.TestCase):
    def test_links_keep_their_place(self):
        field = ["a note of my own", "https://example.org", "[B](https://b.example.org)"]
        self.assertEqual(
            weblinks.links(field),
            [(1, WebLink("https://example.org")), (2, WebLink("https://b.example.org", "B"))],
        )

    def test_add_replace_remove_keep_other_items(self):
        field = ["a note of my own"]
        field = weblinks.add(field, WebLink("https://example.org", "Tides"))
        self.assertEqual(field, ["a note of my own", "[Tides](https://example.org)"])
        field = weblinks.replace(field, 1, WebLink("https://example.org"))
        self.assertEqual(field, ["a note of my own", "https://example.org"])
        self.assertEqual(weblinks.remove(field, 1), ["a note of my own"])

    def test_add_the_same_address_again(self):
        field = ["[Tides](https://example.org)"]
        self.assertEqual(weblinks.add(field, WebLink("https://example.org")), field, "keeps the title")
        self.assertEqual(weblinks.add(field, WebLink("https://example.org", "New")), ["[New](https://example.org)"])

    def test_items_from_front_matter(self):
        self.assertEqual(weblinks.items(["a", "b"]), ["a", "b"])
        self.assertEqual(weblinks.items("https://example.org"), ["https://example.org"])
        self.assertEqual(weblinks.items(""), [])
        self.assertEqual(weblinks.items(None), [])

    def test_in_the_front_matter(self):
        field = weblinks.add([], WebLink("https://example.org/tides", "Tide tables"))
        field = weblinks.add(field, WebLink("https://en.wikipedia.org/wiki/Lighthouse"))
        header = frontmatter.update("---\ntitle: The Storm\n---\n", {weblinks.FIELD: field})
        self.assertEqual(
            header,
            "---\ntitle: The Storm\nlinks:\n"
            '  - "[Tide tables](https://example.org/tides)"\n'
            "  - https://en.wikipedia.org/wiki/Lighthouse\n---\n",
        )
        read = weblinks.items(frontmatter.parse(header)[weblinks.FIELD])
        self.assertEqual([link for _i, link in weblinks.links(read)], [
            WebLink("https://example.org/tides", "Tide tables"), WebLink("https://en.wikipedia.org/wiki/Lighthouse"),
        ])

    def test_short_lists_stay_on_one_line(self):
        self.assertEqual(frontmatter.update(None, {"keywords": ["Plot", "Anna"]}), "---\nkeywords: [Plot, Anna]\n---\n")


if __name__ == "__main__":
    unittest.main()
