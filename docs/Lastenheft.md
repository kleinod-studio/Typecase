# Lastenheft: Markdown-Schreibapp für Linux

Oct 23, 2026 · @Sascha

## 1. Vision und Ziele

Eine native Linux-Schreibapp im Stil von Ulysses: ruhig, aufgeräumt, Markdown-basiert, Open Source und als Hobbyprojekt ohne Gewinnabsicht.

- **Kernidee:** Texte in einer Bibliothek aus Gruppen und Blättern schreiben und verwalten, gespeichert als normale `.md`-Dateien in einem Ordner, ohne eigene Datenbank.
- **Zielgruppe:** zuerst der Autor selbst, danach andere GNOME-Nutzer.
- **Nebenziel:** Lernen, wie man ohne Programmiererfahrung per Vibe Coding eine saubere, native Linux-App baut.
- **Erfolgskriterium (Vorschlag):** Nach Phase 1 schreibt der Autor mindestens eine Woche lang echte Texte in der App, ohne zu einem anderen Editor zu wechseln.

## 2. Rahmenbedingungen

Die App setzt auf GTK4 und libadwaita mit Python und wird als Flatpak verteilt. Alle Punkte sind Vorschläge, bis sie bestätigt sind.

| Thema | Festlegung |
| --- | --- |
| Plattform | Linux; GNOME als Referenz, lauffähig unter Cinnamon und KDE |
| Toolkit | GTK4, libadwaita, GtkSourceView 5 |
| Sprache | Python mit PyGObject |
| Entwicklungsumgebung | GNOME Builder |
| Verteilung | Flatpak; Flathub optional später |
| Lizenz | Open Source, GPL-3.0 |
| Speicherformat | Normale `.md`-Dateien in einem frei wählbaren Ordner |
| Entwicklungsweise | Vibe Coding mit Claude, in Phasen mit festem Funktionsumfang je Phase |

## 3. Phase 1: Minimal nutzbare App (MVP)

Phase 1 liefert eine Seitenleiste mit Bibliothek und einen Editor mit Autosave. Mehr nicht.

| ID | Anforderung | Priorität |
| --- | --- | --- |
| P1-01 | Hauptfenster mit Seitenleiste (Bibliothek) und Editorbereich im libadwaita-Stil | Muss |
| P1-02 | Beim ersten Start wird ein Bibliotheksordner gewählt; Unterordner sind Gruppen, `.md`-Dateien sind Blätter | Muss |
| P1-03 | Blatt anlegen, umbenennen und löschen (Löschen über den System-Papierkorb) | Muss |
| P1-04 | Gruppe anlegen, umbenennen und löschen | Muss |
| P1-05 | Blatt in der Seitenleiste auswählen und im Editor bearbeiten | Muss |
| P1-06 | Autosave: Änderungen werden ohne Speichern-Knopf gesichert | Muss |
| P1-07 | Rückgängig und Wiederholen im Editor | Muss |
| P1-08 | Hell- und Dunkelmodus folgen der Systemeinstellung | Muss |
| P1-09 | Wort- und Zeichenzähler für das geöffnete Blatt | Soll |
| P1-10 | Letztes Blatt und Fenstergröße werden beim Neustart wiederhergestellt | Soll |
| P1-11 | Änderungen an Dateien von außen werden erkannt und überschreiben keine ungesicherten Eingaben | Soll |
| P1-12 | Gängige Tastenkürzel (Neues Blatt, Umbenennen, Vollbild) | Soll |

**Abnahme:** Die App läuft als Flatpak. Ein Blatt lässt sich anlegen, beschreiben, schließen und nach einem Neustart ohne Datenverlust wieder öffnen.

## 4. Phase 2: Komfort

Phase 2 macht das Schreiben angenehm: Markdown wird im Editor sichtbar gestaltet, und ein Schreibmodus nimmt Ablenkung weg.

| ID | Anforderung | Priorität |
| --- | --- | --- |
| P2-01 | Live-Gestaltung von Markdown im Editor: Überschriften, fett, kursiv, Listen, Zitate; Syntaxzeichen gedimmt | Muss |
| P2-02 | Schreibmodus: Seitenleiste und Leisten ausblenden, Text zentriert in begrenzter Zeilenbreite | Muss |
| P2-03 | Volltextsuche über die gesamte Bibliothek | Muss |
| P2-04 | Suchen und Ersetzen im geöffneten Blatt | Soll |
| P2-05 | Schriftart und Schriftgröße einstellbar | Soll |
| P2-06 | Blätter und Gruppen per Drag-and-drop verschieben | Soll |
| P2-07 | Vorschau des gerenderten Markdown | Kann |

## 5. Phase 3: Ulysses-Funktionen

Phase 3 ergänzt, was Ulysses von einem reinen Editor unterscheidet. Jeder Punkt ist einzeln umsetzbar.

| ID | Anforderung | Priorität |
| --- | --- | --- |
| P3-01 | Schreibziele pro Blatt (Wortanzahl) mit Fortschrittsanzeige | Soll |
| P3-02 | Schlagwörter (Keywords) an Blättern und Filter danach | Soll |
| P3-03 | Export als PDF, DOCX und HTML, umgesetzt über Pandoc | Soll |
| P3-04 | Eigene Themes für Editor und Vorschau | Kann |
| P3-05 | Blätter pro Gruppe zu einem Text zusammenfügen und exportieren | Kann |
| P3-06 | Notizen und Anhänge je Blatt | Kann |
| P3-07 | Export-Vorlagen: Vor dem Export wählt man eine Vorlage, zum Beispiel für Lektorat, Brief oder Essay. Eine Vorlage ist eine einzelne Datei (`.typecase-template`, ZIP mit Beschreibung, HTML-Template, CSS und optional DOCX-Referenzdokument), die man in den Einstellungen importiert; einige Standardvorlagen werden mitgeliefert und lassen sich als Ausgangspunkt für eigene als Datei speichern. Technik: Pandoc-Referenzdokument für DOCX, HTML-Template mit CSS für HTML und PDF | Soll |
| P3-08 | Platzhalter in Vorlagen (Titel, Autor, Datum) werden aus den Metadaten des Blatts gefüllt | Kann |

## 6. Nicht-Ziele

Die App bleibt ein lokaler Schreibplatz; alles, was ein Konto, einen Server oder einen eigenen Dateistandard braucht, ist ausgeschlossen.

- Kein eigener Cloud-Sync und keine Benutzerkonten. Synchronisieren lässt sich der Ordner mit Nextcloud oder Syncthing.
- Keine Zusammenarbeit in Echtzeit.
- Kein Layout- oder Textsatz wie in Word; Markdown bleibt das Format.
- Keine mobile Version.
- Keine Plugin-Schnittstelle.
- Kein proprietäres Dateiformat: Die Texte müssen ohne die App lesbar bleiben.

## 7. Nichtfunktionale Anforderungen

Texte dürfen unter keinen Umständen verloren gehen; danach zählen Optik und Tempo. Alle Werte sind Vorschläge.

| Bereich | Anforderung |
| --- | --- |
| Datensicherheit | Speichern atomar (temporäre Datei, dann umbenennen); ungesicherte Eingaben werden nie überschrieben |
| Datenschutz | Keine Telemetrie, keine Netzwerkzugriffe durch die App |
| Optik | libadwaita-Standardlook; selbstgebaute Widgets nur, wenn es keinen Standard gibt |
| Performance | Start unter 2 Sekunden; Bibliothek mit 1.000 Blättern bleibt flüssig; Blätter bis 50.000 Wörter ohne spürbare Eingabeverzögerung |
| Barrierefreiheit | Vollständig per Tastatur bedienbar; Screenreader-Unterstützung über GTK-Standards |
| Sprache der Oberfläche | Deutsch und Englisch (gettext) |

## 8. Offene Fragen

Diese Entscheidungen fehlen noch; keine blockiert den Start von Phase 1, Name und Lizenz sollten aber früh feststehen.

- [ ] **Name der App** (Arbeitstitel genügt für den Start)
- [ ] **Lizenz bestätigen:** GPL-3.0 oder eine andere Open-Source-Lizenz
- [ ] **Metadaten:** Wohin kommen Schlagwörter und Schreibziele später: in den Dateikopf (YAML-Frontmatter) oder in eine versteckte Zusatzdatei im Ordner? Entscheidung vor Phase 3
- [ ] **Reihenfolge in Gruppen:** alphabetisch oder manuell sortierbar (manuell braucht Metadaten)
- [ ] **Live-Gestaltung:** Text-Tags im GTK-Textfeld oder GtkSourceView mit eigener Markdown-Auszeichnung. Technische Entscheidung vor Phase 2
- [ ] **Testumgebungen:** Fedora (GNOME), Linux Mint (Cinnamon) und Kubuntu (KDE) als virtuelle Maschinen
