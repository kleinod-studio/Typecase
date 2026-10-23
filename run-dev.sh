#!/usr/bin/env bash
# Startet Typecase direkt aus dem Quellordner, ohne Meson oder Flatpak (nur für die Entwicklung).
cd "$(dirname "$0")" || exit 1
PYTHONPATH=src exec python3 -m typecase "$@"
