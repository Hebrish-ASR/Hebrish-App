#!/usr/bin/env bash
# Publish a signed release APK to the Hebrish CDN (added 2026-11-05, Daniel: "the pipeline overwrites
# latest, and we're done"). Run by the `cdn` job in .github/workflows/android.yml after every
# android-v* tag; by hand it is also the way to republish a release.
#
#   scripts/publish-android-cdn.sh Hebrish-v1.017.apk v1.017
#
# 1. Overwrites apps/android/Hebrish-latest.apk in R2 bucket hebrish-cdn (attachment filename keeps
#    the version, so a saved file is still identifiable). https://hebrish.app/get/android and the F-Droid
#    build are the same fdroid-flavour APK; old APKs stay on GitHub releases.
# 2. Rewrites downloads/latest.json: files.android and top-level version/released. Desktop entries
#    are left alone. The manifest is read from R2, not the CDN, whose copy is cached for 5 minutes.
# 3. Checks that the public file's sha256 matches.
#
# Needs HEBRISH_CDN_R2_ACCESS_KEY_ID and HEBRISH_CDN_R2_SECRET_ACCESS_KEY (GitHub Actions secrets of
# this repo; locally `with-secrets`). DRY_RUN=1 reads the live manifest, prints the new one, writes nothing.
set -euo pipefail
APK=${1:?usage: publish-android-cdn.sh <apk> <vX.YYY>}
TAG=${2:?usage: publish-android-cdn.sh <apk> <vX.YYY>}
: "${HEBRISH_CDN_R2_ACCESS_KEY_ID:?not set}" "${HEBRISH_CDN_R2_SECRET_ACCESS_KEY:?not set}"
export AWS_ACCESS_KEY_ID=$HEBRISH_CDN_R2_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$HEBRISH_CDN_R2_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
E=https://81ee9810726226b99b56e4d84ffac020.r2.cloudflarestorage.com
S3=s3://hebrish-cdn
KEY=apps/android/Hebrish-latest.apk
NAME="Hebrish-$TAG.apk"
SHA=$(sha256sum "$APK" | cut -d' ' -f1)
SIZE=$(stat -c %s "$APK")
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

aws s3 cp "$S3/downloads/latest.json" "$TMP/old.json" --endpoint-url $E --only-show-errors
python3 - "$TMP/old.json" "$TMP/new.json" "$NAME" "$SIZE" "$SHA" "${TAG#v}" "$KEY" <<'PY'
import datetime, json, sys
old, new, name, size, sha, ver, key = sys.argv[1:]
m = json.load(open(old))
a = m["files"]["android"]
if float(ver) < float(a["version"]):
    sys.exit(f"refusing to go back from {a['version']} to {ver}")
a.update(url=f"https://cdn.hebrish.app/{key}", name=name, size=int(size), sha256=sha, version=ver)
m["version"] = ver
m["released"] = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
json.dump(m, open(new, "w"), indent=2, ensure_ascii=False)
PY

if [ -n "${DRY_RUN:-}" ]; then diff "$TMP/old.json" "$TMP/new.json" || true; exit 0; fi

aws s3 cp "$APK" "$S3/$KEY" --endpoint-url $E --only-show-errors \
  --content-type application/vnd.android.package-archive --cache-control "public, max-age=300" \
  --content-disposition "attachment; filename=\"$NAME\""
aws s3 cp "$TMP/new.json" "$S3/downloads/latest.json" --endpoint-url $E --only-show-errors \
  --content-type application/json --cache-control "public, max-age=300"

# The query string skips the 5-minute cache, so this is the new object, not a stale copy.
GOT=$(curl -fsSL "https://cdn.hebrish.app/$KEY?v=$SHA" | sha256sum | cut -d' ' -f1)
[ "$GOT" = "$SHA" ] || { echo "public sha256 $GOT does not match $SHA" >&2; exit 1; }
echo "Published $NAME ($SIZE bytes, sha256 $SHA)"
