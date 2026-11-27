import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from typecase import tables
from typecase.tables import CENTER, LEFT, RIGHT, Table


class CellTest(unittest.TestCase):
    def test_cells_with_and_without_outer_pipes(self):
        self.assertEqual(tables.cells("| Anna | Hamburg |"), ["Anna", "Hamburg"])
        self.assertEqual(tables.cells("Anna | Hamburg"), ["Anna", "Hamburg"])
        self.assertEqual(tables.cells("| Anna |"), ["Anna"])

    def test_empty_cells(self):
        self.assertEqual(tables.cells("| | x |  |"), ["", "x", ""])

    def test_pipes_in_code_and_escaped_pipes_divide_nothing(self):
        self.assertEqual(tables.cells("| `a|b` | c \\| d |"), ["`a|b`", "c \\| d"])
        self.assertEqual(tables.cells("| ``a`|`b`` | c |"), ["``a`|`b``", "c"])
        self.assertEqual(tables.cells("| `open | c |"), ["`open", "c"], "an unclosed ` is plain text")

    def test_cell_spans_point_at_the_text(self):
        line = "| Anna  |  Hamburg |"
        self.assertEqual([line[a:b] for a, b in tables.cell_spans(line)], ["Anna", "Hamburg"])
        self.assertEqual(tables.pipe_positions(line), [0, 8, 19])

    def test_rows(self):
        self.assertTrue(tables.is_row("a | b"))
        self.assertFalse(tables.is_row("no pipe here"))
        self.assertFalse(tables.is_row(""))
        self.assertFalse(tables.is_row("    | indented as code |"))
        self.assertFalse(tables.is_row("`a|b`"))


class SeparatorTest(unittest.TestCase):
    def test_alignments(self):
        self.assertEqual(tables.separator_aligns("|:--|:-:|--:|---|"), [LEFT, CENTER, RIGHT, None])
        self.assertEqual(tables.separator_aligns("-|-"), [None, None])
        self.assertEqual(tables.separator_aligns("| :--- |"), [LEFT])

    def test_no_separator(self):
        for line in ("---", "| a | b |", "|--|x|", "| |", ""):
            self.assertIsNone(tables.separator_aligns(line), line)


TEXT = """# Crew

| Name | Town |
|:-----|-----:|
| Anna | Hamburg |
| Ben |
After the table.

Text before
| a | b |
|---|---|

```
| x | y |
|---|---|
```

| one |
|-----|
"""


class FindTest(unittest.TestCase):
    def setUp(self):
        self.lines = TEXT.split("\n")

    def test_find(self):
        self.assertEqual(tables.find(self.lines), [(2, 5), (17, 18)])

    def test_a_table_starts_a_block(self):
        self.assertNotIn(9, [first for first, _last in tables.find(self.lines)], "follows a paragraph line")

    def test_table_at(self):
        self.assertEqual(tables.table_at(self.lines, 4), (2, 5))
        self.assertIsNone(tables.table_at(self.lines, 6), "the line without a pipe ends the table")
        self.assertIsNone(tables.table_at(self.lines, 14), "in a code block")

    def test_after_a_heading(self):
        self.assertEqual(tables.find(["## Crew", "| a |", "|---|"]), [(1, 2)])

    def test_header_may_have_fewer_cells(self):
        self.assertEqual(tables.find(["| a |", "|---|---|", "| 1 | 2 |"]), [(0, 2)])


class RenderTest(unittest.TestCase):
    def test_parse(self):
        table = tables.parse(["| Name | Town |", "|:--|--:|", "| Anna | Hamburg |"])
        self.assertEqual(table, Table([["Name", "Town"], ["Anna", "Hamburg"]], [LEFT, RIGHT]))

    def test_tidy_lines_up_the_pipes(self):
        self.assertEqual(
            tables.tidy(["Name|Town|Age", ":-|:-:|-:", "Anna|Hamburg|34", "Ben"]),
            [
                "| Name |  Town   | Age |",
                "|:-----|:-------:|----:|",
                "| Anna | Hamburg |  34 |",
                "| Ben  |         |     |",
            ],
        )

    def test_tidy_keeps_every_cell(self):
        self.assertEqual(
            tables.tidy(["| a | b |", "|---|---|", "| 1 | 2 | 3 |"]),
            ["| a   | b   |     |", "|-----|-----|-----|", "| 1   | 2   | 3   |"],
        )

    def test_tidy_keeps_markup_and_escaped_pipes(self):
        self.assertEqual(
            tables.tidy(["| **a** | `x|y` |", "|-|-|", "| c \\| d | e |"]),
            ["| **a**  | `x|y` |", "|--------|-------|", "| c \\| d | e     |"],
        )

    def test_tidy_is_stable(self):
        lines = tables.tidy(["Name|Town", ":-:|-", "Anna|Hamburg"])
        self.assertEqual(tables.tidy(lines), lines)

    def test_wide_characters_take_two_columns(self):
        self.assertEqual(tables.width("Straße"), 6)
        self.assertEqual(tables.width("東京"), 4)
        self.assertEqual(tables.width("é"), 1)
        self.assertEqual(tables.tidy(["| 東京 |", "|---|", "| abcde |"]), ["| 東京  |", "|-------|", "| abcde |"])

    def test_new(self):
        self.assertEqual(
            tables.new(["Column 1", "Column 2"], 1),
            ["| Column 1 | Column 2 |", "|----------|----------|", "|  |  |"],
        )
        lines = tables.new(["A", "B", "C"])
        self.assertEqual(tables.find(lines), [(0, 3)], "a new table is found again")


class MoveTest(unittest.TestCase):
    LINES = ["| a | b |", "|---|---|", "| 1 | 2 |"]
    TIDY = ["| a   | b   |", "|-----|-----|", "| 1   | 2   |"]

    def test_cell_index(self):
        self.assertEqual([tables.cell_index("| a | b |", c) for c in (0, 1, 4, 5, 8, 9)], [0, 0, 0, 1, 1, 2])
        self.assertEqual([tables.cell_index("a | b", c) for c in (0, 2, 3)], [0, 0, 1])

    def test_tab_goes_to_the_next_cell_and_selects_it(self):
        self.assertEqual(tables.move(self.LINES, 0, 2, True), (self.LINES, 0, 6, 7))
        self.assertEqual(tables.move(self.LINES, 0, 6, True), (self.LINES, 2, 2, 3), "skips the separator")

    def test_shift_tab_goes_back(self):
        self.assertEqual(tables.move(self.LINES, 2, 2, False), (self.LINES, 0, 6, 7))
        self.assertIsNone(tables.move(self.LINES, 0, 2, False), "nothing before the first cell")

    def test_tab_in_the_last_cell_adds_a_row(self):
        self.assertEqual(tables.move(self.LINES, 2, 6, True), (self.LINES + ["|  |  |"], 3, 2, 2))

    def test_tab_can_tidy_on_the_way(self):
        self.assertEqual(tables.move(self.LINES, 0, 2, True, tidy=True), (self.TIDY, 0, 8, 9))
        self.assertEqual(tables.move(self.LINES, 2, 6, True, tidy=True), (self.TIDY + ["|     |     |"], 3, 2, 2))

    def test_from_the_separator(self):
        self.assertEqual(tables.move(self.LINES, 1, 3, True)[1:], (2, 2, 3))
        self.assertEqual(tables.move(self.LINES, 1, 3, False)[1:], (0, 6, 7))

    def test_short_rows_get_their_cells(self):
        lines, row, start, end = tables.move(["| a | b |", "|-|-|", "| 1 |"], 2, 2, True)
        self.assertEqual((lines[2], row, start, end), ("| 1 |  |", 2, 6, 6))
        lines, row, start, end = tables.move(["a | b", "-|-", "1"], 2, 1, True)
        self.assertEqual((lines[2], row, start, end), ("1 |  |", 2, 4, 4), "the open last cell is closed first")

    def test_gaps_line_up_the_pipes(self):
        lines = ["| Name | Town |", "|:--|--:|", "| Anna | Hamburg |", "a | b"]
        self.assertEqual(tables.gaps(lines), [[(13, 3)], [(3, 3), (7, 6)], [], [(1, 5)]])
        self.assertEqual(tables.gaps(self.TIDY), [[], [], []], "a tidy table needs no gaps")

    def test_gaps_measure_with_the_given_width(self):
        bold_header = lambda text, row: len(text) * (2 if row == 0 else 1)
        self.assertEqual(tables.gaps(["| ab |", "|--|", "| abcdef |"], bold_header), [[], [(2, 7)], [(8, 1)]])

    def test_tidy_keeps_the_caret_in_its_cell(self):
        self.assertEqual(tables.tidy_at(self.LINES, 2, 6), (self.TIDY, 9))
        self.assertEqual(tables.tidy_at(self.LINES, 1, 4), (self.TIDY, 0))

    def test_add_row(self):
        self.assertEqual(tables.add_row(self.LINES, 2, True), (self.LINES + ["|  |  |"], 3))
        self.assertEqual(tables.add_row(self.LINES, 2, False), (self.LINES[:2] + ["|  |  |"] + self.LINES[2:], 2))
        self.assertEqual(tables.add_row(self.LINES, 0, False)[1], 2, "above the header: the first body row")
        self.assertEqual(tables.add_row(self.LINES, 1, True)[1], 2)

    def test_remove_row(self):
        self.assertEqual(tables.remove_row(self.LINES, 2), self.LINES[:2])
        self.assertIsNone(tables.remove_row(self.LINES, 0))
        self.assertIsNone(tables.remove_row(self.LINES, 1))

    def test_add_column(self):
        lines = ["| a | b |", "|---|:-:|", "| 1 | 2 |"]
        self.assertEqual(tables.add_column(lines, 1), ["| a |  | b |", "|---|---|:-:|", "| 1 |  | 2 |"])
        self.assertEqual(tables.add_column(lines, 2), ["| a | b |  |", "|---|:-:|---|", "| 1 | 2 |  |"])
        self.assertEqual(tables.add_column(lines, 0), ["|  | a | b |", "|---|---|:-:|", "|  | 1 | 2 |"])

    def test_add_column_to_rows_without_outer_pipes(self):
        self.assertEqual(tables.add_column(["a | b", "-|-", "1"], 2), ["a | b |  |", "-|-|---|", "1 |  |  |"])
        self.assertEqual(tables.add_column(["a | b", "-|-"], 0), ["  | a | b |", "---|-|-|"])
        self.assertEqual(tables.find(tables.add_column(["a | b", "-|-", "1"], 0)), [(0, 2)])

    def test_remove_column(self):
        lines = ["| a | b |", "|---|:-:|", "| 1 | 2 |"]
        self.assertEqual(tables.remove_column(lines, 0), ["| b |", "|:-:|", "| 2 |"])
        self.assertIsNone(tables.remove_column(["| a |", "|---|"], 0), "the last column stays")
        self.assertEqual(tables.remove_column(["a | b", "-|-", "1"], 1), ["| a |", "|-|", "| 1 |"], "rows keep a pipe")

    def test_cell_place(self):
        self.assertEqual([tables.cell_place("| ab |  | c", i) for i in range(3)], [4, 7, 11])

    def test_insert(self):
        text, start, end = tables.insert("Hello\nWorld", 2, 2, ["Column 1", "Column 2"])
        self.assertEqual(text, "Hello\n\n" + "\n".join(tables.new(["Column 1", "Column 2"])) + "\n\nWorld")
        self.assertEqual(text[start:end], "Column 1")
        self.assertEqual(tables.find(text.split("\n")), [(2, 5)])


if __name__ == "__main__":
    unittest.main()
