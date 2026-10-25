import os
from datetime import datetime
from gettext import gettext as _

from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from . import config
from .goal import DEFAULT_GOAL, MAX_GOAL, parse_goal
from .goal_ring import GoalView
from .library import add_attachment, attachments, attachments_folder, remove_empty_attachments_dir

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
    from the app preferences; only what you enter yourself goes into the file.

    The notes tab holds free notes (field "notes") and attachments: copies of files kept in a
    hidden folder next to the sheet (see library.attachments)."""

    __gsignals__ = {
        "message": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # a short notice for a toast
    }

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self._loading = False
        editor.connect("metadata-changed", lambda _e: self.refresh())
        editor.connect("saved", lambda _e: self._refresh_modified())
        editor.connect("counts-changed", self._on_counts_changed)
        self._words = 0

        # Three tabs: the sheet's details, its writing goal, and notes with attachments.
        details_page = Adw.PreferencesPage()
        goal_page = Adw.PreferencesPage()
        notes_page = self._build_notes_page()

        # Writing goal: its own section with a ring that shows progress (field "goal" in the front matter).
        goal_group = Adw.PreferencesGroup()  # the tab already names it
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
        goal_page.add(goal_group)

        text_group = Adw.PreferencesGroup(title=_("Document"))
        self.title_row = self._entry(text_group, _("Title"), "title")
        self.subtitle_row = self._entry(text_group, _("Subtitle"), "subtitle")
        self.author_row = self._entry(text_group, _("Author"), "author")
        self.author_default = Gtk.Label(css_classes=["dim-label"], ellipsize=3, max_width_chars=14)
        self.author_row.add_suffix(self.author_default)
        details_page.add(text_group)

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
        details_page.add(sort_group)

        # Display only: Typecase sets the creation date when creating a sheet; "modified" comes from the file.
        date_group = Adw.PreferencesGroup(title=_("Dates"))
        self.created_row = Adw.ActionRow(title=_("Created"), css_classes=["property"], subtitle_selectable=True)
        date_group.add(self.created_row)
        self.modified_row = Adw.ActionRow(title=_("Last Modified"), css_classes=["property"], subtitle_selectable=True)
        date_group.add(self.modified_row)
        details_page.add(date_group)

        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(details_page, "details", _("Details"), "document-properties-symbolic")
        self.stack.add_titled_with_icon(goal_page, "goal", _("Goal"), "emoji-flags-symbolic")
        self.stack.add_titled_with_icon(notes_page, "notes", _("Notes"), "document-edit-symbolic")
        saved_page = config.load().get("inspector_page")
        if saved_page in ("details", "goal", "notes"):
            self.stack.set_visible_child_name(saved_page)
        self.stack.connect("notify::visible-child-name", lambda st, _p: config.update(inspector_page=st.get_visible_child_name()))
        switcher = Adw.InlineViewSwitcher(
            stack=self.stack,
            display_mode=Adw.InlineViewSwitcherDisplayMode.LABELS,  # three tabs with icons would not fit the narrow pane
            homogeneous=False,  # each tab as wide as its label
            margin_start=12,
            margin_end=12,
            margin_bottom=6,
        )

        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title=_("Properties")))
        view = Adw.ToolbarView(content=self.stack)
        view.add_top_bar(header)
        view.add_top_bar(switcher)
        self.set_child(view)
        self._choices: dict[str, list[str]] = {}
        self.refresh()

    # --- Construction -------------------------------------------------------

    def _build_notes_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        notes_group = Adw.PreferencesGroup(title=_("Notes"), description=_("Not part of the text or the export"))
        self.notes_view = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            accepts_tab=False,
            top_margin=10,
            bottom_margin=10,
            left_margin=12,
            right_margin=12,
            css_classes=["inline"],
        )
        self.notes_view.update_property([Gtk.AccessibleProperty.LABEL], [_("Notes")])
        self.notes_view.get_buffer().connect("changed", self._on_notes_changed)
        scroller = Gtk.ScrolledWindow(
            child=self.notes_view,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            min_content_height=160,
            max_content_height=420,
            propagate_natural_height=True,
        )
        notes_group.add(Gtk.Frame(child=scroller, css_classes=["view"]))
        page.add(notes_group)

        self.attachments_group = Adw.PreferencesGroup(
            title=_("Attachments"), description=_("Copies kept next to the sheet; drop files here")
        )
        add_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add Attachment…"), valign=Gtk.Align.CENTER, css_classes=["flat"])
        add_button.connect("clicked", lambda _b: self._choose_attachments())
        self.attachments_group.set_header_suffix(add_button)
        self.attachments_empty = Adw.ActionRow(title=_("No attachments"), css_classes=["dim-label"])
        self.attachments_group.add(self.attachments_empty)
        self._attachment_rows: list[Adw.ActionRow] = []
        page.add(self.attachments_group)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_files_dropped)
        page.add_controller(drop)
        return page

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
        notes = data.get("notes", "")
        self.notes_view.get_buffer().set_text(notes if isinstance(notes, str) else "\n".join(notes))
        self.refresh_attachments()
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

    def _on_notes_changed(self, buffer):
        if not self._loading:
            self.editor.set_metadata({"notes": buffer.get_text(*buffer.get_bounds(), False)})

    # --- Attachments ----------------------------------------------------------

    def refresh_attachments(self):
        """Lists the open sheet's attachments (also after it was renamed or moved)."""
        for row in self._attachment_rows:
            self.attachments_group.remove(row)
        self._attachment_rows = []
        files = attachments(self.editor.path) if self.editor.path else []
        for path in files:
            row = Adw.ActionRow(title=path.name, title_lines=2, subtitle=_file_size(path), activatable=True, tooltip_text=_("Open"))
            row.add_prefix(Gtk.Image(gicon=_file_icon(path)))
            remove = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Move to Trash"), valign=Gtk.Align.CENTER, css_classes=["flat"])
            remove.connect("clicked", lambda _b, name=path.name: self._remove_attachment(name))
            row.add_suffix(remove)
            row.connect("activated", lambda _r, name=path.name: self._open_attachment(name))
            self.attachments_group.add(row)
            self._attachment_rows.append(row)
        self.attachments_empty.set_visible(not files)

    def _choose_attachments(self):
        if self.editor.path is None:
            return
        dialog = Gtk.FileDialog(title=_("Add Attachment"), modal=True)
        dialog.open_multiple(self.get_root(), None, self._on_attachments_chosen)

    def _on_attachments_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return  # cancelled
        self._add_files([files.get_item(i) for i in range(files.get_n_items())])

    def _on_files_dropped(self, _target, value, _x, _y):
        if self.editor.path is None:
            return False
        self._add_files(value.get_files())
        return True

    def _add_files(self, files):
        sheet = self.editor.path
        for file in files:
            path = file.get_path()
            if path is None or not Path(path).is_file():
                self.emit("message", _("Only files can be attached."))
                continue
            try:
                add_attachment(sheet, Path(path))
            except OSError as error:
                self.emit("message", _("Could not attach “%(name)s”: %(reason)s") % {"name": Path(path).name, "reason": error.strerror or error})
        self.refresh_attachments()

    def _attachment(self, name: str) -> Path | None:
        return attachments_folder(self.editor.path) / name if self.editor.path else None

    def _open_attachment(self, name: str):
        path = self._attachment(name)
        if path is not None:
            Gtk.FileLauncher(file=Gio.File.new_for_path(str(path))).launch(self.get_root(), None, None)

    def _remove_attachment(self, name: str):
        """Into the system trash, like sheets: it can be restored from there."""
        path = self._attachment(name)
        if path is None:
            return
        try:
            Gio.File.new_for_path(str(path)).trash(None)
        except GLib.Error as error:
            self.emit("message", _("Could not move to the trash: %s") % error.message)
        else:
            try:
                path.parent.rmdir()  # the sheet's folder, once empty
            except OSError:
                pass
            remove_empty_attachments_dir(self.editor.path.parent)
            self.emit("message", _("“%s” was moved to the trash.") % name)
        self.refresh_attachments()

    def _on_choice(self, row: Adw.ComboRow, key: str):
        choices = self._choices.get(key)
        if choices and not self._loading:
            self.editor.set_metadata({key: choices[row.get_selected()]})


def _file_size(path: Path) -> str:
    try:
        return GLib.format_size(path.stat().st_size)
    except OSError:
        return ""


def _file_icon(path: Path) -> Gio.Icon:
    content_type, _uncertain = Gio.content_type_guess(path.name, None)
    return Gio.content_type_get_symbolic_icon(content_type)


def _split_keywords(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]
