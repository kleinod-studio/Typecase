import locale
from gettext import gettext as _
from gettext import ngettext
from pathlib import Path

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from .cards import CardData, read_card, save_notes
from .goal import fraction
from .goal_ring import ProgressRing
from .inspector import status_name
from .sheet_editor import AUTOSAVE_DELAY_MS, CHECK_DELAY_MS

CARD_WIDTH = 260


def _number(n: int) -> str:
    return locale.format_string("%d", n, grouping=True)


class _CardDrag(GObject.Object):
    """What a dragged card carries: its sheet. A type of its own, so that the notes fields do not
    take a dragged card as text to insert."""

    __gtype_name__ = "TypecaseCardDrag"

    def __init__(self, path: Path):
        super().__init__()
        self.path = path


class Card(Gtk.Box):
    """One sheet as a card: title, status, keywords, its notes to edit, and the word count.

    The notes are saved on their own (see cards.save_notes) with a short delay, like the text in
    the editor. An external change is shown only while there is no unsaved input on the card."""

    def __init__(self, board: "CardBoard", path: Path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card", "typecase-card"])
        self.set_size_request(CARD_WIDTH, -1)
        self.board = board
        self.path = path
        self.data = CardData()
        self._base = ""  # notes as last read or written
        self._dirty = False
        self._loading = False
        self._timer = 0
        self._check_timer = 0
        self._monitor = None

        header = Gtk.Box(spacing=6)
        self.title = Gtk.Button(css_classes=["flat", "typecase-card-title"], hexpand=True, tooltip_text=_("Open this sheet on its own"))
        self.title.set_child(Gtk.Label(label=path.stem, xalign=0, ellipsize=3, css_classes=["heading"]))  # 3 = END
        self.title.connect("clicked", lambda _b: board.emit("open-sheet", str(self.path)))
        self.status = Gtk.Label(css_classes=["caption", "typecase-card-status"], valign=Gtk.Align.CENTER, visible=False)
        header.append(self.title)
        header.append(self.status)
        self.append(header)

        self.keywords = Gtk.Label(xalign=0, wrap=True, css_classes=["caption", "dim-label"], margin_start=6, visible=False)
        self.append(self.keywords)

        self.notes = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            accepts_tab=False,  # Tab moves on to the next card
            top_margin=6,
            bottom_margin=6,
            left_margin=6,
            right_margin=6,
            css_classes=["typecase-card-notes"],
        )
        self.notes.set_size_request(-1, 96)
        self.notes.update_property([Gtk.AccessibleProperty.LABEL], [_("Notes on “%s”") % path.stem])
        self.notes.get_buffer().connect("changed", self._on_changed)
        self.placeholder = Gtk.Label(
            label=_("Notes"), css_classes=["dim-label"], xalign=0, yalign=0, margin_start=6, margin_top=6, can_target=False
        )
        overlay = Gtk.Overlay(child=self.notes)
        overlay.add_overlay(self.placeholder)
        self.append(overlay)

        footer = Gtk.Box(spacing=6, margin_start=6)
        self.words = Gtk.Label(xalign=0, hexpand=True, css_classes=["caption", "dim-label", "numeric"])
        self.ring = ProgressRing(14, 2.5, visible=False)
        footer.append(self.words)
        footer.append(self.ring)
        self.append(footer)

        # Dragging the card (not from the notes, where dragging selects text) puts it elsewhere.
        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        drag.connect("prepare", self._on_drag_prepare)
        drag.connect("drag-begin", lambda source, _drag: source.set_icon(Gtk.WidgetPaintable(widget=self), 0, 0))
        drag.connect("drag-end", lambda _source, _drag, _delete: board.run_pending_drop())
        self.add_controller(drag)
        drop = Gtk.DropTarget.new(_CardDrag.__gtype__, Gdk.DragAction.MOVE)
        drop.connect("motion", self._on_drop_motion)
        drop.connect("leave", lambda _target: self._show_drop_side(None))
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        self.add_controller(keys)

    # --- Loading and showing ----------------------------------------------

    def load(self) -> None:
        """Reads the sheet. Raises OSError or UnicodeDecodeError."""
        data = read_card(self.path)
        self._set_notes(data.notes)
        self._show(data)
        self._watch()

    def _set_notes(self, notes: str) -> None:
        self._loading = True
        self.notes.get_buffer().set_text(notes)
        self._loading = False
        self._base = notes
        self._dirty = False
        self.placeholder.set_visible(not notes)

    def _show(self, data: CardData) -> None:
        self.data = data
        self.status.set_label(status_name(data.status))
        self.status.set_visible(bool(data.status))
        self.keywords.set_label(", ".join(data.keywords))
        self.keywords.set_visible(bool(data.keywords))
        if data.goal:
            self.words.set_label(_("%(count)s / %(goal)s") % {"count": _number(data.words), "goal": _number(data.goal)})
            self.ring.show_progress(fraction(data.words, data.goal), data.words >= data.goal, animate=False)
        else:
            self.words.set_label(ngettext("%(count)s word", "%(count)s words", data.words) % {"count": _number(data.words)})
        self.ring.set_visible(bool(data.goal))

    def text(self) -> str:
        buffer = self.notes.get_buffer()
        return buffer.get_text(*buffer.get_bounds(), False)

    # --- Saving -------------------------------------------------------------

    def _on_changed(self, buffer):
        self.placeholder.set_visible(buffer.get_char_count() == 0)
        if self._loading:
            return
        self._dirty = True
        self._cancel_timer()
        self._timer = GLib.timeout_add(AUTOSAVE_DELAY_MS, self._on_autosave)

    def _on_autosave(self):
        self._timer = 0
        self.flush()
        return GLib.SOURCE_REMOVE

    def flush(self) -> bool:
        """Saves unsaved notes immediately. True if nothing is pending any more."""
        self._cancel_timer()
        if not self._dirty:
            return True
        notes = self.text()
        try:
            copy = save_notes(self.path, self._base, notes)
        except (OSError, UnicodeDecodeError) as error:
            reason = error.strerror or str(error) if isinstance(error, OSError) else _("not a UTF-8 text file")
            self.board.emit("save-failed", reason)
            return False
        self._base = notes
        self._dirty = False
        if copy is not None:
            self.board.emit(
                "message",
                _("The notes of “%(name)s” were also changed elsewhere; that version is kept as “%(copy)s”.")
                % {"name": self.path.stem, "copy": copy.stem},
            )
        return True

    def _cancel_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def close(self) -> None:
        """Stops saving and watching (call flush() first)."""
        self._cancel_timer()
        if self._check_timer:
            GLib.source_remove(self._check_timer)
            self._check_timer = 0
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None

    # --- External changes -----------------------------------------------------

    def _watch(self):
        try:
            self._monitor = Gio.File.new_for_path(str(self.path)).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return  # without watching, saving still compares with the file on disk
        self._monitor.connect("changed", self._on_file_event)

    def _on_file_event(self, *_args):
        if self._check_timer:
            GLib.source_remove(self._check_timer)
        self._check_timer = GLib.timeout_add(CHECK_DELAY_MS, self._on_check_timer)

    def _on_check_timer(self):
        self._check_timer = 0
        try:
            data = read_card(self.path)
        except (OSError, UnicodeDecodeError):
            return GLib.SOURCE_REMOVE  # deleted or unreadable: the library refresh removes the card
        if not self._dirty and data.notes != self._base:
            self._set_notes(data.notes)  # unsaved input is never replaced; saving handles that case
        self._show(data)
        self.board.update_counts()
        return GLib.SOURCE_REMOVE

    # --- Moving -----------------------------------------------------------

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        """Alt+arrow keys move the card one place back or forward."""
        if state & Gdk.ModifierType.ALT_MASK and not state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK):
            if keyval in (Gdk.KEY_Up, Gdk.KEY_Left, Gdk.KEY_KP_Up, Gdk.KEY_KP_Left):
                self.board.move_step(self, -1)
                return True
            if keyval in (Gdk.KEY_Down, Gdk.KEY_Right, Gdk.KEY_KP_Down, Gdk.KEY_KP_Right):
                self.board.move_step(self, 1)
                return True
        return False

    def _on_drag_prepare(self, _source, x, y):
        target = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        if target is not None and (target is self.notes or target.is_ancestor(self.notes)):
            return None  # in the notes, dragging selects text
        return Gdk.ContentProvider.new_for_value(_CardDrag(self.path))

    def _drop_side(self, x: float) -> str:
        after = x > self.get_width() / 2
        if self.get_direction() == Gtk.TextDirection.RTL:
            after = not after
        return "after" if after else "before"

    def _show_drop_side(self, side: str | None):
        for name in ("before", "after"):
            if name == side:
                self.add_css_class(f"drop-{name}")
            else:
                self.remove_css_class(f"drop-{name}")

    def _on_drop_motion(self, _target, x, _y):
        self._show_drop_side(self._drop_side(x))
        return Gdk.DragAction.MOVE

    def _on_drop(self, _target, value, x, _y):
        self._show_drop_side(None)
        if not isinstance(value, _CardDrag) or value.path == self.path:
            return False
        self.board.request_move(value.path, self.path, after=self._drop_side(x) == "after")
        return True


class CardBoard(Gtk.Box):
    """The sheets of a group as cards with their notes, for plotting: one block of cards per
    subgroup, in the manual order. Moving a card (drag and drop, Alt+arrow keys) changes that
    order; the window carries out the move.

    Like SheetEditor, whoever leaves the board calls flush() first and continues only on True."""

    __gsignals__ = {
        "save-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "message": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "open-sheet": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "counts-changed": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),  # words, characters of the group
        # A card should be put before or after another one: (sheet, anchor, after).
        "move-sheet": (GObject.SignalFlags.RUN_FIRST, None, (str, str, bool)),
    }

    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=24, margin_bottom=48, margin_start=24, margin_end=24
        )
        self.cards: list[Card] = []
        self._pending_drop = None  # move to carry out once the drag has ended

    def open(self, sheets: list[Path], subgroup_title) -> list[str]:
        """Shows a card per sheet. subgroup_title(folder) names the block of a subgroup.
        Returns the names of sheets that could not be read (they are left out)."""
        self.close()
        failed = []
        nested = len({path.parent for path in sheets}) > 1
        flow, folder = None, None
        for path in sheets:
            card = Card(self, path)
            try:
                card.load()
            except (OSError, UnicodeDecodeError):
                card.close()
                failed.append(path.stem)
                continue
            if flow is None or path.parent != folder:
                if nested:
                    title = Gtk.Label(
                        label=subgroup_title(path.parent),
                        css_classes=["title-3"],
                        xalign=0,
                        wrap=True,
                        margin_top=12 if self.cards else 0,
                        accessible_role=Gtk.AccessibleRole.HEADING,
                    )
                    title.update_property([Gtk.AccessibleProperty.LEVEL], [2])
                    self.append(title)
                flow = Gtk.FlowBox(
                    selection_mode=Gtk.SelectionMode.NONE,
                    homogeneous=True,
                    min_children_per_line=1,
                    max_children_per_line=12,
                    column_spacing=12,
                    row_spacing=12,
                    valign=Gtk.Align.START,
                )
                self.append(flow)
                folder = path.parent
            flow.append(Gtk.FlowBoxChild(child=card, focusable=False))
            self.cards.append(card)
        self.update_counts()
        return failed

    def close(self) -> None:
        """Removes all cards without saving (call flush() first)."""
        for card in self.cards:
            card.close()
        child = self.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.remove(child)
            child = following
        self.cards = []
        self.update_counts()

    def flush(self) -> bool:
        ok = True
        for card in self.cards:
            ok = card.flush() and ok
        return ok

    def paths(self) -> list[Path]:
        return [card.path for card in self.cards]

    def focused_path(self) -> Path | None:
        root = self.get_root()
        focus = root.get_focus() if root is not None else None
        for card in self.cards:
            if focus is not None and (focus is card or focus.is_ancestor(card)):
                return card.path
        return None

    def focus_card(self, path: Path | None = None) -> None:
        """Puts the caret into the notes of a card (by default the first one)."""
        card = next((card for card in self.cards if card.path == path), None) if path else None
        card = card or (self.cards[0] if self.cards else None)
        if card is not None:
            card.notes.grab_focus()

    def update_counts(self) -> None:
        self.emit(
            "counts-changed", sum(card.data.words for card in self.cards), sum(card.data.characters for card in self.cards)
        )

    # --- Moving ---------------------------------------------------------------

    def move_step(self, card: Card, direction: int) -> None:
        """One place back or forward among the cards of the same block."""
        siblings = [other for other in self.cards if other.path.parent == card.path.parent]
        index = siblings.index(card) + direction
        if 0 <= index < len(siblings):
            self.emit("move-sheet", str(card.path), str(siblings[index].path), direction > 0)

    def request_move(self, source: Path, anchor: Path, after: bool) -> None:
        """A card was dropped. The move rebuilds the cards, which would destroy the dragged one
        while its drag is still running (on Wayland the pointer then stays grabbed), so it waits
        for the end of the drag."""
        self._pending_drop = (source, anchor, after)

    def run_pending_drop(self) -> None:
        if self._pending_drop is not None:
            GLib.idle_add(self._run_pending_drop)

    def _run_pending_drop(self):
        move, self._pending_drop = self._pending_drop, None
        if move is not None:
            source, anchor, after = move
            self.emit("move-sheet", str(source), str(anchor), after)
        return GLib.SOURCE_REMOVE
