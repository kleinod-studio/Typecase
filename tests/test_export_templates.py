import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import export
from typecase.export_templates import EXTENSION, TemplateError, available, install, localized, pack, peek

HTML = "<html><body>$body$</body></html>"


def make_file(path: Path, files: dict, links: dict | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for name, target in (links or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, target)
    return path


class TemplatesTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._dir.name)
        self.user = self.tmp / "user"
        self._language = os.environ.get("LANGUAGE")
        os.environ["LANGUAGE"] = "de_DE"

    def tearDown(self):
        self._dir.cleanup()
        if self._language is None:
            os.environ.pop("LANGUAGE", None)
        else:
            os.environ["LANGUAGE"] = self._language

    def info(self, **extra):
        return json.dumps({"format": 1, "name": {"en": "Letter", "de": "Brief"}, **extra})

    def test_builtin_text(self):
        templates = available(self.user)
        self.assertEqual([t.id for t in templates], ["text"])
        self.assertTrue(templates[0].builtin and templates[0].title == "Text")

    def test_builtin_roundtrip_as_file(self):
        builtin = available(None)[0]
        file = self.tmp / ("Mein Text" + EXTENSION)
        pack(builtin, file)
        self.assertEqual(peek(file).id, "mein-text")
        imported = install(file, self.user)
        self.assertFalse(imported.builtin)
        self.assertEqual((imported.path / "style.css").read_text(), builtin.css.read_text())
        self.assertEqual([t.id for t in available(self.user)], ["text", "mein-text"])

    def test_pack_old_timestamps(self):
        folder = self.tmp / "alt"
        folder.mkdir()
        (folder / "template.json").write_text(self.info())
        (folder / "template.html").write_text(HTML)
        for file in folder.iterdir():
            os.utime(file, (0, 0))  # wie im Flatpak
        from typecase.export_templates import read_folder

        pack(read_folder(folder, builtin=True), self.tmp / ("alt" + EXTENSION))
        self.assertEqual(install(self.tmp / ("alt" + EXTENSION), self.user).title, "Brief")

    def test_builtin_names_are_reserved(self):
        pack(available(None)[0], self.tmp / ("text" + EXTENSION))
        self.assertEqual(install(self.tmp / ("text" + EXTENSION), self.user).id, "text-custom")

    def test_install_and_localized_name(self):
        file = make_file(self.tmp / ("Brief" + EXTENSION), {"template.json": self.info(), "template.html": HTML, "style.css": "p{}"})
        template = install(file, self.user)
        self.assertEqual((template.id, template.title), ("brief", "Brief"))
        self.assertIsNone(template.reference_docx)

    def test_replace_keeps_old_until_new_is_valid(self):
        good = make_file(self.tmp / ("brief" + EXTENSION), {"template.json": self.info(), "template.html": HTML})
        install(good, self.user)
        bad = make_file(self.tmp / ("brief2" + EXTENSION), {"template.json": self.info(), "template.html": "kein Platzhalter"})
        with self.assertRaises(TemplateError):
            install(bad, self.user)
        newer = make_file(self.tmp / ("brief" + EXTENSION), {"template.json": self.info(description="neu"), "template.html": HTML})
        self.assertEqual(install(newer, self.user).description, "neu")
        self.assertEqual(sorted(p.name for p in self.user.iterdir()), ["brief"], "keine Reste vom Import")

    def test_folder_inside_zip_is_accepted(self):
        file = make_file(self.tmp / ("x" + EXTENSION), {"Brief/template.json": self.info(), "Brief/template.html": HTML})
        self.assertEqual(install(file, self.user).title, "Brief")

    def test_rejects_broken_files(self):
        cases = {
            "kein zip": None,
            "ohne json": {"template.html": HTML},
            "ohne html": {"template.json": self.info()},
            "ohne body": {"template.json": self.info(), "template.html": "<p>"},
            "ohne name": {"template.json": json.dumps({"format": 1}), "template.html": HTML},
            "zu neu": {"template.json": self.info(format=99), "template.html": HTML},
            "kaputtes json": {"template.json": "{", "template.html": HTML},
            "ausbruch": {"template.json": self.info(), "template.html": HTML, "../../boese.txt": "x"},
            "absolut": {"template.json": self.info(), "template.html": HTML, "/tmp/boese.txt": "x"},
        }
        for label, files in cases.items():
            file = self.tmp / (label.replace(" ", "-") + EXTENSION)
            if files is None:
                file.write_text("nur Text")
            else:
                make_file(file, files)
            with self.assertRaises(TemplateError, msg=label):
                install(file, self.user)
        link = make_file(self.tmp / ("link" + EXTENSION), {"template.json": self.info(), "template.html": HTML}, {"font.ttf": "/etc/passwd"})
        with self.assertRaises(TemplateError):
            install(link, self.user)
        self.assertFalse((self.tmp.parent / "boese.txt").exists())
        self.assertEqual([p.name for p in self.user.iterdir()] if self.user.exists() else [], [])

    def test_localized(self):
        self.assertEqual(localized({"en": "Letter", "de": "Brief"}), "Brief")
        os.environ["LANGUAGE"] = "fr_FR"
        self.assertEqual(localized({"en": "Letter", "de": "Brief"}), "Letter")
        self.assertEqual(localized("Brief"), "Brief")
        self.assertEqual(localized(None), "")

    def test_css_resources_are_embedded(self):
        file = make_file(
            self.tmp / ("schrift" + EXTENSION),
            {
                "template.json": self.info(),
                "template.html": HTML,
                "style.css": "@font-face{src:url('fonts/a.woff2')} body{background:url(https://x.org/a.png)} p{background:url(../geheim.png)}",
                "fonts/a.woff2": b"\x00\x01",
            },
        )
        header = export.style_header(install(file, self.user))
        self.assertIn("url('data:font/woff2;base64,AAE=')", header)
        self.assertIn("url(https://x.org/a.png)", header)
        self.assertIn("url(../geheim.png)", header)


if __name__ == "__main__":
    unittest.main()
