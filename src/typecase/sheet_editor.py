import shutil
import time
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Graphene, Gsk, Gtk, GtkSource, Pango

from . import formatting, frontmatter
from .fileio import atomic_write_text, read_text
from .library import unique_path
from .markdown_lists import change_indent, on_enter, renumber
from .markdown_styler import MarkdownStyler
from .textstats import count_characters, count_words

AUTOSAVE_DELAY_MS = 800
COUNT_DELAY_MS = 150  # Zählen erst, wenn kurz nicht getippt wird (lange Texte)
CHECK_DELAY_MS = 300  # Nach einer Dateiänderung kurz warten, bis Sync-Programme fertig geschrieben haben

_UNREADABLE = object()  # Datei existiert, ist aber kein UTF-8-Text (mehr)

# Voreinstellungen fürs Schreiben; später über die Einstellungen änderbar (P2-05).
DEFAULT_FONT_SIZE_PT = 15
DEFAULT_LINE_WIDTH_CHARS = 70
MIN_SIDE_MARGIN = 32
LINE_SPACING_PIXELS = {"compact": 2, "normal": 5, "relaxed": 10}  # Abstand umbrochener Zeilen und Absätze


class _EditorView(GtkSource.View):
    """Textfeld, dessen Textblock eine Höchstbreite hat und mittig steht.

    Die Ränder werden bei jeder Größenänderung neu berechnet; die Breite richtet sich
    nach der Schrift (Anzahl Zeichen), wächst also mit der Schriftgröße mit."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.line_width_chars = DEFAULT_LINE_WIDTH_CHARS
        self._char_width_cache = (None, 0.0)
        self.styler = None  # liefert die Zeilen der Codeblöcke für den Rahmen
        # Text-Mauszeiger auch über den breiten Rändern, damit man die Schreibmarke gezielt setzen kann.
        self.set_cursor_from_name("text")

        # Fokus-Hilfen (nur im Fokus-Modus): aktuelle Zeile mittig halten, Umgebung abblenden.
        self.typewriter = False
        self.dim_others = False
        self._keyboard_moved = False
        self._margins = (kwargs.get("top_margin", 0), kwargs.get("bottom_margin", 0))
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", lambda *_a: setattr(self, "_keyboard_moved", True) or False)
        self.add_controller(keys)
        self.get_buffer().connect("changed", lambda _b: self._keep_centered(force=True))
        self.get_buffer().connect(
            "mark-set", lambda b, _i, mark: mark == b.get_insert() and self._keep_centered()
        )

        # Schreibmarke als Unterstrich: GTK kann das nicht selbst, daher zeichnen wir sie (blinkend).
        self.underline_caret = False
        self._caret_on = True
        self._blink_timer = 0
        self._blink_started = 0
        buffer = self.get_buffer()
        buffer.connect("mark-set", lambda _b, _i, mark: mark == buffer.get_insert() and self._restart_blink())
        buffer.connect("changed", lambda _b: self._restart_blink())
        focus = Gtk.EventControllerFocus()
        focus.connect("enter", lambda _c: self._restart_blink())
        focus.connect("leave", lambda _c: self.queue_draw())
        self.add_controller(focus)

    def set_focus_effects(self, typewriter: bool, dim_others: bool) -> None:
        self.typewriter = typewriter
        self.dim_others = dim_others
        self.queue_resize()
        self.queue_draw()
        if typewriter:
            GLib.idle_add(self._center_cursor)

    def _keep_centered(self, force: bool = False):
        """Schreibmaschinen-Modus: nur beim Tippen und bei Tastatur-Bewegung zentrieren, damit
        Markieren mit der Maus nicht springt."""
        if self.dim_others:
            self.queue_draw()  # der helle Absatz folgt der Schreibmarke
        if self.typewriter and (force or self._keyboard_moved):
            self._keyboard_moved = False
            GLib.idle_add(self._center_cursor)
        return False

    def _center_cursor(self):
        self.scroll_to_mark(self.get_buffer().get_insert(), 0.0, True, 0.0, 0.5)
        return False

    def set_underline_caret(self, enabled: bool) -> None:
        self.underline_caret = enabled
        if enabled:
            self.add_css_class("underline-caret")
        else:
            self.remove_css_class("underline-caret")
        self._restart_blink()

    def _restart_blink(self):
        """Nach Tippen oder Bewegen sichtbar bleiben und neu zu blinken beginnen (wie die normale Schreibmarke)."""
        self._caret_on = True
        if self._blink_timer:
            GLib.source_remove(self._blink_timer)
            self._blink_timer = 0
        settings = Gtk.Settings.get_default()
        if self.underline_caret and settings.props.gtk_cursor_blink:
            self._blink_started = GLib.get_monotonic_time()
            self._blink_timer = GLib.timeout_add(max(100, settings.props.gtk_cursor_blink_time // 2), self._on_blink)
        self.queue_draw()
        return False

    def _on_blink(self):
        timeout_us = Gtk.Settings.get_default().props.gtk_cursor_blink_timeout * 1_000_000
        if GLib.get_monotonic_time() - self._blink_started > timeout_us:
            self._caret_on = True  # nach einer Weile ohne Eingabe ruhig stehen bleiben
            self._blink_timer = 0
            self.queue_draw()
            return GLib.SOURCE_REMOVE
        self._caret_on = not self._caret_on
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def do_size_allocate(self, width, height, baseline):
        side = max(MIN_SIDE_MARGIN, int((width - self.line_width_chars * self._char_width()) / 2))
        if side != self.get_left_margin():
            self.set_left_margin(side)
            self.set_right_margin(side)
        # Schreibmaschinen-Modus: halbe Höhe Luft oben und unten, damit auch erste und letzte Zeile mittig stehen können.
        top, bottom = (height // 2, height // 2) if self.typewriter else self._margins
        if (top, bottom) != (self.get_top_margin(), self.get_bottom_margin()):
            self.set_top_margin(top)
            self.set_bottom_margin(bottom)
        GtkSource.View.do_size_allocate(self, width, height, baseline)

    def do_snapshot_layer(self, layer, snapshot):
        GtkSource.View.do_snapshot_layer(self, layer, snapshot)
        if layer == Gtk.TextViewLayer.ABOVE_TEXT:
            self._snapshot_dimming(snapshot)
            self._snapshot_caret(snapshot)
            return
        if layer != Gtk.TextViewLayer.BELOW_TEXT or self.styler is None or not self.styler.code_blocks:
            return
        dark = self.styler.dark
        fill = Gdk.RGBA()
        fill.parse("rgba(255,255,255,0.04)" if dark else "rgba(0,0,0,0.035)")
        border = Gdk.RGBA()
        border.parse("rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)")

        buffer = self.get_buffer()
        left = self.get_left_margin()
        width = self.get_width() - left - self.get_right_margin()
        for open_line, last_line, _closed in self.styler.code_blocks:
            top, _height = self.get_line_yrange(buffer.get_iter_at_line(open_line)[1])
            bottom_y, bottom_height = self.get_line_yrange(buffer.get_iter_at_line(last_line)[1])
            rect = Graphene.Rect().init(left - 14, top - 6, width + 28, bottom_y + bottom_height - top + 12)
            rounded = Gsk.RoundedRect()
            rounded.init_from_rect(rect, 8)
            snapshot.push_rounded_clip(rounded)
            snapshot.append_color(fill, rect)
            snapshot.pop()
            snapshot.append_border(rounded, [1, 1, 1, 1], [border, border, border, border])

    def _snapshot_dimming(self, snapshot):
        """Umgebung abblenden: alles außer dem aktuellen Absatz mit der Hintergrundfarbe überdecken."""
        if not self.dim_others:
            return
        buffer = self.get_buffer()
        scheme = buffer.get_style_scheme()
        style = scheme.get_style("text") if scheme else None
        background = Gdk.RGBA()
        if not (style and style.props.background and background.parse(style.props.background)):
            return
        background.alpha = 0.6
        line_start = buffer.get_iter_at_mark(buffer.get_insert())
        line_start.set_line_offset(0)
        top, height = self.get_line_yrange(line_start)
        visible = self.get_visible_rect()
        if top > visible.y:
            snapshot.append_color(background, Graphene.Rect().init(visible.x, visible.y, visible.width, top - visible.y))
        bottom = top + height
        if bottom < visible.y + visible.height:
            snapshot.append_color(
                background, Graphene.Rect().init(visible.x, bottom, visible.width, visible.y + visible.height - bottom)
            )

    def _snapshot_caret(self, snapshot):
        buffer = self.get_buffer()
        if not (self.underline_caret and self._caret_on and self.has_focus() and self.get_editable()):
            return
        if buffer.get_has_selection():
            return  # mit Markierung genügt die Markierung
        where = self.get_iter_location(buffer.get_iter_at_mark(buffer.get_insert()))
        width = where.width if where.width > 2 else self._char_width()
        thickness = 2
        rect = Graphene.Rect().init(where.x, where.y + where.height - thickness, width, thickness)
        snapshot.append_color(self.get_color(), rect)

    def _char_width(self) -> float:
        context = self.get_pango_context()
        key = context.get_font_description().to_string()
        if self._char_width_cache[0] != key:
            metrics = context.get_metrics(None, None)
            self._char_width_cache = (key, metrics.get_approximate_char_width() / Pango.SCALE)
        return self._char_width_cache[1]


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
        # Dateikopf (Meta-Informationen) wurde geladen, von außen geändert oder das Blatt geschlossen
        "metadata-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "saved": (GObject.SignalFlags.RUN_FIRST, None, ()),
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
        self._header = None  # Dateikopf (Frontmatter); im Editor ausgeblendet, beim Speichern wieder davor
        self.in_conflict = False  # Solange True, wird nicht gespeichert

        empty = Adw.StatusPage(
            icon_name="document-edit-symbolic",
            title=_("No Sheet Open"),
            description=_("Select a sheet in the library to start writing."),
        )

        self.buffer = GtkSource.Buffer(highlight_syntax=False)  # eigene Gestaltung statt GtkSource-Färbung
        self.styler = MarkdownStyler(self.buffer)
        self.buffer.connect("changed", self._on_changed)

        self.view = _EditorView(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=48,
            bottom_margin=96,
            left_margin=MIN_SIDE_MARGIN,
            right_margin=MIN_SIDE_MARGIN,
            pixels_inside_wrap=5,
            pixels_below_lines=5,
            monospace=False,
            css_classes=["typecase-editor"],
        )
        self.view.styler = self.styler
        self.styler.on_blocks_changed = self.view.queue_draw
        self._css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.set_appearance()
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
        header, body = frontmatter.split(text)
        self._set_text(body)
        self._header = header
        self.path = path
        self._disk_text = text
        self._dirty = False
        self.in_conflict = False
        self.set_visible_child_name("editor")
        self._watch()
        self._emit_counts()
        self.emit("metadata-changed")

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
        self._header = None
        self._dirty = False
        self.in_conflict = False
        self._set_text("")
        self.set_visible_child_name("empty")
        self._emit_counts()

    def set_appearance(
        self,
        font_family: str | None = None,
        font_size_pt: int = DEFAULT_FONT_SIZE_PT,
        line_width_chars: int = DEFAULT_LINE_WIDTH_CHARS,
        line_spacing: str = "normal",
    ) -> None:
        """Schrift, Breite und Zeilenabstand des Textblocks. font_family None = Schrift der Oberfläche."""
        family = ""
        if font_family:
            escaped = font_family.replace("\\", "\\\\").replace('"', '\\"')
            family = f'font-family: "{escaped}";'
        self._css.load_from_string(
            f".typecase-editor {{ {family} font-size: {font_size_pt}pt; }}"
            # Unterstrich-Schreibmarke: die normale nur unsichtbar machen. Abschalten (cursor-visible)
            # ginge nicht, dann scrollen die Pfeiltasten nur noch und der Text-Mauszeiger fehlt.
            ".typecase-editor.underline-caret { caret-color: transparent; }"
        )
        pixels = LINE_SPACING_PIXELS.get(line_spacing, LINE_SPACING_PIXELS["normal"])
        self.view.set_pixels_inside_wrap(pixels)
        self.view.set_pixels_below_lines(pixels)
        self.view.line_width_chars = line_width_chars
        self.view.queue_resize()

    def text(self) -> str:
        """Der ganze Dateiinhalt, wie er gespeichert würde (mit Dateikopf)."""
        return self._file_text()

    # --- Formatieren (Leiste und Tastenkürzel) --------------------------------

    INLINE_FORMATS = {
        "bold": formatting.BOLD,
        "italic": formatting.ITALIC,
        "underline": formatting.UNDERLINE,
        "strike": formatting.STRIKE,
        "code": formatting.CODE,
    }
    LINE_FORMATS = ("h1", "h2", "h3", "paragraph", "bullet", "numbered", "quote")

    def apply_format(self, kind: str) -> bool:
        """Schaltet eine Formatierung für Markierung, Wort oder Zeilen um; ein Schritt für Rückgängig."""
        if self.path is None:
            return False
        buffer = self.buffer
        bounds = buffer.get_selection_bounds()
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        start, end = (bounds[0], bounds[1]) if bounds else (cursor, cursor.copy())

        if kind in self.LINE_FORMATS:
            first, last = start.get_line(), end.get_line()
            if bounds and end.starts_line() and last > first:
                last -= 1
            old = self._lines()
            buffer.begin_user_action()
            self._apply_lines(old, formatting.toggle_lines(old, first, last, kind))
            buffer.end_user_action()
        else:
            text = self._buffer_text()
            a, b = start.get_offset(), end.get_offset()
            if kind in self.INLINE_FORMATS:
                new, a, b = formatting.toggle_inline(text, a, b, self.INLINE_FORMATS[kind])
            elif kind == "link":
                new, a, b = formatting.insert_link(text, a, b, _("Text"), "https://")
            elif kind == "codeblock":
                new, a, b = formatting.insert_code_block(text, a, b)
            else:
                return False
            buffer.begin_user_action()
            self._replace_changed_part(text, new)
            buffer.end_user_action()
            buffer.select_range(buffer.get_iter_at_offset(b), buffer.get_iter_at_offset(a))
        self.view.scroll_mark_onscreen(buffer.get_insert())
        self.focus_editor()
        return True

    def _replace_changed_part(self, old: str, new: str) -> None:
        """Ersetzt nur den Teil, der sich unterscheidet (Marken und Cursor bleiben sonst stehen)."""
        prefix = 0
        limit = min(len(old), len(new))
        while prefix < limit and old[prefix] == new[prefix]:
            prefix += 1
        suffix = 0
        while suffix < limit - prefix and old[len(old) - 1 - suffix] == new[len(new) - 1 - suffix]:
            suffix += 1
        start = self.buffer.get_iter_at_offset(prefix)
        end = self.buffer.get_iter_at_offset(len(old) - suffix)
        self.buffer.delete(start, end)
        self.buffer.insert(self.buffer.get_iter_at_offset(prefix), new[prefix : len(new) - suffix])

    # --- Meta-Informationen (Dateikopf) ---------------------------------------

    def metadata(self) -> dict:
        return frontmatter.parse(self._header)

    def set_metadata(self, changes: dict) -> None:
        """Ändert Felder im Dateikopf; nur die betroffenen Zeilen, gesichert wie eine Texteingabe."""
        if self.path is None:
            return
        header = frontmatter.update(self._header, changes)
        if header == self._header:
            return
        self._header = header
        self._mark_dirty()
        if "goal" in changes:
            self._emit_counts()  # die Wortanzeige nennt das Ziel mit

    def show_match(self, offset: int, length: int) -> None:
        """Markiert eine Fundstelle und scrollt sie in die Mitte."""
        start = self.buffer.get_iter_at_offset(offset)
        end = self.buffer.get_iter_at_offset(offset + length)
        self.buffer.select_range(end, start)
        # Erst nach dem Layout des neuen Texts scrollen, sonst stimmen die Höhen noch nicht.
        GLib.idle_add(lambda: self.view.scroll_to_mark(self.buffer.get_insert(), 0.1, True, 0.0, 0.35) and False)

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
        if not self._write(self._file_text()):
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
        self.emit("saved")
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
                if self._write(self._file_text()):
                    self.emit("external-change", "restored")
            else:
                self.emit("external-change", "deleted")
        elif not self._dirty and disk is not _UNREADABLE:
            self._load_from_disk(disk)
            self.emit("external-change", "reloaded")
        else:
            self._enter_conflict()

    def resolve_conflict(self, keep_mine: bool) -> Path | None:
        """Löst einen Konflikt. Die nicht gewählte Fassung wird als Kopie neben dem Blatt gesichert;
        liefert deren Pfad. Wirft OSError oder UnicodeDecodeError (dann ist die eigene Fassung schon sicher)."""
        mine = self._file_text()
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
            self._load_from_disk(read_text(self.path))
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
        self._mark_dirty()
        if self._count_timer:
            GLib.source_remove(self._count_timer)
        self._count_timer = GLib.timeout_add(COUNT_DELAY_MS, self._emit_counts)

    def _mark_dirty(self):
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
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_KP_Tab, Gdk.KEY_ISO_Left_Tab):
            if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK) or self.path is None:
                return False
            outdent = keyval == Gdk.KEY_ISO_Left_Tab or state & Gdk.ModifierType.SHIFT_MASK
            return self._indent_list(-1 if outdent else 1)
        if keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        if state & Gdk.ModifierType.ALT_MASK:
            # Alt+Enter: Eigenschaften (Seitenfenster); das Textfeld würde sonst einen Zeilenumbruch einfügen.
            return self.activate_action("win.inspector", None)
        ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if state & ctrl_shift == ctrl_shift:
            # Kürzel für den Fokus-Modus; das Textfeld würde sonst einen Zeilenumbruch einfügen.
            return self.activate_action("win.focus-mode", None)
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
            lines = self._lines()
            outdented = change_indent(lines, cursor.get_line(), -1)
            if outdented is not None:
                self._apply_lines(lines, outdented)  # leerer Unterpunkt: erst eine Ebene zurück
            else:
                buffer.delete(line_start, line_end)
        else:
            buffer.insert_at_cursor("\n" + prefix)
            lines = self._lines()
            self._apply_lines(lines, renumber(lines, self._cursor_line()))
        buffer.end_user_action()
        self.view.scroll_mark_onscreen(buffer.get_insert())
        return True

    def _indent_list(self, direction: int) -> bool:
        """Tab/Umschalt+Tab in Listenpunkten (auch mehrere markierte Zeilen). False = normales Tab."""
        buffer = self.buffer
        if buffer.get_has_selection():
            start, end = buffer.get_selection_bounds()
            first, last = start.get_line(), end.get_line()
            if end.starts_line() and last > first:
                last -= 1
        else:
            first = last = self._cursor_line()

        old = self._lines()
        lines = old
        for index in range(first, last + 1):
            changed = change_indent(lines, index, direction)
            if changed is not None:
                lines = changed
        if lines == old:
            return False
        buffer.begin_user_action()
        self._apply_lines(old, lines)
        buffer.end_user_action()
        return True

    def _lines(self) -> list[str]:
        return self._buffer_text().split("\n")

    def _cursor_line(self) -> int:
        return self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_line()

    def _apply_lines(self, old: list[str], new: list[str]) -> None:
        """Überträgt geänderte Zeilen in den Puffer und ändert dabei nur die abweichenden Zeichen,
        damit der Cursor an seiner Stelle im Text bleibt."""
        buffer = self.buffer
        for index, (before, after) in enumerate(zip(old, new)):
            if before == after:
                continue
            prefix = 0
            while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
                prefix += 1
            suffix = 0
            while (
                suffix < min(len(before), len(after)) - prefix
                and before[len(before) - 1 - suffix] == after[len(after) - 1 - suffix]
            ):
                suffix += 1
            _found, start = buffer.get_iter_at_line_offset(index, prefix)
            _found, end = buffer.get_iter_at_line_offset(index, len(before) - suffix)
            buffer.delete(start, end)
            _found, start = buffer.get_iter_at_line_offset(index, prefix)
            buffer.insert(start, after[prefix : len(after) - suffix])

    # --- intern -----------------------------------------------------------

    def _file_text(self) -> str:
        return frontmatter.join(self._header, self._buffer_text())

    def _load_from_disk(self, text: str) -> None:
        """Übernimmt einen neuen Dateiinhalt (Änderung von außen oder gewählte fremde Fassung)."""
        header, body = frontmatter.split(text)
        self._replace_text(body)
        self._header = header
        self._disk_text = text
        self._dirty = False
        self.emit("metadata-changed")

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
