#!/usr/bin/env bash
# Publish .debs to the Hebrish APT repository (https://cdn.hebrish.app/apt, R2 bucket hebrish-cdn,
# prefix apt/) and re-sign it:   scripts/publish-apt.sh dist/hebrish_0.6.2-1_amd64.deb
# With no argument it only regenerates and re-signs the indexes from what is in the pool.
#
# Layout (suite stable, component main, amd64; see docs/maintaining.md, "APT repository"):
#   apt/pool/main/h/hebrish/<deb>          the last $KEEP versions; older ones are deleted
#   apt/dists/stable/{InRelease,Release,Release.gpg}
#   apt/dists/stable/main/binary-amd64/{Packages,Packages.gz,by-hash/SHA{256,512}/<hash>}
#   apt/hebrish-archive-keyring.{gpg,asc}, apt/setup.sh
# Upload order is pool, by-hash, indexes, then Release/InRelease last, and Release sets
# Acquire-By-Hash, so a client that sees a cached-old or freshly-new InRelease always finds
# matching index files.
#
# Needs: aws CLI, gpg, apt-ftparchive (apt-utils).
# Credentials (since 2026-10-25, from Infisical, not op): run it as `with-secrets scripts/publish-apt.sh ...`
# so HEBRISH_CDN_R2_ACCESS_KEY_ID, HEBRISH_CDN_R2_SECRET_ACCESS_KEY and HEBRISH_APT_SIGNING_KEY
# are set (synced from 1Password "Hebrish CDN R2" and "Hebrish APT signing key"). The key is
# imported into a temp GNUPGHOME removed on exit.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

KEEP=${KEEP:-3}
FPR=4745D63577C81400DBB743DFDBD1F5A22CA1B27B
: "${HEBRISH_CDN_R2_ACCESS_KEY_ID:?run under with-secrets}" "${HEBRISH_APT_SIGNING_KEY:?run under with-secrets}"
E=https://81ee9810726226b99b56e4d84ffac020.r2.cloudflarestorage.com
S3=s3://hebrish-cdn/apt
POOL=pool/main/h/hebrish
BIN=dists/stable/main/binary-amd64

for deb in "$@"; do
    [ "$(dpkg-deb -f "$deb" Package)" = hebrish ] || { echo "$deb is not the hebrish package" >&2; exit 1; }
done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export GNUPGHOME="$WORK/gnupg"
mkdir -m 700 "$GNUPGHOME"
export AWS_ACCESS_KEY_ID=$HEBRISH_CDN_R2_ACCESS_KEY_ID \
       AWS_SECRET_ACCESS_KEY=$HEBRISH_CDN_R2_SECRET_ACCESS_KEY \
       AWS_DEFAULT_REGION=auto
printf '%s\n' "$HEBRISH_APT_SIGNING_KEY" | sed 's/^"//; s/"$//' | gpg --batch --quiet --import
gpg --list-secret-keys --with-colons | grep -q "^fpr:*$FPR:" || { echo "signing key not imported" >&2; exit 1; }

REPO="$WORK/repo"
mkdir -p "$REPO/$POOL" "$REPO/$BIN"
aws s3 sync "$S3/$POOL/" "$REPO/$POOL/" --endpoint-url $E --only-show-errors
for deb in "$@"; do cp "$deb" "$REPO/$POOL/"; done

# Keep the newest $KEEP versions (dpkg version order), delete the rest locally and on R2.
mapfile -t debs < <(for f in "$REPO/$POOL"/*.deb; do
    [ -e "$f" ] && printf '%s\t%s\n' "$(dpkg-deb -f "$f" Version)" "$(basename "$f")"; done \
    | sort -t$'\t' -k1,1V | cut -f2)
[ ${#debs[@]} -gt 0 ] || { echo "pool is empty: pass a .deb" >&2; exit 1; }
drop=$(( ${#debs[@]} > KEEP ? ${#debs[@]} - KEEP : 0 ))
for f in "${debs[@]:0:$drop}"; do rm "$REPO/$POOL/$f"; echo "dropping $f"; done

cd "$REPO"
apt-ftparchive packages pool > "$BIN/Packages"
gzip -9nk "$BIN/Packages"
# apt asks for the strongest hash in Release first (SHA512), then falls back ("Ign:" in its log).
for f in Packages Packages.gz; do
    for alg in SHA256 SHA512; do
        h=$(${alg,,}sum "$BIN/$f" | cut -d' ' -f1)
        mkdir -p "$BIN/by-hash/$alg"; cp "$BIN/$f" "$BIN/by-hash/$alg/$h"
    done
done
apt-ftparchive \
    -o APT::FTPArchive::Release::Origin=Hebrish \
    -o APT::FTPArchive::Release::Label=Hebrish \
    -o APT::FTPArchive::Release::Suite=stable \
    -o APT::FTPArchive::Release::Codename=stable \
    -o APT::FTPArchive::Release::Architectures=amd64 \
    -o APT::FTPArchive::Release::Components=main \
    -o "APT::FTPArchive::Release::Description=Hebrish dictation (https://hebrish.app)" \
    -o APT::FTPArchive::Release::Acquire-By-Hash=yes \
    -o APT::FTPArchive::Release::MD5=false -o APT::FTPArchive::Release::SHA1=false \
    release dists/stable | grep -v '/by-hash/' > "$WORK/Release"
mv "$WORK/Release" dists/stable/Release
gpg --batch --yes --local-user $FPR --digest-algo SHA512 --clearsign -o dists/stable/InRelease dists/stable/Release
gpg --batch --yes --local-user $FPR --digest-algo SHA512 -abs -o dists/stable/Release.gpg dists/stable/Release
cd - >/dev/null

cp packaging/apt/hebrish-archive-keyring.gpg packaging/apt/hebrish-archive-keyring.asc packaging/apt/setup.sh "$REPO/"

up() { aws s3 cp "$@" --endpoint-url $E --only-show-errors; }
aws s3 sync "$REPO/pool/" "$S3/pool/" --endpoint-url $E --only-show-errors --delete \
    --content-type application/vnd.debian.binary-package --cache-control "public, max-age=31536000, immutable"
aws s3 sync "$REPO/$BIN/by-hash/" "$S3/$BIN/by-hash/" --endpoint-url $E --only-show-errors \
    --cache-control "public, max-age=31536000, immutable"
for f in Packages Packages.gz; do up "$REPO/$BIN/$f" "$S3/$BIN/$f" --cache-control "public, max-age=60"; done
up "$REPO/dists/stable/Release" "$S3/dists/stable/Release" --content-type text/plain --cache-control "public, max-age=60"
up "$REPO/dists/stable/Release.gpg" "$S3/dists/stable/Release.gpg" --content-type application/pgp-signature --cache-control "public, max-age=60"
up "$REPO/dists/stable/InRelease" "$S3/dists/stable/InRelease" --content-type text/plain --cache-control "public, max-age=60"
up "$REPO/hebrish-archive-keyring.gpg" "$S3/hebrish-archive-keyring.gpg" --content-type application/pgp-keys --cache-control "public, max-age=3600"
up "$REPO/hebrish-archive-keyring.asc" "$S3/hebrish-archive-keyring.asc" --content-type text/plain --cache-control "public, max-age=3600"
up "$REPO/setup.sh" "$S3/setup.sh" --content-type text/x-shellscript --cache-control "public, max-age=300"

echo "Published: $(grep -c '^Package:' "$REPO/$BIN/Packages") package(s) in $S3"
grep -E '^(Package|Version):' "$REPO/$BIN/Packages" | paste - -
