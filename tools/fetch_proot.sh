#!/usr/bin/env bash
# Takes proot, its loader and every library it needs from the Termux package repository and prepares them as native libraries for the APK.
set -euo pipefail
sudo apt-get update -qq && sudo apt-get install -y -qq patchelf binutils xz-utils zstd
python3 tools/fetch_proot.py
