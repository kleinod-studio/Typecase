from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gdk, GLib, GObject, Graphene, Gtk

from .card_view import CardBoard
from .sheet_editor import SheetEditor


class GroupView(Gtk.ScrolledWindow):
    """All sheets of a group, one after another, to read and write as one text.

    Every sheet keeps its own editor (an embedded SheetEditor): autosave, protection against
    external changes and undo work per file exactly as in the single-sheet view. The view only
    stacks them, separated by a line with the sheet's name, and lets the arrow keys move on from
    the end of one sheet to the start of the next.

    Instead of the text, the view can show the sheets as cards with their notes (CardBoard).

    Like SheetEditor, whoever leaves the view calls flush() first and continues only on True."""

    __gsignals__ = {
        "save-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "counts-changed": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),  # words, characters of the group
        # A section reports an external change (same kinds as SheetEditor); the window handles it.
        "external-change": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
        # The user asks to open one sheet on its own (header of a section clicked).
        "open-sheet": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # A section has spell checking on but no dictionary for its language.
        "dictionary-missing": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        # From the cards: something to tell the user, and a card put before or after another one.
        "message": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "move-sheet": (GObject.SignalFlags.RUN_FIRST, None, (str, str, bool)),
    }

    def __init__(self):
        # The background of the editor theme also between the sections (set by the window).
        super().__init__(hexpand=True, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, css_classes=["view", "typecase-group"])
        self.group: Path | None = None
        self.editors: list[SheetEditor] = []
        self._active: SheetEditor | None = None
        self._counts: dict[SheetEditor, tuple[int, int]] = {}
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=32, margin_bottom=96)
        self._empty = Adw.StatusPage(
            icon_name="folder-symbolic",
            title=_("No Sheets in This Group"),
            description=_("Sheets you add to the group appear here one after another."),
        )
        self.cards = CardBoard()
        self.showing_cards = False
        self.cards.connect("save-failed", lambda _b, message: self.emit("save-failed", message))
        self.cards.connect("message", lambda _b, text: self.emit("message", text))
        self.cards.connect("open-sheet", lambda _b, path: self.emit("open-sheet", path))
        self.cards.connect("move-sheet", lambda _b, *move: self.emit("move-sheet", *move))
        self.cards.connect("counts-changed", lambda _b, words, characters: self.emit("counts-changed", words, characters))
        self.set_child(self._box)

    # --- Opening and closing ---------------------------------------------

    def open(self, group: Path, sheets: list[Path], cards: bool = False) -> list[str]:
        """Shows the sheets of a group, as text or as cards. The caller must have flushed whatever
        was open before. Returns the names of sheets that could not be opened (they are left out)."""
        self.close()
        self.group = group
        if cards:
            self.showing_cards = True
            failed = self.cards.open(sheets, self.subgroup_title)
            self.set_child(self.cards if self.cards.cards else self._empty)
            return failed
        failed = []
        nested = len({path.parent for path in sheets}) > 1
        folder = None
        for path in sheets:
            editor = SheetEditor(embedded=True)
            handler = editor.connect("counts-changed", self._on_section_counts)  # open() reports the first counts
            try:
                editor.open(path)
            except (OSError, UnicodeDecodeError):
                editor.disconnect(handler)
                failed.append(path.stem)
                continue
            # With subgroups, their names mark where each one starts (like the page breaks in the export).
            heading = self.subgroup_title(path.parent) if nested and path.parent != folder else None
            folder = path.parent
            self._add_section(editor, heading)
        if self.editors:
            self._active = self.editors[0]
        self.set_child(self._box if self.editors else self._empty)
        self._emit_counts()
        return failed

    def close(self) -> None:
        """Removes all sections without saving (call flush() first)."""
        for editor in self.editors:
            editor.close_sheet()
        child = self._box.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._box.remove(child)
            child = following
        self.editors = []
        self._counts = {}
        self._active = None
        self.cards.close()
        self.showing_cards = False
        self.group = None
        self._emit_counts()

    def flush(self) -> bool:
        """Saves every section. True only if nothing is pending anywhere (a refused save, e.g. in
        a conflict, keeps the view open)."""
        ok = self.cards.flush()
        for editor in self.editors:
            ok = editor.flush() and ok
        return ok

    @property
    def active(self) -> SheetEditor | None:
        """The section with the caret (the formatting bar acts on it), or the one that had it last."""
        root = self.get_root()
        focus = root.get_focus() if root is not None else None
        for editor in self.editors:
            if focus is editor.view:
                self._active = editor
        return self._active

    @active.setter
    def active(self, editor: SheetEditor | None) -> None:
        self._active = editor

    def paths(self) -> list[Path]:
        if self.showing_cards:
            return self.cards.paths()
        return [editor.path for editor in self.editors]

    def editor_for(self, path: Path) -> SheetEditor | None:
        return next((editor for editor in self.editors if editor.path == path), None)

    def focus_start(self) -> None:
        if self.showing_cards:
            self.cards.focus_card()
            return
        target = self.active or (self.editors[0] if self.editors else None)
        if target is not None:
            target.focus_editor()

    # --- Building ------------------------------------------------------------

    def subgroup_title(self, folder: Path) -> str:
        """Name of a subgroup as shown above its sheets: its path below the group, or the group's name."""
        if folder == self.group:
            return self.group.name
        return " › ".join(folder.relative_to(self.group).parts)

    def _add_section(self, editor: SheetEditor, heading: str | None = None) -> None:
        header = Gtk.Button(
            css_classes=["flat", "group-section-header"],
            halign=Gtk.Align.CENTER,
            tooltip_text=_("Open this sheet on its own"),
            margin_top=24 if self.editors else 0,
        )
        header.set_child(Gtk.Label(label=editor.path.stem, css_classes=["dim-label", "caption-heading"]))
        header.connect("clicked", lambda _b: self.emit("open-sheet", str(editor.path)))
        if self.editors:  # a line between sheets, none above the first
            self._box.append(Gtk.Separator(margin_start=48, margin_end=48))
        if heading is not None:
            header.set_margin_top(4)
            title = Gtk.Label(
                label=heading,
                css_classes=["title-3"],
                margin_top=32 if self.editors else 0,
                wrap=True,
                justify=Gtk.Justification.CENTER,
                accessible_role=Gtk.AccessibleRole.HEADING,  # screen readers can jump between subgroups
            )
            title.update_property([Gtk.AccessibleProperty.LEVEL], [2])
            self._box.append(title)
        self._box.append(header)
        self._box.append(editor)
        editor.view.update_property([Gtk.AccessibleProperty.LABEL], [editor.path.stem])  # which sheet is being edited
        self.editors.append(editor)

        editor.connect("save-failed", lambda _e, message: self.emit("save-failed", message))
        editor.connect("external-change", lambda e, kind: self.emit("external-change", e, kind))
        editor.connect("dictionary-missing", lambda _e, lang: self.emit("dictionary-missing", lang))
        editor.buffer.connect("notify::cursor-position", lambda _b, _p: self._queue_caret_visible(editor))
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)  # before the view moves the caret
        keys.connect("key-pressed", self._on_key_pressed, editor)
        editor.view.add_controller(keys)

    # --- Moving between sheets with the keyboard --------------------------

    def _on_key_pressed(self, _controller, keyval, _keycode, state, editor: SheetEditor):
        """Up on the first line goes to the end of the previous sheet, Down on the last line to
        the start of the next one – so the group reads like one continuous text."""
        if state & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK):
            return False
        index = self.editors.index(editor)
        buffer, view = editor.buffer, editor.view
        line = view.get_iter_location(buffer.get_iter_at_mark(buffer.get_insert())).y
        if keyval in (Gdk.KEY_Up, Gdk.KEY_KP_Up) and index > 0:
            if line == view.get_iter_location(buffer.get_start_iter()).y:  # on the first display line
                self._enter(self.editors[index - 1], at_end=True)
                return True
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down) and index < len(self.editors) - 1:
            if line == view.get_iter_location(buffer.get_end_iter()).y:  # on the last display line
                self._enter(self.editors[index + 1], at_end=False)
                return True
        return False

    def _enter(self, editor: SheetEditor, at_end: bool) -> None:
        buffer = editor.buffer
        buffer.place_cursor(buffer.get_end_iter() if at_end else buffer.get_start_iter())
        self._active = editor
        editor.view.grab_focus()
        self._queue_caret_visible(editor)

    def _queue_caret_visible(self, editor: SheetEditor) -> None:
        # After layout, so the caret's position is final.
        if editor.view.has_focus():
            GLib.idle_add(self._show_caret, editor)

    def _show_caret(self, editor: SheetEditor):
        """The sections do not scroll themselves; this view keeps the caret on screen while writing."""
        if editor not in self.editors:
            return GLib.SOURCE_REMOVE
        view = editor.view
        rect = view.get_iter_location(editor.buffer.get_iter_at_mark(editor.buffer.get_insert()))
        x, y = view.buffer_to_window_coords(Gtk.TextWindowType.WIDGET, rect.x, rect.y)
        found, point = view.compute_point(self._box, Graphene.Point().init(x, y))
        if not found:
            return GLib.SOURCE_REMOVE
        adjustment = self.get_vadjustment()
        margin = 48
        top, bottom = point.y - margin, point.y + rect.height + margin
        if top < adjustment.get_value():
            adjustment.set_value(max(0, top))
        elif bottom > adjustment.get_value() + adjustment.get_page_size():
            adjustment.set_value(bottom - adjustment.get_page_size())
        return GLib.SOURCE_REMOVE

    # --- Counts ------------------------------------------------------------------

    def _on_section_counts(self, editor, words, characters):
        self._counts[editor] = (words, characters)
        self._emit_counts()

    def _emit_counts(self) -> None:
        words = sum(c[0] for c in self._counts.values())
        characters = sum(c[1] for c in self._counts.values())
        self.emit("counts-changed", words, characters)
