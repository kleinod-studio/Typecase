"""Explainer video: setting up Flatpak on Ubuntu, before installing Typecase.

    python3 tools/video/prepare-flatpak.py

Plays in the Ubuntu VM (see vmkit.py), which must not have Flatpak yet. When the terminal asks
for the password, type it in the VM by hand and press Enter; the wait is cut out of the video.
Leave the VM alone otherwise while it records (about two minutes)."""

import vmkit
from videokit import Scene

TERMINAL = (348, 188, 1290, 738)  # where Ptyxis opens its window, logical pixels
MENU = (1500, 30, 420, 340)  # the quick settings with the power menu
PROMPT = "$"

FLATHUB = "sudo flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"


def opening(vm):
    vm.move(1100, 700)


def desktop(vm):
    yield 1.0


def open_terminal(vm):
    yield 2.2
    vm.key("Super_L")
    yield 1.0
    vm.type("terminal", 0.09)
    yield 1.6
    vm.key("Return")
    yield 1.8
    vm.wait_text(PROMPT, limit=20)
    yield vm.zoom(TERMINAL, length=1.4)  # the whole window, so the question and the prompt stay in view


def fresh_screen(vm):
    """Clears the terminal (Ctrl+L), so each command starts at the top."""
    vm.key("Control_L+l")
    yield 0.5


def apt(vm, command):
    """Types an apt command and gets it through: the password (typed by hand, cut out), the
    question whether to go on, and the download (shortened)."""
    yield from fresh_screen(vm)
    vm.type(command + "\n")
    asked = vm.wait_text("Password:", "[Y/n]", PROMPT, limit=60)
    if asked == "Password:":
        yield 2.5
        vm.cut()
        print("Type the password in the VM now.", flush=True)
        asked = vm.wait_text("[Y/n]", PROMPT, limit=600)
        vm.uncut()
        yield 0.6
    if asked == "[Y/n]":
        yield 2.4
        vm.key("Return")
        yield 2.0
        vm.cut()
        vm.wait_text(PROMPT, limit=900)
        vm.uncut()
    yield 1.0


def install_flatpak(vm):
    yield 0.8
    yield from apt(vm, "sudo apt install flatpak")


def software_plugin(vm):
    yield 0.6
    yield from apt(vm, "sudo apt install gnome-software-plugin-flatpak")


def flathub(vm):
    yield 0.6
    yield from fresh_screen(vm)
    vm.type(FLATHUB + "\n", 0.035)
    asked = vm.wait_text("Password:", PROMPT, limit=60)
    if asked == "Password:":
        yield 2.0
        vm.cut()
        print("Type the password in the VM now.", flush=True)
        vm.wait_text(PROMPT, limit=600)
        vm.uncut()
    yield 1.5


def restart(vm):
    yield vm.zoom(None, length=1.2)
    yield 0.6
    vm.click(1860, 15)
    yield 0.8
    vm.zoom(MENU, length=1.0)
    yield 1.0
    vm.click(1875, 76)
    yield 1.2
    vm.move(1587, 228)  # over "Restart…", without clicking it
    yield 3.0
    vm.key("Escape")
    yield 0.3
    vm.key("Escape")
    yield vm.zoom(None, length=1.0)


SCENES = [
    Scene(
        "Typecase comes as a Flatpak, a kind of app that runs on almost every Linux. On Ubuntu, Flatpak needs a "
        "short setup, just once. On Fedora or Linux Mint it's already there, so you can skip this video.",
        "Typecase kommt als Flatpak, eine Art App, die auf fast jedem Linux läuft. Unter Ubuntu braucht Flatpak "
        "eine kurze Einrichtung, nur einmal. Unter Fedora oder Linux Mint ist es schon da – dann kannst du dieses "
        "Video überspringen.",
        desktop,
    ),
    Scene(
        "Everything happens in the Terminal. Open it from the search, or press Control, Alt and T. "
        "Don't worry: three commands, and you're done.",
        "Alles passiert im Terminal. Öffne es über die Suche oder mit Strg, Alt und T. "
        "Keine Sorge: drei Befehle, und du bist fertig.",
        open_terminal,
    ),
    Scene(
        "First, install Flatpak itself. Ubuntu asks for your password: type it, the letters stay invisible, and "
        "press Enter. When Ubuntu asks whether to continue, press Enter again.",
        "Zuerst installierst du Flatpak selbst. Ubuntu fragt nach deinem Passwort: Tippe es ein – die Zeichen "
        "bleiben unsichtbar – und drücke Enter. Fragt Ubuntu, ob es weitergehen soll, drückst du noch einmal Enter.",
        install_flatpak,
    ),
    Scene(
        "Second, teach the Software app about Flatpak. That's what lets you install Typecase with a double click.",
        "Als Zweites bringst du der App „Software“ Flatpak bei. Damit installierst du Typecase später mit einem "
        "Doppelklick.",
        software_plugin,
    ),
    Scene(
        "Third, add Flathub. Typecase gets the parts it needs from there.",
        "Als Drittes fügst du Flathub hinzu. Von dort holt sich Typecase die Teile, die es braucht.",
        flathub,
    ),
    Scene(
        "That's it. Restart your computer once, so that new apps show up. You'll find the commands below this "
        "video, ready to copy.",
        "Das war's. Starte deinen Computer einmal neu, damit neue Apps erscheinen. Die Befehle findest du unter "
        "diesem Video zum Kopieren.",
        restart,
        hold=0.5,
    ),
]

VIDEO = vmkit.Video(
    name="prepare-flatpak",
    title="Prepare Flatpak",
    topic="Install and update",
    summary="Set up Flatpak on Ubuntu once, so you can install Typecase. On Fedora and Linux Mint, it's already there.",
    still=20,
    commands=[
        ("Install Flatpak", "sudo apt install flatpak"),
        ("Let the Software app install Flatpaks", "sudo apt install gnome-software-plugin-flatpak"),
        ("Add Flathub", FLATHUB),
        ("Then restart your computer once.", ""),
    ],
)

if __name__ == "__main__":
    vmkit.run(VIDEO, SCENES, before=opening)
