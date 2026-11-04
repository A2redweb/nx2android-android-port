#!/bin/bash
# Runs inside the Ubuntu rootfs (aarch64). Installs the system packages and the Python environment. Safe to run again.
# Kept small on purpose: everything under proot is slow, so only what a port needs is installed, without recommended extras and without fsync.
set -e
export DEBIAN_FRONTEND=noninteractive
D="$(cd "$(dirname "$0")" && pwd)"
cat > /etc/apt/apt.conf.d/98nx2a-fast <<'CONF'
Acquire::Languages "none";
Acquire::GzipIndexes "true";
APT::Install-Recommends "false";
APT::Install-Suggests "false";
Dpkg::Options { "--force-unsafe-io"; };
CONF
apt-get update
apt-get install -y python3 python3-venv ca-certificates clang lld binutils glslc adb fonts-dejavu-core xz-utils
command -v glslc >/dev/null || echo "WARNING: glslc is missing, the Android host build will fail"
[ -d /root/venv ] || python3 -m venv /root/venv
/root/venv/bin/pip install -q --no-cache-dir --prefer-binary lz4 capstone pillow fonttools pyyaml pycryptodome
/root/venv/bin/python -c 'import compression.zstd' 2>/dev/null || /root/venv/bin/pip install -q --no-cache-dir backports.zstd
/root/venv/bin/python -c "import json; print(json.load(open('$D/payload.json'))['setup'])" > /root/.nx2a_setup
echo "setup finished"
