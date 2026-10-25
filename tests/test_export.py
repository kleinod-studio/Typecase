import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import export, export_templates


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.template = next(t for t in export_templates.available(None) if t.id == "text")

    def test_builtin_text_template(self):
        self.assertTrue(self.template.html.is_file() and self.template.css.is_file())
        self.assertIn("$body$", self.template.html.read_text(encoding="utf-8"))

    def test_underline_becomes_pandoc_span(self):
        self.assertEqual(export.prepare_markdown("eine <u>Höhle</u> und <u>noch</u>"), "eine [Höhle]{.underline} und [noch]{.underline}")
        self.assertEqual(export.prepare_markdown("ohne"), "ohne")

    def test_docx_args(self):
        args = export.pandoc_args("docx", self.template, Path("/x/out.docx"), "Blatt")
        self.assertEqual(args[args.index("--to") + 1], "docx")
        self.assertIn(export.INPUT_FORMAT, args)
        self.assertNotIn("--template", args)

    def test_html_and_pdf_args(self):
        html = export.pandoc_args("html", self.template, Path("/x/out.html"), "Blatt", Path("/t/style.html"))
        self.assertIn("--standalone", html)
        self.assertIn(str(self.template.html), html)
        self.assertIn("pagetitle=Blatt", html)
        self.assertIn("/t/style.html", html)
        self.assertNotIn("pdf", html)
        pdf = export.pandoc_args("pdf", self.template, Path("/x/out.html"), None)
        self.assertEqual(pdf[pdf.index("--to") + 1], "html5")
        self.assertIn("pdf", pdf)
        self.assertFalse(any(a.startswith("pagetitle=") for a in pdf), "no fallback title when the front matter has a title")

    def test_defaults_only_when_given(self):
        args = export.pandoc_args("docx", self.template, Path("/x/o.docx"), None, defaults={"author": "Anna", "lang": None})
        self.assertIn("author=Anna", args)
        self.assertFalse(any(a.startswith("lang=") for a in args))

    def test_export_date(self):
        import datetime

        day = datetime.date(2026, 10, 24)
        self.assertEqual(export.export_date(day, "C.UTF-8", "de_DE"), "24.10.2026")
        self.assertEqual(export.export_date(day, "C.UTF-8", "en_US.UTF-8"), "10/24/2026")
        self.assertEqual(export.export_date(day, "C.UTF-8", "en_GB"), "24/10/2026")
        self.assertEqual(export.export_date(day, "C", "fr_FR"), "2026-10-24")

    def test_combine_sheets(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            a, b, empty = Path(tmp) / "a.md", Path(tmp) / "b.md", Path(tmp) / "c.md"
            a.write_text("---\ntitle: A\n---\n# One\n\nText.\n\n", encoding="utf-8")
            b.write_text("# Two\nMore.", encoding="utf-8")
            empty.write_text("---\ngoal: 5\n---\n", encoding="utf-8")
            combined = export.combine_sheets([a, empty, b, Path(tmp) / "missing.md"])
        self.assertEqual(combined, "# One\n\nText.\n\n# Two\nMore.\n")

    def test_combine_sheets_page_breaks(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Part 1").mkdir()
            (root / "Part 2").mkdir()
            sheets = [root / "Preface.md", root / "Part 1" / "a.md", root / "Part 1" / "b.md", root / "Part 2" / "c.md"]
            for sheet, content in zip(sheets, ["P", "A", "B", "C"]):
                sheet.write_text(content, encoding="utf-8")
            self.assertTrue(export.has_subgroups(sheets))
            self.assertFalse(export.has_subgroups(sheets[1:3]))
            self.assertEqual(export.combine_sheets(sheets), "P\n\nA\n\nB\n\nC\n")
            breaks = export.combine_sheets(sheets, page_breaks=True)
        brk = export.PAGE_BREAK
        # A new page where the folder changes, none before the first sheet and none inside a subgroup.
        self.assertEqual(breaks, f"P\n\n{brk}\n\nA\n\nB\n\n{brk}\n\nC\n")

    def test_with_title(self):
        self.assertEqual(export.with_title("Text\n", "My Novel"), "---\ntitle: My Novel\n---\nText\n")
        self.assertEqual(export.with_title("Text\n", "  "), "Text\n")

    def test_style_header(self):
        header = export.style_header(self.template)
        self.assertTrue(header.startswith("<style>") and header.rstrip().endswith("</style>"))


if __name__ == "__main__":
    unittest.main()
