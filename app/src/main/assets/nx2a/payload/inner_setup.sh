#!/bin/bash
# Runs inside the Ubuntu rootfs (aarch64). Installs the system packages and the Python environment. Safe to run again.
set -e
export DEBIAN_FRONTEND=noninteractive
D="$(cd "$(dirname "$0")" && pwd)"
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl ca-certificates unzip xz-utils \
  clang lld llvm glslc adb fonts-dejavu-core libssl-dev zlib1g
LS="$(ls /usr/bin/llvm-strip-* 2>/dev/null | head -1)"
[ -x "$(command -v llvm-strip)" ] || { [ -n "$LS" ] && ln -sf "$LS" /usr/local/bin/llvm-strip; } || true
command -v glslc >/dev/null || echo "WARNING: glslc is missing, the Android host build will fail"
[ -d /root/venv ] || python3 -m venv /root/venv
/root/venv/bin/pip install -q lz4 capstone pillow fonttools pyyaml pycryptodome
/root/venv/bin/python -c 'import compression.zstd' 2>/dev/null || /root/venv/bin/pip install -q backports.zstd
/root/venv/bin/python -c "import json; print(json.load(open('$D/payload.json'))['setup'])" > /root/.nx2a_setup
echo "setup finished"
