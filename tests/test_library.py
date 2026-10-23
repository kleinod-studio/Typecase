import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase.fileio import atomic_write_text
from typecase.library import scan


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


class AtomicWriteTest(unittest.TestCase):
    def test_writes_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "text.md"
            atomic_write_text(target, "Hallo")
            atomic_write_text(target, "Hallo Welt")
            self.assertEqual(target.read_text(encoding="utf-8"), "Hallo Welt")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["text.md"])


if __name__ == "__main__":
    unittest.main()
