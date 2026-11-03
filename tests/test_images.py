import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import formatting, images, library, textstats  # noqa: E402
from typecase.markdown_style import line_spans, link_at  # noqa: E402


class ParsingTests(unittest.TestCase):
    def test_all_fields(self):
        line = 'Before ![A *caption*](<.attachments/Chapter 1/a b.png>){.center width=50% alt="Says \\"hi\\""} after'
        image = images.in_line(line)[0]
        self.assertEqual(image.address, ".attachments/Chapter 1/a b.png")
        self.assertEqual(image.caption, "A *caption*")
        self.assertEqual((image.align, image.width, image.alt), ("center", "50%", 'Says "hi"'))
        self.assertEqual(line[image.start : image.end], line[7:-6])

    def test_plain_image(self):
        image = images.in_line("![](photo.png)")[0]
        self.assertEqual((image.address, image.caption, image.width, image.align, image.alt), ("photo.png", "", "", "", ""))

    def test_percent_encoded_address(self):
        self.assertEqual(images.in_line("![](a%20b.png)")[0].address, "a b.png")

    def test_not_an_image(self):
        self.assertEqual(images.in_line("[link](a.png) and `![](code.png)`"), [])

    def test_code_blocks_are_skipped(self):
        found = images.in_text("![](a.png)\n```\n![](b.png)\n```\n![](c.png)")
        self.assertEqual([(line, image.address) for line, image in found], [(0, "a.png"), (4, "c.png")])

    def test_round_trip_keeps_everything(self):
        for line in (
            "![](a.png)",
            "![Caption](<a b.png>)",
            '![C \\[1\\]](a.png "Title"){.right width=25% alt="x" .other data-x=1}',
            "![](<50%25 (draft).png>)",
        ):
            self.assertEqual(images.to_markdown(images.in_line(line)[0]), line)

    def test_written_value_is_found_again(self):
        image = images.Image("a (b) <c> 5%.png", caption="Fig [1] \\ x", alt='A "b" \\ c', width="50%", align="center")
        again = images.in_line(images.to_markdown(image))[0]
        self.assertEqual((again.address, again.caption, again.alt, again.width, again.align), (image.address, image.caption, image.alt, "50%", "center"))


class AddressTests(unittest.TestCase):
    def test_retarget_only_the_old_folder(self):
        text = "![](<.attachments/Old/a b.png>) ![](other/a.png)\n```\n![](.attachments/Old/code.png)\n```\n![x](.attachments/Old/c.png){width=50%}"
        new = images.retarget(text, ".attachments/Old", ".attachments/New name")
        self.assertEqual(
            new,
            "![](<.attachments/New name/a b.png>) ![](other/a.png)\n```\n![](.attachments/Old/code.png)\n```\n![x](<.attachments/New name/c.png>){width=50%}",
        )

    def test_absolute_paths_leave_web_and_absolute_addresses(self):
        text = "![](<a b.png>) ![](https://example.org/a.png) ![](/abs/a.png)"
        self.assertEqual(
            images.with_absolute_paths(text, Path("/lib/Part")),
            "![](</lib/Part/a b.png>) ![](https://example.org/a.png) ![](/abs/a.png)",
        )

    def test_embedded_keeps_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "a.png").write_bytes(b"png")
            text = images.embedded("![x](a.png){width=50%} ![](missing.png)", Path(folder))
        self.assertEqual(text, "![x](data:image/png;base64,cG5n){width=50%} ![](missing.png)")

    def test_uses_file(self):
        self.assertTrue(images.uses_file("![](.attachments/S/a.png)", "a.png"))
        self.assertFalse(images.uses_file("![](.attachments/S/a.png)", "b.png"))


class PreviewSizeTests(unittest.TestCase):
    def test_natural_size_fits_the_column(self):
        self.assertEqual(images.preview_size(images.Image("a"), (200, 100), 600, 500), (0, 200, 100))
        self.assertEqual(images.preview_size(images.Image("a"), (1200, 600), 600, 500), (0, 600, 300))

    def test_percent_and_alignment(self):
        image = images.Image("a", width="50%", align="center")
        self.assertEqual(images.preview_size(image, (1000, 500), 600, 500), (150, 300, 150))
        image = images.Image("a", width="25%", align="right")
        self.assertEqual(images.preview_size(image, (1000, 500), 600, 500), (450, 150, 75))

    def test_tall_images_are_limited(self):
        self.assertEqual(images.preview_size(images.Image("a"), (500, 2000), 600, 400), (0, 100, 400))


class InsertBlockTests(unittest.TestCase):
    def test_on_an_empty_line_between_paragraphs(self):
        self.assertEqual(formatting.insert_block("a\n\n\n\nb", 3, "X")[0], "a\n\nX\n\nb")

    def test_below_a_line_of_text(self):
        new, cursor, _end = formatting.insert_block("first\nsecond", 2, "X")
        self.assertEqual(new, "first\n\nX\n\nsecond")
        self.assertEqual(new[:cursor], "first\n\nX")

    def test_empty_text(self):
        self.assertEqual(formatting.insert_block("", 0, "X")[0], "X")

    def test_end_of_text(self):
        self.assertEqual(formatting.insert_block("text", 4, "X")[0], "text\n\nX")


class EditorStylingTests(unittest.TestCase):
    def test_markup_is_dimmed_and_caption_stays_text(self):
        line = "![Caption](<a b.png>){width=50%}"
        spans = line_spans(line, False)
        self.assertIn((0, 2, "syntax"), spans)
        self.assertIn((9, len(line), "syntax"), spans)

    def test_no_link_to_open(self):
        self.assertIsNone(link_at("![x](https://example.org/a.png)", 3))

    def test_addresses_are_no_words(self):
        self.assertEqual(textstats.count_words("One ![two three](<.attachments/x y/z.png>){width=50%} four"), 4)
        self.assertEqual(textstats.count_characters("![ab](c.png)"), 2)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.sheet = self.folder / "Old.md"
        self.sheet.write_text("![](.attachments/Old/a.png)\n", encoding="utf-8")
        source = self.folder / "a.png"
        source.write_bytes(b"png")
        library.add_attachment(self.sheet, source)

    def test_rename_keeps_images_linked(self):
        target = library.rename(self.sheet, "New name")
        self.assertEqual(target.read_text(encoding="utf-8"), "![](<.attachments/New name/a.png>)\n")
        self.assertTrue((self.folder / ".attachments" / "New name" / "a.png").is_file())

    def test_duplicate_links_its_own_copy(self):
        copy = library.duplicate(self.sheet, "Copy")
        self.assertEqual(copy.read_text(encoding="utf-8"), "![](.attachments/Copy/a.png)\n")
        self.assertEqual(self.sheet.read_text(encoding="utf-8"), "![](.attachments/Old/a.png)\n")

    def test_move_changes_nothing_in_the_text(self):
        folder = self.folder / "Group"
        folder.mkdir()
        target = library.move(self.sheet, folder)
        self.assertEqual(target.read_text(encoding="utf-8"), "![](.attachments/Old/a.png)\n")
        self.assertTrue((folder / ".attachments" / "Old" / "a.png").is_file())


if __name__ == "__main__":
    unittest.main()
