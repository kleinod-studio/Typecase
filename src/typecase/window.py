import locale
from gettext import gettext as _
from gettext import ngettext
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, GtkSource

from . import config
from .find_bar import FindBar
from .preferences import PreferencesDialog
from .library import Node, create_group, create_sheet, rename, scan
from .search import Hit, LibrarySearch
from .sheet_editor import SheetEditor


class LibraryItem(GObject.Object):
    def __init__(self, node: Node):
        super().__init__()
        self.node = node


def _signature(nodes: list[Node]) -> tuple:
    """Struktur der Bibliothek zum Vergleichen: Pfade und ob Gruppe."""
    return tuple((node.path, node.is_group, _signature(node.children) if node.is_group else ()) for node in nodes)


def _make_store(nodes: list[Node]) -> Gio.ListStore:
    store = Gio.ListStore(item_type=LibraryItem)
    for node in nodes:
        store.append(LibraryItem(node))
    return store


class TypecaseWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        state = config.load()
        width, height = state.get("window_width"), state.get("window_height")
        if not (isinstance(width, int) and isinstance(height, int) and width >= 400 and height >= 300):
            width, height = 1000, 700
        super().__init__(title="Typecase", default_width=width, default_height=height, **kwargs)
        if state.get("window_maximized") is True:
            self.maximize()

        self.library_path: Path | None = None
        self._open_row = None  # Zeile des Blatts, das gerade im Editor offen ist
        self._ignore_selection = False
        self._library_monitors: list[Gio.FileMonitor] = []
        self._tree_check_timer = 0
        self._tree_signature: tuple = ()
        self._search = LibrarySearch()

        self._build_ui()
        self._setup_actions()
        self.editor.connect("save-failed", self._on_save_failed)
        self.editor.connect("counts-changed", self._on_counts_changed)
        self.editor.connect("external-change", self._on_external_change)
        self.connect("close-request", self._on_close_request)

        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_args: self._apply_style_scheme())
        self.apply_settings()
        self._apply_style_scheme()

        self._open_library(config.get_library_path(), restore=True)

    # --- Aufbau -----------------------------------------------------------

    def _build_ui(self):
        self.split = Adw.OverlaySplitView(min_sidebar_width=220, max_sidebar_width=320)
        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_content())
        self.set_content(self.split)

    def _build_sidebar(self):
        self.sidebar_title = Adw.WindowTitle(title=_("Library"), subtitle="")
        header = Adw.HeaderBar(title_widget=self.sidebar_title)

        choose_button = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text=_("Choose Library Folder…"),
        )
        choose_button.connect("clicked", lambda _b: self._choose_library_folder())
        header.pack_start(choose_button)

        new_menu = Gio.Menu()
        new_menu.append(_("New Sheet"), "win.new-sheet")
        new_menu.append(_("New Group"), "win.new-group")
        header.pack_end(
            Gtk.MenuButton(icon_name="list-add-symbolic", menu_model=new_menu, tooltip_text=_("New…"))
        )
        self.search_button = Gtk.ToggleButton(icon_name="system-search-symbolic", tooltip_text=_("Search Library"))
        header.pack_end(self.search_button)

        self.search_entry = Gtk.SearchEntry(placeholder_text=_("Search Library"), hexpand=True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        self.search_entry.connect("stop-search", lambda _e: self.search_bar.set_search_mode(False))
        self.search_bar = Gtk.SearchBar(child=self.search_entry)
        self.search_bar.connect_entry(self.search_entry)
        self.search_button.bind_property(
            "active", self.search_bar, "search-mode-enabled", GObject.BindingFlags.BIDIRECTIONAL
        )
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode)

        row_menu = Gio.Menu()
        creation = Gio.Menu()
        creation.append(_("New Sheet"), "win.new-sheet")
        creation.append(_("New Group"), "win.new-group")
        row_menu.append_section(None, creation)
        changes = Gio.Menu()
        changes.append(_("Rename…"), "win.rename")
        changes.append(_("Move to Trash…"), "win.delete")
        row_menu.append_section(None, changes)
        self.row_menu = Gtk.PopoverMenu(menu_model=row_menu, has_arrow=False, halign=Gtk.Align.START)

        empty = Adw.StatusPage(
            icon_name="folder-symbolic",
            title=_("No Library Yet"),
            description=_("Choose a folder. Its subfolders become groups, its .md files become sheets."),
        )
        empty_button = Gtk.Button(
            label=_("Choose Library Folder…"),
            halign=Gtk.Align.CENTER,
            css_classes=["suggested-action", "pill"],
        )
        empty_button.connect("clicked", lambda _b: self._choose_library_folder())
        empty.set_child(empty_button)

        self.tree_model = None
        self.selection = Gtk.SingleSelection(autoselect=False, can_unselect=True)
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_item_setup)
        factory.connect("bind", self._on_item_bind)
        self.selection.connect("notify::selected-item", self._on_selection_changed)
        self.list_view = Gtk.ListView(
            model=self.selection,
            factory=factory,
            single_click_activate=True,
            css_classes=["navigation-sidebar"],
        )
        self.list_view.connect("activate", self._on_row_activated)
        tree_scroller = Gtk.ScrolledWindow(child=self.list_view, vexpand=True)
        # Dauerhaft an die Liste gehängt, damit "win.…"-Aktionen beim Klick auf einen Menüpunkt gefunden werden.
        self.row_menu.set_parent(self.list_view)
        self.connect("destroy", lambda _w: self.row_menu.unparent())

        self.results = Gtk.ListBox(css_classes=["navigation-sidebar"], activate_on_single_click=True)
        self.results.connect("row-activated", lambda _list, row: self._open_hit(row.hit))
        no_results = Adw.StatusPage(
            icon_name="system-search-symbolic",
            title=_("No Results"),
            description=_("Try a different search term."),
            css_classes=["compact"],
        )

        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.add_named(empty, "empty")
        self.sidebar_stack.add_named(tree_scroller, "library")
        self.sidebar_stack.add_named(Gtk.ScrolledWindow(child=self.results, vexpand=True), "results")
        self.sidebar_stack.add_named(no_results, "no-results")

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.add_top_bar(self.search_bar)
        view.set_content(self.sidebar_stack)
        return Adw.NavigationPage(title=_("Library"), child=view)

    def _build_content(self):
        self.editor = SheetEditor()

        self.content_title = Adw.WindowTitle(title="Typecase", subtitle="")
        header = Adw.HeaderBar(title_widget=self.content_title)
        self.sidebar_button = Gtk.ToggleButton(
            icon_name="sidebar-show-symbolic",
            action_name="win.toggle-sidebar",
            tooltip_text=_("Show Sidebar"),
        )
        header.pack_start(self.sidebar_button)

        view_section = Gio.Menu()
        view_section.append(_("Writing Mode"), "win.writing-mode")
        view_section.append(_("Show Sidebar"), "win.toggle-sidebar")
        view_section.append(_("Fullscreen"), "win.fullscreen")
        help_section = Gio.Menu()
        help_section.append(_("Preferences"), "win.preferences")
        help_section.append(_("Keyboard Shortcuts"), "win.show-shortcuts")
        help_section.append(_("About Typecase"), "app.about")
        main_menu = Gio.Menu()
        main_menu.append_section(None, view_section)
        main_menu.append_section(None, help_section)
        header.pack_end(
            Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=main_menu, primary=True, tooltip_text=_("Main Menu"))
        )

        self.find_bar = FindBar(self.editor)
        self.find_bar.connect(
            "replaced",
            lambda _bar, count: self._toast(ngettext("%(count)s replacement", "%(count)s replacements", count) % {"count": count}),
        )
        self.find_bar.connect("notify::search-mode-enabled", self._on_find_bar_toggled)

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.add_top_bar(self.find_bar)
        view.set_content(self.editor)
        self.content_view = view

        # Im Schreibmodus erscheint die Kopfzeile, wenn die Maus an den oberen Rand kommt.
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_content_motion)
        view.add_controller(motion)

        self.toasts = Adw.ToastOverlay(child=view)
        return Adw.NavigationPage(title="Typecase", child=self.toasts)

    # --- Bibliothek -------------------------------------------------------

    def _choose_library_folder(self):
        dialog = Gtk.FileDialog(title=_("Choose Library Folder"), modal=True)
        if self.library_path is not None:
            dialog.set_initial_folder(Gio.File.new_for_path(str(self.library_path)))
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # Abgebrochen
        path = folder.get_path()
        if path is None:
            return
        if not self.editor.flush():
            return  # Fehlermeldung kam schon über "save-failed"; das offene Blatt bleibt.
        config.set_library_path(Path(path))
        self._open_library(Path(path))

    def _open_library(self, path: Path | None, restore: bool = False):
        self.search_bar.set_search_mode(False)
        self.library_path = path
        self._show_sheet(None)
        self._ignore_selection = True
        self.selection.set_model(None)
        self._ignore_selection = False
        self.tree_model = None
        self._unwatch_library()
        if path is None:
            self.sidebar_title.set_subtitle("")
            self.sidebar_stack.set_visible_child_name("empty")
        else:
            self.sidebar_title.set_subtitle(path.name or str(path))
            expand, last_sheet = self._restored_state(path) if restore else (set(), None)
            self._reload(select_path=last_sheet, expand=expand)
            self.sidebar_stack.set_visible_child_name("library")
            if last_sheet is not None:
                self._open_selected()
                GLib.idle_add(self.editor.focus_editor)
        self._update_actions()

    @staticmethod
    def _restored_state(library: Path) -> tuple[set[Path], Path | None]:
        """Aufgeklappte Gruppen und letztes Blatt aus der Konfiguration; unbrauchbare Einträge werden ignoriert."""
        data = config.load()

        def resolve(relative) -> Path | None:
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                return None
            return library / relative

        groups = data.get("expanded_groups")
        expand = {p for p in map(resolve, groups if isinstance(groups, list) else []) if p and p.is_dir()}
        last = resolve(data.get("last_sheet"))
        return expand, (last if last is not None and last.is_file() else None)

    def _save_state(self):
        """Merkt Fenstergröße, aufgeklappte Gruppen und das offene Blatt für den nächsten Start."""
        values = {"window_maximized": self.is_maximized()}
        if not self.is_maximized() and not self.is_fullscreen() and self.get_width() > 0 and self.get_height() > 0:
            values.update(window_width=self.get_width(), window_height=self.get_height())
        if self.library_path is not None:
            values["expanded_groups"] = sorted(str(p.relative_to(self.library_path)) for p in self._expanded_paths())
            if self.editor.path is not None:
                values["last_sheet"] = str(self.editor.path.relative_to(self.library_path))
        try:
            config.update(**values)
        except OSError:
            pass  # Der Zustand ist nur eine Annehmlichkeit; ein Fehler darf nichts blockieren.

    def _reload(
        self,
        select_path: Path | None = None,
        renamed: tuple[Path, Path] | None = None,
        expand: set[Path] | None = None,
    ):
        """Liest die Bibliothek neu ein und behält aufgeklappte Gruppen, das offene Blatt und die Auswahl.
        renamed=(alt, neu) überträgt den Zustand von einem umbenannten Pfad auf den neuen."""
        expanded = self._expanded_paths() | (expand or set())
        if renamed is not None:
            old, new = renamed
            expanded = {new / p.relative_to(old) if p == old or old in p.parents else p for p in expanded}
        if select_path is None:
            node = self._selected_node()
            select_path = node.path if node else self.editor.path
        if select_path is not None:
            expanded.update(p for p in select_path.parents if p != self.library_path)

        self._ignore_selection = True
        nodes = scan(self.library_path)
        self._tree_signature = _signature(nodes)
        self._watch_library(nodes)
        root = _make_store(nodes)
        self.tree_model = Gtk.TreeListModel.new(root, False, False, self._create_children)
        self.selection.set_model(self.tree_model)
        i = 0
        while i < self.tree_model.get_n_items():  # Klappt auf; Kinder rutschen hinter ihre Gruppe nach.
            row = self.tree_model.get_item(i)
            node = row.get_item().node
            if node.is_group and node.path in expanded:
                row.set_expanded(True)
            i += 1

        open_index = self._index_of(self.editor.path)
        self._open_row = self.tree_model.get_item(open_index) if open_index is not None else None
        if self.editor.path is not None:
            self.content_title.set_title(self.editor.path.stem)
        select_index = self._index_of(select_path)
        self.selection.set_selected(Gtk.INVALID_LIST_POSITION if select_index is None else select_index)
        self._ignore_selection = False
        if select_index is not None:
            self.list_view.scroll_to(select_index, Gtk.ListScrollFlags.NONE, None)
        self._update_actions()

    # --- Bibliothek beobachten (Änderungen von außen) ----------------------

    def _watch_library(self, nodes: list[Node]):
        """Beobachtet den Stammordner und alle Gruppen; Gio beobachtet nicht rekursiv."""
        self._unwatch_library()
        folders = [self.library_path]
        stack = list(nodes)
        while stack:
            node = stack.pop()
            if node.is_group:
                folders.append(node.path)
                stack.extend(node.children)
        for folder in folders:
            try:
                monitor = Gio.File.new_for_path(str(folder)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
            except GLib.Error:
                continue
            monitor.connect("changed", self._on_library_event)
            self._library_monitors.append(monitor)

    def _unwatch_library(self):
        for monitor in self._library_monitors:
            monitor.cancel()
        self._library_monitors = []
        if self._tree_check_timer:
            GLib.source_remove(self._tree_check_timer)
            self._tree_check_timer = 0

    def _on_library_event(self, _monitor, file, other, _event):
        names = [f.get_basename() for f in (file, other) if f is not None]
        if names and all(name.startswith(".") for name in names):
            return  # versteckte Dateien, z. B. unsere eigenen Temp-Dateien beim Speichern
        if self._tree_check_timer:
            GLib.source_remove(self._tree_check_timer)
        self._tree_check_timer = GLib.timeout_add(300, self._check_tree)

    def _check_tree(self):
        self._tree_check_timer = 0
        if self.library_path is not None and _signature(scan(self.library_path)) != self._tree_signature:
            self._reload()  # nur wenn sich Gruppen oder Blätter wirklich geändert haben
        return GLib.SOURCE_REMOVE

    def _on_external_change(self, _editor, kind):
        name = self.editor.path.stem if self.editor.path else ""
        if kind == "reloaded":
            self._toast(_("“%s” was changed outside Typecase and reloaded.") % name)
        elif kind == "deleted":
            self._show_sheet(None)
            self._reload()
            self._toast(_("“%s” was deleted outside Typecase.") % name)
        elif kind == "restored":
            self._toast(_("“%s” was deleted outside Typecase. Your version was saved again.") % name)
            self._check_tree()
        elif kind == "conflict":
            self._ask_conflict(name)

    def _ask_conflict(self, name: str):
        dialog = Adw.AlertDialog(
            heading=_("Sheet Changed Elsewhere"),
            body=_(
                "“%s” was changed outside Typecase while you were writing. "
                "Which version should stay in the sheet? The other one is kept as a copy next to it."
            )
            % name,
        )
        dialog.add_response("theirs", _("Load Other Version"))
        dialog.add_response("mine", _("Keep My Version"))
        dialog.set_response_appearance("mine", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("mine")
        dialog.set_close_response("mine")  # Escape behält die eigene Fassung; beide bleiben erhalten
        dialog.connect("response", self._on_conflict_response)
        dialog.present(self)

    def _on_conflict_response(self, _dialog, response):
        if not self.editor.in_conflict:
            return  # schon entschieden (der Dialog meldet sich beim Schließen ggf. ein zweites Mal)
        try:
            copy = self.editor.resolve_conflict(keep_mine=response == "mine")
        except UnicodeDecodeError:
            # Die fremde Fassung ist kein Text mehr; unsere liegt sicher in der Kopie.
            self._show_sheet(None)
            self._reload()
            self._toast(_("The other version is not a UTF-8 text file. Your version was saved as a copy."))
            return
        except OSError as error:
            # Noch nichts entschieden; erneut fragen, statt im Konflikt hängen zu bleiben.
            self._toast(_("Could not save: %s") % (error.strerror or error))
            self._ask_conflict(self.editor.path.stem)
            return
        self._reload()
        if copy is not None:
            self._toast(_("The other version was kept as “%s”.") % copy.stem)

    def _expanded_paths(self) -> set[Path]:
        paths: set[Path] = set()
        if self.tree_model is not None:
            for i in range(self.tree_model.get_n_items()):
                row = self.tree_model.get_item(i)
                if row.get_expanded():
                    paths.add(row.get_item().node.path)
        return paths

    def _index_of(self, path: Path | None) -> int | None:
        if path is None or self.tree_model is None:
            return None
        for i in range(self.tree_model.get_n_items()):
            if self.tree_model.get_item(i).get_item().node.path == path:
                return i
        return None

    @staticmethod
    def _create_children(item: LibraryItem):
        return _make_store(item.node.children) if item.node.is_group else None

    # --- Blätter öffnen ---------------------------------------------------

    def _on_selection_changed(self, _selection, _pspec):
        self._update_actions()
        if not self._ignore_selection:
            self._open_selected()

    def _open_selected(self):
        row = self.selection.get_selected_item()
        if row is None or row is self._open_row:
            return
        node = row.get_item().node
        if node.is_group:
            return
        if node.path == self.editor.path:
            self._open_row = row
            return

        if not self.editor.flush():
            self._reselect(self._open_row)  # Wechsel verweigert, bisheriges Blatt bleibt offen.
            return
        try:
            self.editor.open(node.path)
        except (OSError, UnicodeDecodeError) as error:
            reason = error.strerror if isinstance(error, OSError) else _("not a UTF-8 text file")
            self.toasts.add_toast(
                Adw.Toast(title=_("Could not open “%(name)s”: %(reason)s") % {"name": node.name, "reason": reason})
            )
            self._reselect(self._open_row)
            return
        self._show_sheet(row)

    def _on_row_activated(self, _list_view, position):
        row = self.tree_model.get_item(position)
        node = row.get_item().node
        if not node.is_group and self.editor.path == node.path:
            self.editor.focus_editor()

    def _show_sheet(self, row):
        """Übernimmt den Zustand nach dem Öffnen (row) oder Schließen (None) eines Blatts."""
        if row is None:
            self.editor.close_sheet()
            self.content_title.set_title("Typecase")
        else:
            self.content_title.set_title(row.get_item().node.name)
        self._open_row = row
        if row is not None:
            self._save_state()

    def _reselect(self, row):
        self._ignore_selection = True
        position = Gtk.INVALID_LIST_POSITION
        if row is not None:
            for i in range(self.tree_model.get_n_items()):
                if self.tree_model.get_item(i) is row:
                    position = i
                    break
        self.selection.set_selected(position)
        self._ignore_selection = False

    def _on_counts_changed(self, _editor, words, characters):
        if self.editor.path is None:
            self.content_title.set_subtitle("")
            return

        def number(n):
            return locale.format_string("%d", n, grouping=True)  # 1.234 statt 1234

        self.content_title.set_subtitle(
            ngettext("%(count)s word", "%(count)s words", words) % {"count": number(words)}
            + " · "
            + ngettext("%(count)s character", "%(count)s characters", characters) % {"count": number(characters)}
        )

    def _on_save_failed(self, _editor, message):
        self.toasts.add_toast(Adw.Toast(title=_("Could not save: %s") % message, priority=Adw.ToastPriority.HIGH))

    def _on_close_request(self, _window):
        if self.editor.flush():
            self._save_state()
            return False
        dialog = Adw.AlertDialog(
            heading=_("Could Not Save"),
            body=_("The latest changes to this sheet could not be saved. Closing now would lose them."),
        )
        dialog.add_response("cancel", _("Keep Editing"))
        dialog.add_response("discard", _("Close Without Saving"))
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_close_dialog_response)
        dialog.present(self)
        return True

    def _on_close_dialog_response(self, _dialog, response):
        if response == "discard":
            self._save_state()
            self.editor.close_sheet()
            self.close()

    # --- Neu, Umbenennen, Löschen -----------------------------------------

    def _setup_actions(self):
        handlers = {
            "new-sheet": self._on_new_sheet,
            "new-group": self._on_new_group,
            "rename": self._on_rename,
            "delete": self._on_delete,
        }
        for name, handler in handlers.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

        # An Eigenschaften gekoppelt: Menü zeigt ein Häkchen, und der Zustand bleibt stimmig,
        # auch wenn der Fenstermanager das Vollbild selbst beendet.
        self.add_action(Gio.PropertyAction.new("toggle-sidebar", self.split, "show-sidebar"))
        self.add_action(Gio.PropertyAction.new("fullscreen", self, "fullscreened"))

        writing = Gio.SimpleAction.new_stateful("writing-mode", None, GLib.Variant.new_boolean(False))
        writing.connect("change-state", self._on_writing_mode_changed)
        self.add_action(writing)
        self._before_writing = (True, False)  # Seitenleiste sichtbar, Vollbild – zum Wiederherstellen
        escape = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        escape.connect("key-pressed", self._on_window_key)
        self.add_controller(escape)

        for name, replace in [("find", False), ("replace", True)]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, r=replace: self._find_in_sheet(r))
            self.add_action(action)

        search = Gio.SimpleAction.new("search", None)
        search.connect("activate", lambda _a, _p: self._start_search())
        self.add_action(search)

        preferences = Gio.SimpleAction.new("preferences", None)
        preferences.connect("activate", lambda _a, _p: PreferencesDialog(self.apply_settings).present(self))
        self.add_action(preferences)

        shortcuts = Gio.SimpleAction.new("show-shortcuts", None)
        shortcuts.connect("activate", lambda _a, _p: self._show_shortcuts())
        self.add_action(shortcuts)

    # --- Volltextsuche ------------------------------------------------------

    def _start_search(self):
        if self.library_path is None:
            return
        if self.writing_mode:
            self.lookup_action("writing-mode").change_state(GLib.Variant.new_boolean(False))
        self.split.set_show_sidebar(True)
        self.search_bar.set_search_mode(True)
        self.search_entry.grab_focus()
        self.search_entry.select_region(0, -1)

    def _on_search_mode(self, bar, _pspec):
        if bar.get_search_mode():
            if self.library_path is None:
                bar.set_search_mode(False)
            return
        self.search_entry.set_text("")
        self._show_library_page()

    def _show_library_page(self):
        self.sidebar_stack.set_visible_child_name("library" if self.library_path else "empty")

    def _on_search_changed(self, entry):
        query = entry.get_text()
        if not query.strip() or self.library_path is None:
            self._show_library_page()
            return
        overrides = {self.editor.path: self.editor.text()} if self.editor.path else {}
        hits = self._search.search(self.library_path, query, overrides)
        self.results.remove_all()
        for hit in hits[:200]:
            self.results.append(self._result_row(hit))
        self.sidebar_stack.set_visible_child_name("results" if hits else "no-results")

    def _on_search_activate(self, _entry):
        first = self.results.get_row_at_index(0)
        if first is not None and self.sidebar_stack.get_visible_child_name() == "results":
            self._open_hit(first.hit)

    def _result_row(self, hit: Hit) -> Gtk.ListBoxRow:
        meta = [hit.group] if hit.group else []
        if hit.count:
            meta.append(ngettext("%(count)s match", "%(count)s matches", hit.count) % {"count": hit.count})
        start, end = hit.snippet_match
        snippet = (
            GLib.markup_escape_text(hit.snippet[:start])
            + "<b>" + GLib.markup_escape_text(hit.snippet[start:end]) + "</b>"
            + GLib.markup_escape_text(hit.snippet[end:])
        )
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6)
        box.append(Gtk.Label(label=hit.name, xalign=0, ellipsize=3, css_classes=["heading"]))
        if meta:
            box.append(Gtk.Label(label=" · ".join(meta), xalign=0, ellipsize=3, css_classes=["caption", "dim-label"]))
        if hit.snippet:
            box.append(
                Gtk.Label(label=snippet, use_markup=True, xalign=0, wrap=True, lines=2, ellipsize=3, css_classes=["caption"])
            )
        row = Gtk.ListBoxRow(child=box)
        row.hit = hit
        return row

    def _open_hit(self, hit: Hit):
        if self.editor.path != hit.path:
            if not self.editor.flush():
                return
            self._reload(select_path=hit.path)
            self._open_selected()
            if self.editor.path != hit.path:
                return  # Öffnen fehlgeschlagen; die Meldung kam schon
        if hit.offset >= 0:
            start, end = hit.snippet_match
            self.find_bar.open(hit.snippet[start:end], focus=False)  # alle Fundstellen im Blatt hervorheben
            self.editor.show_match(hit.offset, end - start)
        self.editor.focus_editor()

    def _find_in_sheet(self, replace: bool):
        if self.editor.path is None:
            return
        self.find_bar.open(replace=replace)

    def _on_find_bar_toggled(self, bar, _pspec):
        if self.writing_mode:
            self.content_view.set_reveal_top_bars(bar.get_search_mode())

    # --- Schreibmodus -------------------------------------------------------

    @property
    def writing_mode(self) -> bool:
        return self.lookup_action("writing-mode").get_state().get_boolean()

    def _on_writing_mode_changed(self, action, value):
        on = value.get_boolean()
        if on == self.writing_mode:
            return
        action.set_state(value)
        if on:
            self._before_writing = (self.split.get_show_sidebar(), self.is_fullscreen())
            self.split.set_show_sidebar(False)
            self.content_view.set_extend_content_to_top_edge(True)  # Kopfzeile legt sich über den Text
            self.content_view.set_reveal_top_bars(False)
            self.fullscreen()
            self.editor.focus_editor()
        else:
            sidebar, was_fullscreen = self._before_writing
            self.content_view.set_reveal_top_bars(True)
            self.content_view.set_extend_content_to_top_edge(False)
            self.split.set_show_sidebar(sidebar)
            if not was_fullscreen:
                self.unfullscreen()

    def _on_content_motion(self, _controller, _x, y):
        if not self.writing_mode:
            return
        if y < 8:
            self.content_view.set_reveal_top_bars(True)
        elif y > 120 and not self.find_bar.get_search_mode():
            self.content_view.set_reveal_top_bars(False)

    def _on_window_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape and self.writing_mode and self.get_visible_dialog() is None:
            self.lookup_action("writing-mode").change_state(GLib.Variant.new_boolean(False))
            return True
        return False

    def _show_shortcuts(self):
        dialog = Adw.ShortcutsDialog()
        for title, items in [
            (
                _("Library"),
                [
                    (_("New Sheet"), "<Primary>n"),
                    (_("New Group"), "<Primary><Shift>n"),
                    (_("Rename"), "F2"),
                    (_("Search Library"), "<Primary><Shift>f"),
                ],
            ),
            (
                _("Editor"),
                [
                    (_("Undo"), "<Primary>z"),
                    (_("Redo"), "<Primary><Shift>z"),
                    (_("New Line Without List Marker"), "<Shift>Return"),
                    (_("Indent List Item"), "Tab"),
                    (_("Outdent List Item"), "<Shift>Tab"),
                    (_("Find"), "<Primary>f"),
                    (_("Find and Replace"), "<Primary>h"),
                    (_("Next / Previous Match"), "Return <Shift>Return"),
                ],
            ),
            (
                _("Window"),
                [
                    (_("Writing Mode"), "<Primary><Shift>Return"),
                    (_("Leave Writing Mode"), "Escape"),
                    (_("Show Sidebar"), "F9 <Primary><Shift>l"),
                    (_("Fullscreen"), "F11"),
                    (_("Preferences"), "<Primary>comma"),
                    (_("Keyboard Shortcuts"), "<Primary>question"),
                    (_("Quit"), "<Primary>q"),
                ],
            ),
        ]:
            section = Adw.ShortcutsSection(title=title)
            for label, accelerator in items:
                section.add(Adw.ShortcutsItem(title=label, accelerator=accelerator))
            dialog.add(section)
        dialog.present(self)

    def _update_actions(self):
        has_library = self.library_path is not None
        has_selection = has_library and self._selected_node() is not None
        for name, enabled in [
            ("new-sheet", has_library),
            ("new-group", has_library),
            ("rename", has_selection),
            ("delete", has_selection),
        ]:
            self.lookup_action(name).set_enabled(enabled)

    def _selected_node(self) -> Node | None:
        row = self.selection.get_selected_item()
        return row.get_item().node if row is not None else None

    def _target_folder(self) -> Path:
        """Ausgewählte Gruppe, bei einem Blatt dessen Gruppe, sonst der Stammordner."""
        node = self._selected_node()
        if node is None:
            return self.library_path
        return node.path if node.is_group else node.path.parent

    def _toast(self, text: str):
        self.toasts.add_toast(Adw.Toast(title=text))

    def _on_new_sheet(self):
        if not self.editor.flush():
            return
        try:
            path = create_sheet(self._target_folder(), _("Untitled"))
        except OSError as error:
            self._toast(_("Could not create the sheet: %s") % (error.strerror or error))
            return
        self._reload(select_path=path)
        self._open_selected()
        self.editor.focus_editor()

    def _on_new_group(self):
        try:
            path = create_group(self._target_folder(), _("New Group"))
        except OSError as error:
            self._toast(_("Could not create the group: %s") % (error.strerror or error))
            return
        self._reload(select_path=path)
        self._on_rename()  # Gleich nach einem Namen fragen.

    def _on_rename(self):
        node = self._selected_node()
        if node is None:
            return
        entry = Gtk.Entry(text=node.name, activates_default=True)
        dialog = Adw.AlertDialog(heading=_("Rename Group") if node.is_group else _("Rename Sheet"))
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("rename", _("Rename"))
        dialog.set_response_appearance("rename", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("rename")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "rename" and self._do_rename(node, entry.get_text()))
        dialog.present(self)
        entry.grab_focus()
        entry.select_region(0, -1)

    def _do_rename(self, node: Node, new_name: str):
        if not self.editor.flush():
            return
        try:
            new_path = rename(node.path, new_name)
        except ValueError:
            self._toast(_("This name is not allowed."))
            return
        except FileExistsError:
            self._toast(_("“%s” already exists.") % new_name.strip())
            return
        except OSError as error:
            self._toast(_("Could not rename: %s") % (error.strerror or error))
            return
        open_path = self.editor.path
        if open_path is not None and (open_path == node.path or node.path in open_path.parents):
            self.editor.set_path(new_path / open_path.relative_to(node.path))
        self._reload(select_path=new_path, renamed=(node.path, new_path))

    def _on_delete(self):
        node = self._selected_node()
        if node is None:
            return
        dialog = Adw.AlertDialog(
            heading=_("Move “%s” to the Trash?") % node.name,
            body=_("The group and everything in it will be moved to the trash.")
            if node.is_group
            else _("The sheet will be moved to the trash."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Move to Trash"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "delete" and self._do_delete(node))
        dialog.present(self)

    def _do_delete(self, node: Node):
        if not self.editor.flush():
            return
        try:
            Gio.File.new_for_path(str(node.path)).trash(None)
        except GLib.Error as error:
            self._toast(_("Could not move to the trash: %s") % error.message)
            return
        open_path = self.editor.path
        if open_path is not None and (open_path == node.path or node.path in open_path.parents):
            self._show_sheet(None)
        self._reload()

    # --- Seitenleisten-Zeilen ---------------------------------------------

    def _on_item_setup(self, _factory, list_item):
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)  # 3 = Pango.EllipsizeMode.END
        box = Gtk.Box(spacing=8)
        box.append(icon)
        box.append(label)
        expander = Gtk.TreeExpander(child=box)
        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self._on_row_right_click, list_item)
        expander.add_controller(right_click)
        list_item.set_child(expander)

    def _on_row_right_click(self, gesture, _n_press, x, y, list_item):
        position = list_item.get_position()
        if position == Gtk.INVALID_LIST_POSITION:
            return
        self.selection.set_selected(position)
        if self.selection.get_selected() != position:
            return  # Auswahl wurde verweigert (Speicherfehler), kein Menü für das falsche Blatt.
        point = gesture.get_widget().translate_coordinates(self.list_view, x, y)
        if point is None:
            return
        list_x, list_y = point
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(list_x), int(list_y), 1, 1
        self.row_menu.set_pointing_to(rect)
        self.row_menu.popup()

    def _on_item_bind(self, _factory, list_item):
        row = list_item.get_item()
        node = row.get_item().node
        expander = list_item.get_child()
        expander.set_list_row(row)
        box = expander.get_child()
        icon, label = box.get_first_child(), box.get_last_child()
        icon.set_from_icon_name("folder-symbolic" if node.is_group else "text-x-generic-symbolic")
        label.set_text(node.name)

    # --- Darstellung ------------------------------------------------------

    def apply_settings(self):
        """Wendet die gespeicherten Einstellungen an (beim Start und bei jeder Änderung im Dialog)."""
        current = config.settings()
        self.editor.set_appearance(
            font_family=current["editor_font"],
            font_size_pt=current["editor_font_size"],
            line_width_chars=current["line_width"],
            line_spacing=current["line_spacing"],
        )
        Adw.StyleManager.get_default().set_color_scheme(
            {
                "system": Adw.ColorScheme.DEFAULT,
                "light": Adw.ColorScheme.FORCE_LIGHT,
                "dark": Adw.ColorScheme.FORCE_DARK,
            }[current["color_scheme"]]
        )

    def _apply_style_scheme(self):
        dark = Adw.StyleManager.get_default().get_dark()
        manager = GtkSource.StyleSchemeManager.get_default()
        scheme = manager.get_scheme("Adwaita-dark" if dark else "Adwaita")
        if scheme is not None:
            self.editor.buffer.set_style_scheme(scheme)
        self.editor.styler.set_dark(dark)
