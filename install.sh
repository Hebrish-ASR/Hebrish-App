#!/usr/bin/env bash
# Per-user install: venv in ~/.local/share/codeswitch-dictation/venv, launchers in
# ~/.local/bin, menu entry in ~/.local/share/applications. Re-run to upgrade.
set -euo pipefail
cd "$(dirname "$0")"

DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="$DATA/codeswitch-dictation/venv"
BIN="$HOME/.local/bin"

missing=()
/usr/bin/python3 -c 'import gi; gi.require_version("Gtk","3.0"); gi.require_version("AyatanaAppIndicator3","0.1"); from gi.repository import Gtk, AyatanaAppIndicator3' 2>/dev/null \
  || missing+=(python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1)
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
VIRTUAL_ENV="$VENV" uv pip install -q --reinstall-package codeswitch-dictation .

mkdir -p "$BIN" "$DATA/applications"
ln -sf "$VENV/bin/codeswitch-dictation" "$BIN/codeswitch-dictation"
ln -sf "$VENV/bin/codeswitch-dictation-model" "$BIN/codeswitch-dictation-model"
install -m644 packaging/codeswitch-dictation.desktop "$DATA/applications/"

echo "Installed. Launch 'Codeswitch Dictation' from the menu or run: codeswitch-dictation"
id -nG | grep -qw input || echo "NOTE: add yourself to the input group for the hotkey: sudo usermod -aG input \$USER (then log in again)"
[ -w /dev/uinput ] || echo "NOTE: /dev/uinput isn't writable, so transcripts will go to the clipboard but won't be pasted."
