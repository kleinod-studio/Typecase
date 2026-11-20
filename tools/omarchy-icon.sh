#!/usr/bin/env bash
# Draw Typecase's app icon in the colors of the current Omarchy theme.
#
#   tools/omarchy-icon.sh install   copy Typecase's icon templates into Omarchy's
#                                   user icon sets and draw them once
#   tools/omarchy-icon.sh remove    take them out again; the normal icon returns
#
# Omarchy redraws the icons of its icon sets on every theme or icon set switch.
# A template in ~/.config/omarchy/icons/<set>/ adds an icon to a built-in set,
# so after `install` Omarchy keeps the Typecase icon in the theme's colors by
# itself. The Typecase Flatpak is not involved and nothing in it changes.
#
# Only the files named studio.kleinod.Typecase.svg.tpl are touched, and a file
# of that name is replaced or removed only if it carries this script's marker.
# Without Omarchy, the script changes nothing.

set -euo pipefail

ICON=studio.kleinod.Typecase.svg.tpl
MARKER=typecase-omarchy-icon
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/data/omarchy"
TARGET="$HOME/.config/omarchy/icons"
COLORS="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/current/theme/colors.toml"

usage() {
  echo "Usage: $0 install|remove" >&2
  exit 2
}

require_omarchy() {
  if ! command -v omarchy-theme-set-icons >/dev/null || [[ ! -f $COLORS ]]; then
    echo "Omarchy was not found (no omarchy-theme-set-icons or no theme colors)." >&2
    echo "Nothing was changed; Typecase keeps its normal icon." >&2
    exit 1
  fi
}

ours() {
  grep -q "$MARKER" "$1"
}

install() {
  require_omarchy
  for dir in "$SOURCE"/*/; do
    set_name=$(basename "$dir")
    dest="$TARGET/$set_name/$ICON"
    if [[ -e $dest ]] && ! ours "$dest"; then
      echo "Skipped $dest: it was not installed by this script." >&2
      continue
    fi
    mkdir -p "$TARGET/$set_name"
    cp "$dir/$ICON" "$dest.tmp"
    mv -f "$dest.tmp" "$dest"
    echo "Installed $dest"
  done
  omarchy-theme-set-icons
  echo "Done. Omarchy now draws the Typecase icon in the theme's colors."
}

remove() {
  removed=0
  for dest in "$TARGET"/*/"$ICON"; do
    [[ -f $dest ]] || continue
    if ! ours "$dest"; then
      echo "Kept $dest: it was not installed by this script." >&2
      continue
    fi
    rm -f "$dest"
    rmdir --ignore-fail-on-non-empty "$(dirname "$dest")"
    echo "Removed $dest"
    removed=1
  done
  if (( removed )) && command -v omarchy-theme-set-icons >/dev/null; then
    omarchy-theme-set-icons
  fi
  echo "Done. Typecase shows its normal icon."
}

case "${1:-}" in
  install) install ;;
  remove) remove ;;
  *) usage ;;
esac
