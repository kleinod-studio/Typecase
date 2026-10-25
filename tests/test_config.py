import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import config


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original = config.CONFIG_PATH
        config.CONFIG_PATH = Path(self._tmp.name) / "config.json"

    def tearDown(self):
        config.CONFIG_PATH = self._original
        self._tmp.cleanup()

    def test_defaults_without_file(self):
        self.assertEqual(config.settings(), config.SETTINGS_DEFAULTS)

    def test_valid_values_are_used(self):
        config.update(editor_font="Cantarell", editor_font_size=20, line_width=90, line_spacing="relaxed", color_scheme="dark", editor_theme="typecase-paper")
        self.assertEqual(
            config.settings(),
            {"editor_font": "Cantarell", "editor_font_size": 20, "line_width": 90, "line_spacing": "relaxed", "color_scheme": "dark", "editor_theme": "typecase-paper"},
        )

    def test_invalid_values_fall_back(self):
        config.CONFIG_PATH.write_text(json.dumps({
            "editor_font": "  ", "editor_font_size": 400, "line_width": "breit",
            "line_spacing": "riesig", "color_scheme": True, "editor_theme": 7,
        }))
        self.assertEqual(config.settings(), config.SETTINGS_DEFAULTS)

    def test_bool_is_not_a_number(self):
        config.update(editor_font_size=True)
        self.assertEqual(config.settings()["editor_font_size"], 15)

    def test_broken_file(self):
        config.CONFIG_PATH.write_text("{kaputt")
        self.assertEqual(config.settings(), config.SETTINGS_DEFAULTS)


    def test_focus_profile_is_separate(self):
        config.update_profile("focus", {"editor_font_size": 24, "color_scheme": "dark"})
        self.assertEqual(config.settings("editor")["editor_font_size"], 15)
        self.assertEqual(config.settings("focus")["editor_font_size"], 24)

    def test_focus_uses_editor_settings_by_default(self):
        config.update_profile("focus", {"color_scheme": "dark"})
        self.assertTrue(config.focus_uses_editor_settings())
        self.assertEqual(config.effective_settings(focus_mode=True)["color_scheme"], "system")
        config.update(focus_same_as_editor=False)
        self.assertEqual(config.effective_settings(focus_mode=True)["color_scheme"], "dark")
        self.assertEqual(config.effective_settings(focus_mode=False)["color_scheme"], "system")


    def test_sheet_defaults(self):
        defaults = config.sheet_defaults()
        self.assertIsNone(defaults["author"])
        self.assertIn(defaults["lang"], config.LANGUAGES)
        config.update(default_author="  Sascha  ", default_lang="en-GB")
        self.assertEqual(config.sheet_defaults(), {"author": "Sascha", "lang": "en-GB"})
        config.update(default_author="", default_lang=42)
        self.assertIsNone(config.sheet_defaults()["author"])
        self.assertIn(config.sheet_defaults()["lang"], config.LANGUAGES)


if __name__ == "__main__":
    unittest.main()
