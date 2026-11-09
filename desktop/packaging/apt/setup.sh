#!/bin/sh
# Add the Hebrish APT repository and install Hebrish (Ubuntu 26.04, amd64).
#   curl -fsSL https://cdn.hebrish.app/apt/setup.sh | sudo sh
# Another app from the same repo: pass its package name (2026-11-09: meorav, the Meorav TTS test app)
#   curl -fsSL https://cdn.hebrish.app/apt/setup.sh | sudo sh -s meorav
# Source: https://github.com/Hebrish-ASR/Hebrish-App/blob/main/desktop/packaging/apt/setup.sh
set -eu
PKG=${1:-hebrish}
case "$PKG" in hebrish|meorav) ;; *) echo "Unknown package: $PKG (hebrish or meorav)" >&2; exit 1 ;; esac
FPR=4745D63577C81400DBB743DFDBD1F5A22CA1B27B
KEYRING=/etc/apt/keyrings/hebrish-archive-keyring.gpg
[ "$(id -u)" = 0 ] || { echo "Run as root: curl -fsSL https://cdn.hebrish.app/apt/setup.sh | sudo sh" >&2; exit 1; }
[ "$(dpkg --print-architecture)" = amd64 ] || { echo "Hebrish is packaged for amd64 only." >&2; exit 1; }
. /etc/os-release
if [ "${ID:-}" != ubuntu ] || [ "${VERSION_ID:-}" != 26.04 ]; then
    echo "Warning: the package is built for Ubuntu 26.04; this is ${PRETTY_NAME:-unknown}. apt may refuse it." >&2
fi
command -v curl >/dev/null || { apt-get update -q && apt-get install -y -q curl; }
command -v gpg >/dev/null || apt-get install -y -q gpg
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
curl -fsSL https://cdn.hebrish.app/apt/hebrish-archive-keyring.gpg -o "$tmp"
gpg --show-keys --with-colons "$tmp" | grep -q "^fpr:*$FPR:" || { echo "Keyring fingerprint mismatch; not installing." >&2; exit 1; }
install -d -m 0755 /etc/apt/keyrings
install -m 0644 "$tmp" "$KEYRING"
# Byte-identical to the conffile the package ships, so installing it raises no conffile prompt.
cat > /etc/apt/sources.list.d/hebrish.sources <<'SRC'
Types: deb
URIs: https://cdn.hebrish.app/apt
Suites: stable
Components: main
Architectures: amd64
Signed-By: /etc/apt/keyrings/hebrish-archive-keyring.gpg
SRC
apt-get update -q
apt-get install -y "$PKG"
echo "$PKG is installed. Start it from the app menu; updates arrive with your normal system updates."
