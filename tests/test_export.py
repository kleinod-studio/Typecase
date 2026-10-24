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
        self.assertFalse(any(a.startswith("pagetitle=") for a in pdf), "mit Titel im Dateikopf kein Ersatztitel")

    def test_defaults_only_when_given(self):
        args = export.pandoc_args("docx", self.template, Path("/x/o.docx"), None, defaults={"author": "Anna", "lang": None})
        self.assertIn("author=Anna", args)
        self.assertFalse(any(a.startswith("lang=") for a in args))

    def test_style_header(self):
        header = export.style_header(self.template)
        self.assertTrue(header.startswith("<style>") and header.rstrip().endswith("</style>"))


if __name__ == "__main__":
    unittest.main()
