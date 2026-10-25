import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.spelling import dictionary_for  # noqa: E402


class DictionaryTest(unittest.TestCase):
    def test_exact_variant_first(self):
        self.assertEqual(dictionary_for("de-DE", ["de_AT", "de_DE", "en_US"]), "de_DE")

    def test_other_variant_of_the_language(self):
        self.assertEqual(dictionary_for("de-CH", ["de_AT", "de_DE"]), "de_AT")
        self.assertEqual(dictionary_for("en-GB", ["en_US"]), "en_US")
        self.assertEqual(dictionary_for("de-DE", ["de"]), "de")

    def test_no_dictionary(self):
        self.assertIsNone(dictionary_for("fr-FR", ["de_DE"]))
        self.assertIsNone(dictionary_for("", ["de_DE"]))
        self.assertIsNone(dictionary_for(None, ["de_DE"]))


if __name__ == "__main__":
    unittest.main()
