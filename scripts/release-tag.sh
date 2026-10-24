#!/usr/bin/env bash
# Set an app's version and create its release tag in one step, so the two can't drift:
#   scripts/release-tag.sh desktop 1.001 [--push]
#   scripts/release-tag.sh android 1.001 [--push]
#
# Versions are MAJOR.NNN, three digits after the point (Daniel, 2026-10-24; D-2026-10-24-01):
# 1.000 was the first, unified across Android and desktop; then 1.001, 1.002, ... Each app still
# releases on its own. Up to 2026-10-24 versions were X.Y.Z (last: Android 0.10.0, desktop 0.8.0).
#
# The tag (desktop-vM.NNN / android-vM.NNN) is the release's identity: CI builds from it, the
# GitHub release, CDN file names, latest.json and F-Droid all take the version from it. The
# version in the code (desktop/hebrish/__init__.py __version__, which the window footer, .deb
# and update check read; android/app/build.gradle.kts versionName, plus versionCode + 1) must
# equal it, and both workflows fail a tag that doesn't match (step "Tag matches version").
#
# Refuses when: the version isn't M.NNN, isn't newer than the last tag for that app, the tag
# already exists, or the release notes (.github/<app>-release-notes.md) don't start with
# **M.NNN. Commits only the version file and the notes (other sessions may have work in the
# tree), then makes an annotated tag. --push pushes main and the tag, which starts CI.
#
# Android also gets the F-Droid changelog for the new versionCode
# (android/app/fastlane/metadata/android/en-US/changelogs/<versionCode>.txt, at most 500
# characters; f-droid.org shows it). Write it by hand for a fuller text, or it is made from the
# notes' first line.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APP=${1:?usage: release-tag.sh desktop|android M.NNN [--push]}
VER=${2:?usage: release-tag.sh desktop|android M.NNN [--push]}
PUSH=${3:-}
[[ $VER =~ ^[0-9]+\.[0-9]{3}$ ]] || { echo "version must be M.NNN (e.g. 1.001), got $VER" >&2; exit 1; }
TAG="$APP-v$VER"
NOTES=".github/$APP-release-notes.md"

case $APP in
    desktop) FILE=desktop/hebrish/__init__.py ;;
    android) FILE=android/app/build.gradle.kts ;;
    *) echo "app must be desktop or android" >&2; exit 1 ;;
esac

git fetch -q --tags origin
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && { echo "$TAG already exists" >&2; exit 1; }
LAST=$(git tag -l "$APP-v*" | sed "s/^$APP-v//" | sort -V | tail -1)
if [ -n "$LAST" ] && [ "$(printf '%s\n%s\n' "$LAST" "$VER" | sort -V | tail -1)" != "$VER" ] || [ "$LAST" = "$VER" ]; then
    echo "$VER is not newer than the last $APP tag ($LAST)" >&2; exit 1
fi
head -1 "$NOTES" | grep -q "^\*\*$VER" || { echo "$NOTES must start with **$VER: (write the notes first)" >&2; exit 1; }

case $APP in
    desktop)
        sed -i "s/^__version__ = \".*\"/__version__ = \"$VER\"/" "$FILE"
        grep -q "^__version__ = \"$VER\"$" "$FILE" ;;
    android)
        CODE=$(sed -n 's/^ *versionCode = \([0-9]*\)$/\1/p' "$FILE")
        sed -i "s/^\( *versionCode = \)[0-9]*$/\1$((CODE + 1))/; s/^\( *versionName = \)\".*\"$/\1\"$VER\"/" "$FILE"
        grep -q "versionName = \"$VER\"" "$FILE"
        CHANGELOG="android/app/fastlane/metadata/android/en-US/changelogs/$((CODE + 1)).txt"
        [ -f "$CHANGELOG" ] || head -1 "$NOTES" | sed 's/\*\*//g; s/\[\([^]]*\)\]([^)]*)/\1/g' > "$CHANGELOG"
        [ "$(wc -m < "$CHANGELOG")" -le 500 ] || { echo "$CHANGELOG is over 500 characters" >&2; exit 1; } ;;
esac

git add "$FILE" "$NOTES" ${CHANGELOG:+"$CHANGELOG"}
git diff --cached --quiet -- "$FILE" "$NOTES" ${CHANGELOG:+"$CHANGELOG"} || git commit -q -m "${APP^} $VER" -- "$FILE" "$NOTES" ${CHANGELOG:+"$CHANGELOG"}
git tag -a "$TAG" -m "Hebrish for $APP $VER"
echo "Tagged $TAG at $(git rev-parse --short HEAD) ($FILE: $VER)"
if [ "$PUSH" = --push ]; then
    git push -q origin HEAD:main
    git push -q origin "$TAG"
    echo "Pushed main and $TAG; CI is building the release."
else
    echo "Not pushed. To release: git push origin HEAD:main $TAG"
fi
