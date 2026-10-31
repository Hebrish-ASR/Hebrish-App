#!/usr/bin/env bash
# Build dist/Hebrish-<version>-x86_64.AppImage: one file that runs on most Linux desktops,
# for systems the .deb doesn't cover (Fedora, Arch, openSUSE...). Daniel, 2026-10-31.
#
# Run it in an ubuntu:22.04 container (CI job `appimage` in .github/workflows/desktop.yml, then
# `appimage-test` self-tests it in fedora:43):
# the bundled binaries are linked against that glibc (2.35), so the AppImage runs on
# Ubuntu 22.04+, Debian 12+, Fedora 36+ and anything newer. Needs: curl, file, binutils, patchelf, desktop-file-utils, zsync,
# xclip, wl-clipboard, libportaudio2 and uv on PATH.
#
# Unlike the .deb (system python3 + apt's PySide6/numpy), everything is bundled:
#   usr/python/           python-build-standalone 3.12 (uv's managed Python, relocatable)
#   usr/lib/hebrish/      the app and its wheels: PySide6-Essentials, numpy, sounddevice,
#                         evdev-binary (the `evdev` module, prebuilt), sherpa-onnx, onnxruntime
#   usr/lib/              libportaudio.so.2 and libjack (sounddevice's PortAudio)
#   usr/bin/              xclip, wl-copy (rpath ../lib), used only when the system has none
# Not bundled: ffmpeg (optional, from the system), python3-gi/AT-SPI (focus.text_target()
# returns None without it, as on Windows), the uinput udev rule (an AppImage can't install
# one; README "AppImage" says how, and the app falls back to the clipboard without it).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' hebrish/__init__.py)
PYVER=3.12
# appimagetool and the type2 runtime it embeds: pinned releases, sha256 checked (left alone,
# appimagetool fetches the runtime's moving `continuous` build). The runtime is static, so the
# AppImage needs no libfuse2 on the user's machine (only FUSE, or --appimage-extract-and-run).
TOOL_URL=https://github.com/AppImage/appimagetool/releases/download/1.9.0/appimagetool-x86_64.AppImage
TOOL_SHA=46fdd785094c7f6e545b61afcfb0f3d98d8eab243f644b4b17698c01d06083d1
RUNTIME_URL=https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64
RUNTIME_SHA=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
APPDIR="$BUILD/Hebrish.AppDir"
LIB="$APPDIR/usr/lib/hebrish"
mkdir -p "$LIB" "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$APPDIR/usr/share/metainfo" \
         "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# 1. Python: uv's python-build-standalone, copied in whole (it finds its stdlib relative to
#    its own executable, so it works from the AppImage's mount point).
UV_PYTHON_INSTALL_DIR="$BUILD/pythons" uv python install --quiet "$PYVER"
src=$(ls -d "$BUILD"/pythons/cpython-"$PYVER".*-linux-x86_64-gnu | head -1)
cp -a "$src" "$APPDIR/usr/python"
PY="$APPDIR/usr/python/bin/python$PYVER"
rm -rf "$APPDIR"/usr/python/lib/python"$PYVER"/{test,idlelib,tkinter,turtledemo,ensurepip} \
       "$APPDIR"/usr/python/lib/{libtcl,libtk,tcl,tk,itcl,thread}* "$APPDIR"/usr/python/share
find "$APPDIR/usr/python" -name EXTERNALLY-MANAGED -delete
# python-build-standalone ships with debug symbols (libpython alone is 32 MB)
# Debug sections only, libraries only: --strip-unneeded, or stripping the python3.12 executable,
# broke it ("symbol lookup error", binutils 2.38, 2026-10-31).
find "$APPDIR/usr/python/lib" -type f -name "*.so*" -exec strip --strip-debug {} +

# 2. The app and its Python dependencies (resolved, not --no-deps as in the .deb).
uv pip install --quiet --python "$PY" --target "$LIB" \
    . "PySide6-Essentials>=6.8" "evdev-binary>=1.9"
# Qt: an allowlist, not a denylist (PySide6-Essentials also ships QML/Quick and more). Keep the
# Python modules the app imports (QtCore, QtGui, QtWidgets, QtNetwork; QtSvg and QtDBus for the
# icons and the tray) and the plugins a desktop session loads, then every Qt library those
# link to (ldd closure) and nothing else. --selftest (CI) then proves the icons still render.
Q="$LIB/PySide6"
rm -rf "$Q"/{Qt/qml,Qt/translations,Qt/libexec,Qt/metatypes,assistant,designer,linguist,lrelease,lupdate,qmllint,qmlformat,qmlls,uic,rcc,examples,include,typesystems,glue,scripts} \
       "$LIB"/bin "$LIB"/onnxruntime/{tools,transformers,quantization} "$LIB"/onnxruntime/capi/libonnxruntime.so.*
for f in "$Q"/Qt*.abi3.so "$Q"/Qt*.pyi; do
    case "$(basename "$f")" in QtCore.*|QtGui.*|QtWidgets.*|QtNetwork.*|QtSvg.*|QtDBus.*) ;; *) rm -f "$f" ;; esac
done
for d in "$Q"/Qt/plugins/*; do
    case "$(basename "$d")" in
        platforms|iconengines|imageformats|platforminputcontexts|platformthemes|tls|networkinformation|\
        xcbglintegrations|wayland-decoration-client|wayland-graphics-integration-client|wayland-shell-integration) ;;
        *) rm -rf "$d" ;;
    esac
done
find "$Q"/Qt/plugins/platforms -name '*.so' ! -name 'libqxcb.so' ! -name 'libqwayland*.so' ! -name 'libqoffscreen.so' -delete
keep=$(find "$Q" -maxdepth 1 -name '*.so*'; find "$Q"/Qt/plugins -name '*.so'; ls "$LIB"/shiboken6/*.so*)
# realpath: a plugin's deps resolve as plugins/<dir>/../../lib/..., which a plain match misses
need=$(for f in $keep; do ldd "$f"; done | awk '$3 ~ /^\// {print $3}' | xargs -r realpath | grep -F "$(realpath "$Q")/Qt/lib/" | xargs -rn1 basename | sort -u)
for f in "$Q"/Qt/lib/*.so*; do
    grep -qxF "$(basename "$f")" <<<"$need" || rm -f "$f"
done
# (system libraries such as libxkbcommon may be absent from the build container: only Qt's own count)
if for f in $keep; do ldd "$f"; done | grep 'not found' | grep -q 'libQt6\|libicu\|libpyside\|libshiboken'; then
    for f in $keep; do ldd "$f" | grep 'not found' | grep 'libQt6\|libicu' | sed "s|^|$f: |"; done | sort -u >&2
    echo "a kept Qt module or plugin is missing a library" >&2; exit 1
fi
find "$LIB" -name '__pycache__' -type d -prune -exec rm -rf {} +

# 3. PortAudio for sounddevice (found through packaging/appimage/sitecustomize.py) with what it
#    links to (Ubuntu's is built with JACK, and libjack needs libdb-5.3: "cannot open
#    libdb-5.3.so" on Fedora 43 without it). glibc, ALSA and the C++ runtime stay the system's.
pa=$(ldconfig -p | awk '$1 == "libportaudio.so.2" && /x86-64/ {print $NF; exit}')
cp -L "$pa" "$APPDIR/usr/lib/"
ldd "$pa" | awk '$3 ~ /^\// {print $1, $3}' | while read -r name path; do
    case "$name" in libc.so*|libm.so*|libpthread*|libdl.so*|librt.so*|ld-linux*|libasound*|libstdc++*|libgcc_s*) ;;
        *) cp -L "$path" "$APPDIR/usr/lib/$name" ;; esac
done

# 4. Clipboard tools, used only when the system has none (AppRun appends usr/bin to PATH).
for t in xclip wl-copy; do
    install -m755 "$(command -v "$t")" "$APPDIR/usr/bin/"
    patchelf --set-rpath '$ORIGIN/../lib' "$APPDIR/usr/bin/$t"
done
cp -L "$(ldconfig -p | awk '$1 == "libXmu.so.6" && /x86-64/ {print $NF; exit}')" "$APPDIR/usr/lib/"

# 5. Desktop integration and the launcher
install -m755 packaging/appimage/AppRun "$APPDIR/AppRun"
install -m644 packaging/appimage/sitecustomize.py "$LIB/"
install -m644 packaging/hebrish.desktop "$APPDIR/usr/share/applications/hebrish.desktop"
cp "$APPDIR/usr/share/applications/hebrish.desktop" "$APPDIR/hebrish.desktop"
install -m644 hebrish/data/icons/hebrish.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cp hebrish/data/icons/hebrish.svg "$APPDIR/hebrish.svg"
ln -s hebrish.svg "$APPDIR/.DirIcon"
sed "s|@RELEASES@|    <release version=\"$VERSION\" date=\"$(date -u +%F)\"><url>https://hebrish.app/changelog</url></release>|" \
    packaging/hebrish.metainfo.xml > "$APPDIR/usr/share/metainfo/app.hebrish.Dictation.metainfo.xml"
# appimagetool (and AppImageHub's check) look for <desktop file name>.appdata.xml and validate it
ln -s app.hebrish.Dictation.metainfo.xml "$APPDIR/usr/share/metainfo/hebrish.appdata.xml"

# 6. Pack
curl -fsSL -o "$BUILD/appimagetool" "$TOOL_URL"
curl -fsSL -o "$BUILD/runtime" "$RUNTIME_URL"
printf '%s  %s\n' "$TOOL_SHA" "$BUILD/appimagetool" "$RUNTIME_SHA" "$BUILD/runtime" | sha256sum -c --quiet -
chmod +x "$BUILD/appimagetool"
mkdir -p dist
OUT="dist/Hebrish-$VERSION-x86_64.AppImage"
# Update information: AppImageUpdate, Gear Lever and AM fetch this .zsync and download only the
# changed blocks. It names the stable CDN copy, not a GitHub release: the repo's releases mix
# Android and desktop, so gh-releases-zsync's "latest" would find an APK release.
UPDATE_INFO="zsync|https://cdn.hebrish.app/apps/linux/Hebrish-latest-x86_64.AppImage.zsync"
# --no-appstream: 22.04's appstreamcli 0.15 rejects current tags (<developer>, vcs-browser URL);
# CI job appimage-test validates the metainfo with fedora:43's current appstreamcli instead.
ARCH=x86_64 "$BUILD/appimagetool" --appimage-extract-and-run --no-appstream --runtime-file "$BUILD/runtime" \
    -u "$UPDATE_INFO" "$APPDIR" "$OUT" >/dev/null
rm -f "$OUT.zsync"          # appimagetool's names the versioned file, which the CDN doesn't keep

# 7. The .zsync for the CDN, beside Hebrish-latest-x86_64.AppImage (its URL is relative to it)
zsyncmake -u Hebrish-latest-x86_64.AppImage -o dist/Hebrish-latest-x86_64.AppImage.zsync "$OUT"
echo "Built: $OUT ($(du -h "$OUT" | cut -f1)) + dist/Hebrish-latest-x86_64.AppImage.zsync"
