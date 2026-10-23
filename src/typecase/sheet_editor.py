import shutil
import time
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, GtkSource

from .fileio import atomic_write_text, read_text
from .library import unique_path
from .markdown_lists import on_enter
from .textstats import count_characters, count_words

AUTOSAVE_DELAY_MS = 800
COUNT_DELAY_MS = 150  # Zählen erst, wenn kurz nicht getippt wird (lange Texte)
CHECK_DELAY_MS = 300  # Nach einer Dateiänderung kurz warten, bis Sync-Programme fertig geschrieben haben

_UNREADABLE = object()  # Datei existiert, ist aber kein UTF-8-Text (mehr)


class SheetEditor(Gtk.Stack):
    """Zeigt ein Blatt im Editor und sichert Änderungen automatisch.

    Ungesicherte Eingaben gehen nie verloren: wer das Blatt wechselt oder das Fenster
    schließt, ruft zuerst flush() auf und macht nur weiter, wenn es True liefert.

    Änderungen von außen (Sync-Programme, andere Editoren) werden nie überschrieben: Vor
    jedem Speichern wird verglichen, ob die Datei noch so aussieht wie zuletzt gelesen oder
    geschrieben. Wenn nicht, und es gibt ungesicherte Eingaben, entsteht ein Konflikt, den
    der Nutzer entscheidet; die jeweils andere Fassung bleibt als Kopie erhalten."""

    __gsignals__ = {
        "save-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "counts-changed": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),  # Wörter, Zeichen
        # "reloaded" | "deleted" | "restored" | "conflict"
        "external-change": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self._dirty = False
        self._loading = False
        self._timer = 0
        self._count_timer = 0
        self._check_timer = 0
        self._monitor = None
        self._disk_text = None  # Inhalt der Datei, wie zuletzt gelesen oder geschrieben
        self.in_conflict = False  # Solange True, wird nicht gespeichert

        empty = Adw.StatusPage(
            icon_name="document-edit-symbolic",
            title=_("No Sheet Open"),
            description=_("Select a sheet in the library to start writing."),
        )

        self.buffer = GtkSource.Buffer()
        self.buffer.set_language(GtkSource.LanguageManager.get_default().get_language("markdown"))
        self.buffer.connect("changed", self._on_changed)

        self.view = GtkSource.View(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=24,
            bottom_margin=24,
            left_margin=32,
            right_margin=32,
            monospace=False,
        )
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key_pressed)
        self.view.add_controller(keys)
        scrolled = Gtk.ScrolledWindow(child=self.view, hexpand=True, vexpand=True)

        self.add_named(empty, "empty")
        self.add_named(scrolled, "editor")
        self.set_visible_child_name("empty")

    # --- Öffnen und Schließen ---------------------------------------------

    def open(self, path: Path) -> None:
        """Lädt ein Blatt. Der Aufrufer muss vorher flush() erfolgreich aufgerufen haben.
        Wirft OSError oder UnicodeDecodeError; dann bleibt der bisherige Zustand unberührt."""
        text = read_text(path)
        self._set_text(text)
        self.path = path
        self._disk_text = text
        self._dirty = False
        self.in_conflict = False
        self.set_visible_child_name("editor")
        self._watch()
        self._emit_counts()

    def set_path(self, path: Path) -> None:
        """Das offene Blatt wurde (samt Gruppe) umbenannt; Inhalt bleibt, Beobachtung zieht um."""
        self.path = path
        self._watch()

    def close_sheet(self) -> None:
        """Schließt das Blatt ohne zu speichern (nach flush() oder bewusstem Verwerfen)."""
        self._cancel_timer()
        self._unwatch()
        self.path = None
        self._disk_text = None
        self._dirty = False
        self.in_conflict = False
        self._set_text("")
        self.set_visible_child_name("empty")
        self._emit_counts()

    def focus_editor(self) -> None:
        if self.path is not None:
            self.view.grab_focus()

    # --- Sichern ----------------------------------------------------------

    def flush(self) -> bool:
        """Sichert ungespeicherte Änderungen sofort. True, wenn nichts mehr aussteht."""
        self._cancel_timer()
        if self.path is None or not self._dirty:
            return True
        return self._save()

    def _save(self) -> bool:
        if self.in_conflict:
            return False
        try:
            disk = self._read_disk()
        except OSError as error:
            self.emit("save-failed", error.strerror or str(error))
            return False
        if disk is not None and disk != self._disk_text:
            self._enter_conflict()  # Fremde Änderung: nicht drüberschreiben
            return False
        if not self._write(self._buffer_text()):
            return False
        if disk is None and self._disk_text is not None:
            self.emit("external-change", "restored")  # außerhalb gelöscht, unsere Fassung neu angelegt
        return True

    def _write(self, text: str) -> bool:
        try:
            atomic_write_text(self.path, text)
        except OSError as error:
            self.emit("save-failed", error.strerror or str(error))
            return False
        self._disk_text = text
        self._dirty = False
        return True

    # --- Änderungen von außen ----------------------------------------------

    def check_disk(self) -> None:
        """Vergleicht die Datei mit dem zuletzt bekannten Stand und reagiert auf fremde Änderungen."""
        if self.path is None or self.in_conflict:
            return
        try:
            disk = self._read_disk()
        except OSError:
            return  # z. B. kurz gesperrt; beim nächsten Ereignis oder Speichern erneut prüfen
        if disk == self._disk_text:
            return  # unverändert oder unsere eigene Speicherung
        if disk is None:
            if self._dirty:
                self._cancel_timer()
                if self._write(self._buffer_text()):
                    self.emit("external-change", "restored")
            else:
                self.emit("external-change", "deleted")
        elif not self._dirty and disk is not _UNREADABLE:
            self._replace_text(disk)
            self._disk_text = disk
            self.emit("external-change", "reloaded")
        else:
            self._enter_conflict()

    def resolve_conflict(self, keep_mine: bool) -> Path | None:
        """Löst einen Konflikt. Die nicht gewählte Fassung wird als Kopie neben dem Blatt gesichert;
        liefert deren Pfad. Wirft OSError oder UnicodeDecodeError (dann ist die eigene Fassung schon sicher)."""
        mine = self._buffer_text()
        stamp = time.strftime("%Y-%m-%d %H.%M")
        base = _("%(name)s (conflict %(date)s)") % {"name": self.path.stem, "date": stamp}
        copy = unique_path(self.path.parent, base, ".md")
        if keep_mine:
            if self.path.exists():
                shutil.copyfile(self.path, copy)
            else:
                copy = None
            self.in_conflict = False
            if not self._write(mine):
                self.in_conflict = True
                raise OSError(_("could not save"))
        else:
            atomic_write_text(copy, mine)
            theirs = read_text(self.path)
            self._replace_text(theirs)
            self._disk_text = theirs
            self._dirty = False
            self.in_conflict = False
        return copy

    def _enter_conflict(self):
        self._cancel_timer()
        self.in_conflict = True
        self.emit("external-change", "conflict")

    def _read_disk(self):
        """Aktueller Dateiinhalt, None wenn gelöscht, _UNREADABLE wenn kein UTF-8. Wirft andere OSError."""
        try:
            return read_text(self.path)
        except FileNotFoundError:
            return None
        except UnicodeDecodeError:
            return _UNREADABLE

    def _watch(self):
        self._unwatch()
        try:
            self._monitor = Gio.File.new_for_path(str(self.path)).monitor_file(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return  # Ohne Beobachtung schützt immer noch die Prüfung vor jedem Speichern.
        self._monitor.connect("changed", self._on_file_event)

    def _unwatch(self):
        if self._check_timer:
            GLib.source_remove(self._check_timer)
            self._check_timer = 0
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None

    def _on_file_event(self, *_args):
        if self._check_timer:
            GLib.source_remove(self._check_timer)
        self._check_timer = GLib.timeout_add(CHECK_DELAY_MS, self._on_check_timer)

    def _on_check_timer(self):
        self._check_timer = 0
        self.check_disk()
        return GLib.SOURCE_REMOVE

    def _on_changed(self, _buffer):
        if self._loading or self.path is None:
            return
        self._dirty = True
        self._cancel_timer()
        self._timer = GLib.timeout_add(AUTOSAVE_DELAY_MS, self._on_autosave)
        if self._count_timer:
            GLib.source_remove(self._count_timer)
        self._count_timer = GLib.timeout_add(COUNT_DELAY_MS, self._emit_counts)

    def _on_autosave(self):
        self._timer = 0
        if self._dirty:
            self._save()
        return GLib.SOURCE_REMOVE

    def _cancel_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    # --- Zählen ------------------------------------------------------------

    def _emit_counts(self):
        if self._count_timer:
            GLib.source_remove(self._count_timer)
            self._count_timer = 0
        text = self.buffer.get_text(*self.buffer.get_bounds(), True)
        self.emit("counts-changed", count_words(text), count_characters(text))
        return GLib.SOURCE_REMOVE

    # --- Listen fortsetzen --------------------------------------------------

    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SHIFT_MASK
        if state & modifiers or self.path is None or self.buffer.get_has_selection():
            return False
        return self._continue_list()

    def _continue_list(self) -> bool:
        buffer = self.buffer
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        line_end = cursor.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()

        decision = on_enter(buffer.get_text(line_start, line_end, False), cursor.get_line_offset())
        if decision is None:
            return False
        action, prefix = decision

        buffer.begin_user_action()  # Ein Schritt für Rückgängig
        if action == "end":
            buffer.delete(line_start, line_end)
        else:
            buffer.insert_at_cursor("\n" + prefix)
        buffer.end_user_action()
        self.view.scroll_mark_onscreen(buffer.get_insert())
        return True

    # --- intern -----------------------------------------------------------

    def _buffer_text(self) -> str:
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    def _replace_text(self, text: str) -> None:
        """Ersetzt den Inhalt nach einer Änderung von außen; der Cursor bleibt ungefähr, wo er war."""
        offset = self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()
        self._set_text(text)
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(min(offset, self.buffer.get_char_count())))
        self._emit_counts()

    def _set_text(self, text: str) -> None:
        # Als nicht rückgängig machbar markieren, damit "Rückgängig" nie ein anderes Blatt zurückholt.
        self._loading = True
        self.buffer.begin_irreversible_action()
        self.buffer.set_text(text)
        self.buffer.end_irreversible_action()
        self._loading = False
        self.buffer.place_cursor(self.buffer.get_start_iter())
