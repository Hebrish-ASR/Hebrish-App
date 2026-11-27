#!/usr/bin/env bash
# Publish a stable AppImage to the Hebrish CDN (desktop/docs/maintaining.md, "Releasing", step 3; scripted 2026-11-27,
# before that by hand). Overwrites apps/linux/Hebrish-latest-x86_64.AppImage and its .zsync (the AppImage's update
# information names that .zsync), then sets files.appimage in downloads/latest.json. Input: the `appimage` artifact of
# the stable promotion run (gh run download <run> -n appimage -D <dir>).
#   with-secrets scripts/publish-appimage-cdn.sh <dir>/Hebrish-<ver>-x86_64.AppImage <dir>/Hebrish-latest-x86_64.AppImage.zsync v<ver>
# DRY_RUN=1 prints the manifest change only. Needs HEBRISH_CDN_R2_ACCESS_KEY_ID / _SECRET_ACCESS_KEY and the aws CLI.
set -euo pipefail
APP=${1:?usage: publish-appimage-cdn.sh <AppImage> <zsync> <vX.YYY>}
ZS=${2:?usage: publish-appimage-cdn.sh <AppImage> <zsync> <vX.YYY>}
TAG=${3:?usage: publish-appimage-cdn.sh <AppImage> <zsync> <vX.YYY>}
: "${HEBRISH_CDN_R2_ACCESS_KEY_ID:?not set}" "${HEBRISH_CDN_R2_SECRET_ACCESS_KEY:?not set}"
export AWS_ACCESS_KEY_ID=$HEBRISH_CDN_R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$HEBRISH_CDN_R2_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
E=https://81ee9810726226b99b56e4d84ffac020.r2.cloudflarestorage.com
S3=s3://hebrish-cdn
KEY=apps/linux/Hebrish-latest-x86_64.AppImage
NAME=$(basename "$APP")
SHA=$(sha256sum "$APP" | cut -d' ' -f1)
SIZE=$(stat -c %s "$APP")
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

aws s3 cp "$S3/downloads/latest.json" "$TMP/old.json" --endpoint-url $E --only-show-errors
python3 - "$TMP/old.json" "$TMP/new.json" "$NAME" "$SIZE" "$SHA" "${TAG#v}" "$KEY" <<'PY'
import json, sys
old, new, name, size, sha, ver, key = sys.argv[1:]
m = json.load(open(old))
a = m["files"].setdefault("appimage", {})
if a.get("version") and float(ver) < float(a["version"]):
    sys.exit(f"refusing to go back from {a['version']} to {ver}")
a.update(url=f"https://cdn.hebrish.app/{key}", name=name, platform="Linux x86_64, AppImage",
         size=int(size), sha256=sha, version=ver)
json.dump(m, open(new, "w"), indent=2, ensure_ascii=False)
PY

if [ -n "${DRY_RUN:-}" ]; then diff "$TMP/old.json" "$TMP/new.json" || true; exit 0; fi

aws s3 cp "$APP" "$S3/$KEY" --endpoint-url $E --only-show-errors \
  --content-type application/octet-stream --cache-control "public, max-age=300" \
  --content-disposition "attachment; filename=\"$NAME\""
aws s3 cp "$ZS" "$S3/$KEY.zsync" --endpoint-url $E --only-show-errors \
  --content-type application/octet-stream --cache-control "public, max-age=300"
aws s3 cp "$TMP/new.json" "$S3/downloads/latest.json" --endpoint-url $E --only-show-errors \
  --content-type application/json --cache-control "public, max-age=300"

GOT=$(curl -fsSL "https://cdn.hebrish.app/$KEY?v=$SHA" | sha256sum | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "public sha256 $GOT does not match $SHA" >&2; exit 1; }
echo "Published $NAME ($SIZE bytes, sha256 $SHA)"
