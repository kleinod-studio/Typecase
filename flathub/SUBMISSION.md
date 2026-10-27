# Flathub submission (draft)

Steps:

1. Fork `flathub/flathub` with your personal GitHub account, keeping all branches (untick "Copy the main branch only").
2. Create a branch from `new-pr`, add `studio.kleinod.Typecase.yml` from this folder at the root, with tag and commit of the release to publish.
3. Open a pull request against `new-pr` with the title below and fill in Flathub's template using the text below.
4. After the app is accepted: log in on flathub.org, open the Developer Portal, verify the app with the website `kleinod.studio`, and publish the token at `https://kleinod.studio/.well-known/org.flathub.VerifiedApps.txt`.

---

**Title:** Add studio.kleinod.Typecase

**Description:**

Typecase is a calm Markdown writing app for GNOME. Texts live in a library of groups and sheets, stored as plain `.md` files in a folder of the user's choice; there is no database, no account and no network access. It offers live Markdown styling, a focus mode, writing goals, spell checking, and export to PDF, DOCX and HTML through Pandoc.

- Upstream: https://github.com/kleinod-studio/Typecase
- Website: https://kleinod.studio/typecase
- License: GPL-3.0-or-later
- I am the upstream developer. The domain kleinod.studio belongs to the project and will be used for verification.

**Permissions:**

- `--filesystem=home`: The library is a folder of plain `.md` files that the user picks once and keeps, often a folder synced by Nextcloud or Syncthing. Typecase creates, renames, moves and trashes files and subfolders in it, and watches the whole folder tree for changes made by other programs, so that unsaved text is never overwritten by an external edit. The document portal grants access to single files and does not deliver change notifications for a folder tree, so the library needs direct access. Apart from exports and imports the user chooses in a file dialog, Typecase never shows or writes anything outside the chosen library folder.
- No network access: Typecase works fully offline and has no telemetry.

**Bundled components:**

- Pandoc (GPL-2.0-or-later), using the official statically linked release binaries for x86_64 and aarch64, as other Flathub apps do. It is used for exporting.
- libspelling (LGPL-2.1-or-later), built from source, for spell checking; dictionaries come from the GNOME runtime's language extensions.
