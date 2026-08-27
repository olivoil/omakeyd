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
  # Omarchy's typed IpcHandler methods are valid in Quickshell, but the
  # qmllint 1.0 currently shipped here rejects the same syntax in first-party
  # files such as Ui/Panel.qml. Lint the panel body statically; the two IPC
  # entry points are exercised against the live shell during local release QA.
  qmllint -I /usr/share/omarchy/shell Panel.qml
fi
