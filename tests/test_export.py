import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import base64
import re
import shutil
import subprocess
import tempfile
import zipfile
from xml.etree import ElementTree

from typecase import export, export_templates, pdf_render, template_builder


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
        self.assertIn(str(export.FOOTNOTE_FILTER), pdf)
        self.assertTrue(export.FOOTNOTE_FILTER.is_file())
        self.assertNotIn(str(export.FOOTNOTE_FILTER), html, "web pages keep their notes at the end")
        self.assertNotIn(str(export.STRUCTURE_FILTER), pdf)
        both = export.pandoc_args("docx", self.template, Path("/x/o.docx"), None, toc_title="Inhalt", cover=True)
        self.assertIn(str(export.STRUCTURE_FILTER), both)
        self.assertIn("typecase-toc-title=Inhalt", both)
        self.assertIn("typecase-cover=true", both)

    def test_pdf_base_css_comes_before_the_template(self):
        header = export.style_header(self.template, pdf=True)
        self.assertLess(header.index("float: footnote"), header.index("font-family"))
        self.assertNotIn("float: footnote", export.style_header(self.template))

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

    def test_combine_sheets_parts(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Part 1").mkdir()
            (root / "Part 2" / "Scenes").mkdir(parents=True)
            sheets = [root / "Preface.md", root / "Part 1" / "a.md", root / "Part 1" / "b.md", root / "Part 2" / "Scenes" / "c.md"]
            for sheet, content in zip(sheets, ["# P", "# A\n## a", "B", "# C"]):
                sheet.write_text(content, encoding="utf-8")
            self.assertTrue(export.has_subgroups(sheets))
            self.assertFalse(export.has_subgroups(sheets[1:3]))
            self.assertEqual(export.combine_sheets(sheets), "# P\n\n# A\n## a\n\nB\n\n# C\n", "without the group: no parts")
            continuous = export.combine_sheets(sheets, root)
            title_pages = export.combine_sheets(sheets, root, "title-page")
            new_pages = export.combine_sheets(sheets, root, "new-page")
        # Each subgroup is a heading at its depth; its sheets' headings move below it
        self.assertEqual(
            continuous,
            "# P\n\n# Part 1 {.part}\n\n## A\n### a\n\nB\n\n# Part 2 {.part}\n\n## Scenes {.part}\n\n### C\n",
        )
        brk = export.DOCX_PAGE_BREAK
        self.assertEqual(new_pages.count(brk), 3, "a Word break before each part, none at the start")
        # Title pages: a break before and after, but never two in a row
        self.assertEqual(title_pages.count(brk), 5)
        self.assertNotIn(f"{brk}\n\n{brk}", title_pages)
        self.assertIn("# Part 1 {.part .title-page}", title_pages)

    def test_shift_headings(self):
        text = "# One\ntext\n```\n# code\n```\n###### Six"
        self.assertEqual(export.shift_headings(text, 1), "## One\ntext\n```\n# code\n```\n###### Six")
        self.assertEqual(export.shift_headings("#hashtag", 1), "#hashtag")

    def test_built_in_template_numbers_word_pages(self):
        with zipfile.ZipFile(self.template.reference_docx) as docx:
            self.assertIn(" PAGE ", docx.read("word/typecase-footer.xml").decode("utf-8"))
            self.assertIn("footerReference", docx.read("word/document.xml").decode("utf-8"))

    def test_title_page_setting(self):
        section = '<w:sectPr><w:footerReference r:id="x"/><w:pgSz/><w:docGrid/></w:sectPr>'
        marked = export._with_title_page("<a/>" + section)
        self.assertIn("<w:pgSz/><w:titlePg/><w:docGrid/>", marked)
        self.assertEqual(export._with_title_page(marked), marked)
        self.assertEqual(export._with_title_page("<w:sectPr/>"), "<w:sectPr/>")

    def test_with_title(self):
        self.assertEqual(export.with_title("Text\n", "My Novel"), "---\ntitle: My Novel\n---\nText\n")
        self.assertEqual(export.with_title("Text\n", "  "), "Text\n")

    def test_style_header(self):
        header = export.style_header(self.template)
        self.assertTrue(header.startswith("<style>") and header.rstrip().endswith("</style>"))


class TemplateBuilderTest(unittest.TestCase):
    def build(self, folder, **changes):
        settings = template_builder.replace(template_builder.Settings(name="Mein Buch"), **changes)
        return template_builder.save(settings, Path(folder))

    def test_saved_template_can_be_used_and_reopened(self):
        with tempfile.TemporaryDirectory() as folder:
            template = self.build(folder, paper="a5", margin_right=40, body_font="Caladea")
            self.assertEqual((template.id, template.title), ("mein-buch", "Mein Buch"))
            self.assertEqual((template.pdf_paper, template.pdf_margins_mm["right"]), ("iso_a5", 40))
            self.assertIn('"Caladea", serif', template.css.read_text(encoding="utf-8"))
            self.assertIn("$body$", template.html.read_text(encoding="utf-8"))
            self.assertEqual(template_builder.settings_of(template).body_font, "Caladea")
            self.assertEqual([p.name for p in Path(folder).iterdir()], ["mein-buch"], "no leftovers")

    def test_a_second_template_never_replaces_the_first(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = self.build(folder), self.build(folder)
            self.assertEqual((first.id, second.id), ("mein-buch", "mein-buch-2"))

    def test_built_in_names_stay_reserved(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(template_builder.new_id("Text", Path(folder)), "text-2")

    def test_editing_replaces_the_template(self):
        with tempfile.TemporaryDirectory() as folder:
            template = self.build(folder)
            settings = template_builder.replace(template_builder.settings_of(template), body_size=14)
            changed = template_builder.save(settings, Path(folder), template)
            self.assertEqual(changed.id, template.id)
            self.assertIn("font-size: 14pt", changed.css.read_text(encoding="utf-8"))
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_word_styles_follow_the_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            template = self.build(folder, paper="a5", body_font="Carlito", chapters_on_new_page=True, page_numbers="right")
            self.assertTrue(export.heading_one_breaks_page(template))
            with zipfile.ZipFile(template.reference_docx) as docx:
                styles, document = docx.read("word/styles.xml").decode(), docx.read("word/document.xml").decode()
                ElementTree.fromstring(styles)
                ElementTree.fromstring(document)
                self.assertIn('w:val="right"', docx.read("word/typecase-footer.xml").decode())
            self.assertIn("Carlito", styles)
            self.assertIn('w:w="8391"', document)
            plain = self.build(folder, page_numbers="none")
            self.assertFalse(export.heading_one_breaks_page(plain))
            with zipfile.ZipFile(plain.reference_docx) as docx:
                self.assertNotIn("word/typecase-footer.xml", docx.namelist())

    def test_every_preset_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            for key, (label, settings) in template_builder.presets().items():
                self.assertTrue(label)
                template_builder.save(template_builder.replace(settings, name=key), Path(folder))
            self.assertEqual(len(list(Path(folder).iterdir())), len(template_builder.presets()))

    def test_stored_settings_are_checked(self):
        template = export_templates.Template("x", Path("/x"), False, {"assistant": {"paper": "tiny", "body_font": 3, "body_size": "big", "margin_top": 10, "justify": True}})
        settings = template_builder.settings_of(template)
        self.assertEqual((settings.paper, settings.body_font, settings.body_size), ("a4", "Liberation Serif", 12))
        self.assertEqual((settings.margin_top, settings.justify), (10, True))
        self.assertIsNone(template_builder.settings_of(export_templates.Template("y", Path("/y"), False, {})))

    def test_chapters_on_new_page_with_parts(self):
        css = template_builder.stylesheet(template_builder.Settings(chapters_on_new_page=True))
        for rule in ("main h1 { break-before: page; }", "main > h1:first-child { break-before: auto; }", "main h1.part ~ h2 { break-before: page; }"):
            self.assertIn(rule, css)
        self.assertNotIn("break-before", template_builder.stylesheet(template_builder.Settings()))

    def test_no_second_word_break_before_a_part(self):
        text = f"V\n\n{export.DOCX_PAGE_BREAK}\n\n# Teil {{.part}}\n\n{export.DOCX_PAGE_BREAK}\n\n## K\n"
        self.assertEqual(export.drop_word_breaks_before_parts(text), f"V\n\n# Teil {{.part}}\n\n{export.DOCX_PAGE_BREAK}\n\n## K\n")


@unittest.skipUnless(shutil.which("pandoc"), "Pandoc is missing")
class StructureFilterTest(unittest.TestCase):
    TEXT = "---\ntitle: Buch\nauthor: Anna\n---\n## Eins\n\n### Unter\n\n#### Tief\n\nText.\n"

    def run_pandoc(self, fmt: str, **options) -> str:
        args = ["pandoc", "--from", export.INPUT_FORMAT, "--to", fmt, "--lua-filter", str(export.STRUCTURE_FILTER)]
        for key, value in options.items():
            args += ["--metadata", f"{key}={value}"]
        if fmt == "docx":
            with tempfile.TemporaryDirectory() as folder:
                out = Path(folder) / "o.docx"
                subprocess.run(args + ["-o", str(out)], input=self.TEXT, text=True, check=True)
                with zipfile.ZipFile(out) as docx:
                    return docx.read("word/document.xml").decode("utf-8")
        return subprocess.run(args, input=self.TEXT, text=True, check=True, capture_output=True).stdout

    def test_contents_count_levels_from_the_top_heading(self):
        html = self.run_pandoc("html5", **{"typecase-toc": 2, "typecase-toc-title": "Inhalt"})
        self.assertIn('<div class="toc-title">\nInhalt', html)
        self.assertIn('href="#unter"', html)
        self.assertNotIn('href="#tief"', html)
        self.assertIn('TOC \\o "2-3"', self.run_pandoc("docx", **{"typecase-toc": 2, "typecase-toc-title": "Inhalt"}))

    def test_word_contents_show_their_entries_as_links(self):
        self.TEXT = "# Eins 100% & mehr^[Note]\n\nText.\n\n## Unter\n\n# " + "Sehr lang " * 6 + "\n\n# 2. Kapitel\n"
        xml = self.run_pandoc("docx", **{"typecase-toc": 2, "typecase-toc-title": "Inhalt"})
        ElementTree.fromstring(xml)  # well-formed, whatever the headings contain
        toc = xml[xml.index("<w:sdt>"):xml.index("</w:sdt>")]
        self.assertIn("Eins 100% &amp; mehr", toc)
        self.assertNotIn("Note", toc)
        self.assertIn('w:left="280"', toc)
        self.assertEqual(toc.count('w:fldCharType="begin"'), 1)
        self.assertEqual(toc.count('w:fldCharType="end"'), 1)
        anchors = re.findall(r'w:anchor="([^"]+)"', toc)
        bookmarks = re.findall(r'w:name="([^"]+)"', xml)
        self.assertEqual(len(anchors), 4)
        for anchor in anchors:
            self.assertIn(anchor, bookmarks, "every entry leads to its heading, also long and numbered ones")

    def test_cover_takes_over_the_title(self):
        html = self.run_pandoc("html5", **{"typecase-cover": "true"})
        self.assertIn('<div class="cover">', html)
        self.assertIn('<div class="title">', html)
        self.assertIn('<div class="author">', html)
        docx = self.run_pandoc("docx", **{"typecase-cover": "true"})
        self.assertEqual(docx.count('w:val="Title"'), 1, "the title appears once, on the cover")
        self.assertIn('w:type="page"', docx)


_ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


@unittest.skipUnless(shutil.which("pandoc"), "Pandoc is missing")
class ImageExportTest(unittest.TestCase):
    def _export(self, fmt, text, work):
        template = next(t for t in export_templates.available(None) if t.id == "text")
        (work / "a.png").write_bytes(base64.b64decode(_ONE_PIXEL_PNG))
        output = work / ("out.docx" if fmt == "docx" else "out.html")
        subprocess.run(export.pandoc_args(fmt, template, output, "Probe"), input=text, text=True, check=True, cwd=work)
        return output

    def test_html_alignment_caption_and_alt_text(self):
        with tempfile.TemporaryDirectory() as folder:
            html = self._export("html", '![Caption](a.png){.right width=50% alt="Described"}\n\n![](a.png){.center alt="Only alt"}\n', Path(folder)).read_text(encoding="utf-8")
        self.assertIn('<figure class="image-right">', html)
        self.assertIn("<figcaption>Caption</figcaption>", html)
        self.assertIn('alt="Described"', html)
        self.assertIn('<div class="image-center">', html)
        self.assertEqual(html.count("<figcaption"), 1, "alternative text alone gives no caption")

    def test_word_alignment_is_a_paragraph_style(self):
        with tempfile.TemporaryDirectory() as folder:
            docx = self._export("docx", '![Caption](a.png){.right alt="Described"}\n', Path(folder))
            export.style_aligned_images(docx)
            with zipfile.ZipFile(docx) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
                styles = archive.read("word/styles.xml").decode("utf-8")
        self.assertIn('w:val="TypecaseImageright"', document)
        self.assertIn('w:val="TypecaseCaptionright"', document)
        self.assertIn('descr="Described"', document)
        self.assertIn('<w:keepNext/><w:jc w:val="right"/>', styles)
        self.assertIn('<w:basedOn w:val="ImageCaption" />', styles)

    def test_a_template_keeps_its_own_style(self):
        xml = '<w:style w:styleId="X"><w:name w:val="Typecase Image left" /><w:pPr><w:jc w:val="both"/></w:pPr></w:style>'
        self.assertEqual(export._with_image_alignment(xml), xml)

    def test_combined_sheets_keep_their_images(self):
        with tempfile.TemporaryDirectory() as folder:
            group = Path(folder)
            (group / "Part").mkdir()
            sheet = group / "Part" / "Chapter.md"
            sheet.write_text("![](<a b.png>)\n", encoding="utf-8")
            text = export.combine_sheets([sheet], group)
            self.assertIn(f"![](<{group / 'Part' / 'a b.png'}>)", text)


class PdfRenderTest(unittest.TestCase):
    def test_page_css(self):
        css = pdf_render.page_css(210, 297, {"top": 25, "right": 50, "bottom": 20, "left": 30})
        self.assertEqual(css, "@page { size: 210mm 297mm; margin: 25mm 50mm 20mm 30mm; }")

    @unittest.skipUnless(pdf_render.available(), "WeasyPrint is not installed")
    def test_network_is_never_used(self):
        with self.assertRaises(ValueError):
            pdf_render._local_only().fetch("https://example.org/image.png")

    @unittest.skipUnless(pdf_render.available() and shutil.which("pandoc"), "WeasyPrint or Pandoc is missing")
    def test_images_reach_the_pdf(self):
        template = next(t for t in export_templates.available(None) if t.id == "text")
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "pictures").mkdir()
            (work / "pictures" / "a b.png").write_bytes(base64.b64decode(_ONE_PIXEL_PNG))
            (work / "style.html").write_text(export.style_header(template, pdf=True), encoding="utf-8")
            html = work / "doc.html"
            args = export.pandoc_args("pdf", template, html, "Probe", work / "style.html")
            subprocess.run(args, input="![Caption](<pictures/a b.png>){.center width=50%}\n", text=True, check=True, cwd=work)
            margins = dict.fromkeys(("top", "right", "bottom", "left"), 25)
            pdf_render.render(html, work, work / "doc.pdf", pdf_render.page_css(210, 297, margins))
            self.assertIn(b"/Subtype /Image", (work / "doc.pdf").read_bytes())

    @unittest.skipUnless(pdf_render.available() and shutil.which("pandoc"), "WeasyPrint or Pandoc is missing")
    def test_footnotes_end_up_on_their_page(self):
        import weasyprint

        template = next(t for t in export_templates.available(None) if t.id == "text")
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "style.html").write_text(export.style_header(template, pdf=True), encoding="utf-8")
            html = work / "doc.html"
            text = "Erste Seite.^[Note eins]\n\n" + "\n\n".join(["Fülltext. " * 60] * 8) + "\n\nLetzte.^[Note zwei]\n"
            args = export.pandoc_args("pdf", template, html, "Probe", work / "style.html")
            subprocess.run(args, input=text, text=True, check=True)
            margins = dict.fromkeys(("top", "right", "bottom", "left"), 25)
            page = weasyprint.CSS(string=pdf_render.page_css(210, 297, margins))
            document = weasyprint.HTML(filename=str(html)).render(stylesheets=[page])
            pages = ["".join(box.text for box in _texts(page._page_box)) for page in document.pages]
        self.assertGreater(len(pages), 1)
        self.assertIn("Note eins", pages[0])
        self.assertIn("Note zwei", pages[-1])
        self.assertNotIn("Note zwei", pages[0])


def _texts(box):
    if hasattr(box, "text"):
        yield box
    for child in getattr(box, "children", []):
        yield from _texts(child)


if __name__ == "__main__":
    unittest.main()
