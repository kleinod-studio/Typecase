"""Fährt die echte Oberfläche automatisch durch und prüft den Schutz vor Datenverlust.

Braucht eine laufende Desktop-Sitzung. Start: python3 tests/gui_smoke.py
Benutzt einen temporären Ordner und eine eigene Konfiguration, nichts von deinen Daten."""

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Im Home-Verzeichnis, damit der System-Papierkorb funktioniert (auf /tmp oft nicht).
TMP = Path(tempfile.mkdtemp(prefix="typecase-smoke-", dir=Path.home() / ".cache"))
LIB = TMP / "lib"
LIB.mkdir()
(LIB / "a.md").write_text("Alpha", encoding="utf-8")
(LIB / "b.md").write_text("Beta", encoding="utf-8")
os.environ["XDG_CONFIG_HOME"] = str(TMP / "cfg")
(TMP / "cfg" / "typecase").mkdir(parents=True)
(TMP / "cfg" / "typecase" / "config.json").write_text(f'{{"library_path": "{LIB}"}}')

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from typecase.main import TypecaseApplication  # noqa: E402

failures = []
checked = []


def check(condition, message):
    checked.append(message)
    print(("ok    " if condition else "FEHLER"), message)
    if not condition:
        failures.append(message)


def text(ed):
    return ed.buffer.get_text(*ed.buffer.get_bounds(), True)


def read(name):
    return (LIB / name).read_text(encoding="utf-8")


def steps(win, app):
    ed = win.editor
    sel = win.selection

    sel.set_selected(0)
    check(ed.path == LIB / "a.md", "Blatt a wird per Auswahl geöffnet")
    check(text(ed) == "Alpha", "Text von a steht im Editor")

    ed.buffer.insert_at_cursor(" eins")
    yield 1.4
    check(read("a.md") == " einsAlpha" and text(ed) == " einsAlpha", "Autosave schreibt nach kurzer Pause")

    ed.buffer.insert_at_cursor("X")
    expected_a = text(ed)
    check(expected_a == " einsXAlpha", "Eingabe steht im Editor")
    sel.set_selected(1)  # sofort wechseln, bevor der Timer feuert
    check(read("a.md") == expected_a, "Wechsel sichert ungespeicherte Eingaben zuerst")
    check(ed.path == LIB / "b.md", "Blatt b ist offen")
    check(not ed.buffer.props.can_undo, "Rückgängig holt kein anderes Blatt zurück")

    ed.buffer.insert_at_cursor("Y")
    ed.buffer.undo()
    check(text(ed) == "Beta", "Rückgängig wirkt im Blatt")
    ed.buffer.redo()
    check(text(ed) == "YBeta", "Wiederholen wirkt im Blatt")
    yield 1.4
    check(read("b.md") == "YBeta", "Autosave nach Rückgängig/Wiederholen")

    # Speichern schlägt fehl: Ordner schreibgeschützt
    ed.buffer.insert_at_cursor("Z")
    expected_b = text(ed)
    os.chmod(LIB, stat.S_IRUSR | stat.S_IXUSR)
    sel.set_selected(0)
    check(ed.path == LIB / "b.md", "Wechsel wird bei Speicherfehler verweigert")
    check(text(ed) == expected_b and read("b.md") == "YBeta", "Eingabe bleibt bei Speicherfehler erhalten")
    check(sel.get_selected() == 1, "Auswahl springt auf das offene Blatt zurück")
    check(not [p for p in LIB.iterdir() if p.name.endswith(".tmp")], "Keine Temp-Dateien übrig")

    os.chmod(LIB, stat.S_IRWXU)
    sel.set_selected(0)
    check(ed.path == LIB / "a.md", "Wechsel klappt wieder, sobald Speichern geht")
    check(read("b.md") == expected_b, "Zurückgehaltene Eingabe wurde nachgeholt")

    # --- Neu, Umbenennen, Löschen ---
    def select(path):
        win.selection.set_selected(win._index_of(path))

    win.lookup_action("new-sheet").activate(None)
    new_sheet = LIB / "Untitled.md"
    check(new_sheet.exists() and ed.path == new_sheet, "Neues Blatt wird angelegt und geöffnet")
    check(not (LIB / "a.md").read_text().startswith("Untitled"), "Neues Blatt überschreibt nichts")
    win.lookup_action("new-sheet").activate(None)
    check((LIB / "Untitled 2.md").exists(), "Zweites neues Blatt bekommt einen freien Namen")

    win.lookup_action("new-group").activate(None)
    check((LIB / "New Group").is_dir(), "Neue Gruppe wird angelegt")
    win._do_rename(win._selected_node(), "Romane")
    check((LIB / "Romane").is_dir() and not (LIB / "New Group").exists(), "Gruppe wird umbenannt")
    check(win._selected_node().path == LIB / "Romane", "Umbenannte Gruppe bleibt ausgewählt")

    win.lookup_action("new-sheet").activate(None)  # Gruppe ist ausgewählt, also landet das Blatt darin
    inner = LIB / "Romane" / "Untitled.md"
    check(inner.exists() and ed.path == inner, "Neues Blatt landet in der ausgewählten Gruppe")
    ed.buffer.insert_at_cursor("Kapitel")
    win._do_rename(win._selected_node(), "Entwurf")
    inner = LIB / "Romane" / "Entwurf.md"
    check(inner.exists() and ed.path == inner, "Offenes Blatt wird umbenannt, Editor folgt")
    check(inner.read_text() == "Kapitel", "Ungesicherte Eingabe überlebt das Umbenennen")

    select(LIB / "Romane")
    win._do_rename(win._selected_node(), "Bücher")
    inner = LIB / "Bücher" / "Entwurf.md"
    check(ed.path == inner, "Gruppe mit offenem Blatt umbenannt, Editor folgt")
    ed.buffer.insert_at_cursor("!")
    check(ed.flush() and inner.read_text() == "!Kapitel" or inner.read_text() == "Kapitel!", "Speichern geht nach Umbenennen an den neuen Ort")

    select(LIB / "Untitled 2.md")
    win._do_rename(win._selected_node(), "a")
    check((LIB / "Untitled 2.md").exists() and read("a.md") != "", "Umbenennen auf vorhandenen Namen wird verweigert")
    win._do_rename(win._selected_node(), "../böse")
    check((LIB / "Untitled 2.md").exists(), "Ungültiger Name wird verweigert")

    select(inner)
    win._do_delete(win._selected_node())
    check(not inner.exists() and ed.path is None, "Gelöschtes offenes Blatt verschwindet, Editor schließt")
    select(LIB / "Bücher")
    win._do_delete(win._selected_node())
    check(not (LIB / "Bücher").exists(), "Gruppe wird gelöscht")
    check(win._index_of(LIB / "Bücher") is None, "Gelöschte Gruppe verschwindet aus der Seitenleiste")

    select(LIB / "a.md")
    check(ed.path == LIB / "a.md", "Danach lässt sich wieder ein Blatt öffnen")

    # Kontextmenü: echter Rechtsklick auf die erste Zeile
    first_row = win.list_view.get_first_child().get_first_child()  # TreeExpander der ersten Zeile
    right_click = next(c for c in first_row.observe_controllers() if isinstance(c, Gtk.GestureClick))
    right_click.emit("pressed", 1, 20.0, 10.0)
    check(win.row_menu.is_visible(), "Rechtsklick öffnet das Kontextmenü")
    win.row_menu.popdown()

    # Kontextmenü: Aktionen müssen vom Popover aus gefunden werden
    while win.get_visible_dialog() is not None:
        win.get_visible_dialog().force_close()
    win.row_menu.popup()
    win.row_menu.activate_action("win.rename", None)
    check(win.get_visible_dialog() is not None, "Kontextmenü: Umbenennen öffnet den Dialog")
    win.get_visible_dialog().force_close()
    win.row_menu.activate_action("win.delete", None)
    check(win.get_visible_dialog() is not None, "Kontextmenü: Löschen fragt nach")
    win.get_visible_dialog().force_close()
    win.row_menu.popdown()

    # Fenster schließen sichert ebenfalls
    ed.buffer.insert_at_cursor("W")
    expected_a = text(ed)
    while win.get_visible_dialog() is not None:  # Offener Umbenennen-Dialog fängt das Schließen zuerst ab.
        win.get_visible_dialog().force_close()
    win.close()
    check(read("a.md") == expected_a, "Schließen sichert ungespeicherte Eingaben")
    app.quit()


def on_activate(app):
    from typecase.window import TypecaseWindow

    win = TypecaseWindow(application=app)  # do_activate nutzt danach dieses Fenster
    win.present()
    gen = steps(win, app)

    def advance():
        try:
            delay = next(gen)
        except StopIteration:
            return GLib.SOURCE_REMOVE
        except Exception as error:  # Testfehler sollen den Lauf beenden, nicht hängen lassen
            check(False, f"Unerwarteter Fehler: {error!r}")
            app.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(int(delay * 1000), advance)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(500, advance)


app = TypecaseApplication()
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)  # läuft getrennt von einem offenen Typecase
app.connect("activate", on_activate)
app.run(None)

os.chmod(LIB, stat.S_IRWXU)
shutil.rmtree(TMP, ignore_errors=True)
if not checked:
    failures.append("Es wurde keine Prüfung ausgeführt")
print(f"\n{len(checked)} Prüfungen, " + ("alle bestanden." if not failures else f"{len(failures)} fehlgeschlagen."))
sys.exit(1 if failures else 0)
