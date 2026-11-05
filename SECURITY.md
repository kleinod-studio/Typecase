# Security policy

## Supported versions

Security fixes go into the latest release of Typecase. Please update before reporting a problem.

## Reporting a vulnerability

Please do not report security problems in a public issue. Write to [sascha@kleinod.studio](mailto:sascha@kleinod.studio) instead, and include:

- the version of Typecase and how you installed it
- what an attacker could do, and what would be needed for it
- the steps or a file that show the problem

You can expect a first reply within a week. Typecase is a hobby project, so a fix may take some time, but you will hear how it is going. If you like, you will be credited in the release notes.

## What is relevant

Typecase has no accounts, no server, no telemetry and no network access of its own, and the Flatpak has no network permission. The most likely risks come from files that someone else made, for example:

- a Markdown file, an image or a `.typecase-template` file that runs code, or reads or changes files it should not, when it is opened or exported
- an export that reaches out to the network, or includes local files that the text does not refer to
- a way to get out of the Flatpak's permissions
- a way for Typecase to lose or overwrite text

Bugs in other software, such as Pandoc, WeasyPrint or GTK, are best reported to those projects. Please still tell us if Typecase is affected.
