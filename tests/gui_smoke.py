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
    check(win.content_title.get_subtitle() == "", "Ohne offenes Blatt kein Zähler")
    select(LIB / "Bücher")
    win._do_delete(win._selected_node())
    check(not (LIB / "Bücher").exists(), "Gruppe wird gelöscht")
    check(win._index_of(LIB / "Bücher") is None, "Gelöschte Gruppe verschwindet aus der Seitenleiste")

    select(LIB / "a.md")
    check(ed.path == LIB / "a.md", "Danach lässt sich wieder ein Blatt öffnen")

    # Listen im Editor fortsetzen (Eingabetaste wie bei echter Tastatur)
    from gi.repository import Gdk

    win.lookup_action("new-sheet").activate(None)
    list_sheet = ed.path
    enter = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))

    def press_enter():
        return enter.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType(0))

    ed.buffer.insert_at_cursor("1. Eins")
    yield 0.4  # Zähler aktualisiert sich kurz nach dem Tippen
    check(win.content_title.get_subtitle() == "1 word · 7 characters", "Zähler zeigt Wörter und Zeichen")
    check(press_enter() and text(ed) == "1. Eins\n2. ", "Eingabetaste setzt nummerierte Liste fort")
    ed.buffer.insert_at_cursor("Zwei")
    press_enter()
    check(text(ed) == "1. Eins\n2. Zwei\n3. ", "Nummer zählt hoch")
    check(press_enter() and text(ed) == "1. Eins\n2. Zwei\n", "Leerer Listenpunkt beendet die Liste")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n2. Zwei\n3. ", "Rückgängig nimmt das Beenden in einem Schritt zurück")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n2. Zwei", "Rückgängig nimmt die Fortsetzung in einem Schritt zurück")
    ed.buffer.set_text("Absatz")
    ed.buffer.place_cursor(ed.buffer.get_end_iter())
    check(not press_enter(), "Normaler Text: Eingabetaste bleibt unberührt")
    ed.flush()
    select(LIB / "a.md")

    # Zustand merken: zweites Fenster stellt Blatt, Gruppen und Größe wieder her
    group = LIB / "Merken"
    group.mkdir()
    (group / "Blatt.md").write_text("gemerkt")
    win._reload()
    select(group)
    win.selection.get_selected_item().set_expanded(True)
    select(group / "Blatt.md")
    from typecase import config

    check(config.load().get("last_sheet") == "Merken/Blatt.md", "Letztes Blatt wird gemerkt")
    win._save_state()
    check(config.load().get("expanded_groups") == ["Merken"], "Aufgeklappte Gruppen werden gemerkt")
    saved = config.load()
    # Unter Tiling-Fenstermanagern gilt ein Fenster als maximiert; dann wird nur das gemerkt.
    check(isinstance(saved.get("window_width"), int) or saved.get("window_maximized") is True, "Fenstergröße wird gemerkt")
    from typecase.window import TypecaseWindow

    second = TypecaseWindow(application=app)
    check(second.editor.path == group / "Blatt.md", "Neustart öffnet das letzte Blatt")
    check(second._index_of(group / "Blatt.md") is not None, "Neustart klappt die Gruppe wieder auf")
    check(text(second.editor) == "gemerkt", "Neustart lädt den Text des letzten Blatts")
    second.close()
    select(LIB / "a.md")

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

    # --- Änderungen von außen (Sync-Programme, andere Editoren) ---
    def conflict_copies():
        return sorted(p for p in LIB.iterdir() if "conflict" in p.name)

    def answer_dialog(response):
        dialog = win.get_visible_dialog()
        dialog.emit("response", response)
        dialog.force_close()

    sheet_b = LIB / "b.md"
    select(sheet_b)
    sheet_b.write_text("Von außen", encoding="utf-8")
    yield 1.0
    check(text(ed) == "Von außen" and win.get_visible_dialog() is None, "Fremde Änderung wird ohne Rückfrage neu geladen")

    ed.buffer.insert_at_cursor("Ich ")
    yield 1.6
    check(read("b.md") == text(ed) and not ed.in_conflict, "Eigenes Speichern gilt nicht als fremde Änderung")

    ed.buffer.insert_at_cursor("tippe")
    mine = text(ed)
    sheet_b.write_text("Fremd 1", encoding="utf-8")
    check(not ed.flush(), "Speichern wird verweigert, wenn die Datei fremd geändert wurde")
    check(read("b.md") == "Fremd 1", "Fremde Änderung wird nicht überschrieben")
    check(ed.in_conflict and win.get_visible_dialog() is not None, "Konfliktdialog erscheint")
    answer_dialog("mine")
    copies = conflict_copies()
    check(read("b.md") == mine and len(copies) == 1 and copies[0].read_text() == "Fremd 1", "Meine Fassung behalten: die andere liegt als Kopie daneben")
    check(win._index_of(copies[0]) is not None, "Konfliktkopie erscheint in der Seitenleiste")
    yield 1.0
    check(not ed.in_conflict and win.get_visible_dialog() is None, "Nach der Entscheidung kein erneuter Konflikt")

    ed.buffer.insert_at_cursor("!")
    mine = text(ed)
    sheet_b.write_text("Fremd 2", encoding="utf-8")  # bevor das Autosave greift
    yield 0.6
    check(ed.in_conflict and win.get_visible_dialog() is not None, "Konflikt wird auch ohne Speichern erkannt")
    check(read("b.md") == "Fremd 2", "Autosave überschreibt die fremde Änderung nicht")
    answer_dialog("theirs")
    check(text(ed) == "Fremd 2" and read("b.md") == "Fremd 2", "Andere Fassung laden: Blatt zeigt sie")
    check(any(p.read_text() == mine for p in conflict_copies()), "Andere Fassung laden: meine liegt als Kopie daneben")

    sheet_b.unlink()
    yield 1.0
    check(ed.path is None and win._index_of(sheet_b) is None, "Außen gelöschtes Blatt schließt und verschwindet")

    select(LIB / "a.md")
    ed.buffer.insert_at_cursor("Rettung")
    mine = text(ed)
    (LIB / "a.md").unlink()
    yield 1.0
    check(read("a.md") == mine and ed.path == LIB / "a.md", "Außen gelöscht mit Eingabe: Fassung wird neu gespeichert")

    (LIB / "Extern.md").write_text("x")
    (LIB / "ExternGruppe").mkdir()
    (LIB / "ExternGruppe" / "Innen.md").write_text("y")
    yield 1.2
    check(win._index_of(LIB / "Extern.md") is not None, "Neues Blatt von außen erscheint")
    check(win._index_of(LIB / "ExternGruppe") is not None, "Neue Gruppe von außen erscheint")
    (LIB / "ExternGruppe" / "Zwei.md").write_text("z")
    yield 1.2
    select(LIB / "ExternGruppe")
    win.selection.get_selected_item().set_expanded(True)
    check(win._index_of(LIB / "ExternGruppe" / "Zwei.md") is not None, "Auch neue Gruppen werden beobachtet")
    check(ed.path == LIB / "a.md", "Offenes Blatt bleibt beim Aktualisieren offen")
    select(LIB / "a.md")

    # Fenster: Seitenleiste, Vollbild, Tastenkürzel, Über
    shown = win.split.get_show_sidebar()
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() != shown, "F9-Aktion blendet die Seitenleiste um")
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() == shown, "F9-Aktion blendet sie wieder ein")
    win.sidebar_button.emit("clicked")  # wie ein Klick
    check(not win.split.get_show_sidebar() and not win.sidebar_button.get_active(), "Knopf blendet die Seitenleiste aus")
    win.sidebar_button.emit("clicked")
    check(win.split.get_show_sidebar() and win.sidebar_button.get_active(), "Knopf blendet sie wieder ein")
    win.lookup_action("fullscreen").activate(None)
    yield 1.5  # der Fenstermanager braucht einen Moment
    check(win.is_fullscreen(), "F11-Aktion schaltet Vollbild ein")
    win.lookup_action("fullscreen").activate(None)
    yield 1.5
    check(not win.is_fullscreen(), "F11-Aktion schaltet Vollbild aus")
    win.lookup_action("show-shortcuts").activate(None)
    check(win.get_visible_dialog() is not None, "Tastenkürzel-Übersicht öffnet sich")
    win.get_visible_dialog().force_close()
    app.lookup_action("about").activate(None)
    check(win.get_visible_dialog() is not None, "Über-Dialog öffnet sich")
    win.get_visible_dialog().force_close()
    accels = {name: app.get_accels_for_action(name) for name in ["win.fullscreen", "win.toggle-sidebar", "app.quit"]}
    check(accels == {"win.fullscreen": ["F11"], "win.toggle-sidebar": ["F9", "<Shift><Control>l"], "app.quit": ["<Control>q"]}, "Tastenkürzel sind registriert")

    # Beenden (Strg+Q) sichert ebenfalls
    ed.buffer.insert_at_cursor("W")
    expected_a = text(ed)
    while win.get_visible_dialog() is not None:  # Offener Umbenennen-Dialog fängt das Schließen zuerst ab.
        win.get_visible_dialog().force_close()
    app.lookup_action("quit").activate(None)
    check(read("a.md") == expected_a, "Beenden sichert ungespeicherte Eingaben")
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
