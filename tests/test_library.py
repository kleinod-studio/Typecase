import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import os
import stat

from typecase.fileio import atomic_write_text, read_text
from typecase.markdown_lists import on_enter
from typecase.library import create_group, create_sheet, rename, scan, sheet_filename, validate_name


class ScanTest(unittest.TestCase):
    def test_groups_first_then_sheets_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.md").write_text("b")
            (root / "A.md").write_text("a")
            (root / "Zeta").mkdir()
            (root / "alpha").mkdir()
            (root / "alpha" / "inner.md").write_text("x")

            nodes = scan(root)

            self.assertEqual([n.name for n in nodes], ["alpha", "Zeta", "A", "b"])
            self.assertTrue(nodes[0].is_group)
            self.assertEqual([c.name for c in nodes[0].children], ["inner"])
            self.assertFalse(nodes[2].is_group)

    def test_ignores_hidden_other_files_and_symlinked_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".hidden.md").write_text("x")
            (root / ".git").mkdir()
            (root / "notes.txt").write_text("x")
            (root / "real").mkdir()
            (root / "link").symlink_to(root / "real")

            self.assertEqual([n.name for n in scan(root)], ["real"])

    def test_empty_group_is_still_a_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "empty").mkdir()
            node = scan(root)[0]
            self.assertTrue(node.is_group)
            self.assertEqual(node.children, [])


class FileOperationsTest(unittest.TestCase):
    def test_create_sheet_picks_free_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = create_sheet(root, "Untitled")
            second = create_sheet(root, "Untitled")
            self.assertEqual([first.name, second.name], ["Untitled.md", "Untitled 2.md"])
            self.assertEqual(first.read_text(), "")

    def test_create_group_picks_free_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(create_group(root, "Neu").name, "Neu")
            self.assertEqual(create_group(root, "Neu").name, "Neu 2")

    def test_rename_sheet_keeps_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "alt.md"
            sheet.write_text("inhalt")
            neu = rename(sheet, "Neuer Name")
            self.assertEqual(neu.name, "Neuer Name.md")
            self.assertEqual(neu.read_text(), "inhalt")
            self.assertFalse(sheet.exists())
            self.assertEqual(rename(neu, "Anders.md").name, "Anders.md")

    def test_rename_group_moves_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            group = Path(tmp) / "A"
            group.mkdir()
            (group / "x.md").write_text("x")
            neu = rename(group, "B")
            self.assertEqual((neu / "x.md").read_text(), "x")

    def test_rename_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.md"
            b = Path(tmp) / "b.md"
            a.write_text("A")
            b.write_text("B")
            with self.assertRaises(FileExistsError):
                rename(a, "b")
            self.assertEqual((a.read_text(), b.read_text()), ("A", "B"))

    def test_rename_only_case_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.md"
            a.write_text("A")
            self.assertEqual(rename(a, "A").name, "A.md")

    def test_invalid_names(self):
        for bad in ["", "   ", ".", "..", ".versteckt", "a/b"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_name(bad)
        self.assertEqual(sheet_filename("  Titel "), "Titel.md")


class ListContinuationTest(unittest.TestCase):
    def test_bullets_keep_their_marker(self):
        for marker in ["-", "*", "+"]:
            line = f"{marker} Eintrag"
            self.assertEqual(on_enter(line, len(line)), ("continue", f"{marker} "))

    def test_numbers_count_up(self):
        self.assertEqual(on_enter("1. Eins", 7), ("continue", "2. "))
        self.assertEqual(on_enter("9) Neun", 7), ("continue", "10) "))

    def test_indentation_is_kept(self):
        self.assertEqual(on_enter("    - Unterpunkt", 16), ("continue", "    - "))

    def test_task_list_and_quote(self):
        self.assertEqual(on_enter("- [x] erledigt", 14), ("continue", "- [ ] "))
        self.assertEqual(on_enter("> Zitat", 7), ("continue", "> "))

    def test_empty_item_ends_list(self):
        self.assertEqual(on_enter("- ", 2), ("end", ""))
        self.assertEqual(on_enter("3. ", 3), ("end", ""))
        self.assertEqual(on_enter("  - [ ] ", 8), ("end", ""))

    def test_cursor_inside_marker_or_plain_text_is_untouched(self):
        self.assertIsNone(on_enter("- Eintrag", 1))
        self.assertIsNone(on_enter("Normaler Text", 5))
        self.assertIsNone(on_enter("**fett** und mehr", 17))
        self.assertIsNone(on_enter("-kein Listenpunkt", 5))

    def test_split_in_the_middle_continues(self):
        self.assertEqual(on_enter("- Anfang Ende", 8), ("continue", "- "))


class AtomicWriteTest(unittest.TestCase):
    def test_writes_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "text.md"
            atomic_write_text(target, "Hallo")
            atomic_write_text(target, "Hallo Welt")
            self.assertEqual(target.read_text(encoding="utf-8"), "Hallo Welt")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["text.md"])

    def test_keeps_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "win.md"
            target.write_bytes(b"a\r\nb\r\n")
            atomic_write_text(target, read_text(target))
            self.assertEqual(target.read_bytes(), b"a\r\nb\r\n")

    def test_keeps_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "t.md"
            target.write_text("x")
            os.chmod(target, 0o640)
            atomic_write_text(target, "y")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_symlink_stays_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.md"
            real.write_text("x")
            link = Path(tmp) / "link.md"
            link.symlink_to(real)
            atomic_write_text(link, "neu")
            self.assertTrue(link.is_symlink())
            self.assertEqual(real.read_text(), "neu")

    def test_non_utf8_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "latin.md"
            target.write_bytes("Käse".encode("latin-1"))
            with self.assertRaises(UnicodeDecodeError):
                read_text(target)

    def test_failed_write_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "t.md"
            target.write_text("original")
            os.chmod(tmp, 0o500)
            try:
                with self.assertRaises(OSError):
                    atomic_write_text(target, "neu")
            finally:
                os.chmod(tmp, 0o700)
            self.assertEqual(target.read_text(), "original")


if __name__ == "__main__":
    unittest.main()
