import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import comments, export, export_templates, textstats


class FindTest(unittest.TestCase):
    def test_marked_passage_with_comment(self):
        text = "The storm {==cracked the lamp==}{>>too dramatic?<<} last night."
        [comment] = comments.find(text)
        self.assertEqual(text[comment.start : comment.end], "{==cracked the lamp==}{>>too dramatic?<<}")
        self.assertEqual(text[slice(*comment.marked)], "cracked the lamp")
        self.assertEqual(comment.note_text(text), "too dramatic?")

    def test_comment_alone(self):
        text = "One.{>> check this <<} Two."
        [comment] = comments.find(text)
        self.assertIsNone(comment.marked)
        self.assertEqual(comment.note_text(text), "check this")

    def test_marked_passage_without_comment(self):
        [comment] = comments.find("A {==marked==} word.")
        self.assertIsNone(comment.note)
        self.assertEqual(comment.note_text("A {==marked==} word."), "")

    def test_space_between_passage_and_comment(self):
        text = "{==this==} {>>that<<}"
        [comment] = comments.find(text)
        self.assertEqual((comment.start, comment.end), (0, len(text)))

    def test_several_comments_in_order(self):
        text = "{>>one<<} text {==two==}{>>2<<} more {>>three<<}"
        self.assertEqual([c.note_text(text) for c in comments.find(text)], ["one", "2", "three"])

    def test_within_one_paragraph(self):
        self.assertEqual(len(comments.find("{>>first line\nsecond line<<}")), 1)
        self.assertEqual(comments.find("{>>first paragraph\n\nsecond<<}"), [])

    def test_code_is_left_alone(self):
        self.assertEqual(comments.find("Write `{>>this<<}` for a comment."), [])
        self.assertEqual(comments.find("```\n{>>in a code block<<}\n```\n"), [])
        self.assertEqual(len(comments.find("```\ncode\n```\n{>>after it<<}")), 1)

    def test_unfinished_markup_is_no_comment(self):
        self.assertEqual(comments.find("{>>never closed"), [])
        self.assertEqual(comments.find("{==never closed"), [])


class StripTest(unittest.TestCase):
    def test_marked_passage_stays_as_text(self):
        self.assertEqual(
            comments.strip("The storm {==cracked **the** lamp==}{>>too dramatic?<<} last night."),
            "The storm cracked **the** lamp last night.",
        )

    def test_comment_alone_disappears(self):
        self.assertEqual(comments.strip("One.{>>check<<} Two."), "One. Two.")

    def test_line_of_only_comments_disappears(self):
        self.assertEqual(comments.strip("First line\n{>>note<<} {>>more<<}\nSecond line\n"), "First line\nSecond line\n")
        self.assertEqual(comments.strip("Paragraph.\n\n{>>note\nover two lines<<}\n\nNext.\n"), "Paragraph.\n\n\nNext.\n")
        self.assertEqual(comments.strip("Text\n{>>last<<}"), "Text\n")

    def test_line_with_a_marked_passage_stays(self):
        self.assertEqual(comments.strip("{==Kept==}{>>why<<}\nNext"), "Kept\nNext")

    def test_text_without_comments_is_unchanged(self):
        text = "Plain text with {braces} and `{>>code<<}`.\n"
        self.assertEqual(comments.strip(text), text)

    def test_comments_do_not_count(self):
        text = "Two words {==marked here==}{>>not counted at all<<}\n{>>gone<<}"
        self.assertEqual(textstats.count_words(text), 4)
        self.assertEqual(textstats.count_characters(text), len("Two words marked here"))

    def test_prepare_markdown_leaves_comments_out(self):
        self.assertEqual(export.prepare_markdown("<u>a</u> {==b==}{>>c<<}"), "[a]{.underline} b")


class EditTest(unittest.TestCase):
    def test_add_on_a_selection(self):
        text = "The storm cracked it."
        new, a, b = comments.add(text, 10, 17)
        self.assertEqual(new, "The storm {==cracked==}{>><<} it.")
        self.assertEqual((a, b), (new.index("<<}"),) * 2)

    def test_add_leaves_out_spaces_at_the_edges(self):
        new, _a, _b = comments.add("One  two  three", 3, 10)
        self.assertEqual(new, "One  {==two==}{>><<}  three")

    def test_add_without_a_selection(self):
        new, a, _b = comments.add("Hello world", 5, 5)
        self.assertEqual(new, "Hello{>><<} world")
        self.assertEqual(new[a - 3 : a], "{>>")

    def test_add_over_paragraphs_stands_alone(self):
        text = "First.\n\nSecond."
        new, _a, _b = comments.add(text, 0, len(text))
        self.assertEqual(new, "First.\n\nSecond.{>><<}")

    def test_add_in_a_comment_goes_into_it(self):
        text = "A {==b==}{>>note<<} c"
        self.assertEqual(comments.add(text, 5, 5), (text, text.index("<<}"), text.index("<<}")))
        new, a, _b = comments.add("A {==b==} c", 5, 5)
        self.assertEqual(new, "A {==b==}{>><<} c")
        self.assertEqual(a, new.index("<<}"))

    def test_add_then_find(self):
        new, _a, _b = comments.add("Some words here.", 5, 10)
        [comment] = comments.find(new)
        self.assertEqual(new[slice(*comment.marked)], "words")

    def test_remove_keeps_the_passage(self):
        self.assertEqual(comments.remove("A {==b==}{>>c<<} d", 10), ("A b d", 3, 3))

    def test_remove_a_comment_alone(self):
        self.assertEqual(comments.remove("One {>>x<<} two", 7)[0], "One two")
        self.assertEqual(comments.remove("Line\n{>>x<<}\nNext", 7)[0], "Line\nNext")
        self.assertIsNone(comments.remove("No comment here", 3))

    def test_neighbour(self):
        text = "{>>a<<} x {>>b<<}"
        self.assertEqual(comments.neighbour(text, 0), text.index("a<<") + 1)
        self.assertEqual(comments.neighbour(text, 4), text.index("b<<") + 1)
        self.assertEqual(comments.neighbour(text, 15), text.index("a<<") + 1, "around the end")
        self.assertEqual(comments.neighbour(text, 14, forward=False), text.index("a<<") + 1)
        self.assertEqual(comments.neighbour(text, 0, forward=False), text.index("b<<") + 1, "around the start")
        self.assertIsNone(comments.neighbour("none", 0))


class WordTest(unittest.TestCase):
    def test_comments_become_comment_spans(self):
        self.assertEqual(
            comments.for_word("The {==storm==}{>>too [loud]?<<} came.{>>check<<}", "Ada"),
            'The [too \\[loud\\]?]{.comment-start id="0" author="Ada"}storm[]{.comment-end id="0"} came.'
            '[check]{.comment-start id="1" author="Ada"}[]{.comment-end id="1"}',
        )

    def test_prepare_markdown_keeps_comments_only_when_asked(self):
        self.assertIn(".comment-start", export.prepare_markdown("A {>>b<<}", comments_by="Ada"))
        self.assertNotIn("comment", export.prepare_markdown("A {>>b<<}"))


@unittest.skipIf(export.pandoc_path() is None, "Pandoc is not installed")
class ExportTest(unittest.TestCase):
    def test_comments_in_the_margin_of_a_word_document(self):
        template = export_templates.read_folder(export_templates.BUILTIN_DIR / "text", builtin=True)
        text = "The storm {==cracked the lamp==}{>>too *dramatic*?<<} last night.{>>check [this]<<}\n"
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "out.docx"
            subprocess.run(
                export.pandoc_args("docx", template, output, "Probe"),
                input=export.prepare_markdown(text, comments_by="Ada Morrow"), text=True, check=True, cwd=folder,
            )
            import zipfile

            with zipfile.ZipFile(output) as docx:
                notes = docx.read("word/comments.xml").decode("utf-8")
                body = docx.read("word/document.xml").decode("utf-8")
        self.assertIn('w:author="Ada Morrow"', notes)
        self.assertIn("dramatic", notes)
        self.assertIn("[this]", notes)
        self.assertEqual(body.count("<w:commentRangeStart"), 2)
        self.assertIn("cracked the lamp", body)
        self.assertNotIn("{==", body)

    def test_comments_never_reach_the_export(self):
        template = export_templates.read_folder(export_templates.BUILTIN_DIR / "text", builtin=True)
        text = "# Chapter\n\nThe storm {==cracked the lamp==}{>>SECRET-NOTE<<} last night.\n{>>SECRET-TOO<<}\nEnd.\n"
        with tempfile.TemporaryDirectory() as folder:
            for fmt in ("html", "docx"):
                output = Path(folder) / f"out.{fmt}"
                subprocess.run(
                    export.pandoc_args(fmt, template, output, "Probe"),
                    input=export.prepare_markdown(text), text=True, check=True, cwd=folder,
                )
                if fmt == "html":
                    content = output.read_text(encoding="utf-8")
                else:
                    import zipfile

                    content = zipfile.ZipFile(output).read("word/document.xml").decode("utf-8")
                self.assertNotIn("SECRET", content)
                self.assertNotIn("{==", content)
                self.assertIn("cracked the lamp", content)


if __name__ == "__main__":
    unittest.main()
