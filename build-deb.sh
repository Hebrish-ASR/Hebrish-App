#!/usr/bin/env bash
# Build an Ubuntu .deb:  ./build-deb.sh  ->  dist/codeswitch-dictation_<version>-1_amd64.deb
#
# /usr/lib/codeswitch-dictation/ holds the app plus sherpa-onnx (+ sherpa-onnx-core,
# which bundles onnxruntime), installed with `uv pip install --target`: Ubuntu ships
# neither, and nothing is fetched at install time. Everything else comes from apt.
# The wheels are CPython-ABI specific, so the package is amd64 and pinned to the
# python3 minor it was built against (see Depends). Same approach as Parakeet-Type-Ubuntu.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PKG=codeswitch-dictation
VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' codeswitch_dictation/__init__.py)
DEB_REVISION=${DEB_REVISION:-1}
ARCH=$(dpkg --print-architecture)
PY=/usr/bin/python3
PYVER=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PYNEXT=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1] + 1}")')
[ "$ARCH" = amd64 ] || { echo "only amd64 is supported (got $ARCH)" >&2; exit 1; }

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
ROOT="$BUILD/root"
LIB="$ROOT/usr/lib/$PKG"
mkdir -p "$ROOT/DEBIAN" "$LIB" "$ROOT/usr/bin" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/doc/$PKG" "$ROOT/usr/lib/udev/rules.d"

uv pip install --quiet --python "$PY" --target "$LIB" --no-deps "sherpa-onnx>=1.12" sherpa-onnx-core
uv pip install --quiet --python "$PY" --target "$LIB" --no-deps .
rm -rf "$LIB/bin" "$LIB/.lock" "$LIB"/*.dist-info/{uv_build.json,uv_cache.json,direct_url.json}
find "$LIB" -name '__pycache__' -type d -prune -exec rm -rf {} +
bundled=$(cd "$LIB" && ls -d sherpa*.dist-info | sed 's/\.dist-info$//' | tr '\n' ' ')

install -m755 packaging/debian/$PKG packaging/debian/$PKG-model "$ROOT/usr/bin/"
install -m644 packaging/$PKG.desktop "$ROOT/usr/share/applications/"
install -m644 packaging/debian/70-$PKG-uinput.rules "$ROOT/usr/lib/udev/rules.d/"
install -m644 README.md packaging/debian/README.Debian "$ROOT/usr/share/doc/$PKG/"
install -m644 LICENSE "$ROOT/usr/share/doc/$PKG/copyright"
install -m755 packaging/debian/postinst "$ROOT/DEBIAN/"

cat > "$ROOT/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION-$DEB_REVISION
Architecture: $ARCH
Section: sound
Priority: optional
Installed-Size: $(du -sk "$ROOT/usr" | cut -f1)
Maintainer: Daniel Rosehill <daniel@danielrosehill.co.il>
Homepage: https://github.com/danielrosehill/English-Hebrew-Codeswitching-Dictation-Linux
Depends: python3 (>= $PYVER), python3 (<< $PYNEXT), python3-gi, python3-numpy, python3-sounddevice, python3-evdev, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, libportaudio2, wl-clipboard | xclip
Recommends: libnotify-bin
Conflicts: parakeet-dictation
Description: English-Hebrew code-switching dictation (Parakeet fine-tune, on-device)
 Tray dictation app for one model: the English-Hebrew code-switching
 fine-tune of NVIDIA Parakeet TDT 0.6B v2, run on the CPU with sherpa-onnx.
 Hotkey from any keyboard or pedal (tap to toggle, or hold to talk), paste at
 the cursor, first-run model download and automatic model update checks.
 Bundles: $bundled
CTRL

mkdir -p dist
OUT="dist/${PKG}_${VERSION}-${DEB_REVISION}_${ARCH}.deb"
dpkg-deb --root-owner-group -Zxz --build "$ROOT" "$OUT" >/dev/null
echo "Built: $OUT ($(du -h "$OUT" | cut -f1)); bundled: $bundled"
