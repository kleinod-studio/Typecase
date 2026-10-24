#!/usr/bin/env bash
# Starts Typecase straight from the source folder, without Meson or Flatpak (for development only).
cd "$(dirname "$0")" || exit 1

# Compile the translations (locale/ is not checked in)
if command -v msgfmt >/dev/null; then
  for po in po/*.po; do
    lang=$(basename "$po" .po)
    mkdir -p "locale/$lang/LC_MESSAGES"
    msgfmt -o "locale/$lang/LC_MESSAGES/typecase.mo" "$po" 2>/dev/null
  done
fi

PYTHONPATH=src exec python3 -m typecase "$@"
