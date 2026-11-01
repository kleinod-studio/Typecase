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

# A local .venv (created with --system-site-packages, holding WeasyPrint for PDF export) is used if present
python=python3
[ -x .venv/bin/python ] && python=.venv/bin/python

PYTHONPATH=src exec "$python" -m typecase "$@"
