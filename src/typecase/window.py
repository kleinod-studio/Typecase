import locale
import weakref
from gettext import gettext as _
from gettext import ngettext
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from . import config
from . import export
from . import frontmatter
from . import spelling, themes
from .export_dialog import ExportDialog
from .find_bar import FindBar
from .fileio import atomic_write_text, read_text
from .goal import GoalIndex, fraction, parse_goal
from .goal_ring import GoalBadge, ProgressRing
from .group_view import GroupView
from .inspector import Inspector
from .keywords import KeywordIndex, filter_nodes
from .keywords import sheets as all_sheets
from .preferences import PreferencesDialog
from .library import Node, all_groups, attachments, attachments_folder, create_group, create_sheet, duplicate, heading_name, is_untitled, move, ordered_names, place, remove_empty_attachments_dir, rename, rename_in_order, scan, unique_path
from .search import Hit, LibrarySearch
from .sheet_editor import SheetEditor


class LibraryItem(GObject.Object):
    def __init__(self, node: Node):
        super().__init__()
        self.node = node


def _signature(nodes: list[Node]) -> tuple:
    """Structure of the library for comparison: paths and whether each is a group."""
    return tuple((node.path, node.is_group, _signature(node.children) if node.is_group else ()) for node in nodes)


_CSS_INSTALLED = False


def _install_css():
    """Look of the floating formatting bar and goal card; colours from the libadwaita scheme (light/dark)."""
    global _CSS_INSTALLED
    if _CSS_INSTALLED:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(
        """
        .format-bar {
            background-color: var(--popover-bg-color);
            color: var(--popover-fg-color);
            border-radius: 14px;
            box-shadow: 0 0 0 1px alpha(currentColor, 0.1), 0 3px 10px alpha(black, 0.2);
            margin: 6px;
        }
        .format-bar > viewport > box { padding: 4px 6px; }
        .goal-badge {
            background-color: var(--popover-bg-color);
            color: var(--popover-fg-color);
            border-radius: 14px;
            box-shadow: 0 0 0 1px alpha(currentColor, 0.1), 0 3px 10px alpha(black, 0.2);
            margin: 6px;
            padding: 8px 12px;
        }
        /* Where a dragged sheet or group lands: a line above or below the row, or the whole row. */
        treeexpander.drop-before { box-shadow: inset 0 2px 0 0 var(--accent-bg-color); }
        treeexpander.drop-after { box-shadow: inset 0 -2px 0 0 var(--accent-bg-color); }
        treeexpander.drop-into { background-color: alpha(var(--accent-bg-color), 0.15); border-radius: 6px; }
        /* Cards of a group: notes on the card's own background; where a dragged card lands. */
        .typecase-card { padding: 8px 10px 10px; }
        .typecase-card-notes, .typecase-card-notes > text { background: none; }
        .typecase-card-status { padding: 1px 8px; border-radius: 99px; background-color: alpha(currentColor, 0.1); }
        .typecase-card.drop-before { box-shadow: inset 3px 0 0 0 var(--accent-bg-color); }
        .typecase-card.drop-after { box-shadow: inset -3px 0 0 0 var(--accent-bg-color); }
        .goal-badge:hover { background-image: image(alpha(currentColor, 0.05)); }
        .goal-badge:active { background-image: image(alpha(currentColor, 0.1)); }
        """
    )
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _CSS_INSTALLED = True


def _group_paths(nodes: list[Node]):
    for node in nodes:
        if node.is_group:
            yield node.path
            yield from _group_paths(node.children)


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
        self._open_row = None  # row of the sheet currently open in the editor
        self._ignore_selection = False
        self._library_monitors: list[Gio.FileMonitor] = []
        self._tree_check_timer = 0
        self._tree_signature: tuple = ()
        self._search = LibrarySearch()
        self._keywords = KeywordIndex()
        self._goals = GoalIndex()
        self._row_rings: weakref.WeakSet[ProgressRing] = weakref.WeakSet()  # writing-goal rings of the library rows
        self._keyword_filter: str | None = None
        self._expanded_before_filter: set[Path] = set()
        self._missing_dictionaries: set[str] = set()  # languages already reported this session
        self._dragging = False  # one of our library rows is being dragged
        self._after_drag = None  # move to carry out once that drag has ended

        self._theme_css = Gtk.CssProvider()
        self._theme_css_text = ""
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self._theme_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._build_ui()
        self._setup_actions()
        self.editor.connect("save-failed", self._on_save_failed)
        self.editor.connect("counts-changed", self._on_counts_changed)
        self.editor.connect("external-change", self._on_external_change)
        self.editor.connect("dictionary-missing", self._on_dictionary_missing)
        self.editor.buffer.connect("notify::cursor-position", self._on_editor_cursor_moved)
        self.group_view.connect("dictionary-missing", self._on_dictionary_missing)
        self.group_view.connect("save-failed", self._on_save_failed)
        self.group_view.connect("counts-changed", self._on_group_counts_changed)
        self.group_view.connect("external-change", lambda _view, editor, kind: self._on_external_change(editor, kind))
        self.group_view.connect("open-sheet", lambda _view, path: self._open_sheet(Path(path)))
        self.group_view.connect("message", lambda _view, text: self._toast(text))
        self.group_view.connect("move-sheet", lambda _view, source, anchor, after: self._move_card(Path(source), Path(anchor), after))
        self.connect("close-request", self._on_close_request)

        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_args: self._apply_style_scheme())
        self.apply_settings()
        self._apply_style_scheme()

        self._open_library(config.get_library_path(), restore=True)

    # --- Layout -----------------------------------------------------------

    def _build_ui(self):
        self.split = Adw.OverlaySplitView(min_sidebar_width=260, max_sidebar_width=340)
        self.split.set_sidebar(self._build_sidebar())
        self.split.set_content(self._build_content())
        self.set_content(self.split)

        # Narrow windows (GNOME pattern): sidebars overlay the text instead of taking up space.
        self.set_size_request(360, 360)
        for condition, split in [("max-width: 1000sp", self.inspector_split), ("max-width: 640sp", self.split)]:
            breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(condition))
            breakpoint.add_setter(split, "collapsed", True)
            self.add_breakpoint(breakpoint)

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

        self.keyword_list = Gtk.ListBox(css_classes=["navigation-sidebar"], activate_on_single_click=True)
        self.keyword_list.connect("row-activated", self._on_keyword_chosen)
        keyword_popover = Gtk.Popover(child=Gtk.ScrolledWindow(
            child=self.keyword_list, propagate_natural_height=True, max_content_height=420, propagate_natural_width=True
        ))
        keyword_popover.connect("show", lambda _p: self._fill_keyword_list())
        self.keyword_button = Gtk.MenuButton(
            icon_name="tag-symbolic", tooltip_text=_("Filter by Keyword"), popover=keyword_popover
        )
        header.pack_end(self.keyword_button)

        self.filter_banner = Adw.Banner(button_label=_("Show All"))
        self.filter_banner.connect("button-clicked", lambda _b: self.set_keyword_filter(None))

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
        changes.append(_("Duplicate"), "win.duplicate")
        changes.append(_("Move Up"), "win.move-up")
        changes.append(_("Move Down"), "win.move-down")
        changes.append(_("Move to…"), "win.move")
        changes.append(_("Move to Trash…"), "win.delete")
        row_menu.append_section(None, changes)
        exporting = Gio.Menu()
        exporting.append(_("Export…"), "win.export-selection")
        row_menu.append_section(None, exporting)
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
            # No single_click_activate: that would already select when hovering with the mouse.
            css_classes=["navigation-sidebar"],
        )
        self.list_view.connect("activate", self._on_row_activated)
        # Alt+Up / Alt+Down reorder, but only while the library has the focus (in the editor the
        # keys belong to the text).
        reorder_keys = Gtk.ShortcutController()
        for accel, action in (("<Alt>Up", "win.move-up"), ("<Alt>Down", "win.move-down")):
            reorder_keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string(accel), Gtk.NamedAction.new(action)))
        self.list_view.add_controller(reorder_keys)
        tree_scroller = Gtk.ScrolledWindow(child=self.list_view, vexpand=True)
        # Dropping in the empty area below the entries: into the root folder.
        root_drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        root_drop.connect("drop", lambda _t, value, _x, _y: self._accept_drop(value, lambda: self._move(Path(value), self.library_path)))
        tree_scroller.add_controller(root_drop)
        # Attached to the list permanently, so "win.…" actions are found when a menu item is clicked.
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
        view.add_top_bar(self.filter_banner)
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
        # A group shows its sheets as one text or as cards with their notes.
        self.group_mode = Adw.ToggleGroup(visible=False)
        # Kept referenced here: PyGObject would otherwise free the toggles the group still uses.
        self._group_toggles = [
            Adw.Toggle(name="text", label=_("Text"), tooltip=_("All sheets as one text")),
            Adw.Toggle(name="cards", label=_("Cards"), tooltip=_("The notes of all sheets as cards")),
        ]
        for toggle in self._group_toggles:
            self.group_mode.add(toggle)
        self.group_mode.connect("notify::active-name", self._on_group_mode_toggled)
        header.pack_start(self.group_mode)

        file_section = Gio.Menu()
        file_section.append(_("Export…"), "win.export")
        view_section = Gio.Menu()
        view_section.append(_("Focus Mode"), "win.focus-mode")
        view_section.append(_("Cards"), "win.cards")
        if spelling.available():
            view_section.append(_("Check Spelling"), "win.spell-check")
        view_section.append(_("Show Sidebar"), "win.toggle-sidebar")
        view_section.append(_("Properties"), "win.inspector")
        view_section.append(_("Fullscreen"), "win.fullscreen")
        help_section = Gio.Menu()
        help_section.append(_("Preferences"), "win.preferences")
        help_section.append(_("Keyboard Shortcuts"), "win.show-shortcuts")
        help_section.append(_("About Typecase"), "app.about")
        main_menu = Gio.Menu()
        main_menu.append_section(None, file_section)
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
        # The formatting bar floats as a card over the text – the same in the editor and in focus mode.
        self.format_revealer = Gtk.Revealer(
            child=self._build_format_bar(),
            transition_type=Gtk.RevealerTransitionType.CROSSFADE,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.END,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        # Writing goal as a small card at the bottom right, while the properties pane is closed.
        self.goal_badge = GoalBadge()
        self.goal_revealer = Gtk.Revealer(child=self.goal_badge, transition_type=Gtk.RevealerTransitionType.CROSSFADE)
        # A sheet on its own, or all sheets of a group one after another (each still its own file).
        self.group_view = GroupView()
        self.content_stack = Gtk.Stack()
        self.content_stack.add_named(self.editor, "sheet")
        self.content_stack.add_named(self.group_view, "group")
        editor_area = Gtk.Overlay(child=self.content_stack)
        editor_area.add_overlay(self.format_revealer)
        editor_area.add_overlay(self.goal_revealer)
        editor_area.connect("get-child-position", self._place_goal_badge)
        view.set_content(editor_area)
        self.editor.connect("metadata-changed", lambda _e: self._update_format_bar())  # sheet opened/closed
        self.content_view = view

        # Properties pane on the right for the metadata (GNOME pattern: second sidebar at the end).
        self.inspector = Inspector(self.editor)
        self.inspector.connect("message", lambda _i, text: self._toast(text))
        self.inspector_split = Adw.OverlaySplitView(
            sidebar_position=Gtk.PackType.END,
            show_sidebar=False,
            # Pinned: otherwise libadwaita reveals it as soon as the window becomes wide enough at startup.
            # This way it only appears when the user opens it.
            pin_sidebar=True,
            min_sidebar_width=280,
            max_sidebar_width=360,
            sidebar=self.inspector,
            content=view,
        )
        header.pack_end(
            Gtk.ToggleButton(icon_name="sidebar-show-right-symbolic", action_name="win.inspector", tooltip_text=_("Properties"))
        )
        self.inspector_split.connect("notify::show-sidebar", self._on_inspector_toggled)

        # In focus mode, the header bar appears when the mouse reaches the top edge.
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_content_motion)
        view.add_controller(motion)

        self.toasts = Adw.ToastOverlay(child=self.inspector_split)
        return Adw.NavigationPage(title="Typecase", child=self.toasts)

    def _build_format_bar(self) -> Gtk.Widget:
        """Bar at the bottom of the editor: Markdown formatting by click, without having to know the syntax."""
        bar = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)

        def button(kind, tooltip, icon=None, label=None):
            widget = Gtk.Button(
                tooltip_text=tooltip,
                action_name="win.format",
                action_target=GLib.Variant.new_string(kind),
                css_classes=["flat"],
            )
            if icon:
                widget.set_icon_name(icon)
            else:
                widget.set_label(label)
            widget.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
            bar.append(widget)

        def separator():
            bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL, margin_start=6, margin_end=6))

        button("bold", _("Bold"), icon="format-text-bold-symbolic")
        button("italic", _("Italic"), icon="format-text-italic-symbolic")
        button("underline", _("Underline"), icon="format-text-underline-symbolic")
        button("strike", _("Strikethrough"), icon="format-text-strikethrough-symbolic")
        button("code", _("Code"), label="</>")
        button("link", _("Link"), icon="insert-link-symbolic")
        separator()
        headings = Gio.Menu()
        for level in (1, 2, 3):
            headings.append(_("Heading %d") % level, f"win.format::h{level}")
        headings.append(_("Normal Text"), "win.format::paragraph")
        heading_button = Gtk.MenuButton(label="H", tooltip_text=_("Heading"), menu_model=headings, css_classes=["flat"])
        heading_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Heading")])  # not "H"
        bar.append(heading_button)
        button("bullet", _("Bulleted List"), icon="view-list-bullet-symbolic")
        button("numbered", _("Numbered List"), icon="view-list-ordered-symbolic")
        button("quote", _("Quote"), label="“ ”")
        button("codeblock", _("Code Block"), label="{ }")
        if spelling.available():
            separator()
            spell_button = Gtk.ToggleButton(
                icon_name="tools-check-spelling-symbolic",
                action_name="win.spell-check",
                tooltip_text=_("Check Spelling (F7)"),
                css_classes=["flat"],
            )
            spell_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Check Spelling")])
            bar.append(spell_button)
        self.format_bar = bar
        # Scrollable sideways in a narrow window, instead of making the editor wider.
        _install_css()
        return Gtk.ScrolledWindow(
            css_classes=["format-bar"],
            child=bar,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_width=True,
            propagate_natural_height=True,
        )

    # --- Library ----------------------------------------------------------

    def _choose_library_folder(self):
        dialog = Gtk.FileDialog(title=_("Choose Library Folder"), modal=True)
        if self.library_path is not None:
            dialog.set_initial_folder(Gio.File.new_for_path(str(self.library_path)))
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # cancelled
        path = folder.get_path()
        if path is None:
            return
        if not self._flush():
            return  # error message already came via "save-failed"; the open sheet stays.
        config.set_library_path(Path(path))
        self._open_library(Path(path))

    def _open_library(self, path: Path | None, restore: bool = False):
        self.search_bar.set_search_mode(False)
        self._keyword_filter = None
        self.filter_banner.set_revealed(False)
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
        """Expanded groups and last sheet from the configuration; unusable entries are ignored."""
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
        """Remembers window size, expanded groups and the open sheet for the next start."""
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
            pass  # The state is only a convenience; an error must not block anything.

    def _reload(
        self,
        select_path: Path | None = None,
        renamed: tuple[Path, Path] | None = None,
        expand: set[Path] | None = None,
    ):
        """Re-reads the library and keeps expanded groups, the open sheet and the selection.
        renamed=(old, new) transfers the state from a renamed path to the new one."""
        expanded = self._expanded_paths() | (expand or set())
        if renamed is not None:
            old, new = renamed
            expanded = {new / p.relative_to(old) if p == old or old in p.parents else p for p in expanded}
        if select_path is None:
            node = self._selected_node()
            select_path = node.path if node else self._open_path()
        if select_path is not None:
            expanded.update(p for p in select_path.parents if p != self.library_path)

        self._ignore_selection = True
        nodes = scan(self.library_path)
        self._watch_library(nodes)  # watch all folders, including those currently filtered out
        nodes = self._displayed(nodes)
        if self._keyword_filter:
            expanded |= set(_group_paths(nodes))  # filtered: expand everything so the matches are visible
        self._tree_signature = _signature(nodes)
        root = _make_store(nodes)
        self.tree_model = Gtk.TreeListModel.new(root, False, False, self._create_children)
        self.selection.set_model(self.tree_model)
        i = 0
        while i < self.tree_model.get_n_items():  # Expands; children move in after their group.
            row = self.tree_model.get_item(i)
            node = row.get_item().node
            if node.is_group and node.path in expanded:
                row.set_expanded(True)
            i += 1

        if self.group_view.group is not None:
            self._refresh_group()
        open_index = self._index_of(self._open_path())
        self._open_row = self.tree_model.get_item(open_index) if open_index is not None else None
        if self.editor.path is not None:
            self.content_title.set_title(self.editor.path.stem)
        elif self.group_view.group is not None:
            self.content_title.set_title(self.group_view.group.name)
        select_index = self._index_of(select_path)
        self.selection.set_selected(Gtk.INVALID_LIST_POSITION if select_index is None else select_index)
        self._ignore_selection = False
        if select_index is not None:
            self.list_view.scroll_to(select_index, Gtk.ListScrollFlags.NONE, None)
        self._update_actions()

    # --- Watching the library (external changes) --------------------------

    def _watch_library(self, nodes: list[Node]):
        """Watches the root folder and all groups; Gio does not watch recursively."""
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
            return  # hidden files, e.g. our own temp files while saving
        if self._tree_check_timer:
            GLib.source_remove(self._tree_check_timer)
        self._tree_check_timer = GLib.timeout_add(300, self._check_tree)

    def _check_tree(self):
        self._tree_check_timer = 0
        if self.library_path is not None and _signature(self._displayed(scan(self.library_path))) != self._tree_signature:
            self._reload()  # only if groups or sheets have actually changed
        return GLib.SOURCE_REMOVE

    # --- Keyword filter -------------------------------------------------------

    def _displayed(self, nodes: list[Node]) -> list[Node]:
        """What the sidebar shows: everything, or with an active filter only matching sheets plus their groups."""
        if not self._keyword_filter:
            return nodes
        return filter_nodes(nodes, lambda node: self._keywords.has(node.path, self._keyword_filter))

    def set_keyword_filter(self, keyword: str | None):
        if keyword == self._keyword_filter or self.library_path is None:
            return
        if keyword and not self._keyword_filter:
            self._expanded_before_filter = self._expanded_paths()
        self._keyword_filter = keyword
        if keyword:
            self.filter_banner.set_title(_("Filtered by “%s”") % keyword)
            self.filter_banner.set_revealed(True)
        else:
            self.filter_banner.set_revealed(False)
            self.tree_model = None  # expanded groups as before filtering
            self._reload(expand=self._expanded_before_filter)
            return
        self._reload()

    def _fill_keyword_list(self):
        self.keyword_list.remove_all()
        summary = self._keywords.summary(scan(self.library_path)) if self.library_path else []
        if not summary:
            hint = Gtk.Label(
                label=_("No keywords yet. Add them in the properties of a sheet."),
                wrap=True, max_width_chars=28, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
                css_classes=["dim-label"],
            )
            row = Gtk.ListBoxRow(child=hint, activatable=False, selectable=False)
            row.keyword = None
            self.keyword_list.append(row)
            return
        entries = [(None, _("All Sheets"), None)] + [(word, word, count) for word, count in summary]
        for keyword, label, count in entries:
            box = Gtk.Box(spacing=12, margin_top=6, margin_bottom=6, margin_start=6, margin_end=6)
            box.append(Gtk.Image(icon_name="object-select-symbolic", opacity=1 if keyword == self._keyword_filter else 0))
            box.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            if count is not None:
                box.append(Gtk.Label(label=str(count), css_classes=["dim-label", "numeric"]))
            row = Gtk.ListBoxRow(child=box)
            row.keyword = keyword
            self.keyword_list.append(row)

    def _on_keyword_chosen(self, _list, row):
        self.keyword_button.popdown()
        self.set_keyword_filter(row.keyword)

    def _on_external_change(self, editor, kind):
        """editor: the single sheet or a section of the group view."""
        name = editor.path.stem if editor.path else ""
        if kind == "reloaded":
            self._toast(_("“%s” was changed outside Typecase and reloaded.") % name)
        elif kind == "deleted":
            if editor is self.editor:
                self._show_sheet(None)
            self._reload()  # the group view drops the sheet
            self._toast(_("“%s” was deleted outside Typecase.") % name)
        elif kind == "restored":
            self._toast(_("“%s” was deleted outside Typecase. Your version was saved again.") % name)
            self._check_tree()
        elif kind == "conflict":
            self._ask_conflict(editor)

    def _ask_conflict(self, editor: SheetEditor):
        name = editor.path.stem
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
        dialog.set_close_response("mine")  # Escape keeps our own version; both are preserved
        dialog.connect("response", self._on_conflict_response, editor)
        dialog.present(self)

    def _on_conflict_response(self, _dialog, response, editor: SheetEditor):
        if not editor.in_conflict:
            return  # already decided (the dialog may report a second time when closing)
        try:
            copy = editor.resolve_conflict(keep_mine=response == "mine")
        except UnicodeDecodeError:
            # The external version is no longer text; ours is safe in the copy.
            if editor is self.editor:
                self._show_sheet(None)
            else:
                editor.close_sheet()  # the group view leaves it out when it refreshes
            self._reload()
            self._toast(_("The other version is not a UTF-8 text file. Your version was saved as a copy."))
            return
        except OSError as error:
            # Nothing decided yet; ask again instead of getting stuck in the conflict.
            self._toast(_("Could not save: %s") % (error.strerror or error))
            self._ask_conflict(editor)
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

    # --- Opening sheets ---------------------------------------------------

    def _on_selection_changed(self, _selection, _pspec):
        self._update_actions()
        if not self._ignore_selection:
            self._open_selected()

    def _open_selected(self):
        row = self.selection.get_selected_item()
        if row is None or row is self._open_row:
            return
        node = row.get_item().node
        if node.path in (self.editor.path, self.group_view.group):
            self._open_row = row
            return

        if not self._flush():
            self._reselect(self._open_row)  # Switch refused, the previous sheet stays open.
            return
        left = self.editor.path
        if left is not None:  # the sheet left behind may still take its heading as its name
            GLib.idle_add(lambda: self._name_after_heading(left) and False)
        if node.is_group:
            self._show_group(row)
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
        self._close_group()
        self._show_sheet(row)

    def _on_row_activated(self, _list_view, position):
        row = self.tree_model.get_item(position)
        node = row.get_item().node
        if not node.is_group and self.editor.path == node.path:
            self.editor.focus_editor()
        elif node.is_group and self.group_view.group == node.path:
            self.group_view.focus_start()

    def _show_sheet(self, row):
        """Applies the state after opening (row) or closing (None) a sheet."""
        if row is None:
            self.editor.close_sheet()
            self._close_group()
            self.content_title.set_title("Typecase")
        else:
            self.content_title.set_title(row.get_item().node.name)
        self._open_row = row
        if row is not None:
            self._save_state()

    def _open_sheet(self, path: Path):
        """Opens one sheet on its own, e.g. from the header of a section in the group view."""
        self._reload(select_path=path)
        self._open_selected()
        self.editor.focus_editor()

    def _show_group(self, row):
        """Shows all sheets of a group one after another. Whatever was open is already flushed."""
        node = row.get_item().node
        self.editor.close_sheet()
        self.find_bar.set_search_mode(False)  # find and replace work on a single sheet
        failed = self.group_view.open(node.path, self._group_sheets(node.path), cards=self._cards_wanted(node.path))
        for editor in self.group_view.editors:
            self._style_editor(editor)
        self.content_stack.set_visible_child_name("group")
        self._sync_group_mode()
        self.content_title.set_title(node.name)
        self._open_row = row
        self._update_format_bar()
        self._update_export_action()
        self._update_goal_badge()
        if failed:
            self._toast(_("Could not open: %s") % ", ".join(failed))
        self._save_state()

    def _close_group(self):
        """Leaves the group view without saving (call _flush() first)."""
        if self.group_view.group is None:
            return
        self.group_view.close()
        self.content_stack.set_visible_child_name("sheet")
        self._sync_group_mode()
        self._update_format_bar()
        self._update_export_action()

    def _cards_wanted(self, group: Path) -> bool:
        return self._group_key(group) in config.load().get("card_groups", [])

    def _group_key(self, group: Path) -> str:
        return str(group.relative_to(self.library_path))

    def _remember_cards(self, group: Path, cards: bool, old: Path | None = None):
        """Stores which groups show cards (by their path in the library); old: the group's previous path."""
        keys = [key for key in config.load().get("card_groups", []) if isinstance(key, str)]
        keys = [key for key in keys if key not in (self._group_key(group), old and self._group_key(old))]
        if cards:
            keys.append(self._group_key(group))
        try:
            config.update(card_groups=sorted(keys))
        except OSError:
            pass  # only a convenience

    def _sync_group_mode(self):
        """Switch in the header bar and menu entry follow the group shown (hidden for a sheet)."""
        shown = self.group_view.group is not None
        cards = shown and self.group_view.showing_cards
        action = self.lookup_action("cards")
        action.set_enabled(shown)
        action.set_state(GLib.Variant.new_boolean(cards))
        self.group_mode.set_visible(shown)
        self.group_mode.set_active_name("cards" if cards else "text")

    def _on_group_mode_toggled(self, toggles, _pspec):
        cards = toggles.get_active_name() == "cards"
        if self.group_view.group is not None and cards != self.group_view.showing_cards:
            self.lookup_action("cards").change_state(GLib.Variant.new_boolean(cards))

    def _on_cards_changed(self, _action, value):
        """Switches the group shown between text and cards; unsaved input is saved first."""
        group = self.group_view.group
        cards = value.get_boolean()
        if group is None or cards == self.group_view.showing_cards:
            return
        if not self.group_view.flush():
            self._sync_group_mode()  # refused: the view stays as it is
            return
        had_focus = self._content_has_focus()
        failed = self.group_view.open(group, self._group_sheets(group), cards=cards)
        for editor in self.group_view.editors:
            self._style_editor(editor)
        if failed:
            self._toast(_("Could not open: %s") % ", ".join(failed))
        self._remember_cards(group, cards)
        self._sync_group_mode()
        self._update_format_bar()
        if had_focus:
            self.group_view.focus_start()

    def _content_has_focus(self) -> bool:
        focus = self.get_focus()
        return focus is not None and (focus is self.group_view or focus.is_ancestor(self.group_view))

    def _move_card(self, source: Path, anchor: Path, after: bool):
        """A card was put before or after another one: the same as moving the sheet in the library."""
        if not (self._inside_library(source) and self._inside_library(anchor)) or source == anchor or not source.exists():
            return
        if not self._flush():
            return
        try:
            target = place(source, anchor, after)
        except FileExistsError:
            self._toast(_("“%s” already exists there.") % source.name)
            return
        except OSError as error:
            self._toast(_("Could not move: %s") % (error.strerror or error))
            return
        self._reload()
        self.group_view.cards.focus_card(target)

    def _refresh_group(self):
        """Keeps the group view in step with its folder: sheets added, removed, renamed or reordered."""
        group = self.group_view.group
        if not group.is_dir():
            if self.group_view.flush():
                self._show_sheet(None)
            return
        sheets = self._group_sheets(group)
        if sheets == self.group_view.paths() or not self.group_view.flush():
            return  # unchanged, or unsaved text that must not be dropped; the next change tries again
        if self.group_view.showing_cards:
            focused = self.group_view.cards.focused_path()
            scroll = self.group_view.get_vadjustment().get_value()
            failed = self.group_view.open(group, sheets, cards=True)
            if failed:
                self._toast(_("Could not open: %s") % ", ".join(failed))
            GLib.idle_add(lambda: self.group_view.get_vadjustment().set_value(scroll) and False)
            if focused is not None:
                self.group_view.cards.focus_card(focused)
            return
        active = self.group_view.active
        active_path = active.path if active is not None else None
        had_focus = active is not None and active.view.has_focus()
        scroll = self.group_view.get_vadjustment().get_value()
        failed = self.group_view.open(group, sheets)
        for editor in self.group_view.editors:
            self._style_editor(editor)
        if failed:
            self._toast(_("Could not open: %s") % ", ".join(failed))
        GLib.idle_add(lambda: self.group_view.get_vadjustment().set_value(scroll) and False)
        editor = self.group_view.editor_for(active_path) if active_path else None
        if editor is not None:
            self.group_view.active = editor
            if had_focus:
                editor.focus_editor()

    @staticmethod
    def _group_sheets(group: Path) -> list[Path]:
        """All sheets of a group in the manual order, those in subgroups included."""
        return [sheet.path for sheet in all_sheets(scan(group))]

    def _open_path(self) -> Path | None:
        """The open sheet, or the group shown in the group view."""
        return self.editor.path or self.group_view.group

    def _flush(self) -> bool:
        """Saves the open sheet or every sheet of the group view. Whoever switches, moves or
        closes something continues only on True."""
        return self.editor.flush() and self.group_view.flush()

    def _active_editor(self) -> SheetEditor | None:
        """The editor the formatting bar acts on: the single sheet or the section with the caret."""
        if self.group_view.group is not None:
            return self.group_view.active
        return self.editor if self.editor.path is not None else None

    def _focus_text(self):
        if self.group_view.group is not None:
            self.group_view.focus_start()
        else:
            self.editor.focus_editor()

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
        self._words = words
        self._update_goal_badge()
        for ring in self._row_rings:
            if ring.path is not None:
                self._update_row_ring(ring)
        if self.editor.path is None:
            if self.group_view.group is None:
                self.content_title.set_subtitle("")
            return
        self._show_counts(words, characters, parse_goal(self.editor.metadata().get("goal")))

    def _on_group_counts_changed(self, _view, words, characters):
        if self.group_view.group is not None:
            self._show_counts(words, characters, None)

    def _show_counts(self, words: int, characters: int, goal: int | None):
        def number(n):
            return locale.format_string("%d", n, grouping=True)  # 1,234 instead of 1234

        if goal:
            word_text = ngettext("%(count)s of %(goal)s word", "%(count)s of %(goal)s words", goal) % {
                "count": number(words),
                "goal": number(goal),
            }
        else:
            word_text = ngettext("%(count)s word", "%(count)s words", words) % {"count": number(words)}
        self.content_title.set_subtitle(
            word_text
            + " · "
            + ngettext("%(count)s character", "%(count)s characters", characters) % {"count": number(characters)}
        )

    def _update_goal_badge(self, animate: bool = True):
        """Goal card at the bottom right: only with a writing goal and while the properties pane (big ring) is closed."""
        goal = parse_goal(self.editor.metadata().get("goal")) if self.editor.path is not None else None
        show = goal is not None and not self.inspector_split.get_show_sidebar()
        if goal is not None:
            self.goal_badge.update(getattr(self, "_words", 0), goal, animate=animate and self.goal_revealer.get_child_revealed())
        self.goal_revealer.set_reveal_child(show)
        self.goal_revealer.set_can_target(show)  # when hidden, no invisible click area over the text

    def _place_goal_badge(self, overlay, widget, rect):
        """Into the bottom right corner; if it gets too tight next to the formatting bar, the card moves above it."""
        if widget is not self.goal_revealer:
            return False
        width, height = overlay.get_width(), overlay.get_height()
        size = widget.get_preferred_size()[1]
        rect.width, rect.height = size.width, size.height
        rect.x = width - size.width - 12
        rect.y = height - size.height - 12
        if self.format_revealer.get_reveal_child():
            bar = self.format_revealer.get_preferred_size()[1]
            if rect.x < (width + min(bar.width, width)) / 2:
                rect.y -= bar.height
        return True

    def _on_save_failed(self, _editor, message):
        self.toasts.add_toast(Adw.Toast(title=_("Could not save: %s") % message, priority=Adw.ToastPriority.HIGH))

    def _on_close_request(self, _window):
        if self._flush():
            if self.editor.path is not None:
                self._name_after_heading(self.editor.path)
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
            self.group_view.close()
            self.close()

    # --- New, rename, delete ----------------------------------------------

    def _setup_actions(self):
        handlers = {
            "new-sheet": self._on_new_sheet,
            "new-group": self._on_new_group,
            "rename": self._on_rename,
            "duplicate": self._on_duplicate,
            "move": self._on_move_to,
            "delete": self._on_delete,
            "move-up": lambda: self._move_step(-1),
            "move-down": lambda: self._move_step(1),
            "export-selection": self._export_selection,
        }
        for name, handler in handlers.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, h=handler: h())
            self.add_action(action)

        # Bound to the properties pane: the menu shows a check mark, and the state stays consistent
        # even if the window manager ends fullscreen by itself.
        self.add_action(Gio.PropertyAction.new("toggle-sidebar", self.split, "show-sidebar"))
        self.add_action(Gio.PropertyAction.new("inspector", self.inspector_split, "show-sidebar"))
        self.add_action(Gio.PropertyAction.new("fullscreen", self, "fullscreened"))

        focus_action = Gio.SimpleAction.new_stateful("focus-mode", None, GLib.Variant.new_boolean(False))
        focus_action.connect("change-state", self._on_focus_mode_changed)
        self.add_action(focus_action)
        self._before_focus = (True, False, False)  # sidebar, fullscreen, properties pane – for restoring
        escape = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        escape.connect("key-pressed", self._on_window_key)
        self.add_controller(escape)

        for name, replace in [("find", False), ("replace", True)]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, r=replace: self._find_in_sheet(r))
            self.add_action(action)

        # Cards instead of text for the group shown; remembered per group.
        cards_action = Gio.SimpleAction.new_stateful("cards", None, GLib.Variant.new_boolean(False))
        cards_action.connect("change-state", self._on_cards_changed)
        cards_action.set_enabled(False)
        self.add_action(cards_action)

        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", lambda _a, _p: self._export())
        export_action.set_enabled(False)
        self.editor.connect("metadata-changed", lambda _e: self._update_export_action())
        self.add_action(export_action)

        # Spell checking on/off, for the editor and focus mode separately (each remembers its own).
        spell_action = Gio.SimpleAction.new_stateful("spell-check", None, GLib.Variant.new_boolean(False))
        spell_action.connect("change-state", self._on_spell_check_changed)
        spell_action.set_enabled(spelling.available())
        self.add_action(spell_action)

        format_action = Gio.SimpleAction.new("format", GLib.VariantType.new("s"))
        format_action.connect("activate", lambda _a, kind: self._apply_format(kind.get_string()))
        self.add_action(format_action)

        search = Gio.SimpleAction.new("search", None)
        search.connect("activate", lambda _a, _p: self._start_search())
        self.add_action(search)

        preferences = Gio.SimpleAction.new("preferences", None)
        preferences.connect("activate", lambda _a, _p: PreferencesDialog(self.apply_settings).present(self))
        self.add_action(preferences)

        shortcuts = Gio.SimpleAction.new("show-shortcuts", None)
        shortcuts.connect("activate", lambda _a, _p: self._show_shortcuts())
        self.add_action(shortcuts)

    def _apply_format(self, kind: str):
        editor = self._active_editor()
        if editor is not None:
            editor.apply_format(kind)

    def _update_export_action(self):
        self.lookup_action("export").set_enabled(self._open_path() is not None)

    # --- Full-text search ---------------------------------------------------

    def _start_search(self):
        if self.library_path is None:
            return
        if self.focus_mode:
            self.lookup_action("focus-mode").change_state(GLib.Variant.new_boolean(False))
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
        # Unsaved text counts too, in the single sheet and in every section of the group view.
        overrides = {editor.path: editor.text() for editor in [self.editor, *self.group_view.editors] if editor.path}
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
            if not self._flush():
                return
            self._reload(select_path=hit.path)
            self._open_selected()
            if self.editor.path != hit.path:
                return  # opening failed; the message was already shown
        if hit.offset >= 0:
            start, end = hit.snippet_match
            self.find_bar.open(hit.snippet[start:end], focus=False)  # highlight all matches in the sheet
            self.editor.show_match(hit.offset, end - start)
        self.editor.focus_editor()

    def _on_inspector_toggled(self, split, _pspec):
        """If the cursor lands in a field when revealed, select nothing: continued typing must not overwrite anything."""
        self._update_goal_badge()
        if not split.get_show_sidebar():
            return

        def deselect():
            focus = self.get_focus()
            editable = focus if isinstance(focus, Gtk.Editable) else None
            if editable is None and focus is not None and isinstance(focus.get_parent(), Gtk.Editable):
                editable = focus.get_parent()
            if editable is not None and editable.is_ancestor(self.inspector):
                position = editable.get_position()
                editable.select_region(position, position)
            return False

        GLib.idle_add(deselect)

    def _find_in_sheet(self, replace: bool):
        if self.editor.path is None:
            return
        self.find_bar.open(replace=replace)

    def _on_find_bar_toggled(self, bar, _pspec):
        if self.focus_mode:
            self.content_view.set_reveal_top_bars(bar.get_search_mode())

    # --- Focus mode --------------------------------------------------------

    @property
    def focus_mode(self) -> bool:
        return self.lookup_action("focus-mode").get_state().get_boolean()

    def _on_focus_mode_changed(self, action, value):
        on = value.get_boolean()
        if on == self.focus_mode:
            return
        action.set_state(value)
        self.apply_settings()  # focus mode can have its own font, size and style
        if on:
            self._before_focus = (self.split.get_show_sidebar(), self.is_fullscreen(), self.inspector_split.get_show_sidebar())
            # Pin: otherwise libadwaita reveals the sidebars again when fullscreen makes the window wider.
            self.split.set_pin_sidebar(True)
            self.split.set_show_sidebar(False)
            self.inspector_split.set_show_sidebar(False)
            self.content_view.set_extend_content_to_top_edge(True)  # header bar overlays the text
            self.content_view.set_reveal_top_bars(False)
            self.fullscreen()
            self._focus_text()
        else:
            sidebar, was_fullscreen, inspector = self._before_focus
            self.inspector_split.set_show_sidebar(inspector)
            self.split.set_pin_sidebar(False)
            self.content_view.set_reveal_top_bars(True)
            self.content_view.set_extend_content_to_top_edge(False)
            self.split.set_show_sidebar(sidebar)
            if not was_fullscreen:
                self.unfullscreen()

    def _spell_check_wanted(self) -> bool:
        """Editor: on unless switched off. Focus mode: off unless switched on (nothing to distract)."""
        data = config.load()
        return data.get("focus_spell_check") is True if self.focus_mode else data.get("spell_check") is not False

    def _on_spell_check_changed(self, _action, value):
        config.update(**{"focus_spell_check" if self.focus_mode else "spell_check": value.get_boolean()})
        self.apply_settings()

    def _on_dictionary_missing(self, _editor_or_view, lang: str):
        if lang in self._missing_dictionaries:
            return
        self._missing_dictionaries.add(lang)
        from .inspector import language_name

        self._toast(_("No spelling dictionary for %s is installed, so spelling is not checked.") % language_name(lang))

    def _update_format_bar(self):
        self.format_revealer.set_reveal_child(self._format_bar_wanted() and self._active_editor() is not None)

    def _format_bar_wanted(self) -> bool:
        """Show the formatting bar permanently? Editor and focus mode each have their own setting."""
        data = config.load()
        return data.get("focus_format_bar" if self.focus_mode else "format_bar") is not False

    def _on_content_motion(self, _controller, _x, y):
        if not self.focus_mode:
            return
        if y < 8:
            self.content_view.set_reveal_top_bars(True)
        elif y > 120 and not self.find_bar.get_search_mode():
            self.content_view.set_reveal_top_bars(False)
        # A hidden formatting bar appears at the bottom edge, like the header bar at the top.
        if not self._format_bar_wanted():
            height = self.content_view.get_height()
            if y > height - 8:
                self.format_revealer.set_reveal_child(self._active_editor() is not None)
            elif y < height - 120:
                self.format_revealer.set_reveal_child(False)

    def _on_window_key(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape and self.focus_mode and self.get_visible_dialog() is None:
            self.lookup_action("focus-mode").change_state(GLib.Variant.new_boolean(False))
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
                    (_("Move Up"), "<Alt>Up"),
                    (_("Move Down"), "<Alt>Down"),
                    (_("Move Card"), "<Alt>Left <Alt>Right"),
                    (_("Search Library"), "<Primary><Shift>f"),
                ],
            ),
            (
                _("Editor"),
                [
                    (_("Undo"), "<Primary>z"),
                    (_("Redo"), "<Primary><Shift>z"),
                    (_("New Line Without List Marker"), "<Shift>Return"),
                    (_("Export"), "<Primary>e"),
                    (_("Bold"), "<Primary>b"),
                    (_("Italic"), "<Primary>i"),
                    (_("Underline"), "<Primary>u"),
                    (_("Link"), "<Primary>k"),
                    (_("Heading 1 / 2 / 3"), "<Primary>1 <Primary>2 <Primary>3"),
                    (_("Normal Text"), "<Primary>0"),
                    (_("Indent List Item"), "Tab"),
                    (_("Outdent List Item"), "<Shift>Tab"),
                    (_("Find"), "<Primary>f"),
                    (_("Find and Replace"), "<Primary>h"),
                    (_("Check Spelling"), "F7"),
                    (_("Next / Previous Match"), "Return <Shift>Return"),
                ],
            ),
            (
                _("Window"),
                [
                    (_("Focus Mode"), "<Primary><Shift>Return"),
                    (_("Group as Text or Cards"), "<Primary><Alt>c"),
                    (_("Leave Focus Mode"), "Escape"),
                    (_("Show Sidebar"), "F9 <Primary><Shift>l"),
                    (_("Properties"), "<Alt>Return"),
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
            ("duplicate", has_selection),
            ("move", has_selection),
            ("delete", has_selection),
            ("move-up", has_selection),
            ("move-down", has_selection),
            ("export-selection", has_selection),
        ]:
            self.lookup_action(name).set_enabled(enabled)

    def _selected_node(self) -> Node | None:
        row = self.selection.get_selected_item()
        return row.get_item().node if row is not None else None

    def _target_folder(self) -> Path:
        """Selected group; for a sheet, its group; otherwise the root folder."""
        node = self._selected_node()
        if node is None:
            return self.library_path
        return node.path if node.is_group else node.path.parent

    # --- Export -------------------------------------------------------------

    def _export(self):
        if self.group_view.group is not None:
            self._export_group(self.group_view.group)
            return
        if self.editor.path is None:
            return
        data = self.editor.metadata()
        defaults = config.sheet_defaults()
        # Defaults apply only to fields that the sheet does not set itself.
        missing = {
            "author": None if data.get("author") else defaults["author"],
            "lang": None if data.get("lang") else defaults["lang"],
            # $date$ in templates: the date of the export, if the sheet has no "date" of its own
            "date": None if data.get("date") else export.export_date(),
        }
        dialog = ExportDialog(self.editor.file_text(), self.editor.path, data.get("title") or None, missing, self._on_exported)
        dialog.present(self)

    def _export_selection(self):
        """Context menu "Export…": a group as one document, a sheet as usual."""
        node = self._selected_node()
        if node is None:
            return
        if not node.is_group:
            self._export()
            return
        self._export_group(node.path)

    def _export_group(self, group: Path):
        """All sheets of a group as one document."""
        if not self._flush():  # export what is on disk, including what was just typed
            return
        sheets = self._group_sheets(group)
        if not sheets:
            self._toast(_("This group has no sheets to export."))
            return
        defaults = config.sheet_defaults()
        missing = {"author": defaults["author"], "lang": defaults["lang"], "date": export.export_date()}
        # A virtual sheet path inside the group: the group's name for the file, its folder for resources.
        virtual = group / f"{group.name}.md"
        dialog = ExportDialog(
            export.combine_sheets(sheets),
            virtual,
            group.name,
            missing,
            self._on_exported,
            editable_title=True,
            page_break_text=export.combine_sheets(sheets, page_breaks=True) if export.has_subgroups(sheets) else None,
        )
        dialog.present(self)

    def _on_exported(self, output: Path | None, error: str | None):
        if error is not None:
            alert = Adw.AlertDialog(heading=_("Export Failed"), body=error)
            alert.add_response("close", _("Close"))
            alert.present(self)
            return
        toast = Adw.Toast(title=_("Exported “%s”") % output.name, button_label=_("Open"))
        toast.connect("button-clicked", lambda _t: Gtk.FileLauncher(file=Gio.File.new_for_path(str(output))).launch(self, None, None))
        self.toasts.add_toast(toast)

    def _toast(self, text: str):
        self.toasts.add_toast(Adw.Toast(title=text))

    def _on_new_sheet(self):
        if not self._flush():
            return
        self.set_keyword_filter(None)  # otherwise the new sheet (without a keyword) would be invisible
        try:
            path = create_sheet(self._target_folder(), _("Untitled"))
            # Creation date written once into the front matter; that way it survives sync and copying.
            atomic_write_text(path, frontmatter.update(None, {"created": GLib.DateTime.new_now_local().format("%Y-%m-%dT%H:%M")}))
        except OSError as error:
            self._toast(_("Could not create the sheet: %s") % (error.strerror or error))
            return
        self._reload(select_path=path)
        self._open_selected()
        self.editor.focus_editor()

    def _on_new_group(self):
        self.set_keyword_filter(None)
        try:
            path = create_group(self._target_folder(), _("New Group"))
        except OSError as error:
            self._toast(_("Could not create the group: %s") % (error.strerror or error))
            return
        self._reload(select_path=path)
        self._on_rename()  # Ask for a name right away.

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
        if not self._flush():
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
        try:
            rename_in_order(node.path.parent, node.path.name, new_path.name)
        except OSError:
            pass  # the order file is a convenience; the rename itself has worked
        self._follow_rename(node.path, new_path)
        self._reload(select_path=new_path, renamed=(node.path, new_path))

    def _on_editor_cursor_moved(self, buffer, _pspec):
        """The caret has left the heading an untitled sheet starts with: the heading becomes its name."""
        path = self.editor.path
        if path is None or not self._is_untitled(path):
            return
        _found, end = buffer.get_iter_at_line(50)  # the heading is at the start; no need to copy a long text
        found = heading_name(buffer.get_text(buffer.get_start_iter(), end, True))
        if found is not None and buffer.get_iter_at_mark(buffer.get_insert()).get_line() != found[1]:
            GLib.idle_add(lambda: self._name_after_heading(path) and False)  # not while GTK moves the caret

    def _is_untitled(self, path: Path) -> bool:
        return path.suffix == ".md" and is_untitled(path.stem, (_("Untitled"), "Untitled"))

    def _name_after_heading(self, path: Path) -> bool:
        """A sheet that still has its automatic name ("Untitled") is named after the heading its
        text starts with – only once: with a real name it is never renamed automatically again.
        Returns True if it was renamed."""
        if not (self._inside_library(path) and self._is_untitled(path)):
            return False
        if path == self.editor.path and not self.editor.flush():
            return False
        try:
            found = heading_name(frontmatter.split(read_text(path))[1])
        except (OSError, UnicodeDecodeError):
            return False
        if found is None:
            return False
        name = unique_path(path.parent, found[0], ".md").stem  # "Chapter 2" if "Chapter" exists
        try:
            new_path = rename(path, name)
        except (ValueError, OSError):
            return False  # it simply stays "Untitled"; renaming by hand still works
        try:
            rename_in_order(path.parent, path.name, new_path.name)
        except OSError:
            pass
        selected = self._selected_node()
        self._follow_rename(path, new_path)
        self._reload(select_path=new_path if selected is not None and selected.path == path else None, renamed=(path, new_path))
        return True

    def _on_duplicate(self):
        """A copy of the selected sheet or group right below it; the copy is then selected."""
        node = self._selected_node()
        if node is None or not self._flush():  # copy what was just typed, too
            return
        try:
            # Translators: name of a duplicated sheet or group, e.g. "Chapter 1 (Copy)"
            copy = duplicate(node.path, _("%(name)s (Copy)") % {"name": node.name})
        except OSError as error:
            self._toast(_("Could not duplicate: %s") % (error.strerror or error))
            return
        self._reload(select_path=copy)
        self._open_selected()

    def _on_delete(self):
        node = self._selected_node()
        if node is None:
            return
        dialog = Adw.AlertDialog(
            heading=_("Move “%s” to the Trash?") % node.name,
            body=_("The group and everything in it will be moved to the trash.")
            if node.is_group
            else _("The sheet and its attachments will be moved to the trash.")
            if attachments(node.path)
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
        if not self._flush():
            return
        try:
            Gio.File.new_for_path(str(node.path)).trash(None)
        except GLib.Error as error:
            self._toast(_("Could not move to the trash: %s") % error.message)
            return
        folder = attachments_folder(node.path)
        if not node.is_group and folder.is_dir():
            # The attachments go along into the trash; if that fails they simply stay where they are.
            try:
                Gio.File.new_for_path(str(folder)).trash(None)
            except GLib.Error:
                pass
            remove_empty_attachments_dir(node.path.parent)
        open_path = self._open_path()
        if open_path is not None and (open_path == node.path or node.path in open_path.parents):
            self._show_sheet(None)
        self._reload()

    # --- Sidebar rows -----------------------------------------------------

    def _on_item_setup(self, _factory, list_item):
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)  # 3 = Pango.EllipsizeMode.END
        ring = ProgressRing(16, 3, visible=False, margin_end=6)  # writing goal of the sheet
        ring.path = None
        self._row_rings.add(ring)
        box = Gtk.Box(spacing=8)
        box.append(icon)
        box.append(label)
        box.append(ring)
        expander = Gtk.TreeExpander(child=box)
        drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        drag.connect("prepare", self._on_drag_prepare, list_item)
        drag.connect("drag-begin", self._on_drag_begin, box)
        drag.connect("drag-end", self._on_drag_end)
        expander.add_controller(drag)
        drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop.connect("motion", self._on_row_drag_motion, list_item)
        drop.connect("leave", lambda target: self._show_drop_zone(target.get_widget(), None))
        drop.connect("drop", self._on_row_drop, list_item)
        expander.add_controller(drop)

        left_click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        left_click.connect("released", self._on_row_clicked, list_item)
        expander.add_controller(left_click)
        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", self._on_row_right_click, list_item)
        expander.add_controller(right_click)
        list_item.set_child(expander)

    # --- Moving (drag and drop, "Move to…") -----------------------------------

    def _on_drag_prepare(self, _source, _x, _y, list_item):
        row = list_item.get_item()
        if row is None:
            return None
        return Gdk.ContentProvider.new_for_value(str(row.get_item().node.path))

    def _on_drag_begin(self, source, _drag, box):
        self._dragging = True
        source.set_icon(Gtk.WidgetPaintable(widget=box), 0, 0)

    def _on_drag_end(self, _source, _drag, _delete):
        self._dragging = False
        self._run_after_drag()

    def _accept_drop(self, value: str, action) -> bool:
        """Accepts a dropped library path and moves it only after the drag has ended. Moving rebuilds
        the library list, which destroys the dragged row; doing that during the drop leaves the
        drag unfinished, and on Wayland the compositor then keeps the pointer (no window takes
        clicks any more). Dragged text that is not an entry of the library is refused."""
        path = Path(value)
        if not (self._inside_library(path) and path != self.library_path and path.exists()):
            return False
        self._after_drag = action
        if not self._dragging:  # dropped from elsewhere: there is no drag of ours to wait for
            GLib.idle_add(self._run_after_drag)
        return True

    def _run_after_drag(self):
        action, self._after_drag = self._after_drag, None
        if action is not None:
            action()
        return GLib.SOURCE_REMOVE

    def _drop_zone(self, list_item, y: float) -> str | None:
        """Upper or lower half of a sheet: before or after it. A group also has a middle zone: into it."""
        row = list_item.get_item()
        if row is None:
            return None
        height = max(1, list_item.get_child().get_height())
        if row.get_item().node.is_group:
            return "before" if y < height * 0.25 else "after" if y > height * 0.75 else "into"
        return "before" if y < height / 2 else "after"

    def _show_drop_zone(self, widget, zone: str | None):
        for name in ("before", "after", "into"):
            if name == zone:
                widget.add_css_class(f"drop-{name}")
            else:
                widget.remove_css_class(f"drop-{name}")

    def _on_row_drag_motion(self, target, _x, y, list_item):
        zone = self._drop_zone(list_item, y)
        self._show_drop_zone(target.get_widget(), zone)
        return Gdk.DragAction.MOVE if zone else 0

    def _on_row_drop(self, target, value, _x, y, list_item):
        self._show_drop_zone(target.get_widget(), None)
        row = list_item.get_item()
        zone = self._drop_zone(list_item, y)
        if row is None or zone is None:
            return False
        node = row.get_item().node
        if zone == "into":
            return self._accept_drop(value, lambda: self._move(Path(value), node.path, to_end=True))
        return self._accept_drop(value, lambda: self._place(Path(value), node.path, after=(zone == "after")))

    def _place(self, source: Path, anchor: Path, after: bool) -> bool:
        """Puts a sheet or group before or after another entry (manual order, also across groups)."""
        if not (self._inside_library(source) and source != self.library_path and self._inside_library(anchor)):
            return False
        if source == anchor or not source.exists():
            return False
        if source.is_dir() and source in anchor.parents:
            self._toast(_("A group cannot be moved into itself."))
            return False
        if not self._flush():
            return False
        try:
            target = place(source, anchor, after)
        except FileExistsError:
            self._toast(_("“%s” already exists there.") % source.name)
            return False
        except OSError as error:
            self._toast(_("Could not move: %s") % (error.strerror or error))
            return False
        self._after_move(source, target)
        return True

    def _move_step(self, direction: int):
        """Alt+Up / Alt+Down: the selected entry one place up or down within its group."""
        node = self._selected_node()
        if node is None:
            return
        names = ordered_names(node.path.parent)
        index = names.index(node.path.name) if node.path.name in names else -1
        neighbour = index + direction
        if index < 0 or not 0 <= neighbour < len(names):
            return
        self._place(node.path, node.path.parent / names[neighbour], after=direction > 0)

    def _inside_library(self, path: Path) -> bool:
        return self.library_path is not None and (path == self.library_path or self.library_path in path.parents)

    def _move(self, source: Path, folder: Path, to_end: bool = False) -> bool:
        """Moves a sheet or a group within the library. Foreign drag data
        (e.g. text from the editor) is ignored, because it is not a path in the library."""
        if not (self._inside_library(source) and source != self.library_path and self._inside_library(folder)):
            return False
        if not source.exists() or source.parent == folder:
            return False
        if not self._flush():
            return False
        try:
            target = move(source, folder)
        except ValueError:
            self._toast(_("A group cannot be moved into itself."))
            return False
        except FileExistsError:
            self._toast(_("“%s” already exists there.") % source.name)
            return False
        except OSError as error:
            self._toast(_("Could not move: %s") % (error.strerror or error))
            return False
        if to_end:
            place(target, None)  # dropped onto a group: at the end of its order
        self._after_move(source, target)
        return True

    def _after_move(self, source: Path, target: Path):
        self._follow_rename(source, target)
        self._reload(select_path=target, renamed=(source, target))

    def _follow_rename(self, old: Path, new: Path):
        """An entry was renamed or moved: the open sheet or group moves along. Sections of the
        group view are reopened by _reload when their paths change."""
        open_path = self.editor.path
        if open_path is not None and (open_path == old or old in open_path.parents):
            self.editor.set_path(new / open_path.relative_to(old))
            self.inspector.refresh_attachments()
        group = self.group_view.group
        if group is not None and (group == old or old in group.parents):
            self.group_view.group = new / group.relative_to(old)
            if self.group_view.showing_cards:
                self._remember_cards(self.group_view.group, True, old=group)

    def _on_move_to(self):
        node = self._selected_node()
        if node is None:
            return
        # Targets: root folder and all groups except its own (and, for groups, their subgroups).
        targets = [self.library_path] + [
            group
            for group in all_groups(scan(self.library_path))
            if group != node.path.parent and not (node.is_group and (group == node.path or node.path in group.parents))
        ]
        if node.path.parent == self.library_path:
            targets.remove(self.library_path)
        if not targets:
            self._toast(_("There is no other group to move to."))
            return
        labels = [
            _("Library (top level)") if target == self.library_path else str(target.relative_to(self.library_path))
            for target in targets
        ]
        choice = Gtk.DropDown(model=Gtk.StringList.new(labels))
        dialog = Adw.AlertDialog(heading=_("Move “%s” to…") % node.name)
        dialog.set_extra_child(choice)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("move", _("Move"))
        dialog.set_response_appearance("move", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("move")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response", lambda _d, response: response == "move" and self._move(node.path, targets[choice.get_selected()])
        )
        dialog.present(self)

    def _on_row_clicked(self, _gesture, _n_press, _x, _y, list_item):
        """After clicking a sheet, allow writing right away (arrow keys stay in the list)."""
        row = list_item.get_item()
        if row is not None and not row.get_item().node.is_group:
            GLib.idle_add(lambda: self.editor.focus_editor() and False)

    def _on_row_right_click(self, gesture, _n_press, x, y, list_item):
        position = list_item.get_position()
        if position == Gtk.INVALID_LIST_POSITION:
            return
        self.selection.set_selected(position)
        if self.selection.get_selected() != position:
            return  # selection was refused (save error), no menu for the wrong sheet.
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
        icon = box.get_first_child()
        label = icon.get_next_sibling()
        icon.set_from_icon_name("folder-symbolic" if node.is_group else "text-x-generic-symbolic")
        label.set_text(node.name)
        ring = label.get_next_sibling()
        ring.path = None if node.is_group else node.path
        self._update_row_ring(ring, animate=False)

    def _update_row_ring(self, ring: ProgressRing, animate: bool = True):
        """Ring next to a sheet with a writing goal. The open sheet counts live (including unsaved text)."""
        progress = None
        if ring.path is not None:
            if ring.path == self.editor.path:
                goal = parse_goal(self.editor.metadata().get("goal"))
                progress = (getattr(self, "_words", 0), goal) if goal else None
            else:
                progress = self._goals.progress_of(ring.path)
        ring.set_visible(progress is not None)
        if progress is not None:
            words, goal = progress
            text = ngettext("%(count)s of %(goal)s word", "%(count)s of %(goal)s words", goal) % {
                "count": locale.format_string("%d", words, grouping=True),
                "goal": locale.format_string("%d", goal, grouping=True),
            }
            ring.set_tooltip_text(text)
            ring.update_property([Gtk.AccessibleProperty.LABEL], [_("Writing Goal") + ": " + text])
            ring.show_progress(fraction(words, goal), words >= goal, animate)

    # --- Appearance -------------------------------------------------------

    def apply_settings(self):
        """Applies the saved settings (at startup and on every change in the dialog)."""
        current = config.effective_settings(self.focus_mode)
        for editor in [self.editor, *self.group_view.editors]:
            self._style_editor(editor)
        Adw.StyleManager.get_default().set_color_scheme(
            {
                "system": Adw.ColorScheme.DEFAULT,
                "light": Adw.ColorScheme.FORCE_LIGHT,
                "dark": Adw.ColorScheme.FORCE_DARK,
            }[current["color_scheme"]]
        )
        self._update_format_bar()
        self.lookup_action("spell-check").set_state(GLib.Variant.new_boolean(self._spell_check_wanted()))
        self.inspector.refresh()  # defaults for author and language may have changed

    def _style_editor(self, editor: SheetEditor):
        """Font, caret and focus aids for one editor (the single sheet or a section of the group view)."""
        current = config.effective_settings(self.focus_mode)
        data = config.load()
        editor.set_appearance(
            font_family=current["editor_font"],
            font_size_pt=current["editor_font_size"],
            line_width_chars=current["line_width"],
            line_spacing=current["line_spacing"],
        )
        editor.view.set_underline_caret(data.get("underline_caret") is not False)
        editor.set_spell_checking(self._spell_check_wanted(), config.sheet_defaults()["lang"])
        # Typewriter scrolling and dimming need the editor's own scrolling: not in the group view.
        single = editor is self.editor
        editor.view.set_focus_effects(
            typewriter=single and self.focus_mode and data.get("focus_typewriter") is not False,
            dim_others=single and self.focus_mode and data.get("focus_dim") is not False,
        )
        self._style_scheme(editor)

    def _apply_style_scheme(self):
        for editor in [self.editor, *self.group_view.editors]:
            self._style_scheme(editor)

    def _style_scheme(self, editor: SheetEditor):
        """The editor theme (its light or dark variant, following the style) for one editor."""
        dark = Adw.StyleManager.get_default().get_dark()
        theme_id = themes.find(config.effective_settings(self.focus_mode)["editor_theme"]).id
        scheme = themes.scheme(theme_id, dark)
        editor.buffer.set_style_scheme(scheme)
        palette = themes.palette(scheme)
        editor.styler.set_palette(palette)
        # The group view shows the theme's background between its sections, too; any theme other
        # than Standard tints the rest of the window to match (Standard keeps the usual GNOME look).
        css = f".typecase-group {{ background-color: {palette['background'].to_string()}; color: {palette['text'].to_string()}; }}"
        if theme_id != themes.DEFAULT:
            css += "\n" + themes.window_css(palette)
        if css != self._theme_css_text:
            self._theme_css_text = css
            self._theme_css.load_from_string(css)
