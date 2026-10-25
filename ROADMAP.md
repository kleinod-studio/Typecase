# Roadmap

Typecase is a hobby project without commercial intent. It grows in phases, and each phase has to be solid before the next one starts. This page shows what is done, what is planned, and what Typecase deliberately will not do.

## Principles

These apply to every feature:

- **Your text is never lost.** Saves are atomic, and changes made by other programs never overwrite unsaved input.
- **Plain files.** Texts are ordinary `.md` files in a folder you choose. There is no database and no proprietary format, and everything stays readable without Typecase.
- **Private.** No telemetry, no accounts, no network access.
- **GNOME-native.** Typecase uses standard libadwaita widgets and patterns, and builds its own widgets only where no standard exists.
- **Accessible.** Everything works with the keyboard, the UI is translatable (English and German today), and screen readers are supported through GTK.

## Phase 1: Minimal usable app ✅

- [x] Main window with a library sidebar and an editor
- [x] Choose a library folder; subfolders are groups, `.md` files are sheets
- [x] Create, rename and delete sheets and groups (deleting uses the system trash)
- [x] Autosave, undo and redo
- [x] Light and dark style follow the system
- [x] Word and character count
- [x] Restore the last sheet and the window size on restart
- [x] Detect external changes without ever overwriting unsaved input
- [x] Common keyboard shortcuts

## Phase 2: Comfort ✅

- [x] Live Markdown styling in the editor, with dimmed syntax characters and highlighted code blocks
- [x] Focus mode: full screen with a centered text column, separate font settings, typewriter scrolling and dimmed surroundings
- [x] Full-text search across the library
- [x] Find and replace in the current sheet
- [x] Configurable font, size, line width and spacing
- [x] Move sheets and groups by drag and drop
- [ ] Rendered Markdown preview (on hold; live styling covers most of it)

## Phase 3: Organizing and publishing 🚧

- [x] Writing goals per sheet (word count) with progress rings
- [x] Keywords on sheets and filtering by keyword
- [x] Sheet properties (title, subtitle, author, status, language) in YAML front matter, edited in a side pane
- [x] Formatting bar and shortcuts, so you can format without knowing Markdown syntax
- [x] Export to PDF, DOCX and HTML via Pandoc
- [x] Export templates as single `.typecase-template` files, imported in the preferences, with a [Claude skill](skills/typecase-template/) that builds them from a description
- [x] Template placeholders (title, author, date, any front-matter field)
- [x] Duplicate sheets (with their attachments) and whole groups
- [x] Combine the sheets of a group (subgroups included) into one text and export it, optionally with every subgroup on a new page
- [x] Group view: select a group to read and edit all of its sheets as one continuous text, while each sheet is still saved to its own file
- [x] Notes per sheet (in the front matter) and attachments (copies of files that move along with the sheet), in the properties pane
- [ ] Custom editor themes

## Next

- [x] Manual ordering of sheets and groups (drag between rows, or Alt+Up and Alt+Down)
- [ ] Spell checking while you type, offline, in the sheet's language; switched on and off with one click or a shortcut, so it never gets in the way of your flow
- [x] English version of the template guide
- [ ] Testing on Fedora (GNOME), Linux Mint (Cinnamon) and Kubuntu (KDE)
- [x] Screenshots and a first public release (0.9.0)
- [ ] Version 1.0 and publishing on Flathub
- [x] A project website with documentation and downloads: [kleinod.studio/typecase](https://kleinod.studio/typecase/)

## Later

Ideas for after 1.0:

- [ ] Custom icons and colors for sheets and groups in the library
- [ ] Group templates that set up a writing space in one step (for example a novel with groups for manuscript, characters, places and research)
- [ ] Tables in Markdown, styled in the editor
- [ ] Optional grammar checking with LanguageTool, running locally on your computer; installed only if you ask for it in the preferences, as a separate third-party component
- [ ] Publish texts to WordPress and other platforms (opt-in: only this feature would connect to the internet, and only when you publish)

## Non-goals

Typecase stays a local writing place. Anything that needs an account, a server or a file format of its own is out of scope:

- No built-in cloud sync and no user accounts. Sync the folder with Nextcloud, Syncthing or similar instead.
- No real-time collaboration.
- No desktop publishing or page layout like a word processor; Markdown stays the format.
- No mobile version.
- No plugin interface.
- No proprietary file format.

## Quality targets

- Starts in under two seconds.
- A library with 1,000 sheets stays fluid.
- Sheets of up to 50,000 words show no noticeable typing delay.
