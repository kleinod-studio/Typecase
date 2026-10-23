import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GtkSource

from .window import TypecaseWindow

APP_ID = "studio.kleinod.Typecase"


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
    return TypecaseApplication().run(None)
