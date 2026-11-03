import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.markdown_style import fence_language, line_spans, link_at, list_text_start, link_spans, note_definition, note_spans


def styled(line, in_code=False):
    """Helper representation: {tag: [text pieces]}"""
    result = {}
    for start, end, tag in line_spans(line, in_code):
        result.setdefault(tag, []).append(line[start:end])
    return result


class HeadingTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(styled("# Titel"), {"syntax": ["# "], "h1": ["Titel"]})
        self.assertEqual(styled("### Drei"), {"syntax": ["### "], "h3": ["Drei"]})

    def test_not_a_heading(self):
        self.assertEqual(styled("#hashtag"), {})
        self.assertEqual(styled("####### sieben"), {})

    def test_inline_inside_heading(self):
        self.assertEqual(styled("## Ein **fettes** Wort")["bold"], ["fettes"])


class InlineTest(unittest.TestCase):
    def test_bold_and_italic(self):
        s = styled("Ein **fettes** und *kursives* Wort")
        self.assertEqual(s["bold"], ["fettes"])
        self.assertEqual(s["italic"], ["kursives"])
        self.assertEqual(s["syntax"], ["**", "**", "*", "*"])

    def test_underscore_variants(self):
        s = styled("__fett__ und _kursiv_")
        self.assertEqual((s["bold"], s["italic"]), (["fett"], ["kursiv"]))

    def test_bold_italic(self):
        s = styled("***beides***")
        self.assertEqual((s["bold"], s["italic"]), (["beides"], ["beides"]))

    def test_no_emphasis_inside_words_or_with_spaces(self):
        self.assertEqual(styled("snake_case_name"), {})
        self.assertEqual(styled("2 * 3 * 4"), {})
        self.assertEqual(styled("** nicht fett **"), {})

    def test_code_wins(self):
        s = styled("Nimm `**kein** fett` hier")
        self.assertEqual(s["code"], ["**kein** fett"])
        self.assertNotIn("bold", s)

    def test_link(self):
        s = styled("Siehe [die Seite](https://example.org) dort")
        self.assertEqual(s["link"], ["die Seite"])
        self.assertEqual(s["syntax"], ["[", "](https://example.org)"])

    def test_inline_footnote(self):
        s = styled("Satz.^[Quelle: [Buch](https://x.org), S. 12] weiter")
        self.assertEqual(s["footnote"], ["Quelle: [Buch](https://x.org), S. 12"])
        self.assertEqual(s["link"], ["Buch"])
        self.assertEqual(sorted(s["syntax"]), sorted(["^[", "[", "](https://x.org)", "]"]))

    def test_footnote_reference_and_definition(self):
        self.assertEqual(styled("Text[^1] mehr")["syntax"], ["[^1]"])
        s = styled("[^1]: Die *Notiz*")
        self.assertEqual(s["syntax"][0], "[^1]: ")
        self.assertEqual(s["footnote"], ["Die *Notiz*"])
        self.assertEqual(s["italic"], ["Notiz"])

    def test_unclosed_footnote_is_plain_text(self):
        self.assertNotIn("footnote", styled("a ^[offen"))

    def test_bare_and_angle_addresses_are_links(self):
        s = styled("Siehe https://example.org/a_b_c. und <https://gnome.org>")
        self.assertEqual(sorted(s["link"]), ["https://example.org/a_b_c", "https://gnome.org"])
        self.assertEqual(s["syntax"], ["<", ">"])
        self.assertNotIn("italic", s)  # underscores in an address are no emphasis

    def test_underline(self):
        s = styled("ein <u>wichtiges **fettes**</u> Wort")
        self.assertEqual(s["underline"], ["wichtiges **fettes**"])
        self.assertEqual(s["bold"], ["fettes"])
        self.assertEqual(s["syntax"][:2], ["<u>", "</u>"])

    def test_strike(self):
        self.assertEqual(styled("~~weg~~")["strike"], ["weg"])


class BlockTest(unittest.TestCase):
    def test_lists(self):
        self.assertEqual(styled("- Punkt")["list-marker"], ["-"])
        self.assertEqual(styled("  12. Zwölf")["list-marker"], ["12."])
        s = styled("- [x] erledigt")
        self.assertEqual((s["list-marker"], s["syntax"]), (["-"], ["[x] "]))

    def test_list_with_bold(self):
        self.assertEqual(styled("* **fett** im Punkt")["bold"], ["fett"])

    def test_quote(self):
        s = styled("> Ein *Zitat*")
        self.assertEqual(s["quote"], ["Ein *Zitat*"])
        self.assertEqual(s["italic"], ["Zitat"])
        self.assertEqual(s["syntax"][0], "> ")

    def test_rule_and_fence(self):
        self.assertEqual(styled("---"), {"syntax": ["---"]})
        self.assertEqual(styled("```python"), {"syntax": ["```python"]})

    def test_code_block_content(self):
        self.assertEqual(styled("**nicht fett**", in_code=True), {"codeblock": ["**nicht fett**"]})

    def test_fence_language(self):
        self.assertEqual(fence_language("```Python"), "python")
        self.assertEqual(fence_language("~~~ c++"), "c++")
        self.assertEqual(fence_language("```"), "")
        self.assertEqual(fence_language("Text"), "")

    def test_plain_and_empty(self):
        self.assertEqual(styled("Nur Text."), {})
        self.assertEqual(styled(""), {})



class ListTextStartTest(unittest.TestCase):
    def test_where_the_text_begins(self):
        self.assertEqual(list_text_start("- Punkt"), 2)
        self.assertEqual(list_text_start("12. Punkt"), 4)
        self.assertEqual(list_text_start("  - eingerückt"), 4)
        self.assertEqual(list_text_start("- [ ] Aufgabe"), 6)
        self.assertEqual(list_text_start("> - im Zitat"), 4)

    def test_no_list_item(self):
        for line in ("Text", "-", "- ", "-Kein Abstand", "# Überschrift", ""):
            self.assertIsNone(list_text_start(line), line)


if __name__ == "__main__":
    unittest.main()


class LinkAtTest(unittest.TestCase):
    def test_link_spans(self):
        line = "[a](b) <https://c.de> www.d.de ![e](f.png) `[g](h)` ^[[i](j)]"
        self.assertEqual(link_spans(line), [(0, 1, 2, 6), (7, 8, 20, 21), (22, 26, 30, 30)])

    def test_note_spans(self):
        line = "a^[note [x](y)] b[^1] `^[code]` ![c^[d]](e.png)"
        self.assertEqual(note_spans(line), [(1, 3, 14, 15), (17, 19, 20, 21)])
        self.assertEqual(note_definition("[^1]: The text"), ("1", "The text"))
        self.assertIsNone(note_definition("No [^1] definition"))

    LINE = 'Die [Seite](https://example.org "Titel"), <mailto:a@b.de> und www.gnome.org. ![Bild](b.png) [Datei](notes.md)'

    def at(self, word):
        return link_at(self.LINE, self.LINE.index(word))

    def test_markdown_link_anywhere_in_it(self):
        for word in ("[Seite", "Seite", "example", "Titel"):
            self.assertEqual(self.at(word), "https://example.org", word)

    def test_angle_and_bare_addresses(self):
        self.assertEqual(self.at("mailto"), "mailto:a@b.de")
        self.assertEqual(self.at("gnome"), "https://www.gnome.org")

    def test_trailing_punctuation_is_not_part_of_the_address(self):
        self.assertIsNone(link_at(self.LINE, self.LINE.index("org. ") + 3))

    def test_no_link(self):
        self.assertIsNone(self.at("Die"))
        self.assertIsNone(self.at("und"))

    def test_images_and_files_are_not_opened(self):
        self.assertIsNone(self.at("Bild"))
        self.assertIsNone(self.at("Datei"))

    def test_other_schemes_are_not_opened(self):
        self.assertIsNone(link_at("[x](javascript:alert(1))", 1))
        self.assertIsNone(link_at("[x](file:///etc/passwd)", 1))
