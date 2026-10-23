from gettext import gettext as _
from gettext import ngettext

from gi.repository import Adw, Gdk, GObject, Gtk, GtkSource


class FindBar(Gtk.SearchBar):
    """Suchen und Ersetzen im offenen Blatt (über GtkSourceView: Hervorhebung, Zählen, Ersetzen)."""

    __gsignals__ = {"replaced": (GObject.SignalFlags.RUN_FIRST, None, (int,))}  # Anzahl bei "Alle ersetzen"

    def __init__(self, editor):
        super().__init__(show_close_button=True)
        self.editor = editor
        self.buffer = editor.buffer
        self.settings = GtkSource.SearchSettings(wrap_around=True, case_sensitive=False)
        self.context = GtkSource.SearchContext(buffer=self.buffer, settings=self.settings, highlight=False)
        self.context.connect("notify::occurrences-count", lambda *_args: self._update_label())
        self.buffer.connect("mark-set", self._on_mark_set)

        self.entry = Gtk.SearchEntry(placeholder_text=_("Find"), hexpand=True)
        self.entry.connect("search-changed", self._on_search_changed)
        self.entry.connect("activate", lambda _e: self.find_next())
        self.entry.connect("next-match", lambda _e: self.find_next())
        self.entry.connect("previous-match", lambda _e: self.find_previous())
        self.entry.connect("stop-search", lambda _e: self.set_search_mode(False))
        shift_enter = Gtk.EventControllerKey()
        shift_enter.connect("key-pressed", self._on_entry_key)
        self.entry.add_controller(shift_enter)

        self.label = Gtk.Label(css_classes=["dim-label", "numeric"], width_chars=12, xalign=1)
        previous = Gtk.Button(icon_name="go-up-symbolic", tooltip_text=_("Previous Match"))
        previous.connect("clicked", lambda _b: self.find_previous())
        following = Gtk.Button(icon_name="go-down-symbolic", tooltip_text=_("Next Match"))
        following.connect("clicked", lambda _b: self.find_next())
        self.replace_toggle = Gtk.ToggleButton(icon_name="edit-find-replace-symbolic", tooltip_text=_("Replace"))

        self.replace_entry = Gtk.Entry(placeholder_text=_("Replace with"), hexpand=True)
        self.replace_entry.connect("activate", lambda _e: self.replace())
        replace_one = Gtk.Button(label=_("Replace"))
        replace_one.connect("clicked", lambda _b: self.replace())
        replace_all = Gtk.Button(label=_("Replace All"))
        replace_all.connect("clicked", lambda _b: self.replace_all())

        find_row = Gtk.Box(spacing=6)
        for widget in (self.entry, self.label, previous, following, self.replace_toggle):
            find_row.append(widget)
        replace_row = Gtk.Box(spacing=6, margin_top=6)
        for widget in (self.replace_entry, replace_one, replace_all):
            replace_row.append(widget)
        revealer = Gtk.Revealer(child=replace_row)
        self.replace_toggle.bind_property("active", revealer, "reveal-child", GObject.BindingFlags.SYNC_CREATE)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(find_row)
        box.append(revealer)
        self.set_child(Adw.Clamp(maximum_size=640, child=box))
        self.connect_entry(self.entry)
        self.connect("notify::search-mode-enabled", self._on_mode_changed)

    # --- Öffnen und Schließen ---------------------------------------------

    def open(self, text: str | None = None, replace: bool = False, focus: bool = True):
        """Öffnet die Leiste. Ohne Text wird eine einzeilige Markierung im Editor übernommen."""
        if text is None and self.buffer.get_has_selection():
            start, end = self.buffer.get_selection_bounds()
            if start.get_line() == end.get_line():
                text = self.buffer.get_text(start, end, True)
        if text is not None:
            self.entry.set_text(text)
        self.settings.set_search_text(self.entry.get_text() or None)
        self.context.set_highlight(True)
        if replace:
            self.replace_toggle.set_active(True)
        self.set_search_mode(True)
        if focus:
            self.entry.grab_focus()
            self.entry.select_region(0, -1)
        self._update_label()

    def _on_mode_changed(self, *_args):
        if not self.get_search_mode():
            self.context.set_highlight(False)
            self.editor.focus_editor()

    # --- Suchen -------------------------------------------------------------

    def _on_search_changed(self, entry):
        self.settings.set_search_text(entry.get_text() or None)
        if entry.get_text():
            # Beim Weitertippen ab dem Anfang des aktuellen Treffers suchen, damit er stehen bleibt.
            bounds = self.buffer.get_selection_bounds()
            start = bounds[0] if bounds else self.buffer.get_iter_at_mark(self.buffer.get_insert())
            self._select(*self._forward(start))
        self._update_label()

    def _on_entry_key(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.SHIFT_MASK:
            self.find_previous()
            return True
        return False

    def find_next(self) -> bool:
        if not self.settings.get_search_text():
            return False
        bounds = self.buffer.get_selection_bounds()
        start = bounds[1] if bounds else self.buffer.get_iter_at_mark(self.buffer.get_insert())
        return self._select(*self._forward(start))

    def find_previous(self) -> bool:
        if not self.settings.get_search_text():
            return False
        bounds = self.buffer.get_selection_bounds()
        start = bounds[0] if bounds else self.buffer.get_iter_at_mark(self.buffer.get_insert())
        found, match_start, match_end, _wrapped = self.context.backward(start)
        return self._select(found, match_start, match_end)

    def _forward(self, start):
        found, match_start, match_end, _wrapped = self.context.forward(start)
        return found, match_start, match_end

    def _select(self, found, start, end) -> bool:
        if found:
            self.buffer.select_range(start, end)
            self.editor.view.scroll_to_mark(self.buffer.get_insert(), 0.1, False, 0.0, 0.0)
        self._update_label()
        return found

    # --- Ersetzen -----------------------------------------------------------

    def replace(self):
        """Ersetzt den markierten Treffer und springt zum nächsten."""
        bounds = self.buffer.get_selection_bounds()
        if bounds and self.context.get_occurrence_position(*bounds) > 0:
            self.context.replace(bounds[0], bounds[1], self.replace_entry.get_text(), -1)
        self.find_next()

    def replace_all(self) -> int:
        if not self.settings.get_search_text():
            return 0
        count = self.context.replace_all(self.replace_entry.get_text(), -1)
        self.emit("replaced", count)
        self._update_label()
        return count

    # --- Anzeige ------------------------------------------------------------

    def _on_mark_set(self, _buffer, _location, mark):
        if mark == self.buffer.get_insert() and self.get_search_mode():
            self._update_label()

    def _update_label(self):
        total = self.context.get_occurrences_count()
        searching = bool(self.settings.get_search_text())
        if not searching or total < 0:  # < 0: wird noch gezählt
            self.label.set_text("")
            self.entry.remove_css_class("error")
            return
        if total == 0:
            self.label.set_text(_("No matches"))
            self.entry.add_css_class("error")
            return
        self.entry.remove_css_class("error")
        bounds = self.buffer.get_selection_bounds()
        position = self.context.get_occurrence_position(*bounds) if bounds else -1
        if position > 0:
            self.label.set_text(_("%(current)s of %(total)s") % {"current": position, "total": total})
        else:
            self.label.set_text(ngettext("%(count)s match", "%(count)s matches", total) % {"count": total})
