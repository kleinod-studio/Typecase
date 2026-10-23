from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, GLib, GObject, Gtk, GtkSource

from .fileio import atomic_write_text, read_text

AUTOSAVE_DELAY_MS = 800


class SheetEditor(Gtk.Stack):
    """Zeigt ein Blatt im Editor und sichert Änderungen automatisch.

    Ungesicherte Eingaben gehen nie verloren: wer das Blatt wechselt oder das Fenster
    schließt, ruft zuerst flush() auf und macht nur weiter, wenn es True liefert."""

    __gsignals__ = {"save-failed": (GObject.SignalFlags.RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self._dirty = False
        self._loading = False
        self._timer = 0

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
        self._dirty = False
        self.set_visible_child_name("editor")

    def close_sheet(self) -> None:
        """Schließt das Blatt ohne zu speichern (nach flush() oder bewusstem Verwerfen)."""
        self._cancel_timer()
        self.path = None
        self._dirty = False
        self._set_text("")
        self.set_visible_child_name("empty")

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
        start, end = self.buffer.get_bounds()
        text = self.buffer.get_text(start, end, True)
        try:
            atomic_write_text(self.path, text)
        except OSError as error:
            self.emit("save-failed", error.strerror or str(error))
            return False
        self._dirty = False
        return True

    def _on_changed(self, _buffer):
        if self._loading or self.path is None:
            return
        self._dirty = True
        self._cancel_timer()
        self._timer = GLib.timeout_add(AUTOSAVE_DELAY_MS, self._on_autosave)

    def _on_autosave(self):
        self._timer = 0
        if self._dirty:
            self._save()
        return GLib.SOURCE_REMOVE

    def _cancel_timer(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    # --- intern -----------------------------------------------------------

    def _set_text(self, text: str) -> None:
        # Als nicht rückgängig machbar markieren, damit "Rückgängig" nie ein anderes Blatt zurückholt.
        self._loading = True
        self.buffer.begin_irreversible_action()
        self.buffer.set_text(text)
        self.buffer.end_irreversible_action()
        self._loading = False
        self.buffer.place_cursor(self.buffer.get_start_iter())
