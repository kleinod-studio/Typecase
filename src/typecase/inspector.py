import os
from datetime import datetime
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk

from . import config
from .goal import DEFAULT_GOAL, MAX_GOAL, parse_goal
from .goal_ring import GoalView

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
    """Creation date from the front matter for display: with time if stored; unreadable values unchanged."""
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return value
    if len(value.strip()) <= 10:  # date only
        return GLib.DateTime.new_local(moment.year, moment.month, moment.day, 0, 0, 0).format("%x")
    return _format_time(moment.timestamp())


class Inspector(Adw.Bin):
    """Properties pane on the right: edit the metadata of the open sheet (front matter).

    Empty fields are removed from the front matter. Author and language only display their default
    from the app preferences; only what you enter yourself goes into the file."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self._loading = False
        editor.connect("metadata-changed", lambda _e: self.refresh())
        editor.connect("saved", lambda _e: self._refresh_modified())
        editor.connect("counts-changed", self._on_counts_changed)
        self._words = 0

        page = Adw.PreferencesPage()

        # Writing goal: its own section with a ring that shows progress (field "goal" in the front matter).
        goal_group = Adw.PreferencesGroup(title=_("Writing Goal"))
        self.goal_row = Adw.ExpanderRow(title=_("Word Goal"), show_enable_switch=True)
        self.goal_row.connect("notify::enable-expansion", lambda *_a: self._on_goal_changed())
        self.goal_spin = Adw.SpinRow(
            title=_("Words"),
            adjustment=Gtk.Adjustment(lower=1, upper=MAX_GOAL, step_increment=100, page_increment=1000, value=DEFAULT_GOAL),
        )
        self.goal_spin.connect("notify::value", lambda *_a: self._on_goal_changed())
        self.goal_row.add_row(self.goal_spin)
        goal_group.add(self.goal_row)
        self.goal_view = GoalView()
        goal_group.add(self.goal_view)
        page.add(goal_group)

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

        # Display only: Typecase sets the creation date when creating a sheet; "modified" comes from the file.
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

    # --- Construction -------------------------------------------------------

    def _entry(self, group, title: str, key: str) -> Adw.EntryRow:
        row = Adw.EntryRow(title=title)
        row.connect("changed", lambda r: self._set(key, r.get_text().strip()))
        group.add(row)
        return row

    def _fill_choice(self, row: Adw.ComboRow, key: str, values: list[str], labels: list[str], current: str):
        """Choice list: first entry = nothing specified; unknown values from the file remain selectable."""
        if current and current not in values:
            values, labels = values + [current], labels + [current]
        self._choices[key] = [""] + values
        row.set_model(Gtk.StringList.new([self._none_label(key)] + labels))
        row.set_selected(self._choices[key].index(current) if current in self._choices[key] else 0)

    def _none_label(self, key: str) -> str:
        if key == "lang":
            return _("Default (%s)") % language_name(config.sheet_defaults()["lang"])
        return _("None")

    # --- Displaying -----------------------------------------------------------

    def refresh(self):
        """Load the fields from the open sheet's front matter (without writing back)."""
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
        goal = parse_goal(data.get("goal"))
        self.goal_row.set_enable_expansion(goal is not None)
        self.goal_row.set_expanded(goal is not None)
        self.goal_spin.set_value(goal or DEFAULT_GOAL)  # suggested value for switching it on
        self._update_goal_view(animate=False)
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
        # Only show defaults while the field is empty.
        self.author_default.set_visible(not self.author_row.get_text())

    # --- Changing -------------------------------------------------------------

    def _set(self, key: str, value):
        self._update_defaults_visibility()
        if not self._loading:
            self.editor.set_metadata({key: value})

    def _on_goal_changed(self):
        self._update_goal_view()
        if not self._loading:
            enabled = self.goal_row.get_enable_expansion()
            self.editor.set_metadata({"goal": int(self.goal_spin.get_value()) if enabled else None})

    def _on_counts_changed(self, _editor, words, _characters):
        self._words = words
        self._update_goal_view()

    def _update_goal_view(self, animate: bool = True):
        enabled = self.goal_row.get_enable_expansion()
        self.goal_view.set_visible(enabled)
        if enabled:
            self.goal_view.update(self._words, int(self.goal_spin.get_value()), animate=animate)

    def _on_choice(self, row: Adw.ComboRow, key: str):
        choices = self._choices.get(key)
        if choices and not self._loading:
            self.editor.set_metadata({key: choices[row.get_selected()]})


def _split_keywords(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]
