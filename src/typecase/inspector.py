import os
from datetime import datetime
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk

from . import config

STATUSES = ("draft", "revision", "final")


def language_name(code: str) -> str:
    names = {
        "de-DE": _("German"),
        "de-AT": _("German (Austria)"),
        "de-CH": _("German (Switzerland)"),
        "en-US": _("English (US)"),
        "en-GB": _("English (UK)"),
        "fr-FR": _("French"),
        "es-ES": _("Spanish"),
        "it-IT": _("Italian"),
        "nl-NL": _("Dutch"),
    }
    return names.get(code, code)


def _status_name(value: str) -> str:
    return {"draft": _("Draft"), "revision": _("Revision"), "final": _("Final")}.get(value, value)


def _format_time(timestamp: float) -> str:
    return GLib.DateTime.new_from_unix_local(int(timestamp)).format("%x, %H:%M")


def format_created(value: str) -> str:
    """Erstelldatum aus dem Dateikopf zur Anzeige: mit Uhrzeit, wenn gespeichert; Unlesbares unverändert."""
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return value
    if len(value.strip()) <= 10:  # nur Datum
        return GLib.DateTime.new_local(moment.year, moment.month, moment.day, 0, 0, 0).format("%x")
    return _format_time(moment.timestamp())


class Inspector(Adw.Bin):
    """Seitenfenster rechts: Meta-Informationen des offenen Blatts (Dateikopf) bearbeiten.

    Leere Felder werden aus dem Dateikopf entfernt. Autor und Sprache zeigen ihre Voreinstellung
    aus den App-Einstellungen nur an; in die Datei kommt nur, was man selbst einträgt."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self._loading = False
        editor.connect("metadata-changed", lambda _e: self.refresh())
        editor.connect("saved", lambda _e: self._refresh_modified())

        page = Adw.PreferencesPage()

        text_group = Adw.PreferencesGroup()
        self.title_row = self._entry(text_group, _("Title"), "title")
        self.subtitle_row = self._entry(text_group, _("Subtitle"), "subtitle")
        self.author_row = self._entry(text_group, _("Author"), "author")
        self.author_default = Gtk.Label(css_classes=["dim-label"], ellipsize=3, max_width_chars=14)
        self.author_row.add_suffix(self.author_default)
        page.add(text_group)

        sort_group = Adw.PreferencesGroup(title=_("Organize"))
        self.keywords_row = Adw.EntryRow(title=_("Keywords, separated by commas"))
        self.keywords_row.connect("changed", lambda row: self._set("keywords", _split_keywords(row.get_text())))
        sort_group.add(self.keywords_row)
        self.status_row = Adw.ComboRow(title=_("Status"))
        self.status_row.connect("notify::selected", lambda *_a: self._on_choice(self.status_row, "status"))
        sort_group.add(self.status_row)
        self.lang_row = Adw.ComboRow(title=_("Language"))
        self.lang_row.connect("notify::selected", lambda *_a: self._on_choice(self.lang_row, "lang"))
        sort_group.add(self.lang_row)
        page.add(sort_group)

        # Reine Anzeigen: das Erstelldatum setzt Typecase beim Anlegen, "geändert" kommt aus der Datei.
        date_group = Adw.PreferencesGroup(title=_("Dates"))
        self.created_row = Adw.ActionRow(title=_("Created"), css_classes=["property"], subtitle_selectable=True)
        date_group.add(self.created_row)
        self.modified_row = Adw.ActionRow(title=_("Last Modified"), css_classes=["property"], subtitle_selectable=True)
        date_group.add(self.modified_row)
        page.add(date_group)

        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title=_("Properties")))
        view = Adw.ToolbarView(content=page)
        view.add_top_bar(header)
        self.set_child(view)
        self._choices: dict[str, list[str]] = {}
        self.refresh()

    # --- Aufbau -------------------------------------------------------------

    def _entry(self, group, title: str, key: str) -> Adw.EntryRow:
        row = Adw.EntryRow(title=title)
        row.connect("changed", lambda r: self._set(key, r.get_text().strip()))
        group.add(row)
        return row

    def _fill_choice(self, row: Adw.ComboRow, key: str, values: list[str], labels: list[str], current: str):
        """Auswahlliste: erster Eintrag = nichts angegeben; unbekannte Werte aus der Datei bleiben wählbar."""
        if current and current not in values:
            values, labels = values + [current], labels + [current]
        self._choices[key] = [""] + values
        row.set_model(Gtk.StringList.new([self._none_label(key)] + labels))
        row.set_selected(self._choices[key].index(current) if current in self._choices[key] else 0)

    def _none_label(self, key: str) -> str:
        if key == "lang":
            return _("Default (%s)") % language_name(config.sheet_defaults()["lang"])
        return _("None")

    # --- Anzeigen -------------------------------------------------------------

    def refresh(self):
        """Felder aus dem Dateikopf des offenen Blatts übernehmen (ohne zurückzuschreiben)."""
        self._loading = True
        data = self.editor.metadata() if self.editor.path else {}
        defaults = config.sheet_defaults()

        def text(key):
            value = data.get(key, "")
            return ", ".join(value) if isinstance(value, list) else str(value)

        self.title_row.set_text(text("title"))
        self.subtitle_row.set_text(text("subtitle"))
        self.author_row.set_text(text("author"))
        self.author_default.set_label(defaults["author"] or "")
        self.keywords_row.set_text(text("keywords"))
        self._fill_choice(self.status_row, "status", list(STATUSES), [_status_name(s) for s in STATUSES], text("status"))
        self._fill_choice(self.lang_row, "lang", list(config.LANGUAGES), [language_name(c) for c in config.LANGUAGES], text("lang"))
        self._created = text("created")
        self._update_defaults_visibility()
        self._refresh_modified()
        self.set_sensitive(self.editor.path is not None)
        self._loading = False

    def _refresh_modified(self):
        path = self.editor.path
        modified, born = "", ""
        if path is not None:
            try:
                stat = os.stat(path)
                modified = _format_time(stat.st_mtime)
                birth = getattr(stat, "st_birthtime", None)
                born = _format_time(birth) if birth else ""
            except OSError:
                pass
        self.modified_row.set_subtitle(modified or "—")
        created = getattr(self, "_created", "")
        if created:
            self.created_row.set_subtitle(format_created(created))
        elif born:
            self.created_row.set_subtitle(_("%s (according to the file system)") % born)
        else:
            self.created_row.set_subtitle("—")

    def _update_defaults_visibility(self):
        # Voreinstellungen nur zeigen, solange das Feld leer ist.
        self.author_default.set_visible(not self.author_row.get_text())

    # --- Ändern ---------------------------------------------------------------

    def _set(self, key: str, value):
        self._update_defaults_visibility()
        if not self._loading:
            self.editor.set_metadata({key: value})

    def _on_choice(self, row: Adw.ComboRow, key: str):
        choices = self._choices.get(key)
        if choices and not self._loading:
            self.editor.set_metadata({key: choices[row.get_selected()]})


def _split_keywords(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]
