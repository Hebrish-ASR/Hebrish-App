#!/usr/bin/env bash
# Set an app's version and create its release tag in one step, so the two can't drift:
#   scripts/release-tag.sh desktop 0.6.3 [--push]
#   scripts/release-tag.sh android 0.7.1 [--push]
#
# The tag (desktop-vX.Y.Z / android-vX.Y.Z) is the release's identity: CI builds from it, the
# GitHub release, CDN file names, latest.json and F-Droid all take the version from it. The
# version in the code (desktop/hebrish/__init__.py __version__, which the window footer, .deb
# and update check read; android/app/build.gradle.kts versionName, plus versionCode + 1) must
# equal it, and both workflows fail a tag that doesn't match (step "Tag matches version").
#
# Refuses when: the version isn't X.Y.Z, isn't newer than the last tag for that app, the tag
# already exists, or the release notes (.github/<app>-release-notes.md) don't start with
# **X.Y.Z. Commits only the version file and the notes (other sessions may have work in the
# tree), then makes an annotated tag. --push pushes main and the tag, which starts CI.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

APP=${1:?usage: release-tag.sh desktop|android X.Y.Z [--push]}
VER=${2:?usage: release-tag.sh desktop|android X.Y.Z [--push]}
PUSH=${3:-}
[[ $VER =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "version must be X.Y.Z, got $VER" >&2; exit 1; }
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
        grep -q "versionName = \"$VER\"" "$FILE" ;;
esac

git add "$FILE" "$NOTES"
git diff --cached --quiet -- "$FILE" "$NOTES" || git commit -q -m "${APP^} $VER" -- "$FILE" "$NOTES"
git tag -a "$TAG" -m "Hebrish for $APP $VER"
echo "Tagged $TAG at $(git rev-parse --short HEAD) ($FILE: $VER)"
if [ "$PUSH" = --push ]; then
    git push -q origin HEAD:main
    git push -q origin "$TAG"
    echo "Pushed main and $TAG; CI is building the release."
else
    echo "Not pushed. To release: git push origin HEAD:main $TAG"
fi
