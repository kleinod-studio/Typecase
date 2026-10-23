from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource

from . import config
from .library import Node, scan


class LibraryItem(GObject.Object):
    def __init__(self, node: Node):
        super().__init__()
        self.node = node


def _make_store(nodes: list[Node]) -> Gio.ListStore:
    store = Gio.ListStore(item_type=LibraryItem)
    for node in nodes:
        store.append(LibraryItem(node))
    return store


class TypecaseWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title="Typecase", default_width=1000, default_height=700, **kwargs)

        self.library_path: Path | None = None

        self._build_ui()

        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_args: self._apply_style_scheme())
        self._apply_style_scheme()

        self._open_library(config.get_library_path())

    # --- Aufbau -----------------------------------------------------------

    def _build_ui(self):
        split = Adw.OverlaySplitView(min_sidebar_width=220, max_sidebar_width=320)
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())
        self.set_content(split)

    def _build_sidebar(self):
        self.sidebar_title = Adw.WindowTitle(title=_("Library"), subtitle="")
        header = Adw.HeaderBar(title_widget=self.sidebar_title)

        choose_button = Gtk.Button(
            icon_name="folder-open-symbolic",
            tooltip_text=_("Choose Library Folder…"),
        )
        choose_button.connect("clicked", lambda _b: self._choose_library_folder())
        header.pack_start(choose_button)

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
        self.list_view = Gtk.ListView(model=self.selection, factory=factory, css_classes=["navigation-sidebar"])
        tree_scroller = Gtk.ScrolledWindow(child=self.list_view, vexpand=True)

        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.add_named(empty, "empty")
        self.sidebar_stack.add_named(tree_scroller, "library")

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.sidebar_stack)
        return Adw.NavigationPage(title=_("Library"), child=view)

    def _build_content(self):
        self.buffer = GtkSource.Buffer()
        self.buffer.set_language(GtkSource.LanguageManager.get_default().get_language("markdown"))

        editor = GtkSource.View(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=24,
            bottom_margin=24,
            left_margin=32,
            right_margin=32,
            monospace=False,
        )

        scrolled = Gtk.ScrolledWindow(child=editor, hexpand=True, vexpand=True)

        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title="Typecase", subtitle=""))

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(scrolled)
        return Adw.NavigationPage(title="Typecase", child=view)

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
        config.set_library_path(Path(path))
        self._open_library(Path(path))

    def _open_library(self, path: Path | None):
        self.library_path = path
        if path is None:
            self.sidebar_title.set_subtitle("")
            self.sidebar_stack.set_visible_child_name("empty")
            return

        self.sidebar_title.set_subtitle(path.name or str(path))
        root = _make_store(scan(path))
        self.tree_model = Gtk.TreeListModel.new(root, False, False, self._create_children)
        self.selection.set_model(self.tree_model)
        self.sidebar_stack.set_visible_child_name("library")

    @staticmethod
    def _create_children(item: LibraryItem):
        return _make_store(item.node.children) if item.node.is_group else None

    # --- Seitenleisten-Zeilen ---------------------------------------------

    def _on_item_setup(self, _factory, list_item):
        icon = Gtk.Image()
        label = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)  # 3 = Pango.EllipsizeMode.END
        box = Gtk.Box(spacing=8)
        box.append(icon)
        box.append(label)
        expander = Gtk.TreeExpander(child=box)
        list_item.set_child(expander)

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

    def _apply_style_scheme(self):
        dark = Adw.StyleManager.get_default().get_dark()
        manager = GtkSource.StyleSchemeManager.get_default()
        scheme = manager.get_scheme("Adwaita-dark" if dark else "Adwaita")
        if scheme is not None:
            self.buffer.set_style_scheme(scheme)
