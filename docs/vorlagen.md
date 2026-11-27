# Eigene Export-Vorlagen für Typecase

Typecase exportiert Blätter als PDF, Word-Dokument (DOCX) und Webseite (HTML). Wie das Ergebnis aussieht, bestimmt die **Vorlage**. Eine Vorlage ist eine einzelne Datei mit der Endung `.typecase-template`. Sie lässt sich weitergeben und in Typecase unter **Einstellungen → Vorlagen → Importieren …** einlesen. Beim Exportieren wählst du sie dann im Dropdown „Vorlage“.

Diese Anleitung beschreibt, wie eine Vorlage aufgebaut ist und wie du eine eigene baust. Am einfachsten geht das mit dem **Vorlagen-Assistenten**: Unter **Einstellungen → Vorlagen → Neu …** wählst du einen Ausgangspunkt, passt Papier, Schriften und Abstände an, und die Vorlage ist fertig, für PDF, Word und HTML. Dort kannst du auch **Felder** anlegen, etwa Empfänger und Betreff für einen Brief (siehe [Felder](#felder-angaben-die-jedes-blatt-ausfüllt)). Später kannst du die Vorlage über den Bearbeiten-Knopf ändern. Für Geschäftsbriefe bringt Typecase die Vorlage **Brief (DIN 5008)** schon mit. Für Sonderwünsche wie einen Briefkopf oder Verlagsrichtlinien gibt es den **Claude-Skill „typecase-template“**: Du beschreibst Claude, wie dein Dokument aussehen soll, und bekommst eine fertige Vorlagendatei. Wer lieber selbst Hand anlegt, findet hier alles Nötige.

## Schnellstart: von einer vorhandenen Vorlage ausgehen

1. In Typecase **Einstellungen → Vorlagen** öffnen.
2. Bei „Text“ auf **Als Datei speichern** klicken. Du bekommst `Text.typecase-template`.
3. Die Datei in `Brief.typecase-template` umbenennen (der Dateiname wird zur Kennung der Vorlage).
4. Mit einem Archivprogramm öffnen (die Datei ist ein ZIP-Archiv; notfalls die Endung kurz in `.zip` ändern), die Dateien darin anpassen, wieder einpacken.
5. In Typecase importieren und ausprobieren.

## Was in einer Vorlage steckt

| Datei | Pflicht | Wofür |
| --- | --- | --- |
| `template.json` | ja | Name, Beschreibung, Papier und Ränder fürs PDF |
| `template.html` | ja | Gerüst für HTML und PDF (Pandoc-Vorlage) |
| `style.css` | nein | Aussehen für HTML und PDF |
| `reference.docx` | nein | Formatvorlagen für Word; ohne sie nimmt Pandoc seine Standardvorlage |
| weitere Dateien | nein | Schriften, Logos usw., auf die `style.css` verweist |

Alle Dateien liegen direkt im Archiv (oder gemeinsam in genau einem Ordner darin).

### template.json

```json
{
  "format": 1,
  "name": {"en": "Letter", "de": "Brief"},
  "description": {"en": "DIN 5008 business letter", "de": "Geschäftsbrief nach DIN 5008"},
  "author": "Dein Name",
  "version": "1.0",
  "pdf": {
    "paper": "a4",
    "margins_mm": {"top": 45, "right": 20, "bottom": 25, "left": 25}
  }
}
```

- **format**: immer `1`. Typecase lehnt Vorlagen ab, die eine neuere Fassung des Formats brauchen.
- **name** (Pflicht) und **description**: als einfacher Text oder je Sprache (`"de"`, `"en"`, …). Typecase zeigt die Sprache der Oberfläche, sonst Englisch.
- **author**, **version**: zur Information.
- **pdf.paper**: `a4`, `a5`, `a3`, `letter` oder `legal`. Ohne Angabe nimmt Typecase das übliche Papier der Systemsprache.
- **pdf.margins_mm**: Seitenränder des PDFs in Millimetern (0 bis 100). Fehlende Seiten bekommen 25 mm.
- **structure** (optional): `false` für Briefe und Formulare. Der Export-Dialog bietet dann kein Inhaltsverzeichnis und keine Titelseite an, und Word-Dateien lassen Titel, Untertitel und Autor weg.
- **fields** (optional): Angaben, die jedes Blatt ausfüllt; siehe [Felder](#felder-angaben-die-jedes-blatt-ausfüllt).

Papier und Ränder für **Word** stehen nicht hier, sondern in `reference.docx` (Seite einrichten).

### template.html

Das Gerüst ist eine [Pandoc-Vorlage](https://pandoc.org/MANUAL.html#templates): normales HTML mit Platzhaltern in Dollarzeichen. Typecase füllt sie beim Export.

Unverzichtbar sind:

- `$body$`: der Text des Blatts. Ohne ihn lehnt Typecase die Vorlage ab.
- `$for(header-includes)$$header-includes$$endfor$` im `<head>`: Darüber bettet Typecase `style.css` ein. Fehlt die Zeile, wird dein CSS nicht angewendet.

Weitere Platzhalter:

| Platzhalter | Inhalt |
| --- | --- |
| `$title$`, `$subtitle$` | Titel und Untertitel aus den Eigenschaften des Blatts |
| `$for(author)$$author$$endfor$` | Autor; ohne Angabe im Blatt die Voreinstellung aus den Einstellungen |
| `$date$` | Datum aus dem Feld `date` im Dateikopf, sonst das Datum des Exports |
| `$lang$` | Sprache, z. B. `de-DE` (für `<html lang="…">`, wichtig für Silbentrennung) |
| `$pagetitle$` | Fenstertitel, wenn das Blatt keinen Titel hat (der Blattname) |
| `$created$`, `$status$`, `$keywords$`, … | jedes weitere Feld aus dem Dateikopf des Blatts |
| `$empfaenger$` usw. | der Wert eines [Felds](#felder-angaben-die-jedes-blatt-ausfüllt) der Vorlage |
| `$absender-oneline$` | ein mehrzeiliges Feld in einer Zeile, mit „ · “ verbunden, bis zur ersten Leerzeile |
| `$if(pdf)$…$endif$` | nur beim PDF-Export; die mitgelieferte Vorlage setzt damit `<body class="pdf">` |
| `$highlighting-css$` | Farben für Codeblöcke |

Bedingungen: `$if(subtitle)$<p class="subtitle">$subtitle$</p>$endif$`.

Ein vollständiges, schlankes Gerüst:

```html
<!DOCTYPE html>
<html lang="$lang$">
<head>
<meta charset="utf-8">
<title>$if(title-meta)$$title-meta$$else$$pagetitle$$endif$</title>
$if(highlighting-css)$<style>$highlighting-css$</style>$endif$
$for(header-includes)$
$header-includes$
$endfor$
</head>
<body$if(pdf)$ class="pdf"$endif$>
$if(title)$
<header class="title-block">
<h1 class="title">$title$</h1>
$if(subtitle)$<p class="subtitle">$subtitle$</p>$endif$
</header>
$endif$
$body$
</body>
</html>
```

### style.css

Gilt für HTML und PDF. Einige Hinweise:

- **Druck und Bildschirm unterscheiden**: Beim PDF hat `<body>` die Klasse `pdf` (wenn das Gerüst sie setzt). Die Webseite darf eine begrenzte Zeilenbreite und Außenabstand haben; im PDF bestimmen Papier und Ränder aus `template.json` die Breite, also dort `max-width: none; margin: 0;`.
- **Regeln für den Text auf `main` beschränken**: Das Gerüst setzt den Titelblock außerhalb von `<main>`, den Text des Blatts innerhalb – und der Titel ist ebenfalls eine `h1`-Überschrift. Schreib deshalb `main h1`, `main p` usw. Sonst beginnt das PDF mit einer leeren Seite (der Umbruch vor dem Titel) oder Absatzregeln überschreiben die Ausrichtung des Titelblocks.
- **Seitenumbrüche**: `main h1 { break-before: page; }` für Kapitel auf neuer Seite, `.title-block { break-after: page; }` für ein eigenes Titelblatt, `break-after: avoid` für Überschriften, `orphans`/`widows` gegen einzelne Zeilen.
- **Seitenzahlen und Kopfzeilen** im PDF: `@page { @bottom-center { content: counter(page); } }` (auch `@top-center`, `@bottom-right` und so weiter). Im Word-Dokument gehen sie über `reference.docx`.
- **Deckblatt, Inhaltsverzeichnis und Teile** sind Export-Optionen und funktionieren mit jeder Vorlage. Zum Umgestalten: `.cover` (mit `.title`, `.subtitle`, `.author`, `.date`), `.toc` (mit `.toc-title`) und `.part` für den Namen einer Untergruppe, je nach Export-Einstellung zusätzlich `.new-page` oder `.title-page`. In einer Gruppe mit Teilen sind Kapitel `h2`.
- **Fußnoten** stehen im PDF unten auf ihrer Seite. `.footnote`, `::footnote-call` und `::footnote-marker` gestalten sie um.
- **Schriften**: Verlass dich nur auf verbreitete Schriften (z. B. „Liberation Serif“, „DejaVu Serif“, „Noto Sans“) oder bette eigene ein: Schriftdatei mit ins Archiv legen und per `@font-face { font-family: "Meine"; src: url("fonts/Meine-Regular.woff2"); }` einbinden. Typecase bettet Dateien, auf die `url(…)` verweist, in HTML und PDF ein. Achte auf die Lizenz der Schrift.
- **Bilder** (etwa ein Logo) funktionieren genauso: `background-image: url("logo.svg")`.
- **Bilder im Text** stehen in `<figure>` mit `<figcaption>`, ohne Bildunterschrift in einem Absatz. Eine im Bild-Dialog gewählte Ausrichtung ergänzt darum die Klasse `image-left`, `image-center` oder `image-right`. Ohne Ausrichtung entscheidet dein CSS: `figure { text-align: center; }` zentriert alle Bilder. In der `reference.docx` gelten die Formatvorlagen „Captioned Figure“ und „Image Caption“; ausgerichtete Bilder nutzen „Typecase Image center“ und „Typecase Caption center“ (entsprechend `left` und `right`), die Typecase selbst ergänzt, solange deine Vorlage sie nicht festlegt.
- Verweise auf Dateien außerhalb der Vorlage und Adressen im Internet bleiben unverändert; Typecase lädt nichts aus dem Netz.

Was Typecase aus Markdown macht, kannst du so gestalten:

| Markdown | HTML |
| --- | --- |
| `# Überschrift` bis `######` | `h1` … `h6` |
| `**fett**`, `*kursiv*`, `~~durch~~` | `strong`, `em`, `del` |
| `<u>unterstrichen</u>` | `u` |
| `> Zitat` | `blockquote` |
| Listen | `ul`, `ol`, `li` |
| `` `Code` ``, Codeblöcke | `code`, `pre` |
| Titelblock (aus den Eigenschaften) | `.title-block`, `.title`, `.subtitle`, `.author` (wenn das Gerüst sie so nennt) |

Jede Zeile im Editor bleibt im Export eine eigene Zeile (`<br>`); Absätze trennt eine Leerzeile.

### reference.docx

Für Word verwendet Pandoc die Formatvorlagen eines Referenzdokuments: Schrift und Größe von „Standard“, „Überschrift 1“ usw., Seitenformat und Ränder. Den Inhalt des Referenzdokuments übernimmt Pandoc nicht, nur das Aussehen.

So entsteht eins:

1. Pandocs Standard holen: `pandoc -o reference.docx --print-default-data-file reference.docx`
2. In LibreOffice oder Word öffnen und die **Formatvorlagen** ändern (nicht den Text direkt formatieren): „Standard“/„Textkörper“, „Überschrift 1–3“, „Titel“, „Untertitel“, „Zitat“, „Quelltext“. Seitenränder unter Format → Seite.
3. Als DOCX speichern und ins Archiv legen.

Ohne Textverarbeitung geht es mit dem Skript `style_docx.py` aus dem Claude-Skill: Es setzt Schriften, Größen, Zeilenabstand, Einzug, Papier und Ränder und fügt auf Wunsch Seitenzahlen und einen kleinen Briefkopf hinzu (`python3 style_docx.py --help`).

Pandoc schreibt Titel, Untertitel und Autor im Word-Dokument immer als erste Absätze vor den Text; frei positionierte Bereiche aus dem HTML (etwa ein Anschriftfeld) lassen sich in Word nicht nachbilden. Felder der Vorlage folgen danach als eigene Absätze, in ihrer Reihenfolge; jeder bekommt die Formatvorlage, die so heißt wie sein Schlüssel (mit `style_docx.py --field-style` lässt sie sich gestalten).

## Felder: Angaben, die jedes Blatt ausfüllt

Manche Dokumente brauchen mehr als Titel und Autor: Ein Brief hat Absender, Empfänger und Betreff, eine Rechnung eine Nummer. Solche Angaben gehören nicht in den Text, sondern in **Felder** der Vorlage.

So sieht das beim Schreiben aus: Im Eigenschaften-Bereich des Blatts wählst du unter **Vorlage** die gewünschte Vorlage. Darunter erscheint für jedes Feld eine Eingabezeile. Was du einträgst, speichert Typecase im Dateikopf des Blatts, und beim Export setzt die Vorlage es an die richtige Stelle. Im Editor steht nur der eigentliche Text. Der Export-Dialog wählt die Vorlage des Blatts dann von selbst.

Im **Vorlagen-Assistenten** legst du Felder im Bereich „Felder“ an: Name, Art (eine Zeile, mehrere Zeilen, Datum) und Reihenfolge. Seine Vorlagen setzen die Felder unter den Titel. Wer die Felder frei anordnen möchte, etwa die Anschrift im Adressfeld eines Briefs, schreibt sie selbst in `template.html`.

In `template.json` stehen die Felder so:

```json
"structure": false,
"fields": [
  {"key": "absender", "label": {"en": "Sender", "de": "Absender"}, "type": "lines"},
  {"key": "empfaenger", "label": {"en": "Recipient", "de": "Empfänger"}, "type": "lines"},
  {"key": "datum", "label": {"en": "Date", "de": "Datum"}, "type": "date"},
  {"key": "betreff", "label": {"en": "Subject", "de": "Betreff"}}
]
```

- **key**: der Name, unter dem das Blatt den Wert speichert und unter dem `template.html` ihn findet: Kleinbuchstaben, Ziffern, `-` und `_`, beginnend mit einem Buchstaben. Schlüssel, die Typecase selbst verwendet (`title`, `author`, `lang`, `status` usw.), sind ausgenommen. Ändere den Schlüssel einer verwendeten Vorlage nicht mehr, sonst finden die Blätter ihre Werte nicht wieder; die Beschriftung darfst du jederzeit ändern.
- **label**: die Beschriftung der Eingabezeile, als Text oder je Sprache.
- **type**: `text` (eine Zeile, Voreinstellung), `lines` (mehrere Zeilen, etwa eine Anschrift) oder `date` (Datum mit Kalender; leer bedeutet: der Tag des Exports).

In `template.html` setzt du ein Feld mit seinem Schlüssel ein, am besten in eine Bedingung: `$if(empfaenger)$<div class="empfaenger">$empfaenger$</div>$endif$`. Zeilenumbrüche und Leerzeilen eines mehrzeiligen Felds bleiben erhalten. `$absender-oneline$` gibt die Zeilen bis zur ersten Leerzeile in einer Zeile aus, etwa für die kleine Absenderzeile über dem Anschriftfeld; Telefon und E-Mail stehen dann einfach nach einer Leerzeile.

Ein vollständiges Beispiel ist die mitgelieferte Vorlage **Brief (DIN 5008)**: In den Einstellungen unter **Vorlagen** speicherst du sie mit **Als Datei speichern** und schaust sie dir an.

## Prüfen und weitergeben

Beim Import prüft Typecase die Datei und meldet verständlich, was fehlt. Es weist außerdem Archive ab, die Dateien außerhalb ihres Ordners anlegen wollen, Verknüpfungen enthalten oder größer als 50 MB sind. Eine schon installierte Vorlage mit gleichem Dateinamen wird nach Rückfrage ersetzt.

Weitergeben kannst du die `.typecase-template`-Datei einfach so. Importierte Vorlagen gelten auf dem Rechner, auf dem du sie importiert hast.
