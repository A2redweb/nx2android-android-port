#!/usr/bin/env bash
# Builds ndk-lite-r27c.tar.xz: only the parts of Android NDK r27c that the ARM host build reads (the arm64 sysroot, the arm64 compiler runtime, source.properties).
# The official download is 1.4 GB and 2.6 GB unpacked; this is a small fraction of it.
set -euo pipefail
N=android-ndk-r27c; P="$N/toolchains/llvm/prebuilt/linux-x86_64"
curl -fL --retry 3 -o /tmp/ndk.zip "https://dl.google.com/android/repository/$N-linux.zip"
rm -rf /tmp/ndk && mkdir /tmp/ndk && cd /tmp/ndk
unzip -q /tmp/ndk.zip "$N/source.properties" "$P/sysroot/*" "$P/lib/clang/*/lib/*"
for a in arm-linux-androideabi i686-linux-android x86_64-linux-android riscv64-linux-android; do rm -rf "$P/sysroot/usr/lib/$a" "$P/sysroot/usr/include/$a"; done
find "$P/lib/clang" -type f ! -path '*aarch64*' -delete; find "$P/lib/clang" -type d -empty -delete
du -sh "$N"
XZ_OPT='-9e -T0' tar -cJf /tmp/ndk-lite-r27c.tar.xz "$N"
(cd /tmp && sha256sum ndk-lite-r27c.tar.xz > ndk-lite-r27c.tar.xz.sha256)
ls -l /tmp/ndk-lite-r27c.tar.xz
