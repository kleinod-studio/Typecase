import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gi  # noqa: E402

gi.require_version("Gdk", "4.0")
gi.require_version("GtkSource", "5")

from typecase import themes  # noqa: E402

SCHEME = """<?xml version="1.0" encoding="UTF-8"?>
<style-scheme id="{id}" name="{name}" version="1.0">
  {metadata}
  <style name="text" foreground="{fg}" background="{bg}"/>
</style-scheme>
"""


def scheme_file(folder: Path, scheme_id: str, name: str, dark: bool = False, metadata: str = "") -> Path:
    path = folder / f"{scheme_id}.xml"
    fg, bg = ("#eeeeee", "#111111") if dark else ("#222222", "#fafafa")
    path.write_text(SCHEME.format(id=scheme_id, name=name, metadata=metadata, fg=fg, bg=bg))
    return path


class ThemesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._original = themes.USER_DIR
        themes.USER_DIR = self.root / "themes"
        themes._manager = None

    def tearDown(self):
        themes.USER_DIR = self._original
        themes._manager = None
        self._tmp.cleanup()

    def test_builtin_themes_have_both_variants(self):
        available = themes.available()
        self.assertEqual([t.id for t in available], list(themes.BUILTIN))
        for theme in available:
            light, dark = themes.scheme(theme.id, False), themes.scheme(theme.id, True)
            self.assertEqual((light.get_id(), dark.get_id()), (theme.id, theme.id + "-dark"))
            self.assertFalse(themes.palette(light)["dark"])
            self.assertTrue(themes.palette(dark)["dark"])

    def test_unknown_theme_falls_back_to_standard(self):
        self.assertEqual(themes.scheme("gibt-es-nicht", True).get_id(), "typecase-standard-dark")

    def test_palette_from_typecase_styles_and_fallbacks(self):
        paper = themes.palette(themes.scheme("typecase-paper", False))
        self.assertEqual(paper["link"].to_string(), "rgb(156,91,46)")
        self.assertIsNotNone(paper["heading"])
        standard = themes.palette(themes.scheme("typecase-standard", False))
        self.assertIsNone(standard["heading"], "the standard theme keeps headings in the text color")
        # A foreign scheme without typecase:* styles: dimmed syntax derived from its text color.
        source = scheme_file(self.root, "fremd", "Fremd")
        themes.install(source)
        foreign = themes.palette(themes.scheme("fremd", False))
        self.assertAlmostEqual(foreign["syntax"].alpha, 0.4, places=3)
        self.assertEqual(foreign["text"].to_string(), "rgb(34,34,34)")

    def test_imported_pair_and_single(self):
        outside = self.root / "outside"
        outside.mkdir()
        themes.install(scheme_file(outside, "nacht", "Nacht", metadata='<metadata><property name="variant">light</property></metadata>'))
        themes.install(scheme_file(outside, "nacht-dark", "Nacht Dunkel", dark=True))
        themes.install(scheme_file(outside, "einzeln", "Einzeln"))
        imported = [t for t in themes.available() if not t.builtin]
        self.assertEqual([(t.name, t.light, t.dark) for t in imported], [("Einzeln", "einzeln", "einzeln"), ("Nacht", "nacht", "nacht-dark")])
        self.assertEqual(themes.scheme("nacht", True).get_id(), "nacht-dark")
        self.assertEqual(len(imported[1].files), 2)

    def test_saved_builtin_theme_imports_next_to_the_original(self):
        folder = self.root / "saved"
        folder.mkdir()
        files = themes.save_builtin("typecase-paper", folder, "Paper (custom)")
        self.assertEqual([p.name for p in files], ["Paper (custom).xml", "Paper (custom) (dark).xml"])
        self.assertIn("Markdown marks", files[0].read_text())
        again = themes.save_builtin("typecase-paper", folder, "Paper (custom)")
        self.assertEqual(again[0].name, "Paper (custom) 2.xml", "existing files are never overwritten")
        for path in files:
            themes.install(path)
        imported = [t for t in themes.available() if not t.builtin]
        self.assertEqual([(t.name, t.light, t.dark) for t in imported], [("Paper (custom)", "paper-custom", "paper-custom-dark")])
        original = themes.palette(themes.scheme("typecase-paper", True))
        copy = themes.palette(themes.scheme("paper-custom", True))
        self.assertEqual({k: str(v) for k, v in copy.items()}, {k: str(v) for k, v in original.items()}, "the copy looks exactly like the original")
        # Standard inherits its text colors from Adwaita; the saved file spells them out.
        standard = themes.save_builtin("typecase-standard", folder, "Mine")
        adwaita = themes.scheme("typecase-standard", False).get_style("text")
        self.assertIn(f'<style name="text" foreground="{adwaita.props.foreground}" background="{adwaita.props.background}"/>', standard[0].read_text())

    def test_invalid_files_are_refused(self):
        broken = self.root / "kaputt.xml"
        broken.write_text("<style-scheme")
        with self.assertRaises(themes.ThemeError):
            themes.install(broken)
        other = self.root / "anders.xml"
        other.write_text('<?xml version="1.0"?><language id="x" name="X"/>')
        with self.assertRaises(themes.ThemeError):
            themes.install(other)
        with self.assertRaises(themes.ThemeError):
            themes.install(scheme_file(self.root, "typecase-paper", "Fake"))
        self.assertFalse(any(themes.USER_DIR.glob("*.xml")) if themes.USER_DIR.exists() else False)


if __name__ == "__main__":
    unittest.main()
