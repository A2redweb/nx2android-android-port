#!/usr/bin/env bash
# Downloads the official Ubuntu Base (arm64) tarball and bundles it in the APK assets. UBUNTU_REL picks the release (default 26.04).
set -euo pipefail
REL="${UBUNTU_REL:-26.04}"
BASE="https://cdimage.ubuntu.com/ubuntu-base/releases/$REL/release"
FILE="$(curl -fsSL "$BASE/" | grep -oE 'ubuntu-base-[0-9.]+-base-arm64\.tar\.gz' | sort -uV | tail -1)"
[ -n "$FILE" ] || { echo "no arm64 Ubuntu Base found at $BASE (set UBUNTU_REL)"; exit 1; }
echo "using $FILE"
curl -fsSL "$BASE/$FILE" -o /tmp/rootfs.tar.gz
curl -fsSL "$BASE/SHA256SUMS" | grep " \*\?$FILE\$" | sed "s# \*\?$FILE# /tmp/rootfs.tar.gz#" | sha256sum -c -
mkdir -p app/src/main/assets && mv /tmp/rootfs.tar.gz app/src/main/assets/rootfs.bin
ls -l app/src/main/assets/rootfs.bin
