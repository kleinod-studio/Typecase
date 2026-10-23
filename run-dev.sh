#!/usr/bin/env bash
# Startet Typecase direkt aus dem Quellordner, ohne Meson oder Flatpak (nur für die Entwicklung).
cd "$(dirname "$0")" || exit 1

# Übersetzungen übersetzen (locale/ wird nicht eingecheckt)
if command -v msgfmt >/dev/null; then
  for po in po/*.po; do
    lang=$(basename "$po" .po)
    mkdir -p "locale/$lang/LC_MESSAGES"
    msgfmt -o "locale/$lang/LC_MESSAGES/typecase.mo" "$po" 2>/dev/null
  done
fi

PYTHONPATH=src exec python3 -m typecase "$@"
