"""Explainer video: downloading and installing Typecase on Ubuntu, and adding dictionaries.

    python3 tools/video/install-typecase.py

Plays in the Ubuntu VM (see vmkit.py) after prepare-flatpak.py: Flatpak, the Software plugin and
Flathub are set up, the VM was restarted once, Typecase is not installed, ~/Downloads holds no
Typecase file, and no window is open. The video keeps one window open at a time and closes each
one when it is done. When the VM asks for the password (a window of Ubuntu, later the terminal),
type it in the VM by hand; the wait is cut out of the video.
The VM is an ARM machine, so the video downloads the aarch64 bundle."""

import vmkit
from videokit import Scene

# Where things are on the VM's screen, in logical pixels (1920x1080)
FIREFOX = (33, 64)  # in the dock
FILES = (33, 128)
ADDRESS = (451, 96)  # Firefox's address bar
GET_TYPECASE = (588, 475)  # the button on kleinod.studio/typecase that jumps to "Install"
DOWNLOAD_ARM = (856, 685)
DOWNLOAD_X86 = (618, 685)
DOWNLOAD_BUTTONS = (500, 600, 520, 140)
FIREFOX_CLOSE = (1897, 53)
DOWNLOADS = (550, 539)  # in the sidebar of Files
BUNDLE = (750, 210)  # the downloaded file in Files
INSTALL = (1367, 170)  # in Software
SOFTWARE_HEAD = (560, 110, 900, 200)
TERMINAL = (348, 188, 1290, 738)
PROMPT = "$"

OVERVIEW_CLOSED = ("gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method "
                   "org.freedesktop.DBus.Properties.Get org.gnome.Shell OverviewActive | grep -q false")
FILE = "Typecase-1.3.0-aarch64.flatpak"
LANGUAGES = 'sudo flatpak config --set languages "de;en"'


def opening(vm):
    # a Typecase or Files window left over from an earlier take would show up on the desktop
    vm.wait_shell("! pgrep -f '[s]tudio.kleinod.Typecase' && ! pgrep -x nautilus", 5)
    vm.move(1100, 700)


def desktop(vm):
    yield 1.0


def website(vm):
    yield 1.5
    vm.click(*FIREFOX)
    yield 1.0
    vm.cut()  # Firefox takes its time to start the first time
    vm.wait_shell("pgrep -f /snap/firefox >/dev/null", 60)
    yield 5.0
    vm.uncut()
    vm.click(*ADDRESS)
    yield 0.5
    vm.type("kleinod.studio/typecase\n", 0.07)
    yield 3.0
    vm.move(GET_TYPECASE[0] - 120, GET_TYPECASE[1] + 60)
    yield 0.4
    vm.click(*GET_TYPECASE)
    yield 1.2
    yield vm.zoom(DOWNLOAD_BUTTONS, length=1.2)


def download(vm):
    vm.move(*DOWNLOAD_X86)
    yield 2.2
    vm.move(*DOWNLOAD_ARM)
    yield 1.6
    vm.click(*DOWNLOAD_ARM)
    yield 1.5
    vm.cut()
    vm.wait_shell(f"test -s ~/Downloads/{FILE} && ! ls ~/Downloads/*.part 2>/dev/null", 300)
    vm.uncut()
    yield 1.5
    yield vm.zoom(None, length=1.0)
    vm.key("Escape")  # closes the list of downloads, which would catch the next click
    yield 0.5
    vm.click(*FIREFOX_CLOSE)
    yield 1.0
    try:  # make sure Firefox is gone, so later typing can't land in it
        vm.wait_shell("! pgrep -f '[/]snap/firefox/.*/firefox$'", 8)
    except RuntimeError:
        vm.key("Control_L+q")
        yield 1.0
        vm.wait_shell("! pgrep -f '[/]snap/firefox/.*/firefox$'", 15)


def double_click(vm):
    vm.click(*FILES)
    yield 2.0
    vm.click(*DOWNLOADS)
    yield 1.5
    vm.move(*BUNDLE)
    yield 0.8
    vm.click(*BUNDLE, 2)
    yield 1.0
    vm.cut()  # Software reads the file
    vm.wait_running("gnome-software", 30)
    vm.wait_shell("nautilus -q; true", 10)  # Files is done; closed while cut out, so it can't clutter the desktop
    yield 5.0
    vm.uncut()
    yield vm.zoom(SOFTWARE_HEAD, length=1.2)


def install(vm):
    yield 1.0
    vm.move(*INSTALL)
    yield 2.0
    vm.click(*INSTALL)
    yield 2.5
    vm.cut()
    print("Type the password in the VM now (in Ubuntu's window).", flush=True)
    vm.wait_shell("flatpak info --system studio.kleinod.Typecase >/dev/null", 1800)
    yield 4.0  # Software shows "Open" instead of "Install"
    vm.uncut()
    yield 1.5


def apps(vm):
    yield vm.zoom(None, length=1.0)
    # One window at a time: Software is done. Quit, not closed by its window button, which can
    # crash it for a local file on Ubuntu 26.04
    vm.wait_shell("gnome-software --quit; true", 10)
    yield 1.0
    vm.key("Super_L+a")
    yield 2.5
    vm.type("typecase", 0.09)
    yield 3.0
    for _ in range(3):  # the search, the app grid, the overview
        vm.key("Escape")
        yield 0.4
    vm.wait_shell(OVERVIEW_CLOSED, 5)
    yield 0.5


def terminal_command(vm, command):
    """Types a command and gets it through the password (typed by hand, cut out), Flatpak's
    question whether to go on, and the download (shortened)."""
    vm.type(command + "\n", 0.045)
    asked = vm.wait_text("Password:", "[Y/n]:", PROMPT, limit=60)
    if asked == "Password:":
        yield 2.0
        vm.cut()
        print("Type the password in the VM now (in the terminal).", flush=True)
        asked = vm.wait_text("[Y/n]:", PROMPT, limit=600)
        vm.uncut()
        yield 0.6
    if asked == "[Y/n]:":
        yield 2.0
        vm.key("Return")
        yield 1.5
        vm.cut()
        vm.wait_text(PROMPT, limit=900)
        vm.uncut()
    yield 1.0


def dictionaries(vm):
    yield 0.5
    vm.key("Super_L+a")
    yield 1.0
    vm.type("terminal", 0.09)
    yield 1.4
    vm.key("Return")
    yield 1.8
    vm.wait_text(PROMPT, limit=20)
    yield vm.zoom(TERMINAL, length=1.2)
    yield from terminal_command(vm, LANGUAGES)
    yield from terminal_command(vm, "sudo flatpak update")


def closing(vm):
    yield 1.0
    yield vm.zoom(None, length=1.0)
    vm.key("Control_L+d")  # closes the terminal
    yield 1.0


SCENES = [
    Scene(
        "Now let's install Typecase. If you're on Ubuntu, set up Flatpak first, as shown in the previous video.",
        "Jetzt installierst du Typecase. Unter Ubuntu richtest du vorher Flatpak ein, wie im vorigen Video gezeigt.",
        desktop,
    ),
    Scene(
        "Open kleinod.studio/typecase in your browser and click Get Typecase.",
        "Öffne kleinod.studio/typecase im Browser und klicke auf „Get Typecase“.",
        website,
        say="Open Kline oat dot studio slash Type case in your browser, and click Get Type case.",
    ),
    Scene(
        "Pick the download for your computer. Most PCs need x86_64. ARM computers, like this one, need the "
        "second button.",
        "Wähle den Download für deinen Computer. Die meisten PCs brauchen x86_64. ARM-Computer wie dieser "
        "brauchen den zweiten Knopf.",
        download,
        say="Pick the download for your computer. Most PCs need x 86 64. Arm computers, like this one, need the "
            "second button.",
    ),
    Scene(
        "Open your Downloads folder and double-click the file. The Software app opens.",
        "Öffne deinen Ordner „Downloads“ und klicke die Datei doppelt an. Die App „Software“ öffnet sich.",
        double_click,
    ),
    Scene(
        "Click Install and type your password. Software may warn that Typecase can read and write your files: "
        "it needs that to open the folder with your texts.",
        "Klicke auf „Install“ und gib dein Passwort ein. Software weist vielleicht darauf hin, dass Typecase deine "
        "Dateien lesen und schreiben kann: Das braucht es, um den Ordner mit deinen Texten zu öffnen.",
        install,
        say="Click Install, and type your password. Software may warn that Type case can read and write your "
            "files: it needs that to open the folder with your texts.",
    ),
    Scene(
        "Done. Typecase is now among your apps.",
        "Fertig. Typecase ist jetzt bei deinen Apps.",
        apps,
        say="Done. Type case is now among your apps.",
    ),
    Scene(
        "Typecase checks your spelling. Dictionaries for your system's language usually come along. For more "
        "languages, add them in the Terminal, here German and English, and update.",
        "Typecase prüft deine Rechtschreibung. Wörterbücher für die Sprache deines Systems sind meist schon "
        "dabei. Weitere Sprachen fügst du im Terminal hinzu, hier Deutsch und Englisch, und aktualisierst.",
        dictionaries,
        say="Type case checks your spelling. Dictionaries for your system's language usually come along. For "
            "more languages, add them in the Terminal, here German and English, and update.",
    ),
    Scene(
        "Prefer the Terminal for everything? You'll find all commands below this video.",
        "Du magst lieber alles im Terminal machen? Alle Befehle findest du unter diesem Video.",
        closing,
        hold=0.5,
    ),
]

VIDEO = vmkit.Video(
    name="install-typecase",
    title="Install Typecase",
    topic="Install and update",
    summary="Download Typecase, install it with a double click, and add dictionaries for more languages.",
    still=30,
    commands=[
        ("Install the downloaded file from your Downloads folder", "sudo flatpak install ~/Downloads/Typecase-*.flatpak"),
        ("Add dictionaries for more languages, here German and English (use your language codes)", LANGUAGES),
        ("Download them", "sudo flatpak update"),
    ],
)

if __name__ == "__main__":
    vmkit.run(VIDEO, SCENES, before=opening)
