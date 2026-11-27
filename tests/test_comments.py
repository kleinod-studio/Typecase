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


@unittest.skipIf(export.pandoc_path() is None, "Pandoc is not installed")
class ExportTest(unittest.TestCase):
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
