# Typecase

A calm, native Markdown writing app for Linux, inspired by Ulysses. Built with GTK 4, libadwaita and Python.

Your texts stay plain `.md` files in a folder of your choice: no database, no proprietary format, no account, no network access. Sync the folder with Nextcloud or Syncthing if you like.

> **Status:** 0.9.0, the first public release. Typecase is usable day to day; 1.0 will come together with the release on Flathub. Expect changes. See the [roadmap](ROADMAP.md) for what is done and what comes next, and the [changelog](CHANGELOG.md) for releases.

## Features

- **Library**: any folder becomes your library; subfolders are groups. Create, rename, move (also by drag and drop) and delete sheets and groups. Deleted items go to the system trash.
- **Your text is safe**: autosave with atomic writes. If another program or a sync tool changes a file, Typecase notices and never overwrites your unsaved text. On a conflict, both versions are kept.
- **Writing**: Markdown is styled as you type and code blocks are highlighted. Lists continue on Enter, and you can find and replace in a sheet.
- **Formatting without syntax**: a floating formatting bar and keyboard shortcuts for bold, italic, headings, lists, links and more.
- **Organize**: search the whole library, add keywords and filter by them, and edit sheet properties (title, author, status, language). Properties are stored as YAML front matter, which stays hidden in the editor.
- **Writing goals**: set a word goal per sheet. Progress rings show how far you are, in the properties pane, in the library and as a small floating badge.
- **Focus mode**: full screen with only your text. Typewriter scrolling keeps the current line centered and the other paragraphs are dimmed. Focus mode has its own font settings.
- **Export**: PDF, Word (DOCX) and HTML via Pandoc. Export templates are single `.typecase-template` files that you import in the preferences ([how templates work](docs/templates.md)).
- **GNOME-native**: libadwaita look, light and dark style, fully usable with the keyboard. The UI is in English and German.

## Install from source (Flatpak)

You need `flatpak-builder` and the GNOME 51 runtime:

```bash
flatpak install flathub org.gnome.Platform//51 org.gnome.Sdk//51
```

Build and install for your user. Run the same command again later to update to the current state of the source tree:

```bash
flatpak-builder --user --install --force-clean build-dir studio.kleinod.Typecase.yml
flatpak run studio.kleinod.Typecase
```

The Flatpak includes Pandoc, so export works out of the box.

## Development

Requirements: Python 3, PyGObject, GTK 4, libadwaita and GtkSourceView 5. Export also needs Pandoc, and PDF export needs WebKitGTK 6.0 (both are included in the Flatpak).

Run Typecase from the source tree without building:

```bash
./run-dev.sh
```

Tests:

```bash
python3 -m unittest discover -s tests   # logic
python3 tests/gui_smoke.py              # drives the real UI, needs a desktop session
```

The UI test uses its own temporary library and configuration and never touches your data. To run it against the installed Flatpak:

```bash
flatpak run --env=TYPECASE_CODE=/app/share/typecase --env=LANGUAGE=en --command=python3 studio.kleinod.Typecase tests/gui_smoke.py
```

Project layout:

- `src/typecase/`: the application (Python package)
- `data/`: desktop file, AppStream metainfo, icon
- `po/`: translations (gettext, English source strings)
- `skills/typecase-template/`: a Claude skill that builds export templates from a description; `python3 skills/package.py skills/typecase-template` packs it into `dist/typecase-template.skill`
- `docs/`: the template guide (`templates.md`; German: `vorlagen.md`)

## Translations

Source strings are English. Translations live in `po/`; German is maintained in `po/de.po`. `run-dev.sh` compiles them into `locale/` automatically.

## Privacy

Typecase has no telemetry and makes no network connections. The Flatpak has no network permission.

## License

Copyright © 2026 Sascha Wübbena ([kleinod.studio](https://kleinod.studio)).

Typecase is free software, licensed under the GNU General Public License, version 3 or later (GPL-3.0-or-later). See [LICENSE](LICENSE).

The Flatpak bundles [Pandoc](https://pandoc.org) (GPL-2.0-or-later) for exporting.
