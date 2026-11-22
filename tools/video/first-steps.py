"""Explainer video: the first start of Typecase, choosing a library folder and writing a first sheet.

    python3 tools/video/first-steps.py

Plays in the Ubuntu VM (see vmkit.py) with Typecase installed. The opening resets Typecase there to
its first start (no configuration, no ~/Documents/Writing, no folder remembered by the file chooser)
and needs no password. The video keeps one window open at a time."""

import vmkit
from videokit import Scene

# Where things are on the VM's screen, in logical pixels (1920x1080)
CHOOSE = (623, 731)  # "Choose Library Folder…" in Typecase's empty library
EMPTY_LIBRARY = (493, 206, 260, 560)  # the sidebar with "No Library Yet"
DIALOG = (548, 282, 889, 548)  # the file chooser
DOCUMENTS = (912, 384)  # in the file chooser, showing the home folder
NEW_FOLDER = (1312, 304)
SELECT = (1370, 797)
PLUS = (730, 229)
NEW_SHEET = (680, 280)
SHEET = (493, 206, 767, 214)  # the library row and the start of the text
FILES = (32, 128)  # in the dock
FILES_DOCUMENTS = (864, 216)  # in Files, showing the home folder
FILES_FIRST = (750, 216)  # the first item of a folder in Files
FILE = (684, 114, 612, 198)  # the path bar and the file in Files

TYPECASE_RUNS = "pgrep -f '[s]tudio.kleinod.Typecase' >/dev/null"
TYPECASE_GONE = "! pgrep -f '[s]tudio.kleinod.Typecase'"
FIRST_START = ("flatpak kill studio.kleinod.Typecase 2>/dev/null; nautilus -q 2>/dev/null; "
               "rm -f ~/.var/app/studio.kleinod.Typecase/config/typecase/config.json; "
               "rm -rf ~/Documents/Writing; "
               "dconf reset -f /org/gnome/portal/filechooser/studio.kleinod.Typecase/; true")


def opening(vm):
    vm.wait_shell(FIRST_START, 15)
    vm.wait_shell(f"{TYPECASE_GONE} && ! pgrep -x nautilus", 10)
    vm.move(1100, 700)


def introduction(vm):
    yield 1.5
    vm.key("Super_L+a")
    yield 1.2
    vm.type("typecase", 0.08)
    yield 1.0
    vm.key("Return")
    vm.wait_shell(TYPECASE_RUNS, 30)
    yield 1.5
    yield vm.zoom(EMPTY_LIBRARY, length=1.2)
    vm.move(*CHOOSE)
    yield 1.0


def choose(vm):
    vm.click(*CHOOSE)
    yield 0.4
    yield vm.zoom(DIALOG, length=1.0)
    yield 0.8
    vm.move(*DOCUMENTS)
    yield 0.4
    vm.click(*DOCUMENTS, 2)
    yield 1.2
    vm.move(*NEW_FOLDER)
    yield 0.4
    vm.click(*NEW_FOLDER)
    yield 1.0
    vm.type("Writing\n", 0.09)
    yield 1.0


def synced(vm):
    vm.move(*SELECT)
    yield 1.0


def library(vm):
    vm.click(*SELECT)
    yield 0.6
    yield vm.zoom(None, length=1.0)
    yield 1.0


def new_sheet(vm):
    vm.move(*PLUS)
    yield 0.5
    vm.click(*PLUS)
    yield 0.8
    vm.move(*NEW_SHEET)
    yield 0.4
    vm.click(*NEW_SHEET)
    yield 0.6


def write(vm):
    yield vm.zoom(SHEET, length=1.2)
    vm.type("# The Lighthouse\n\n", 0.09)
    yield 1.5
    vm.type("The lamp had burned every night for forty years.", 0.06)
    yield 1.5


def saved(vm):
    yield vm.zoom(None, length=1.0)
    vm.key("Control_L+q")  # one window at a time
    vm.wait_shell(TYPECASE_GONE, 10)
    yield 0.4
    vm.click(*FILES)
    vm.wait_shell("pgrep -x nautilus >/dev/null", 15)
    yield 1.6
    vm.click(*FILES_DOCUMENTS, 2)
    yield 1.2
    vm.click(*FILES_FIRST, 2)
    yield 0.8
    vm.move(1100, 700)
    yield vm.zoom(FILE, length=1.2)
    yield 1.0


def closing(vm):
    yield 0.5
    yield vm.zoom(None, length=1.2)


SCENES = [
    Scene(
        "The first time you open Typecase, it asks for your library: the folder where your texts live.",
        "Wenn du Typecase zum ersten Mal öffnest, fragt es nach deiner Bibliothek: dem Ordner, in dem deine "
        "Texte liegen.",
        introduction,
        say="The first time you open Type case, it asks for your library: the folder where your texts live.",
    ),
    Scene(
        "Pick a folder, or create a new one, like this one in Documents.",
        "Wähle einen Ordner aus oder lege einen neuen an, wie diesen hier in „Documents“.",
        choose,
    ),
    Scene(
        "Writing on more than one computer? Choose a folder that Nextcloud, Syncthing or another sync service "
        "keeps up to date.",
        "Du schreibst auf mehreren Computern? Dann wähle einen Ordner, den Nextcloud, Syncthing oder ein anderer "
        "Sync-Dienst aktuell hält.",
        synced,
        say="Writing on more than one computer? Choose a folder that Next cloud, Sync thing, or another sync "
            "service keeps up to date.",
    ),
    Scene(
        "Now this folder is your library. Its subfolders become groups, its Markdown files become sheets.",
        "Jetzt ist dieser Ordner deine Bibliothek. Seine Unterordner werden zu Gruppen, seine Markdown-Dateien "
        "zu Blättern.",
        library,
    ),
    Scene(
        "Click the plus button for a new sheet.",
        "Klicke auf den Plus-Knopf für ein neues Blatt.",
        new_sheet,
    ),
    Scene(
        "Start writing. Your first heading becomes the name of the sheet.",
        "Fang an zu schreiben. Deine erste Überschrift wird zum Namen des Blatts.",
        write,
    ),
    Scene(
        "There's no Save button: Typecase saves as you type, into a plain Markdown file that any text editor "
        "can open.",
        "Einen Speichern-Knopf gibt es nicht: Typecase speichert, während du tippst, in eine ganz normale "
        "Markdown-Datei, die jeder Texteditor öffnen kann.",
        saved,
        say="There's no Save button: Type case saves as you type, into a plain Markdown file that any text "
            "editor can open.",
    ),
    Scene(
        "Next, learn how to format your text, with or without Markdown.",
        "Als Nächstes erfährst du, wie du deinen Text formatierst, mit oder ohne Markdown.",
        closing,
        hold=0.5,
    ),
]

VIDEO = vmkit.Video(
    name="first-steps",
    title="First steps",
    topic="Write",
    summary="Open Typecase for the first time, choose a folder for your library, and write your first sheet.",
    still=30,
)

if __name__ == "__main__":
    vmkit.run(VIDEO, SCENES, before=opening)
