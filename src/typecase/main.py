import gettext
import locale
import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk, GtkSource

from .window import TypecaseWindow

APP_ID = "studio.kleinod.Typecase"
VERSION = "1.1.1"  # must match meson.build
GETTEXT_DOMAIN = "typecase"
WEBSITE = "https://kleinod.studio/typecase"
REPOSITORY = "https://github.com/kleinod-studio/Typecase"


def _setup_translations(localedir: str | None = None):
    """Binds the translations: when installed, given by the launcher; otherwise ./locale in the source folder (run-dev.sh)."""
    if localedir is None:
        source_locale = Path(__file__).resolve().parents[2] / "locale"
        localedir = str(source_locale) if source_locale.is_dir() else None
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        _fall_back_to_utf8()
    for module in (gettext, locale):
        module.bindtextdomain(GETTEXT_DOMAIN, localedir)
    gettext.textdomain(GETTEXT_DOMAIN)


def _fall_back_to_utf8():
    """The system locale is missing (in the Flatpak, when its locale data is not installed).
    Then don't run in plain ASCII "C", or umlauts and PDF printing (WebKit) fail, but in
    C.UTF-8 instead; the translations still follow the requested language."""
    wanted = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG", "")
    if wanted and not os.environ.get("LANGUAGE"):
        os.environ["LANGUAGE"] = wanted.split(".")[0]
    os.environ["LC_ALL"] = "C.UTF-8"  # also applies to GTK and the helper programs we launch
    try:
        locale.setlocale(locale.LC_ALL, "C.UTF-8")
    except locale.Error:
        pass


class TypecaseApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        GtkSource.init()
        self.set_accels_for_action("win.new-sheet", ["<Primary>n"])
        self.set_accels_for_action("win.new-group", ["<Primary><Shift>n"])
        self.set_accels_for_action("win.rename", ["F2"])
        self.set_accels_for_action("win.search", ["<Primary><Shift>f"])
        self.set_accels_for_action("win.find", ["<Primary>f"])
        self.set_accels_for_action("win.replace", ["<Primary>h"])
        # F9 is the GNOME default; on Omarchy the system uses F9 (dictation), hence Ctrl+Shift+L as well.
        self.set_accels_for_action("win.toggle-sidebar", ["F9", "<Primary><Shift>l"])
        self.set_accels_for_action("win.fullscreen", ["F11"])
        self.set_accels_for_action("win.focus-mode", ["<Primary><Shift>Return"])
        self.set_accels_for_action("win.cards", ["<Primary><Alt>c"])
        self.set_accels_for_action("win.show-shortcuts", ["<Primary>question"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])
        self.set_accels_for_action("win.preferences", ["<Primary>comma"])
        self.set_accels_for_action("win.inspector", ["<Alt>Return"])
        self.set_accels_for_action("win.export", ["<Primary>e"])
        self.set_accels_for_action("win.spell-check", ["F7"])
        for kind, keys in [
            ("bold", ["<Primary>b"]),
            ("italic", ["<Primary>i"]),
            ("underline", ["<Primary>u"]),
            ("link", ["<Primary>k"]),
            ("h1", ["<Primary>1"]),
            ("h2", ["<Primary>2"]),
            ("h3", ["<Primary>3"]),
            ("paragraph", ["<Primary>0"]),
        ]:
            self.set_accels_for_action(f"win.format::{kind}", keys)

        for name, handler in [("quit", self._on_quit), ("about", self._on_about)]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def _on_quit(self, _action, _param):
        # Via close() instead of quit(): each window saves first and may refuse to quit.
        for window in list(self.get_windows()):
            window.close()

    def _on_about(self, _action, _param):
        about = Adw.AboutDialog(
            application_name="Typecase",
            application_icon=APP_ID,
            version=VERSION,
            developer_name="kleinod.studio",
            comments=_("Calm Markdown writing"),
            website=WEBSITE,
            issue_url=REPOSITORY + "/issues",
            copyright="© 2026 Sascha Wübbena (kleinod.studio)",
            license_type=Gtk.License.GPL_3_0,
            # Translators: put your name here (one per line) so it appears in the about dialog.
            translator_credits=_("translator-credits"),
        )
        about.add_link(_("Source Code"), REPOSITORY)
        about.add_link("kleinod.studio", "https://kleinod.studio")
        # Bundled in the Flatpak for exporting; its licence requires a notice.
        about.add_legal_section(
            "Pandoc",
            "© 2006–2026 John MacFarlane and contributors",
            Gtk.License.GPL_2_0,
            None,
        )
        windows = self.get_windows()
        about.present(self.props.active_window or (windows[0] if windows else None))

    def do_activate(self):
        win = self.props.active_window or TypecaseWindow(application=self)
        win.present()


def main(localedir: str | None = None):
    _setup_translations(localedir)
    return TypecaseApplication().run(None)
