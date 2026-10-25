import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import os
import stat

from typecase.fileio import atomic_write_text, read_text
from typecase.markdown_lists import change_indent, on_enter, renumber
from typecase.textstats import count_characters, count_words
from typecase.library import add_attachment, all_groups, attachments, create_group, duplicate, read_order, create_sheet, move, rename, scan, sheet_filename, validate_name


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


class MoveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "A" / "Unter").mkdir(parents=True)
        (self.root / "B").mkdir()
        (self.root / "blatt.md").write_text("Text")

    def tearDown(self):
        self._tmp.cleanup()

    def test_move_sheet_into_group(self):
        moved = move(self.root / "blatt.md", self.root / "A")
        self.assertEqual(moved, self.root / "A" / "blatt.md")
        self.assertEqual(moved.read_text(), "Text")
        self.assertFalse((self.root / "blatt.md").exists())

    def test_move_group_with_contents(self):
        (self.root / "A" / "Unter" / "x.md").write_text("x")
        moved = move(self.root / "A", self.root / "B")
        self.assertEqual((moved / "Unter" / "x.md").read_text(), "x")

    def test_same_folder_is_a_no_op(self):
        self.assertEqual(move(self.root / "blatt.md", self.root), self.root / "blatt.md")

    def test_group_cannot_go_into_itself(self):
        with self.assertRaises(ValueError):
            move(self.root / "A", self.root / "A")
        with self.assertRaises(ValueError):
            move(self.root / "A", self.root / "A" / "Unter")

    def test_never_overwrites(self):
        (self.root / "B" / "blatt.md").write_text("Anderes")
        with self.assertRaises(FileExistsError):
            move(self.root / "blatt.md", self.root / "B")
        self.assertEqual((self.root / "B" / "blatt.md").read_text(), "Anderes")
        self.assertEqual((self.root / "blatt.md").read_text(), "Text")

    def test_all_groups(self):
        groups = all_groups(scan(self.root))
        self.assertEqual(groups, [self.root / "A", self.root / "A" / "Unter", self.root / "B"])


class RenumberTest(unittest.TestCase):
    def test_inserted_item_shifts_following(self):
        lines = ["1. Eins", "2. Zwei", "3. Neu", "3. Drei", "4. Vier", "", "Absatz"]
        self.assertEqual(renumber(lines, 2), ["1. Eins", "2. Zwei", "3. Neu", "4. Drei", "5. Vier", "", "Absatz"])

    def test_nested_items_are_skipped_and_kept(self):
        lines = ["1. A", "    1. a", "    2. b", "1. B", "1. C"]
        self.assertEqual(renumber(lines, 3), ["1. A", "    1. a", "    2. b", "2. B", "3. C"])

    def test_stops_at_bullets_text_and_blank_lines(self):
        self.assertEqual(renumber(["1. A", "1. B", "- x", "1. C"], 1), ["1. A", "2. B", "- x", "1. C"])
        self.assertEqual(renumber(["5) A", "5) B"], 1), ["5) A", "6) B"])

    def test_restart(self):
        self.assertEqual(renumber(["3. A", "4. B"], 0, restart=True), ["1. A", "2. B"])


class IndentTest(unittest.TestCase):
    def test_indent_bullet(self):
        self.assertEqual(change_indent(["- A", "- B"], 1, 1), ["- A", "    - B"])

    def test_outdent_bullet(self):
        self.assertEqual(change_indent(["- A", "    - B"], 1, -1), ["- A", "- B"])
        self.assertEqual(change_indent(["- A", "\t- B"], 1, -1), ["- A", "- B"])
        self.assertIsNone(change_indent(["- A"], 0, -1))

    def test_not_a_list(self):
        self.assertIsNone(change_indent(["Text"], 0, 1))
        self.assertIsNone(change_indent(["> Zitat"], 0, 1))

    def test_indent_numbered_starts_sublist_and_closes_gap(self):
        lines = ["1. A", "2. B", "3. C", "4. D"]
        self.assertEqual(change_indent(lines, 2, 1), ["1. A", "2. B", "    1. C", "3. D"])

    def test_indent_numbered_continues_existing_sublist(self):
        lines = ["1. A", "    1. a", "2. B"]
        self.assertEqual(change_indent(lines, 2, 1), ["1. A", "    1. a", "    2. B"])

    def test_outdent_numbered(self):
        lines = ["1. A", "    1. a", "    2. b", "    3. c", "2. B"]
        self.assertEqual(change_indent(lines, 2, -1), ["1. A", "    1. a", "2. b", "    1. c", "3. B"])


class TextStatsTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(count_words(""), 0)
        self.assertEqual(count_words("Hallo Welt"), 2)
        self.assertEqual(count_words("# Überschrift\n\n- **fett** und *kursiv*"), 4)
        self.assertEqual(count_words("E-Mail, geht's? 2026!"), 3)
        self.assertEqual(count_words("  ---  > *  "), 0)
        self.assertEqual(count_words("1. Eins\n2) Zwei\n  10. Zehn\n> 3. Zitat"), 4)
        self.assertEqual(count_words("Im Jahr 2026 waren es 3. Plätze"), 7)

    def test_characters(self):
        self.assertEqual(count_characters(""), 0)
        self.assertEqual(count_characters("ab c"), 4)
        self.assertEqual(count_characters("a\nb\r\nc"), 3)
        self.assertEqual(count_characters("Ä😀"), 2)


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


class AttachmentTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.sheet = self.root / "Chapter.md"
        self.sheet.write_text("Text")
        self.source = self.root / "outside" / "photo.jpg"
        self.source.parent.mkdir()
        self.source.write_bytes(b"jpeg")

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_lists_and_never_overwrites(self):
        first = add_attachment(self.sheet, self.source)
        second = add_attachment(self.sheet, self.source)
        self.assertEqual(first, self.root / ".attachments" / "Chapter" / "photo.jpg")
        self.assertEqual(second.name, "photo 2.jpg")
        self.assertEqual(attachments(self.sheet), [first, second])
        self.assertEqual(first.read_bytes(), b"jpeg")
        self.assertTrue(self.source.exists(), "the original stays where it is")
        self.assertEqual([node.name for node in scan(self.root)], ["outside", "Chapter"], "the hidden folder is no group in the library")

    def test_follow_rename_and_move(self):
        add_attachment(self.sheet, self.source)
        renamed = rename(self.sheet, "Prologue")
        self.assertEqual([p.name for p in attachments(renamed)], ["photo.jpg"])
        self.assertFalse((self.root / ".attachments" / "Chapter").exists())
        group = create_group(self.root, "Part")
        moved = move(renamed, group)
        self.assertEqual(attachments(moved), [group / ".attachments" / "Prologue" / "photo.jpg"])
        self.assertFalse((self.root / ".attachments").exists(), "the empty hidden folder is cleaned up")

    def test_merge_keeps_existing_files(self):
        add_attachment(self.sheet, self.source)
        group = create_group(self.root, "Part")
        orphan = group / ".attachments" / "Chapter" / "photo.jpg"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"older")
        moved = move(self.sheet, group)
        self.assertEqual(sorted(p.name for p in attachments(moved)), ["photo 2.jpg", "photo.jpg"])
        self.assertEqual(orphan.read_bytes(), b"older")

    def test_sheet_without_attachments(self):
        self.assertEqual(attachments(self.sheet), [])
        moved = move(self.sheet, create_group(self.root, "Part"))
        self.assertFalse((moved.parent / ".attachments").exists())


class DuplicateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sheet_with_attachments_lands_after_the_original(self):
        for name in ("A.md", "B.md", "C.md"):
            (self.root / name).write_text(name)
        source = self.root / "photo.jpg"
        source.write_bytes(b"jpeg")
        add_attachment(self.root / "B.md", source)
        copy = duplicate(self.root / "B.md", "B (Copy)")
        self.assertEqual(copy, self.root / "B (Copy).md")
        self.assertEqual(copy.read_text(), "B.md")
        self.assertEqual([p.name for p in attachments(copy)], ["photo.jpg"])
        self.assertEqual([p.name for p in attachments(self.root / "B.md")], ["photo.jpg"], "the original keeps its attachments")
        self.assertEqual(read_order(self.root), ["A.md", "B.md", "B (Copy).md", "C.md"])
        self.assertEqual(duplicate(self.root / "B.md", "B (Copy)").name, "B (Copy) 2.md")
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.endswith(".part")), [], "no temporary files are left")

    def test_group_with_everything_in_it(self):
        group = create_group(self.root, "Novel")
        (group / "Part").mkdir()
        (group / "Part" / "Chapter.md").write_text("Text")
        (group / "Intro.md").write_text("Hi")
        add_attachment(group / "Intro.md", group / "Part" / "Chapter.md")
        (group / ".typecase.json").write_text('{"order": ["Intro.md", "Part"]}')
        copy = duplicate(group, "Novel (Copy)")
        self.assertEqual(copy, self.root / "Novel (Copy)")
        self.assertEqual((copy / "Part" / "Chapter.md").read_text(), "Text")
        self.assertEqual([p.name for p in attachments(copy / "Intro.md")], ["Chapter.md"])
        self.assertEqual(read_order(copy), ["Intro.md", "Part"], "the manual order inside is copied too")
        self.assertEqual([n.name for n in scan(self.root)], ["Novel", "Novel (Copy)"])
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".") and p.name != ".typecase.json"], [])


if __name__ == "__main__":
    unittest.main()
