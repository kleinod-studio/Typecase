from gettext import gettext as _

from gi.repository import Adw, Gtk, GtkSource


class TypecaseWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(title="Typecase", default_width=1000, default_height=700, **kwargs)

        self._build_ui()

        style = Adw.StyleManager.get_default()
        style.connect("notify::dark", lambda *_args: self._apply_style_scheme())
        self._apply_style_scheme()

    def _build_ui(self):
        split = Adw.OverlaySplitView(min_sidebar_width=220, max_sidebar_width=320)
        split.set_sidebar(self._build_sidebar())
        split.set_content(self._build_content())
        self.set_content(split)

    def _build_sidebar(self):
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(title=_("Library"), subtitle=""))

        placeholder = Adw.StatusPage(
            icon_name="folder-symbolic",
            title=_("No library yet"),
            description=_("Choosing a library folder comes in the next step."),
        )

        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(placeholder)
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

    def _apply_style_scheme(self):
        dark = Adw.StyleManager.get_default().get_dark()
        manager = GtkSource.StyleSchemeManager.get_default()
        scheme = manager.get_scheme("Adwaita-dark" if dark else "Adwaita")
        if scheme is not None:
            self.buffer.set_style_scheme(scheme)
