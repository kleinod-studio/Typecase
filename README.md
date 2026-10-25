# Typecase

A calm, native Markdown writing app for Linux. Built with GTK 4, libadwaita and Python.

Your texts stay plain `.md` files in a folder of your choice: no database, no proprietary format, no account, no network access. Sync the folder with Nextcloud or Syncthing if you like.

> **Status:** 0.10.0. Typecase is usable day to day; 1.0 will come together with the release on Flathub. Expect changes. See the [roadmap](ROADMAP.md) for what is done and what comes next, and the [changelog](CHANGELOG.md) for releases.

## Features

- **Library**: any folder becomes your library; subfolders are groups. Create, rename, duplicate, move (also by drag and drop) and delete sheets and groups, and sort them in your own order. Deleted items go to the system trash.
- **Group view**: select a group to read and edit all of its sheets as one continuous text; each sheet is still saved to its own file.
- **Your text is safe**: autosave with atomic writes. If another program or a sync tool changes a file, Typecase notices and never overwrites your unsaved text. On a conflict, both versions are kept.
- **Writing**: Markdown is styled as you type and code blocks are highlighted. Lists continue on Enter, and you can find and replace in a sheet.
- **Spell checking**: offline, in each sheet's language, with suggestions in the right-click menu; F7 or one click switches it on and off.
- **Formatting without syntax**: a floating formatting bar and keyboard shortcuts for bold, italic, headings, lists, links and more.
- **Organize**: search the whole library, add keywords and filter by them, and edit sheet properties (title, author, status, language). Properties are stored as YAML front matter, which stays hidden in the editor.
- **Notes and attachments**: free notes per sheet (stored in the front matter) and attached files, which move along with the sheet.
- **Writing goals**: set a word goal per sheet. Progress rings show how far you are, in the properties pane, in the library and as a small floating badge.
- **Focus mode**: full screen with only your text. Typewriter scrolling keeps the current line centered and the other paragraphs are dimmed. Focus mode can have its own font settings and theme.
- **Export**: PDF, Word (DOCX) and HTML via Pandoc. Export templates are single `.typecase-template` files that you import in the preferences ([how templates work](docs/templates.md)). A group can be exported as one document, optionally with every subgroup on a new page.
- **Editor themes**: Standard, Paper, Solarized, Calm and High Contrast, each with a light and a dark variant; the whole window takes on the theme's colors. Themes are GtkSourceView style schemes, so you can import your own ([how themes work](docs/themes.md)).
- **GNOME-native**: libadwaita look, light and dark style, fully usable with the keyboard. The UI is in English and German.

## Install

Typecase comes as a Flatpak, a format that runs on almost every Linux distribution.

### First time with Flatpak?

Fedora and Linux Mint come with Flatpak and Flathub already set up; you can skip this step. On Ubuntu and most other distributions, set it up once in a terminal:

```bash
sudo apt install flatpak
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
```

The first command installs Flatpak (on other distributions, use their package manager, see [flatpak.org/setup](https://flatpak.org/setup/)); the second adds Flathub, where the GNOME runtime that Typecase needs comes from. Log out and back in afterwards, so that Flatpak apps appear in your app launcher.

### Install Typecase

Download the Flatpak bundle for your computer from the [latest release](https://github.com/kleinod-studio/Typecase/releases/latest) (most PCs: `x86_64`, ARM machines: `aarch64`) and install it:

```bash
flatpak install --user Typecase-0.10.0-x86_64.flatpak
```

Bundles don't update by themselves; install the next release the same way. Typecase will come to Flathub with version 1.0.

### Spell checking dictionaries

In the Flatpak, the dictionaries come from the GNOME runtime’s language packs, which Flatpak installs only for the languages it is set up for. If Typecase says that no dictionary is installed for a language, add the language (here German and English) and update:

```bash
flatpak config --user --set languages "de;en"
flatpak update --user
```

If you installed the GNOME runtime system-wide instead, run `sudo flatpak config --set languages "de;en"` and `sudo flatpak update`.

Outside the Flatpak, install Hunspell dictionaries from your distribution, for example `hunspell-de` and `hunspell-en_us`.

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

Requirements: Python 3, PyGObject, GTK 4, libadwaita and GtkSourceView 5. Export also needs Pandoc, PDF export needs WebKitGTK 6.0, and spell checking needs libspelling with Hunspell dictionaries (all included in the Flatpak).

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
- `docs/`: the template guide (`templates.md`; German: `vorlagen.md`) and the theme guide (`themes.md`)

## Translations

Source strings are English. Translations live in `po/`; German is maintained in `po/de.po`. `run-dev.sh` compiles them into `locale/` automatically.

## Privacy

Typecase has no telemetry and makes no network connections. The Flatpak has no network permission.

## License

Copyright © 2026 Sascha Wübbena ([kleinod.studio](https://kleinod.studio)).

Typecase is free software, licensed under the GNU General Public License, version 3 or later (GPL-3.0-or-later). See [LICENSE](LICENSE).

The Flatpak bundles [Pandoc](https://pandoc.org) (GPL-2.0-or-later) for exporting.
