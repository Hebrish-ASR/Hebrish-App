#!/usr/bin/env bash
# Publish a desktop release .deb (Ubuntu, beta channel) to the Hebrish CDN. Mirrors publish-android-cdn.sh (2026-11-13;
# until then this step was done by hand from desktop/docs/maintaining.md, "Releasing", step 4). Run it by hand after
# CI has attached the .deb to desktop-vM.NNN, then run desktop/scripts/publish-apt.sh (APT after latest.json).
#
#   scripts/publish-ubuntu-cdn.sh hebrish_1.033-1_amd64.deb v1.033
#
# 1. Overwrites apps/ubuntu/hebrish-latest-amd64.deb in R2 bucket hebrish-cdn (attachment filename keeps
#    the version, so a saved file is still identifiable); https://hebrish.app/get/ubuntu follows it. Old
#    .debs stay on GitHub releases.
# 2. Rewrites downloads/latest.json: files.ubuntu and top-level version/released. Android, Windows and
#    AppImage entries are left alone. The manifest is read from R2, not the CDN, whose copy is cached for 5 minutes.
# 3. Checks that the public file's sha256 matches.
#
# Needs HEBRISH_CDN_R2_ACCESS_KEY_ID and HEBRISH_CDN_R2_SECRET_ACCESS_KEY (GitHub Actions secrets of
# this repo; locally `with-secrets`). DRY_RUN=1 reads the live manifest, prints the new one, writes nothing.
set -euo pipefail
DEB=${1:?usage: publish-ubuntu-cdn.sh <deb> <vX.YYY>}
TAG=${2:?usage: publish-ubuntu-cdn.sh <deb> <vX.YYY>}
: "${HEBRISH_CDN_R2_ACCESS_KEY_ID:?not set}" "${HEBRISH_CDN_R2_SECRET_ACCESS_KEY:?not set}"
export AWS_ACCESS_KEY_ID=$HEBRISH_CDN_R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$HEBRISH_CDN_R2_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
E=https://81ee9810726226b99b56e4d84ffac020.r2.cloudflarestorage.com
S3=s3://hebrish-cdn
KEY=apps/ubuntu/hebrish-latest-amd64.deb
NAME=$(basename "$DEB")
SHA=$(sha256sum "$DEB" | cut -d' ' -f1)
SIZE=$(stat -c %s "$DEB")
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

aws s3 cp "$S3/downloads/latest.json" "$TMP/old.json" --endpoint-url $E --only-show-errors
python3 - "$TMP/old.json" "$TMP/new.json" "$NAME" "$SIZE" "$SHA" "${TAG#v}" "$KEY" <<'PY'
import datetime, json, sys
old, new, name, size, sha, ver, key = sys.argv[1:]
m = json.load(open(old))
a = m["files"]["ubuntu"]
if float(ver) < float(a["version"]):
    sys.exit(f"refusing to go back from {a['version']} to {ver}")
a.update(url=f"https://cdn.hebrish.app/{key}", name=name, size=int(size), sha256=sha, version=ver)
m["version"] = ver
m["released"] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
json.dump(m, open(new, "w"), indent=2, ensure_ascii=False)
PY

if [ -n "${DRY_RUN:-}" ]; then diff "$TMP/old.json" "$TMP/new.json" || true; exit 0; fi

aws s3 cp "$DEB" "$S3/$KEY" --endpoint-url $E --only-show-errors \
  --content-type application/vnd.debian.binary-package --cache-control "public, max-age=300" \
  --content-disposition "attachment; filename=\"$NAME\""
aws s3 cp "$TMP/new.json" "$S3/downloads/latest.json" --endpoint-url $E --only-show-errors \
  --content-type application/json --cache-control "public, max-age=300"

# The query string skips the 5-minute cache, so this is the new object, not a stale copy.
GOT=$(curl -fsSL "https://cdn.hebrish.app/$KEY?v=$SHA" | sha256sum | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "public sha256 $GOT does not match $SHA" >&2; exit 1; }
echo "Published $NAME ($SIZE bytes, sha256 $SHA)"
