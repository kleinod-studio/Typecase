import gettext
import locale
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GtkSource

from .window import TypecaseWindow

APP_ID = "studio.kleinod.Typecase"
GETTEXT_DOMAIN = "typecase"


def _setup_translations():
    """Bindet die Übersetzungen: erst ./locale im Quellordner (run-dev.sh), dann <prefix>/share/locale."""
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / "locale", here.parents[4] / "share" / "locale"] if len(here.parents) > 4 else []
    localedir = next((str(path) for path in candidates if path.is_dir()), None)
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

    def do_activate(self):
        win = self.props.active_window or TypecaseWindow(application=self)
        win.present()


def main():
    _setup_translations()
    return TypecaseApplication().run(None)
