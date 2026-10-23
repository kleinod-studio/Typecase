import gettext
import locale
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk, GtkSource

from .window import TypecaseWindow

APP_ID = "studio.kleinod.Typecase"
VERSION = "0.1.0"  # muss zu meson.build passen
GETTEXT_DOMAIN = "typecase"


def _setup_translations(localedir: str | None = None):
    """Bindet die Übersetzungen: installiert vom Startprogramm vorgegeben, sonst ./locale im Quellordner (run-dev.sh)."""
    if localedir is None:
        source_locale = Path(__file__).resolve().parents[2] / "locale"
        localedir = str(source_locale) if source_locale.is_dir() else None
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass  # Unbekannte Locale: Texte bleiben englisch.
    for module in (gettext, locale):
        module.bindtextdomain(GETTEXT_DOMAIN, localedir)
    gettext.textdomain(GETTEXT_DOMAIN)


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
        # F9 ist GNOME-Standard; unter Omarchy belegt das System F9 (Diktieren), daher zusätzlich Strg+Umschalt+L.
        self.set_accels_for_action("win.toggle-sidebar", ["F9", "<Primary><Shift>l"])
        self.set_accels_for_action("win.fullscreen", ["F11"])
        self.set_accels_for_action("win.writing-mode", ["<Primary><Shift>Return"])
        self.set_accels_for_action("win.show-shortcuts", ["<Primary>question"])
        self.set_accels_for_action("app.quit", ["<Primary>q"])

        for name, handler in [("quit", self._on_quit), ("about", self._on_about)]:
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def _on_quit(self, _action, _param):
        # Über close() statt quit(): jedes Fenster sichert zuerst und darf das Beenden verweigern.
        for window in list(self.get_windows()):
            window.close()

    def _on_about(self, _action, _param):
        about = Adw.AboutDialog(
            application_name="Typecase",
            application_icon=APP_ID,
            version=VERSION,
            developer_name="Sascha Wuebbena",
            comments=_("Calm Markdown writing"),
            license_type=Gtk.License.GPL_3_0,
        )
        windows = self.get_windows()
        about.present(self.props.active_window or (windows[0] if windows else None))

    def do_activate(self):
        win = self.props.active_window or TypecaseWindow(application=self)
        win.present()


def main(localedir: str | None = None):
    _setup_translations(localedir)
    return TypecaseApplication().run(None)
