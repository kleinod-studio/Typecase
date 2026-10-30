import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.markdown_style import fence_language, line_spans, list_text_start


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
