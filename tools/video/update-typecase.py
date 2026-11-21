"""Explainer video: updating Typecase to a new release.

    python3 tools/video/update-typecase.py

Plays in the Ubuntu VM (see vmkit.py) after install-typecase.py, with an older Typecase (1.2.1)
installed system-wide in place of the current one, ~/Downloads holding no Typecase file, and no
window open. The video keeps one window open at a time. When the terminal asks for the password,
type it in the VM by hand; the wait is cut out of the video. The Software app cannot update from
a downloaded file (it only offers to uninstall), so the update happens in the terminal."""

import vmkit
from videokit import Scene

# Where things are on the VM's screen, in logical pixels (1920x1080)
FIREFOX = (33, 64)  # in the dock
ADDRESS = (451, 96)  # Firefox's address bar
VERSION = (500, 440, 520, 130)  # the buttons on kleinod.studio/typecase and "Version 1.3.0" under them
GET_TYPECASE = (588, 475)
DOWNLOAD_ARM = (856, 685)
DOWNLOAD_BUTTONS = (500, 600, 520, 140)
FIREFOX_CLOSE = (1897, 53)
MENU = (1356, 228)  # Typecase's main menu, in its window as it opens
ABOUT = (1314, 593)  # "About Typecase" in that menu
ABOUT_HEAD = (813, 293, 360, 300)  # icon, name and version in the about dialog
TERMINAL = (348, 188, 1290, 738)
PROMPT = "$"

FILE = "Typecase-1.3.0-aarch64.flatpak"
TYPECASE_RUNS = "pgrep -f '[s]tudio.kleinod.Typecase' >/dev/null"
TYPECASE_GONE = "! pgrep -f '[s]tudio.kleinod.Typecase'"
FIREFOX_GONE = "! pgrep -f '[/]snap/firefox/.*/firefox$'"


def opening(vm):
    vm.wait_shell(f"{TYPECASE_GONE} && ! pgrep -x nautilus && ! ls ~/Downloads/Typecase-* 2>/dev/null", 5)
    vm.move(1100, 700)


def launch(vm, name):
    """Opens an app through the app grid's search."""
    vm.key("Super_L+a")
    yield 1.2
    vm.type(name, 0.08)
    yield 1.0
    vm.key("Return")


def open_typecase(vm):
    yield from launch(vm, "typecase")
    vm.wait_shell(TYPECASE_RUNS, 30)
    yield 1.4


def show_about(vm):
    """Opens the about dialog of the running Typecase, shows its version and quits Typecase."""
    vm.move(*MENU)
    yield 0.5
    vm.click(*MENU)
    yield 1.0
    vm.move(*ABOUT)
    yield 0.4
    vm.click(*ABOUT)
    yield 0.8
    yield vm.zoom(ABOUT_HEAD, length=1.2)
    yield 2.2
    yield vm.zoom(None, length=1.0)
    vm.key("Escape")
    yield 0.5
    vm.key("Control_L+q")  # one window at a time
    vm.wait_shell(TYPECASE_GONE, 10)
    yield 0.5


# Each scene's narration starts with its scene, so slow things (an app starting) happen while
# the narration speaks about them, and the narration names what the picture shows right then.


def introduction(vm):
    yield 2.5
    yield from open_typecase(vm)


def old_version(vm):
    yield from show_about(vm)
    vm.click(*FIREFOX)
    yield 1.0
    vm.cut()  # Firefox takes its time to start
    vm.wait_shell("pgrep -f /snap/firefox >/dev/null", 60)
    yield 5.0
    vm.uncut()


def website(vm):
    vm.click(*ADDRESS)
    yield 0.4
    vm.type("kleinod.studio/typecase\n", 0.05)
    yield 2.0
    yield vm.zoom(VERSION, length=1.2)
    yield 2.0


def download(vm):
    yield vm.zoom(None, length=1.0)
    vm.move(GET_TYPECASE[0] - 120, GET_TYPECASE[1] + 60)
    yield 0.3
    vm.click(*GET_TYPECASE)
    yield 1.0
    yield vm.zoom(DOWNLOAD_BUTTONS, length=1.2)
    vm.move(*DOWNLOAD_ARM)
    yield 0.8
    vm.click(*DOWNLOAD_ARM)
    yield 1.2
    vm.cut()
    vm.wait_shell(f"test -s ~/Downloads/{FILE} && ! ls ~/Downloads/*.part 2>/dev/null", 300)
    vm.uncut()
    yield 1.0
    yield vm.zoom(None, length=1.0)
    vm.key("Escape")  # closes the list of downloads, which would catch the next click
    yield 0.4
    vm.click(*FIREFOX_CLOSE)  # Ctrl+Q would ask whether to quit
    yield 0.8
    vm.wait_shell(FIREFOX_GONE, 10)  # gone, so later typing can't land in it


def terminal(vm):
    yield 0.3
    yield from launch(vm, "terminal")
    yield 0.8
    vm.wait_text(PROMPT, limit=20)
    yield vm.zoom(TERMINAL, length=1.2)
    vm.type("sudo flatpak install ~/Downloads/Typ", 0.06)
    yield 0.6
    vm.key("Tab")  # completes the file name
    yield 1.0


def confirm(vm):
    vm.key("Return")
    asked = vm.wait_text("Password:", "[Y/n]:", PROMPT, limit=60)
    if asked == "Password:":
        yield 1.2
        vm.cut()
        print("Type the password in the VM now (in the terminal).", flush=True)
        asked = vm.wait_text("[Y/n]:", PROMPT, limit=600)
        vm.uncut()
        yield 0.4
    if asked == "[Y/n]:":
        yield 1.5
        vm.key("Return")
        yield 0.8
        vm.cut()
        vm.wait_text(PROMPT, limit=900)
        vm.uncut()
    yield 1.2
    yield vm.zoom(None, length=1.0)
    vm.key("Control_L+d")  # closes the terminal
    yield 0.6


def new_version(vm):
    yield 0.3
    yield from open_typecase(vm)
    yield from show_about(vm)


def closing(vm):
    yield 1.0


SCENES = [
    Scene(
        "Typecase never goes online, so it doesn't look for updates by itself. Now and then, compare your "
        "version with the newest one.",
        "Typecase geht nie ins Internet und sucht darum nicht selbst nach Updates. Vergleiche ab und zu deine "
        "Version mit der neuesten.",
        introduction,
        say="Type case never goes online, so it doesn't look for updates by itself. Now and then, compare your "
            "version with the newest one.",
    ),
    Scene(
        "Your version is in the menu, under About Typecase. This one has 1.2.1.",
        "Deine Version steht im Menü unter „About Typecase“. Hier ist es 1.2.1.",
        old_version,
        say="Your version is in the menu, under About Type case. This one has one point two point one.",
    ),
    Scene(
        "The newest version is on kleinod.studio/typecase, right below the buttons. Here it's 1.3.0.",
        "Die neueste Version steht auf kleinod.studio/typecase gleich unter den Knöpfen. Hier ist es 1.3.0.",
        website,
        say="The newest version is on Kline oat dot studio slash Type case, right below the buttons. Here it's "
            "one point three point oh.",
    ),
    Scene(
        "Download it, just like the first time: click Get Typecase, then the button for your computer.",
        "Lade sie herunter, genau wie beim ersten Mal: Klicke auf „Get Typecase“, dann auf den Knopf für "
        "deinen Computer.",
        download,
        say="Download it, just like the first time: click Get Type case, then the button for your computer.",
    ),
    Scene(
        "The Software app can't update from a downloaded file, so open the Terminal. Type sudo flatpak install "
        "and the start of the file name, then press Tab: the Terminal completes it.",
        "Die App „Software“ kann mit einer heruntergeladenen Datei nicht aktualisieren, darum öffnest du das "
        "Terminal. Tippe sudo flatpak install und den Anfang des Dateinamens, dann drücke die Tabulatortaste: "
        "Das Terminal ergänzt ihn.",
        terminal,
        say="The Software app can't update from a downloaded file, so open the Terminal. Type, sudo flatpak "
            "install, and the start of the file name, then press Tab: the Terminal completes it.",
    ),
    Scene(
        "Press Enter, type your password, and confirm with Enter once more.",
        "Drücke Enter, gib dein Passwort ein und bestätige noch einmal mit Enter.",
        confirm,
    ),
    Scene(
        "Your texts and settings stay as they are. Open Typecase again and look at About Typecase: now it "
        "has 1.3.0.",
        "Deine Texte und Einstellungen bleiben, wie sie sind. Öffne Typecase wieder und sieh in „About "
        "Typecase“ nach: Jetzt ist es 1.3.0.",
        new_version,
        say="Your texts and settings stay as they are. Open Type case again, and look at About Type case: now "
            "it has one point three point oh.",
    ),
    Scene(
        "Tip: run sudo flatpak update now and then, to keep the parts Typecase builds on up to date. You'll "
        "find the commands below this video.",
        "Tipp: Führe ab und zu sudo flatpak update aus, damit auch die Teile aktuell bleiben, auf denen Typecase "
        "aufbaut. Die Befehle findest du unter diesem Video.",
        closing,
        say="Tip: run, sudo flatpak update, now and then, to keep the parts Type case builds on up to date. "
            "You'll find the commands below this video.",
        hold=0.5,
    ),
]

VIDEO = vmkit.Video(
    name="update-typecase",
    title="Update Typecase",
    topic="Install and update",
    summary="Check your version, download the new one, and install it over the old one in the Terminal.",
    still=40,
    commands=[
        ("Install the new file over the old one (use the name of the file you downloaded)",
         "sudo flatpak install ~/Downloads/Typecase-1.3.0-x86_64.flatpak"),
        ("Keep the GNOME runtime and the dictionaries up to date", "sudo flatpak update"),
    ],
)

if __name__ == "__main__":
    vmkit.run(VIDEO, SCENES, before=opening)
