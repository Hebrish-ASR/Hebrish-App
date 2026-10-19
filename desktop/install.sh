#!/usr/bin/env bash
# Per-user install: venv in ~/.local/share/parlance/venv, launchers in
# ~/.local/bin, menu entry in ~/.local/share/applications. Re-run to upgrade.
set -euo pipefail
cd "$(dirname "$0")"

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="$DATA/parlance/venv"
BIN="$HOME/.local/bin"

missing=()
/usr/bin/python3 -c 'import PySide6.QtWidgets, PySide6.QtNetwork' 2>/dev/null \
  || missing+=(python3-pyside6.qtwidgets python3-pyside6.qtnetwork qt6-svg-plugins)
/usr/bin/python3 -c 'import evdev' 2>/dev/null || missing+=(python3-evdev)
grep -q libportaudio.so <<<"$(ldconfig -p)" || missing+=(libportaudio2)   # not a pipe: pipefail + grep -q = SIGPIPE false negative
command -v wl-copy >/dev/null || [ -z "${WAYLAND_DISPLAY:-}" ] || missing+=(wl-clipboard)
if ((${#missing[@]})); then
  echo "Missing system packages. Install them first:"
  echo "  sudo apt install ${missing[*]}"
  exit 1
fi
command -v uv >/dev/null || { echo "Needs uv: https://docs.astral.sh/uv/"; exit 1; }

# The distro python, not a uv-managed one: gi and evdev are built for it.
uv venv -q --allow-existing --python /usr/bin/python3 --system-site-packages "$VENV"
VIRTUAL_ENV="$VENV" uv pip install -q --reinstall-package parlance .

mkdir -p "$BIN" "$DATA/applications"
ln -sf "$VENV/bin/parlance" "$BIN/parlance"
ln -sf "$VENV/bin/parlance-model" "$BIN/parlance-model"
install -m644 packaging/parlance.desktop "$DATA/applications/"
mkdir -p "$DATA/icons/hicolor/scalable/apps"
install -m644 parlance/data/icons/parlance.svg "$DATA/icons/hicolor/scalable/apps/"

echo "Installed. Launch 'Parlance' from the menu or run: parlance"
id -nG | grep -qw input || echo "NOTE: add yourself to the input group for the hotkey: sudo usermod -aG input \$USER (then log in again)"
[ -w /dev/uinput ] || echo "NOTE: /dev/uinput isn't writable, so transcripts will go to the clipboard but won't be pasted."
