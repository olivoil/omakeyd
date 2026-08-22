#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

python -m py_compile omakeyd/core.py bin/omakeyd
python -m unittest discover -s tests -v

if command -v omarchy >/dev/null 2>&1; then
  omarchy plugin validate "$repo_dir"
fi

if command -v qmllint >/dev/null 2>&1 && [[ -d /usr/share/omarchy/shell ]]; then
  qmllint -I /usr/share/omarchy/shell Omakeyd.qml Panel.qml Service.qml
fi

cmp -s presets/colemak_dh_yoga "${XDG_CONFIG_HOME:-$HOME/.config}/xkb/symbols/colemak_dh_yoga" 2>/dev/null || {
  if [[ -f ${XDG_CONFIG_HOME:-$HOME/.config}/xkb/symbols/colemak_dh_yoga ]]; then
    echo "note: installed colemak_dh_yoga differs from the documented preset" >&2
  fi
}
