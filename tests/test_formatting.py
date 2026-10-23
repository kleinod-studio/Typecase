import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.formatting import BOLD, CODE, ITALIC, STRIKE, UNDERLINE, insert_code_block, insert_link, toggle_inline, toggle_lines


def apply(text, start, end, markers):
    new, a, b = toggle_inline(text, start, end, markers)
    return new, new[a:b]


class InlineTest(unittest.TestCase):
    def test_wrap_selection(self):
        self.assertEqual(apply("Ein Wort hier", 4, 8, BOLD), ("Ein **Wort** hier", "Wort"))
        self.assertEqual(apply("Ein Wort hier", 4, 8, ITALIC), ("Ein *Wort* hier", "Wort"))
        self.assertEqual(apply("Ein Wort hier", 4, 8, UNDERLINE), ("Ein <u>Wort</u> hier", "Wort"))
        self.assertEqual(apply("Ein Wort hier", 4, 8, STRIKE), ("Ein ~~Wort~~ hier", "Wort"))

    def test_unwrap_selection(self):
        self.assertEqual(apply("Ein **Wort** hier", 6, 10, BOLD), ("Ein Wort hier", "Wort"))
        self.assertEqual(apply("Ein <u>Wort</u> hier", 7, 11, UNDERLINE), ("Ein Wort hier", "Wort"))

    def test_unwrap_when_markers_are_selected(self):
        self.assertEqual(apply("Ein **Wort** hier", 4, 12, BOLD), ("Ein Wort hier", "Wort"))

    def test_italic_and_bold_are_not_confused(self):
        self.assertEqual(apply("**Wort**", 2, 6, ITALIC), ("***Wort***", "Wort"))
        self.assertEqual(apply("***Wort***", 3, 7, ITALIC), ("**Wort**", "Wort"))
        self.assertEqual(apply("***Wort***", 3, 7, BOLD), ("*Wort*", "Wort"))
        self.assertEqual(apply("*Wort*", 1, 5, BOLD), ("***Wort***", "Wort"))

    def test_word_under_cursor(self):
        self.assertEqual(apply("Ein Wort hier", 6, 6, BOLD), ("Ein **Wort** hier", "Wort"))
        self.assertEqual(apply("Ein **Wort** hier", 8, 8, BOLD), ("Ein Wort hier", "Wort"))

    def test_empty_place_inserts_markers(self):
        new, a, b = toggle_inline("Ein  hier", 4, 4, CODE)
        self.assertEqual((new, a, b), ("Ein `` hier", 5, 5))


class LinesTest(unittest.TestCase):
    def test_heading_set_change_remove(self):
        self.assertEqual(toggle_lines(["Titel"], 0, 0, "h2"), ["## Titel"])
        self.assertEqual(toggle_lines(["## Titel"], 0, 0, "h1"), ["# Titel"])
        self.assertEqual(toggle_lines(["## Titel"], 0, 0, "h2"), ["Titel"])
        self.assertEqual(toggle_lines(["### Titel"], 0, 0, "paragraph"), ["Titel"])

    def test_lists_and_quote(self):
        lines = ["Eins", "", "Zwei", "Drei"]
        self.assertEqual(toggle_lines(lines, 0, 3, "bullet"), ["- Eins", "", "- Zwei", "- Drei"])
        self.assertEqual(toggle_lines(lines, 0, 3, "numbered"), ["1. Eins", "", "2. Zwei", "3. Drei"])
        self.assertEqual(toggle_lines(["- Eins", "- Zwei"], 0, 1, "bullet"), ["Eins", "Zwei"])
        self.assertEqual(toggle_lines(["- Eins", "Zwei"], 0, 1, "quote"), ["> Eins", "> Zwei"])
        self.assertEqual(toggle_lines(["- Eins"], 0, 0, "numbered"), ["1. Eins"])

    def test_indent_is_kept(self):
        self.assertEqual(toggle_lines(["    - Unter"], 0, 0, "numbered"), ["    1. Unter"])


class InsertTest(unittest.TestCase):
    def test_link_from_selection(self):
        new, a, b = insert_link("Siehe hier mehr", 6, 10, "Text", "https://")
        self.assertEqual(new, "Siehe [hier](https://) mehr")
        self.assertEqual(new[a:b], "https://")

    def test_link_from_url_and_empty(self):
        new, a, b = insert_link("https://example.org", 0, 19, "Text", "https://")
        self.assertEqual((new, new[a:b]), ("[Text](https://example.org)", "Text"))
        new, a, b = insert_link("", 0, 0, "Text", "https://")
        self.assertEqual((new, new[a:b]), ("[Text](https://)", "Text"))

    def test_code_block(self):
        new, a, b = insert_code_block("x = 1\ny = 2", 0, 11)
        self.assertEqual((new, new[a:b]), ("```\nx = 1\ny = 2\n```", "x = 1\ny = 2"))
        new, a, b = insert_code_block("Text\n\nmehr", 5, 5)
        self.assertEqual((new, a), ("Text\n```\n\n```\nmehr", 9))


if __name__ == "__main__":
    unittest.main()
