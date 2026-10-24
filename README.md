# Typecase

Eine ruhige, native Linux-Schreibapp für Markdown (GTK4, libadwaita, Python). Texte liegen als normale `.md`-Dateien in einem Ordner deiner Wahl, ohne Datenbank und ohne eigenes Format.

Status: frühe Entwicklung (Phase 1). Die Anforderungen stehen im Lastenheft.

## Entwickeln

Benötigt Python, PyGObject, GTK 4, libadwaita und GtkSourceView 5. Für den Export zusätzlich Pandoc und (für PDF) WebKitGTK 6.0; im Flatpak ist beides enthalten.

```bash
./run-dev.sh
```

Tests:

```bash
python3 -m unittest discover -s tests
python3 tests/gui_smoke.py   # braucht eine laufende Desktop-Sitzung
```

## Flatpak bauen

Einmalig: `flatpak-builder`, `meson` und die GNOME-Laufzeit installieren.

```bash
flatpak install flathub org.gnome.Platform//51 org.gnome.Sdk//51
```

Bauen und für den eigenen Benutzer installieren. Derselbe Befehl aktualisiert eine schon installierte Version auf den aktuellen Stand des Projektordners; eine laufende Typecase danach neu starten:

```bash
flatpak-builder --user --install --force-clean build-dir studio.kleinod.Typecase.yml
flatpak run studio.kleinod.Typecase
```

Den Oberflächentest gegen das installierte Flatpak laufen lassen (eigener Testordner, berührt keine echten Daten):

```bash
flatpak run --env=TYPECASE_CODE=/app/share/typecase --env=LANGUAGE=en --command=python3 studio.kleinod.Typecase tests/gui_smoke.py
```

## Lizenz

GPL-3.0-or-later, siehe [LICENSE](LICENSE).
