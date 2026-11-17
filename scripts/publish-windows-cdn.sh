#!/usr/bin/env bash
# Publish a stable Windows release to the Hebrish CDN (2026-11-17, desktop 1.041+). Run it by hand after the
# stable promotion (desktop.yml, stable=true, tag) has passed; it takes the CI artifacts `velopack` and
# `windows-build`:
#
#   gh run download <run-id> -R Hebrish-ASR/Hebrish-App -n velopack -D dist/velopack
#   gh run download <run-id> -R Hebrish-ASR/Hebrish-App -n windows-build -D dist
#   with-secrets scripts/publish-windows-cdn.sh dist/velopack dist/Hebrish-v1.041-windows-x64.zip v1.041
#
# 1. The Velopack feed, apps/windows/velopack/: every package and the Setup.exe first, the feed files
#    (releases.stable.json, assets.stable.json, RELEASES-stable) last, so an installed copy never reads a
#    feed that names a package not uploaded yet. Old .nupkg files stay (a delta needs its base). The
#    feed is what installed copies (app_update.VELOPACK_FEED) update from.
# 2. apps/windows/Hebrish-Setup-latest.exe (attachment name Hebrish-<ver>-Setup.exe), which
#    hebrish.app/get/windows follows through files.windows in downloads/latest.json. Zip copies (1.040
#    and older) read files.windows too: they are told about the new version and sent to the download
#    page, which offers the installer.
# 3. apps/windows/Hebrish-latest-windows-x64.zip is still overwritten (portable copy; files.windows_zip).
# 4. Checks the public sha256 of the Setup.exe and that the feed names this version.
#
# Needs HEBRISH_CDN_R2_ACCESS_KEY_ID and HEBRISH_CDN_R2_SECRET_ACCESS_KEY. DRY_RUN=1 prints the new
# latest.json and the upload list, writes nothing.
set -euo pipefail
VDIR=${1:?usage: publish-windows-cdn.sh <velopack-dir> <zip> <vM.NNN>}
ZIP=${2:?usage: publish-windows-cdn.sh <velopack-dir> <zip> <vM.NNN>}
TAG=${3:?usage: publish-windows-cdn.sh <velopack-dir> <zip> <vM.NNN>}
VER=${TAG#v}
: "${HEBRISH_CDN_R2_ACCESS_KEY_ID:?not set}" "${HEBRISH_CDN_R2_SECRET_ACCESS_KEY:?not set}"
export AWS_ACCESS_KEY_ID=$HEBRISH_CDN_R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$HEBRISH_CDN_R2_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
E=https://81ee9810726226b99b56e4d84ffac020.r2.cloudflarestorage.com
S3=s3://hebrish-cdn
FEED=apps/windows/velopack
SETUP=$(ls "$VDIR"/*Setup.exe | head -1)
SETUP_KEY=apps/windows/Hebrish-Setup-latest.exe
SETUP_NAME="Hebrish-$VER-Setup.exe"
ZIP_KEY=apps/windows/Hebrish-latest-windows-x64.zip
SHA=$(sha256sum "$SETUP" | cut -d' ' -f1); SIZE=$(stat -c %s "$SETUP")
ZSHA=$(sha256sum "$ZIP" | cut -d' ' -f1); ZSIZE=$(stat -c %s "$ZIP")
SEMVER=$(python3 -c "v='$VER'; a,b=v.split('.'); print(f'{int(a)}.{int(b)}.0')")
grep -q "\"$SEMVER\"" "$VDIR/releases.stable.json" || { echo "$VDIR/releases.stable.json does not list $SEMVER" >&2; exit 1; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

aws s3 cp "$S3/downloads/latest.json" "$TMP/old.json" --endpoint-url $E --only-show-errors
python3 - "$TMP/old.json" "$TMP/new.json" "$VER" "$SETUP_KEY" "$SETUP_NAME" "$SIZE" "$SHA" "$ZIP_KEY" "$(basename "$ZIP")" "$ZSIZE" "$ZSHA" <<'PY'
import json, sys
old, new, ver, key, name, size, sha, zkey, zname, zsize, zsha = sys.argv[1:]
m = json.load(open(old))
w = m["files"].get("windows") or {}
if w.get("version") and float(ver) < float(w["version"]):
    sys.exit(f"refusing to go back from {w['version']} to {ver}")
m["files"]["windows"] = {**w, "url": f"https://cdn.hebrish.app/{key}", "name": name, "size": int(size),
                         "sha256": sha, "version": ver, "platform": "Windows 10/11 x64, installer"}
m["files"]["windows_zip"] = {"url": f"https://cdn.hebrish.app/{zkey}", "name": zname, "size": int(zsize),
                             "sha256": zsha, "version": ver, "platform": "Windows 10/11 x64, portable zip"}
json.dump(m, open(new, "w"), indent=2, ensure_ascii=False)
PY

if [ -n "${DRY_RUN:-}" ]; then diff "$TMP/old.json" "$TMP/new.json" || true; ls -l "$VDIR"; exit 0; fi

cp_() { aws s3 cp "$@" --endpoint-url $E --only-show-errors; }
for f in "$VDIR"/*; do
  case $(basename "$f") in releases.*.json|assets.*.json|RELEASES*|*-Portable.zip) continue ;; esac   # our own zip goes separately
  cp_ "$f" "$S3/$FEED/$(basename "$f")" --cache-control "public, max-age=300"
done
for f in "$VDIR"/releases.*.json "$VDIR"/assets.*.json "$VDIR"/RELEASES*; do
  [ -e "$f" ] && cp_ "$f" "$S3/$FEED/$(basename "$f")" --cache-control "public, max-age=60" --content-type application/json
done
cp_ "$SETUP" "$S3/$SETUP_KEY" --content-type application/vnd.microsoft.portable-executable \
  --cache-control "public, max-age=300" --content-disposition "attachment; filename=\"$SETUP_NAME\""
cp_ "$ZIP" "$S3/$ZIP_KEY" --content-type application/zip --cache-control "public, max-age=300" \
  --content-disposition "attachment; filename=\"$(basename "$ZIP")\""
cp_ "$TMP/new.json" "$S3/downloads/latest.json" --content-type application/json --cache-control "public, max-age=300"

GOT=$(curl -fsSL "https://cdn.hebrish.app/$SETUP_KEY?v=$SHA" | sha256sum | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "public sha256 $GOT does not match $SHA" >&2; exit 1; }
curl -fsSL -A "hebrish (+https://github.com/Hebrish-ASR/Hebrish-App)" "https://cdn.hebrish.app/$FEED/releases.stable.json?v=$SHA" \
  | grep -q "\"$SEMVER\"" || { echo "the public feed does not list $SEMVER" >&2; exit 1; }
echo "Published Windows $VER: $SETUP_NAME ($SIZE bytes, sha256 $SHA), feed $FEED, zip $(basename "$ZIP")"
