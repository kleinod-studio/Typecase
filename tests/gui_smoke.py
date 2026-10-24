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
# TYPECASE_CODE: anderen Code testen, z. B. den im Flatpak installierten (/app/share/typecase)
sys.path.insert(0, os.environ.get("TYPECASE_CODE", str(ROOT / "src")))

# Im Home-Verzeichnis, damit der System-Papierkorb funktioniert (auf /tmp oft nicht).
TMP = Path(tempfile.mkdtemp(prefix="typecase-smoke-", dir=Path.home() / ".cache"))
LIB = TMP / "lib"
LIB.mkdir()
(LIB / "a.md").write_text("Alpha", encoding="utf-8")
(LIB / "b.md").write_text("Beta", encoding="utf-8")
os.environ["XDG_CONFIG_HOME"] = str(TMP / "cfg")
os.environ["XDG_DATA_HOME"] = str(TMP / "data")  # importierte Vorlagen
(TMP / "cfg" / "typecase").mkdir(parents=True)
(TMP / "cfg" / "typecase" / "config.json").write_text(f'{{"library_path": "{LIB}"}}')

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from typecase.main import TypecaseApplication, _fall_back_to_utf8  # noqa: E402

try:  # wie beim echten Start: ohne passende Sprachdaten (Flatpak) in C.UTF-8 statt ASCII
    import locale

    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    _fall_back_to_utf8()

failures = []
checked = []


def check(condition, message):
    checked.append(message)
    print(("ok    " if condition else "FEHLER"), message)
    if not condition:
        failures.append(message)


def text(ed):
    return ed.buffer.get_text(*ed.buffer.get_bounds(), True)


def wait_until(condition, timeout=3.0):
    """Wartet (im Schritt-Generator mit 'yield from'), bis condition() wahr ist – höchstens timeout Sekunden.
    Robuster als feste Pausen, wenn Dateibenachrichtigungen auf einem beschäftigten Rechner länger brauchen."""
    waited = 0.0
    while not condition() and waited < timeout:
        yield 0.1
        waited += 0.1


def body(path):
    """Textteil einer Datei ohne Dateikopf (neue Blätter bekommen ein Erstelldatum im Kopf)."""
    from typecase.frontmatter import split

    return split(path.read_text(encoding="utf-8"))[1]


def read(name):
    return (LIB / name).read_text(encoding="utf-8")


def steps(win, app):
    ed = win.editor
    sel = win.selection

    sel.set_selected(0)
    check(ed.path == LIB / "a.md", "Blatt a wird per Auswahl geöffnet")
    check(not win.list_view.get_single_click_activate(), "Darüberfahren mit der Maus wählt kein Blatt aus")
    check(text(ed) == "Alpha", "Text von a steht im Editor")

    ed.buffer.insert_at_cursor(" eins")
    yield from wait_until(lambda: read("a.md") == " einsAlpha")
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
    yield from wait_until(lambda: read("b.md") == "YBeta")
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
        if path.suffix == ".md" and ed.path != path:
            check(False, f"Auswahl von {path.name} öffnet es im Editor (offen: {ed.path and ed.path.name})")

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
    check(body(inner) == "Kapitel", "Ungesicherte Eingabe überlebt das Umbenennen")

    select(LIB / "Romane")
    win._do_rename(win._selected_node(), "Bücher")
    inner = LIB / "Bücher" / "Entwurf.md"
    check(ed.path == inner, "Gruppe mit offenem Blatt umbenannt, Editor folgt")
    ed.buffer.insert_at_cursor("!")
    check(ed.flush() and body(inner) in ("!Kapitel", "Kapitel!"), "Speichern geht nach Umbenennen an den neuen Ort")

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

    # Nachnummerieren und Einrücken
    def press(keyval, state=0):
        return enter.emit("key-pressed", keyval, 0, Gdk.ModifierType(state))

    def cursor_to(line, column):
        ed.buffer.place_cursor(ed.buffer.get_iter_at_line_offset(line, column)[1])

    ed.buffer.set_text("1. Eins\n2. Zwei\n3. Drei")
    cursor_to(0, 7)
    press(Gdk.KEY_Return)
    check(text(ed) == "1. Eins\n2. \n3. Zwei\n4. Drei", "Eingefügter Punkt: die folgenden zählen mit hoch")
    ed.buffer.insert_at_cursor("Neu")
    check(press(Gdk.KEY_Tab) and text(ed) == "1. Eins\n    1. Neu\n2. Zwei\n3. Drei", "Tab rückt ein und nummeriert beide Ebenen neu")
    cursor = ed.buffer.get_iter_at_mark(ed.buffer.get_insert())
    check((cursor.get_line(), cursor.get_line_offset()) == (1, 10), "Cursor bleibt hinter dem Wort")
    check(press(Gdk.KEY_ISO_Left_Tab, Gdk.ModifierType.SHIFT_MASK) and text(ed) == "1. Eins\n2. Neu\n3. Zwei\n4. Drei", "Umschalt+Tab rückt aus")
    ed.buffer.undo()
    check(text(ed) == "1. Eins\n    1. Neu\n2. Zwei\n3. Drei", "Rückgängig nimmt das Ausrücken in einem Schritt zurück")

    ed.buffer.set_text("- A")
    ed.buffer.place_cursor(ed.buffer.get_end_iter())
    press(Gdk.KEY_Return)
    press(Gdk.KEY_Tab)
    check(text(ed) == "- A\n    - ", "Tab rückt einen leeren Unterpunkt ein")
    press(Gdk.KEY_Return)
    check(text(ed) == "- A\n- ", "Enter auf leerem Unterpunkt rückt erst aus")
    press(Gdk.KEY_Return)
    check(text(ed) == "- A\n", "Enter auf leerem Punkt der obersten Ebene beendet die Liste")
    ed.buffer.set_text("Normaler Text")
    check(not press(Gdk.KEY_Tab), "Tab außerhalb von Listen bleibt ein normales Tab")

    # Markdown-Gestaltung beim Tippen
    def tags_at(offset):
        return {t.props.name for t in ed.buffer.get_iter_at_offset(offset).get_tags()}

    ed.buffer.set_text("")
    ed.buffer.insert_at_cursor("# Titel\nEin **fettes** Wort")
    yield 0.2
    check("md-h1" in tags_at(3) and "md-syntax" in tags_at(0), "Überschrift wird groß, # gedimmt")
    check("md-bold" in tags_at(15) and "md-syntax" in tags_at(12), "Fett wird fett, ** gedimmt")
    ed.buffer.insert(ed.buffer.get_iter_at_offset(14), " ")  # "** fettes**" ist kein Fett mehr
    yield 0.2
    check("md-bold" not in tags_at(16), "Gestaltung verschwindet, wenn die Auszeichnung kaputtgeht")
    ed.buffer.set_text("```\n**kein fett**\n```\nnach dem Block **fett**")
    yield 0.2
    check("md-codeblock" in tags_at(6) and "md-bold" not in tags_at(6), "Codeblock: Inhalt als Code, nicht fett")
    check("md-bold" in tags_at(40), "Nach dem Codeblock wird wieder gestaltet")

    # Codeblock: Rahmen-Zeilen und Syntaxfarben
    ed.buffer.set_text("Text\n```python\nreturn 42\n```\nnoch Text\n```\nohne Sprache\n```")
    yield 0.2
    check(ed.styler.code_blocks == [(1, 3, True), (5, 7, True)], "Codeblöcke werden für den Rahmen erkannt")
    colored = [t for t in ed.buffer.get_iter_at_offset(16).get_tags() if t.props.foreground_set and not (t.props.name or "").startswith("md-")]
    check(colored, "Codeblock mit Sprache bekommt Syntaxfarben")
    plain = [t for t in ed.buffer.get_iter_at_offset(43).get_tags() if t.props.foreground_set]
    check(not plain, "Codeblock ohne Sprache bleibt ungefärbt")
    ed.buffer.insert(ed.buffer.get_iter_at_offset(14), "x")  # ```pythonx: unbekannte Sprache
    yield 0.2
    colored = [t for t in ed.buffer.get_iter_at_offset(17).get_tags() if t.props.foreground_set and not (t.props.name or "").startswith("md-")]
    check(not colored, "Farben verschwinden bei unbekannter Sprache")

    # Formatieren: Leiste und Tastenkürzel
    def fmt(kind):
        win.lookup_action("format").activate(GLib.Variant.new_string(kind))

    def select_text(a, b):
        ed.buffer.select_range(ed.buffer.get_iter_at_offset(a), ed.buffer.get_iter_at_offset(b))

    ed.buffer.set_text("Ein Wort hier")
    select_text(4, 8)
    fmt("bold")
    check(text(ed) == "Ein **Wort** hier", "Fett umschließt die Markierung")
    fmt("bold")
    check(text(ed) == "Ein Wort hier", "Zweites Fett nimmt es wieder weg")
    fmt("underline")
    check(text(ed) == "Ein <u>Wort</u> hier", "Unterstreichen setzt <u>…</u>")
    ed.buffer.undo()
    check(text(ed) == "Ein Wort hier", "Rückgängig nimmt eine Formatierung in einem Schritt zurück")
    ed.buffer.place_cursor(ed.buffer.get_iter_at_offset(6))
    fmt("italic")
    check(text(ed) == "Ein *Wort* hier", "Ohne Markierung wird das Wort unter dem Cursor formatiert")
    ed.buffer.set_text("Titel\nEins\nZwei")
    ed.buffer.place_cursor(ed.buffer.get_start_iter())
    fmt("h2")
    check(text(ed) == "## Titel\nEins\nZwei", "Überschrift setzt ## vor die Zeile")
    select_text(9, 17)
    fmt("numbered")
    check(text(ed) == "## Titel\n1. Eins\n2. Zwei", "Nummerierte Liste für alle markierten Zeilen")
    accels = {kind: app.get_accels_for_action(f"win.format::{kind}") for kind in ("bold", "italic", "underline", "link", "h1", "paragraph")}
    check(accels == {"bold": ["<Control>b"], "italic": ["<Control>i"], "underline": ["<Control>u"], "link": ["<Control>k"], "h1": ["<Control>1"], "paragraph": ["<Control>0"]}, "Tastenkürzel für Formatierungen sind registriert")
    bold_button = win.format_bar.get_first_child()
    ed.buffer.set_text("klick")
    select_text(0, 5)
    bold_button.emit("clicked")
    check(text(ed) == "**klick**", "Knopf in der Leiste formatiert")
    check(win.format_revealer.get_reveal_child(), "Formatierungsleiste ist anfangs sichtbar")
    from typecase import config as cfg2

    cfg2.update(format_bar=False)
    win.apply_settings()
    check(not win.format_revealer.get_reveal_child(), "Formatierungsleiste lässt sich abschalten")
    cfg2.update(format_bar=True)
    win.apply_settings()

    # Mauszeiger und Schreibmarke
    check(ed.view.get_cursor() is not None and ed.view.get_cursor().get_name() == "text", "Über dem Textblock erscheint der Text-Mauszeiger")
    check(ed.view.underline_caret and ed.view.has_css_class("underline-caret"), "Schreibmarke ist anfangs ein Unterstrich (GTK-Marke unsichtbar)")
    # Nicht abschalten: ohne sichtbare Schreibmarke scrollen die Pfeiltasten nur noch, statt sie zu bewegen.
    check(ed.view.get_cursor_visible(), "Pfeiltasten bewegen weiter die Schreibmarke (cursor-visible bleibt an)")
    cfg2.update(underline_caret=False)
    win.apply_settings()
    check(not ed.view.underline_caret and not ed.view.has_css_class("underline-caret"), "Abschaltbar: dann wieder die normale Schreibmarke")
    cfg2.update(underline_caret=True)
    win.apply_settings()
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

    win.inspector_split.set_show_sidebar(True)
    win._save_state()
    second = TypecaseWindow(application=app)
    second.present()  # erst beim Anzeigen wächst das Fenster über die Umbruchbreite – da blendete libadwaita es ein
    yield 0.8
    check(not second.inspector_split.get_show_sidebar(), "Eigenschaften sind beim Start immer ausgeblendet")
    second.inspector_split.set_collapsed(True)  # Fenster startet schmal und wird dann breit (Tiling, Maximieren)
    second.inspector_split.set_collapsed(False)
    check(not second.inspector_split.get_show_sidebar(), "Breiter werdendes Fenster blendet die Eigenschaften nicht ein")
    win.inspector_split.set_show_sidebar(False)
    check(second.editor.path == group / "Blatt.md", "Neustart öffnet das letzte Blatt")
    check(second._index_of(group / "Blatt.md") is not None, "Neustart klappt die Gruppe wieder auf")
    check(text(second.editor) == "gemerkt", "Neustart lädt den Text des letzten Blatts")
    check(second.editor.flush(), "Zweites Fenster hat nichts Ungesichertes")
    second.destroy()  # ohne close(): das würde Fenstergröße und Zustand des Tests überschreiben
    check(app.get_windows() == [win], "Nur noch das Testfenster ist offen")
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
    yield from wait_until(lambda: text(ed) == "Von außen")
    check(text(ed) == "Von außen" and win.get_visible_dialog() is None, "Fremde Änderung wird ohne Rückfrage neu geladen")

    ed.buffer.insert_at_cursor("Ich ")
    yield from wait_until(lambda: read("b.md") == text(ed))
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
    yield from wait_until(lambda: ed.in_conflict)
    check(ed.in_conflict and win.get_visible_dialog() is not None, "Konflikt wird auch ohne Speichern erkannt")
    check(read("b.md") == "Fremd 2", "Autosave überschreibt die fremde Änderung nicht")
    answer_dialog("theirs")
    check(text(ed) == "Fremd 2" and read("b.md") == "Fremd 2", "Andere Fassung laden: Blatt zeigt sie")
    check(any(p.read_text() == mine for p in conflict_copies()), "Andere Fassung laden: meine liegt als Kopie daneben")

    sheet_b.unlink()
    yield from wait_until(lambda: ed.path is None and win._index_of(sheet_b) is None)
    check(ed.path is None and win._index_of(sheet_b) is None, "Außen gelöschtes Blatt schließt und verschwindet")

    select(LIB / "a.md")
    ed.buffer.insert_at_cursor("Rettung")
    mine = text(ed)
    (LIB / "a.md").unlink()
    yield from wait_until(lambda: (LIB / "a.md").exists())
    check(read("a.md") == mine and ed.path == LIB / "a.md", "Außen gelöscht mit Eingabe: Fassung wird neu gespeichert")

    (LIB / "Extern.md").write_text("x")
    (LIB / "ExternGruppe").mkdir()
    (LIB / "ExternGruppe" / "Innen.md").write_text("y")
    yield from wait_until(lambda: win._index_of(LIB / "Extern.md") is not None and win._index_of(LIB / "ExternGruppe") is not None)
    check(win._index_of(LIB / "Extern.md") is not None, "Neues Blatt von außen erscheint")
    check(win._index_of(LIB / "ExternGruppe") is not None, "Neue Gruppe von außen erscheint")
    (LIB / "ExternGruppe" / "Zwei.md").write_text("z")
    yield from wait_until(lambda: str(LIB / "ExternGruppe" / "Zwei.md") in repr(win._tree_signature))
    select(LIB / "ExternGruppe")
    win.selection.get_selected_item().set_expanded(True)
    check(win._index_of(LIB / "ExternGruppe" / "Zwei.md") is not None, "Auch neue Gruppen werden beobachtet")
    check(ed.path == LIB / "a.md", "Offenes Blatt bleibt beim Aktualisieren offen")
    select(LIB / "a.md")

    # Volltextsuche
    (LIB / "ExternGruppe" / "Fabel.md").write_text("Vorher.\nEs war einmal ein Drache, der schlief.\n")
    (LIB / "Drachenkunde.md").write_text("Nichts hier.")
    yield from wait_until(lambda: win._index_of(LIB / "Drachenkunde.md") is not None)
    win.lookup_action("search").activate(None)
    check(win.search_bar.get_search_mode() and win.search_button.get_active(), "Strg+Umschalt+F öffnet die Suche")
    win.search_entry.set_text("drache")
    yield from wait_until(lambda: win.sidebar_stack.get_visible_child_name() == "results")  # Suchfeld wartet kurz
    rows = []
    row = win.results.get_row_at_index(0)
    while row is not None:
        rows.append(row.hit)
        row = win.results.get_row_at_index(len(rows))
    check(win.sidebar_stack.get_visible_child_name() == "results", "Treffer ersetzen den Ordnerbaum")
    check([h.name for h in rows] == ["Drachenkunde", "Fabel"], "Treffer im Namen zuerst, dann im Text")
    ed.buffer.insert_at_cursor("Ein Drache auch hier ")  # ungesichert im offenen Blatt
    win.search_entry.set_text("drache ")
    win.search_entry.set_text("drache")
    yield 0.6
    names = []
    row = win.results.get_row_at_index(0)
    while row is not None:
        names.append(row.hit.name)
        row = win.results.get_row_at_index(len(names))
    check(ed.path.stem in names, "Suche findet auch Ungespeichertes im offenen Blatt")
    win._open_hit(next(h for h in rows if h.name == "Fabel"))
    yield 0.3
    selected = ed.buffer.get_text(*ed.buffer.get_selection_bounds(), True) if ed.buffer.get_has_selection() else ""
    check(ed.path == LIB / "ExternGruppe" / "Fabel.md" and selected == "Drache", "Treffer öffnet das Blatt und markiert die Fundstelle")
    win.search_entry.set_text("Einhorn")
    yield 0.6
    check(win.sidebar_stack.get_visible_child_name() == "no-results", "Keine Treffer wird angezeigt")
    win.search_entry.emit("stop-search")
    check(not win.search_bar.get_search_mode() and win.sidebar_stack.get_visible_child_name() == "library", "Escape schließt die Suche, Ordnerbaum kommt zurück")
    check(win._index_of(LIB / "ExternGruppe" / "Fabel.md") == win.selection.get_selected(), "Geöffnetes Blatt ist im Baum ausgewählt")
    check(win.find_bar.get_search_mode() and win.find_bar.entry.get_text() == "Drache", "Treffer übernimmt das Suchwort in die Suchleiste des Blatts")
    win.find_bar.set_search_mode(False)

    # Suchen und Ersetzen im Blatt
    bar = win.find_bar
    ed.buffer.set_text("Rot und rot und ROT, dazu Blau.")
    ed.buffer.place_cursor(ed.buffer.get_start_iter())
    win.lookup_action("find").activate(None)
    check(bar.get_search_mode() and bar.context.get_highlight(), "Strg+F öffnet die Suchleiste mit Hervorhebung")
    bar.entry.set_text("rot")
    yield from wait_until(lambda: bar.context.get_occurrences_count() == 3)

    def selection():
        bounds = ed.buffer.get_selection_bounds()
        return (bounds[0].get_offset(), bounds[1].get_offset()) if bounds else None

    check(bar.context.get_occurrences_count() == 3, "Alle drei Fundstellen werden gezählt (ohne Groß/klein)")
    check(selection() == (0, 3) and bar.label.get_text() == "1 of 3", "Erster Treffer ist markiert: 1 von 3")
    bar.find_next()
    check(selection() == (8, 11) and bar.label.get_text() == "2 of 3", "Weiter springt zum zweiten Treffer")
    bar.find_previous()
    check(selection() == (0, 3), "Zurück springt zum ersten Treffer")
    bar.find_previous()
    check(selection() == (16, 19), "Zurück vom ersten springt ans Ende (rundherum)")
    bar.replace_entry.set_text("Grün")
    bar.replace()
    check(text(ed) == "Rot und rot und Grün, dazu Blau.", "Ersetzen ersetzt nur den markierten Treffer")
    bar.replace_all()
    check(text(ed) == "Grün und Grün und Grün, dazu Blau.", "Alle ersetzen ersetzt den Rest")
    ed.buffer.undo()
    check(text(ed) == "Rot und rot und Grün, dazu Blau.", "Rückgängig nimmt Alle ersetzen in einem Schritt zurück")
    bar.entry.set_text("Gelb")
    yield 0.6
    check(bar.label.get_text() == "No matches" and bar.entry.has_css_class("error"), "Keine Treffer wird angezeigt")
    win.lookup_action("replace").activate(None)
    check(bar.replace_toggle.get_active(), "Strg+H öffnet die Leiste mit Ersetzen")
    bar.entry.emit("stop-search")
    check(not bar.get_search_mode() and not bar.context.get_highlight(), "Escape schließt die Leiste und entfernt die Hervorhebung")
    select(LIB / "a.md")

    # Verschieben: Ziehen und Ablegen, "Verschieben nach …"
    def row_widget(path):
        child = win.list_view.get_first_child()
        while child is not None:
            expander = child.get_first_child()
            row = expander.get_list_row() if isinstance(expander, Gtk.TreeExpander) else None
            if row is not None and row.get_item().node.path == path:
                return expander
            child = child.get_next_sibling()
        return None

    def controller(widget, kind):
        return next(c for c in widget.observe_controllers() if isinstance(c, kind))

    select(LIB / "a.md")
    content = read("a.md")
    group_row = row_widget(LIB / "ExternGruppe")
    check(isinstance(controller(row_widget(LIB / "a.md"), Gtk.DragSource), Gtk.DragSource), "Einträge lassen sich ziehen")
    dropped = controller(group_row, Gtk.DropTarget).emit("drop", str(LIB / "a.md"), 0.0, 0.0)
    moved = LIB / "ExternGruppe" / "a.md"
    check(dropped and moved.exists() and not (LIB / "a.md").exists(), "Ablegen auf einer Gruppe verschiebt hinein")
    check(ed.path == moved and moved.read_text() == content, "Offenes Blatt zieht mit, Inhalt unverändert")
    check(win._index_of(moved) is not None and win.selection.get_selected() == win._index_of(moved), "Verschobenes Blatt ist sichtbar und ausgewählt")
    dropped = controller(row_widget(LIB / "Extern.md"), Gtk.DropTarget).emit("drop", str(moved), 0.0, 0.0)
    check(dropped and (LIB / "a.md").exists() and ed.path == LIB / "a.md", "Ablegen auf einem Blatt verschiebt in dessen Gruppe")
    check(not win._move(LIB / "ExternGruppe", LIB / "ExternGruppe"), "Gruppe lässt sich nicht in sich selbst verschieben")
    (LIB / "Merken" / "a.md").write_text("anderes")
    check(not win._move(LIB / "a.md", LIB / "Merken") and read("a.md") == content, "Gleichnamiges am Ziel wird nie überschrieben")
    (LIB / "Merken" / "a.md").unlink()
    root_drop = controller(win.sidebar_stack.get_child_by_name("library"), Gtk.DropTarget)
    check(not root_drop.emit("drop", "Ein Stück Text aus dem Editor", 0.0, 0.0), "Fremder gezogener Text wird ignoriert")

    select(LIB / "Extern.md")
    win.lookup_action("move").activate(None)
    dialog = win.get_visible_dialog()
    choice = dialog.get_extra_child()
    labels = [choice.get_model().get_string(i) for i in range(choice.get_model().get_n_items())]
    check("ExternGruppe" in labels and "Library (top level)" not in labels, "Verschieben nach … bietet passende Ziele an")
    choice.set_selected(labels.index("ExternGruppe"))
    dialog.emit("response", "move")
    dialog.force_close()
    check((LIB / "ExternGruppe" / "Extern.md").exists() and ed.path == LIB / "ExternGruppe" / "Extern.md", "Verschieben nach … verschiebt per Tastatur")
    select(LIB / "a.md")

    # Meta-Informationen: Dateikopf ausgeblendet, Seitenfenster rechts
    from typecase.frontmatter import parse, split
    from gi.repository import Adw

    meta = LIB / "Meta.md"
    meta.write_text("---\ntitle: Der Drache\ncssclass: wide   # fremdes Feld\n---\nEs war einmal.\n", encoding="utf-8")
    yield from wait_until(lambda: win._index_of(meta) is not None)
    select(meta)
    check(text(ed) == "Es war einmal.\n", "Dateikopf ist im Editor ausgeblendet")
    check(win.inspector.title_row.get_text() == "Der Drache", "Seitenfenster zeigt den Titel aus dem Dateikopf")
    check(win.content_title.get_subtitle().startswith("3 words"), "Wortzähler zählt den Dateikopf nicht mit")
    ed.buffer.insert(ed.buffer.get_end_iter(), "Ende.")
    ed.flush()
    check(meta.read_text().startswith("---\ntitle: Der Drache\ncssclass: wide   # fremdes Feld\n---\n") and body(meta) == "Es war einmal.\nEnde.", "Speichern setzt den Dateikopf unverändert wieder davor")

    inspector = win.inspector
    win.lookup_action("inspector").activate(None)
    check(win.inspector_split.get_show_sidebar(), "Eigenschaften lassen sich einblenden")
    inspector.author_row.set_text("Anna")
    inspector.keywords_row.set_text("Roman, Entwurf ,")
    inspector.status_row.set_selected(1)
    ed.flush()
    data = parse(split(meta.read_text())[0])
    check(data.get("author") == "Anna" and data.get("keywords") == ["Roman", "Entwurf"] and data.get("status") == "draft", "Eingaben im Seitenfenster landen im Dateikopf")
    check(data.get("cssclass") == "wide" and "# fremdes Feld" in meta.read_text(), "Fremde Felder bleiben erhalten")
    inspector.author_row.set_text("")
    ed.flush()
    check("author" not in parse(split(meta.read_text())[0]), "Geleertes Feld verschwindet aus dem Dateikopf")
    check(not ed.buffer.props.can_undo or text(ed) == "Es war einmal.\nEnde.", "Text bleibt von Meta-Änderungen unberührt")

    meta.write_text(meta.read_text().replace("title: Der Drache", "title: Fridolin"), encoding="utf-8")
    yield from wait_until(lambda: inspector.title_row.get_text() == "Fridolin")
    check(inspector.title_row.get_text() == "Fridolin" and not ed.in_conflict, "Änderung am Dateikopf von außen wird übernommen")
    check(text(ed) == "Es war einmal.\nEnde.", "Text bleibt dabei unverändert")

    # Schreibziel
    check(not inspector.goal_row.get_enable_expansion() and not inspector.goal_view.get_visible(), "Ohne Schreibziel kein Ring")
    inspector.goal_row.set_enable_expansion(True)
    ed.flush()
    check(parse(split(meta.read_text())[0]).get("goal") == "1000", "Eingeschaltetes Schreibziel landet im Dateikopf (Vorschlag 1000)")
    inspector.goal_spin.set_value(8)
    ed.flush()
    check(parse(split(meta.read_text())[0]).get("goal") == "8", "Geändertes Wortziel wird gespeichert")
    check(win.content_title.get_subtitle().startswith("4 of 8 words"), "Kopfzeile nennt das Ziel")
    meta_rings = [r for r in win._row_rings if r.path == meta and r.get_mapped()]

    def ring_target(ring):
        # Ziel der Animation: im Hintergrund pausiert der Bildtakt des Fensters, dann gleitet der Ring nicht weiter.
        animation = ring._animation
        return animation.get_value_to() if animation.get_state() == Adw.AnimationState.PLAYING else ring.value

    check(
        len(meta_rings) == 1 and meta_rings[0].get_visible() and abs(ring_target(meta_rings[0]) - 0.5) < 0.01,
        "Bibliothek zeigt neben dem Blatt einen Ring mit dem Fortschritt",
    )
    check(not any(r.get_visible() for r in win._row_rings if r.path is not None and r.path != meta), "Blätter ohne Ziel haben keinen Ring")
    check(inspector.goal_view.get_visible() and "50%" in inspector.goal_view.status_label.get_label(), "Ring zeigt den Fortschritt")
    check(not win.goal_revealer.get_reveal_child(), "Ziel-Karte fehlt, solange die Eigenschaften offen sind")
    win.inspector_split.set_show_sidebar(False)
    check(win.goal_revealer.get_reveal_child() and win.goal_badge.label.get_label() == "4 / 8", "Ziel-Karte unten rechts bei geschlossenen Eigenschaften")
    yield from wait_until(lambda: win.goal_revealer.get_child_revealed())
    area = win.goal_revealer.get_parent()
    bounds = win.goal_revealer.compute_bounds(area)[1]
    check(
        bounds.get_x() + bounds.get_width() > area.get_width() - 40 and bounds.get_y() + bounds.get_height() > area.get_height() - 200,
        "Ziel-Karte sitzt in der Ecke unten rechts",
    )
    format_bounds = win.format_revealer.compute_bounds(area)[1]
    check(not bounds.intersection(format_bounds)[0], "Ziel-Karte überdeckt die Formatierungsleiste nicht")
    win.goal_badge.emit("clicked")
    check(win.inspector_split.get_show_sidebar(), "Klick auf die Ziel-Karte öffnet die Eigenschaften")
    ed.buffer.insert(ed.buffer.get_end_iter(), " Und dann kam der Drache.")
    ed.flush()
    yield from wait_until(lambda: inspector.goal_view.ring.has_css_class("success"))
    check(inspector.goal_view.ring.has_css_class("success") and inspector.goal_view.status_label.get_label() == "Goal reached", "Erreichtes Ziel wird grün")
    inspector.goal_row.set_enable_expansion(False)
    ed.flush()
    check("goal" not in parse(split(meta.read_text())[0]) and not inspector.goal_view.get_visible(), "Ausgeschaltetes Ziel verschwindet aus dem Dateikopf")
    win.inspector_split.set_show_sidebar(False)
    check(not win.goal_revealer.get_reveal_child() and not win.goal_revealer.get_can_target(), "Ohne Ziel keine Ziel-Karte (und keine unsichtbare Klickfläche)")
    check(not any(r.get_visible() for r in win._row_rings if r.path == meta), "Ohne Ziel verschwindet der Ring in der Bibliothek")
    win.inspector_split.set_show_sidebar(True)
    check(not win.content_title.get_subtitle().startswith("9 of"), "Kopfzeile ohne Ziel")
    ed.buffer.set_text("Es war einmal.\nEnde.")
    ed.flush()

    # Export
    from typecase import export, export_templates
    from typecase.export_dialog import ExportDialog, pdf_available, run_export

    check(win.lookup_action("export").get_enabled(), "Export ist mit offenem Blatt möglich")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(isinstance(dialog, ExportDialog) and dialog.template_row.get_model().get_n_items() >= 1, "Export-Dialog bietet Format und Vorlage an")
    dialog.force_close()
    if export.pandoc_path() is None:
        print("      (Pandoc fehlt hier – Export-Dateien werden nur im Flatpak geprüft)")
    else:
        results = {}
        for fmt in export.FORMATS:
            run_export(
                "---\ntitle: Der Drache\n---\nEs war eine <u>Höhle</u>.\n", fmt, export_templates.available(None)[0],
                TMP / ("export" + export.EXTENSIONS[fmt]), meta, "Der Drache", {"lang": "de-DE"},
                lambda path, error, fmt=fmt: results.__setitem__(fmt, (path, error)),
            )
        yield from wait_until(lambda: len(results) == 3, timeout=30)
        check(results["docx"][1] is None and results["html"][1] is None, f"Export ohne Fehler: {results}")
        if pdf_available():
            check(results["pdf"][1] is None and (TMP / "export.pdf").read_bytes()[:4] == b"%PDF", "PDF wird erzeugt")
        else:
            check(results["pdf"][1] == "PDF export needs WebKitGTK 6.0." and not (TMP / "export.pdf").exists(), "Ohne WebKit verständliche Meldung statt PDF")
        check((TMP / "export.docx").read_bytes()[:2] == b"PK", "DOCX wird erzeugt")
        check("Der Drache" in (TMP / "export.html").read_text(encoding="utf-8"), "HTML enthält den Titel")
        check(not [p for p in TMP.iterdir() if "typecase-tmp" in p.name], "Keine halben Export-Dateien übrig")

    # Eigene Vorlagen: als Datei speichern, importieren, im Export-Dialog wählen, entfernen
    from typecase import config as tc_config
    from typecase.preferences import PreferencesDialog

    check(tc_config.TEMPLATES_DIR.is_relative_to(TMP), "Test benutzt einen eigenen Vorlagenordner")
    prefs = PreferencesDialog(win.apply_settings)
    page = prefs.templates_page
    check(len(page._rows) == 1, "Einstellungen zeigen die mitgelieferte Vorlage")
    template_file = TMP / ("Mein Brief" + export_templates.EXTENSION)
    export_templates.pack(export_templates.available(None)[0], template_file)
    check(template_file.is_file(), "Vorlage lässt sich als Datei speichern")
    page._install(template_file)
    check(len(page._rows) == 2 and (tc_config.TEMPLATES_DIR / "mein-brief").is_dir(), "Importierte Vorlage erscheint in den Einstellungen")
    win.lookup_action("export").activate(None)
    dialog = win.get_visible_dialog()
    check(dialog.template_row.get_model().get_n_items() == 2, "Export-Dialog bietet die importierte Vorlage an")
    dialog.template_row.set_selected(1)
    chosen = dialog._templates[1]
    dialog.force_close()
    if export.pandoc_path() is not None:
        results = {}
        run_export("Text.\n", "html", chosen, TMP / "eigen.html", meta, None, {}, lambda path, error: results.__setitem__("html", error))
        yield from wait_until(lambda: "html" in results, timeout=15)
        check(results.get("html") is None and (TMP / "eigen.html").is_file(), "Export mit importierter Vorlage")
    page._remove(chosen)
    check(len(page._rows) == 1 and not (tc_config.TEMPLATES_DIR / "mein-brief").exists(), "Entfernte Vorlage landet im Papierkorb")

    from typecase import config as cfg

    cfg.update(default_author="Sascha")
    win.apply_settings()
    check(inspector.author_default.get_label() == "Sascha" and inspector.author_default.get_visible(), "Voreinstellung Autor erscheint als Platzhalter")
    check("author" not in parse(split(meta.read_text())[0]), "Voreinstellung wird nicht in die Datei geschrieben")

    editor_keys = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))
    before = text(ed)
    check(editor_keys.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType.ALT_MASK) and not win.inspector_split.get_show_sidebar(), "Alt+Enter blendet die Eigenschaften um")
    check(text(ed) == before, "Alt+Enter fügt keinen Zeilenumbruch ein")

    # Schlagwort-Filter
    lyrik = LIB / "Merken" / "Lyrik.md"
    lyrik.write_text("---\nkeywords: [Gedicht]\n---\nVerse.\n", encoding="utf-8")
    yield from wait_until(lambda: str(lyrik) in repr(win._tree_signature))
    win._fill_keyword_list()
    offered = []
    row = win.keyword_list.get_row_at_index(0)
    while row is not None:
        offered.append(row.keyword)
        row = win.keyword_list.get_row_at_index(len(offered))
    check(offered == [None, "Entwurf", "Gedicht", "Roman"], "Filter bietet alle Schlagwörter an (plus Alle Blätter)")
    win.set_keyword_filter("roman")
    check(win._index_of(meta) is not None and win._index_of(LIB / "a.md") is None, "Filter zeigt nur passende Blätter (ohne Groß/klein)")
    check(win.filter_banner.get_revealed(), "Hinweisleiste zeigt den aktiven Filter")
    win.set_keyword_filter("Gedicht")
    check(win._index_of(lyrik) is not None and win._index_of(meta) is None, "Treffer in Gruppen werden aufgeklappt gezeigt")
    meta.write_text(meta.read_text().replace("keywords: [Roman, Entwurf]", "keywords: [Roman, Entwurf, Gedicht]"), encoding="utf-8")
    yield from wait_until(lambda: win._index_of(meta) is not None)
    check(win._index_of(meta) is not None, "Neues Schlagwort von außen erscheint im gefilterten Baum")
    win.filter_banner.emit("button-clicked")
    check(not win.filter_banner.get_revealed() and win._index_of(LIB / "a.md") is not None, "Aufheben zeigt wieder alle Blätter")
    win.set_keyword_filter("Gedicht")

    win.lookup_action("new-sheet").activate(None)
    check(not win.filter_banner.get_revealed() and win._index_of(ed.path) is not None, "Neues Blatt hebt den Filter auf und ist sichtbar")
    created = parse(split(ed.path.read_text())[0]).get("created", "")
    now = GLib.DateTime.new_now_local()
    check(created.startswith(now.format("%Y-%m-%dT")) and len(created) == 16 and text(ed) == "", "Neues Blatt bekommt Erstelldatum mit Uhrzeit im Dateikopf")
    from typecase.inspector import format_created

    check(inspector.created_row.get_subtitle() == format_created(created) and ":" in inspector.created_row.get_subtitle(), "Seitenfenster zeigt das Erstelldatum mit Uhrzeit")
    check(isinstance(inspector.created_row, Adw.ActionRow) and not isinstance(inspector.created_row, Adw.EntryRow), "Erstellt ist nicht bearbeitbar")
    check(not isinstance(inspector.modified_row, Adw.EntryRow), "Zuletzt geändert ist nicht bearbeitbar")
    select(LIB / "a.md")

    # Fokus-Modus: Strg+Umschalt+Enter im Text, Kopfzeile am oberen Rand, Escape
    from gi.repository import Gdk

    editor_keys = next(c for c in ed.view.observe_controllers() if isinstance(c, Gtk.EventControllerKey))
    ctrl_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
    text_before = text(ed)
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt F2 vor Fokus-Modus: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    win.inspector_split.set_show_sidebar(True)
    check(editor_keys.emit("key-pressed", Gdk.KEY_Return, 0, ctrl_shift), "Strg+Umschalt+Enter wird im Text abgefangen")
    check(not win.inspector_split.get_show_sidebar(), "Fokus-Modus blendet die Eigenschaften aus")
    check(win.focus_mode and not win.split.get_show_sidebar(), "Fokus-Modus blendet die Seitenleiste aus")
    check(not win.content_view.get_reveal_top_bars(), "Fokus-Modus blendet die Kopfzeile aus")
    check(win.format_revealer.get_reveal_child(), "Formatierungsleiste ist auch im Fokus-Modus da")
    from typecase import config as cfg3

    cfg3.update(focus_format_bar=False)
    win.apply_settings()
    check(not win.format_revealer.get_reveal_child(), "Im Fokus-Modus lässt sich die Leiste verbergen")
    bottom = win.content_view.get_height()
    win._on_content_motion(None, 200, bottom - 2)
    check(win.format_revealer.get_reveal_child(), "Maus am unteren Rand zeigt die verborgene Leiste")
    win._on_content_motion(None, 200, bottom - 400)
    check(not win.format_revealer.get_reveal_child(), "Maus weg vom Rand verbirgt sie wieder")
    cfg3.update(focus_format_bar=True, focus_typewriter=False, focus_dim=False)
    win.apply_settings()
    check(not ed.view.typewriter and not ed.view.dim_others, "Fokus-Hilfen lassen sich abschalten")
    cfg3.update(focus_typewriter=True, focus_dim=True)
    win.apply_settings()
    check(text(ed) == text_before, "Kein Zeilenumbruch durch das Kürzel")
    yield 1.5
    check(win.is_fullscreen(), "Fokus-Modus schaltet auf Vollbild")
    check(ed.view.typewriter and ed.view.dim_others, "Fokus-Hilfen sind im Fokus-Modus an")
    yield from wait_until(lambda: ed.view.get_top_margin() == ed.view.get_height() // 2)
    check(ed.view.get_top_margin() == ed.view.get_height() // 2, "Schreibmaschinen-Modus gibt oben halbe Höhe Luft")
    check(not win.inspector_split.get_show_sidebar() and not win.split.get_show_sidebar(), "Seitenleisten bleiben im Vollbild ausgeblendet")
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt F3 im Fokus-Modus: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    margin = ed.view.get_left_margin()
    check(margin > 100 and margin == ed.view.get_right_margin(), "Textblock steht mittig mit begrenzter Breite")
    win._on_content_motion(None, 200, 2)
    check(win.content_view.get_reveal_top_bars(), "Maus am oberen Rand zeigt die Kopfzeile")
    win._on_content_motion(None, 200, 400)
    check(not win.content_view.get_reveal_top_bars(), "Maus weg vom Rand blendet sie wieder aus")
    window_keys = next(
        c for c in win.observe_controllers()
        if isinstance(c, Gtk.EventControllerKey) and c.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE
    )
    check(window_keys.emit("key-pressed", Gdk.KEY_Escape, 0, Gdk.ModifierType(0)), "Escape wird abgefangen")
    check(not win.focus_mode and win.split.get_show_sidebar() and win.content_view.get_reveal_top_bars(), "Escape beendet den Fokus-Modus und stellt alles wieder her")
    check(win.inspector_split.get_show_sidebar(), "Eigenschaften kommen nach dem Fokus-Modus zurück")
    check(win.format_revealer.get_reveal_child(), "Formatierungsleiste kommt nach dem Fokus-Modus zurück")
    win.inspector_split.set_show_sidebar(False)
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt F4 nach Escape: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    yield 1.5
    check(not win.is_fullscreen(), "Vollbild endet mit dem Fokus-Modus")
    check(not ed.view.typewriter and not ed.view.dim_others, "Außerhalb des Fokus-Modus keine Fokus-Hilfen")
    yield from wait_until(lambda: ed.view.get_top_margin() == 48)
    check(ed.view.get_top_margin() == 48, "Normale Ränder kommen zurück")
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt F5 Vollbild aus: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    check(not window_keys.emit("key-pressed", Gdk.KEY_Escape, 0, Gdk.ModifierType(0)), "Escape außerhalb des Fokus-Modus bleibt unberührt")

    # Einstellungen
    from gi.repository import Adw
    from typecase import config

    win.lookup_action("preferences").activate(None)
    prefs = win.get_visible_dialog()
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt Einstellungen geöffnet: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    check(prefs is not None and type(prefs).__name__ == "PreferencesDialog", "Strg+Komma öffnet die Einstellungen")
    check(app.get_accels_for_action("win.preferences") == ["<Control>comma"], "Strg+Komma ist registriert")
    prefs.editor_page.font_size.set_value(22)
    prefs.editor_page.line_width.set_value(55)
    prefs.editor_page.line_spacing.set_selected(2)
    prefs.editor_page.color_scheme.set_selected(2)
    saved = config.settings()
    check((saved["editor_font_size"], saved["line_width"], saved["line_spacing"]) == (22, 55, "relaxed"), "Änderungen werden sofort gespeichert")
    check(ed.view.line_width_chars == 55 and ed.view.get_pixels_inside_wrap() == 10, "Breite und Zeilenabstand wirken sofort")
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK, "Stil Dunkel wirkt sofort")
    prefs.editor_page.system_font.set_active(False)
    from gi.repository import Pango

    prefs.editor_page.font_button.set_font_desc(Pango.FontDescription.from_string("Monospace"))
    check(config.settings()["editor_font"] == "Monospace", "Eigene Schrift wird gespeichert")
    prefs.editor_page.reset()
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt Zurückgesetzt: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    check(config.settings() == config.SETTINGS_DEFAULTS, "Zurücksetzen stellt die Voreinstellungen her")
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT, "Stil folgt wieder dem System")

    # Eigene Einstellungen für den Fokus-Modus
    focus = prefs.focus_page
    check(prefs.focus_same.get_active() and not focus.groups[0].get_sensitive(), "Fokus-Modus übernimmt zunächst die Editor-Einstellungen")
    prefs.focus_same.set_active(False)
    focus.color_scheme.set_selected(2)
    focus.font_size.set_value(26)
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT, "Außerhalb des Fokus-Modus bleibt der Editor-Stil")
    prefs.force_close()
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt Einstellungen geschlossen: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    win.lookup_action("focus-mode").activate(None)
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.FORCE_DARK, "Fokus-Modus schaltet auf seinen eigenen Stil (Dunkel)")
    check("26pt" in ed._css.to_string(), "Fokus-Modus nutzt seine eigene Schriftgröße")
    win.lookup_action("focus-mode").activate(None)
    check(Adw.StyleManager.get_default().get_color_scheme() == Adw.ColorScheme.DEFAULT and "15pt" in ed._css.to_string(), "Zurück im Editor gelten wieder dessen Einstellungen")
    yield from wait_until(lambda: not win.is_fullscreen())
    config.update(focus_same_as_editor=True)
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt nach Fokus-Modus: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")

    # Fenster: Seitenleiste, Vollbild, Tastenkürzel, Über
    shown = win.split.get_show_sidebar()
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() != shown, "F9-Aktion blendet die Seitenleiste um")
    win.lookup_action("toggle-sidebar").activate(None)
    check(win.split.get_show_sidebar() == shown, "F9-Aktion blendet sie wieder ein")
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt nach Seitenleiste: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
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
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt nach Vollbild: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
    win.lookup_action("show-shortcuts").activate(None)
    check(win.get_visible_dialog() is not None, "Tastenkürzel-Übersicht öffnet sich")
    win.get_visible_dialog().force_close()
    app.lookup_action("about").activate(None)
    check(win.get_visible_dialog() is not None, "Über-Dialog öffnet sich")
    win.get_visible_dialog().force_close()
    check(ed.path and ed.path.name == "a.md", "Kontrollpunkt nach Über-Dialog: a.md noch offen (offen: " + str(ed.path and ed.path.name) + ")")
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
