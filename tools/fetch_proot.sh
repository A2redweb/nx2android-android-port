#!/usr/bin/env bash
# Takes proot (+ its loader and libtalloc) from the Termux package repository and prepares them as native libraries for the APK.
set -euo pipefail
sudo apt-get update -qq && sudo apt-get install -y -qq patchelf binutils xz-utils zstd
B=https://packages.termux.dev/apt/termux-main
curl -fsSL "$B/dists/stable/main/binary-aarch64/Packages" -o /tmp/Packages
pick() { awk -v p="$1" 'BEGIN{RS="";FS="\n"} { n=""; f=""; for(i=1;i<=NF;i++){ if($i=="Package: " p) n=p; if($i ~ /^Filename: /) f=substr($i,11) } if(n==p){print f; exit} }' /tmp/Packages; }
rm -rf /tmp/x; mkdir -p /tmp/x
for p in proot libtalloc; do
  f="$(pick $p)"; [ -n "$f" ] || { echo "package $p not found in the Termux repo"; exit 1; }
  curl -fsSL "$B/$f" -o "/tmp/$p.deb"; mkdir -p "/tmp/x/$p"
  (cd "/tmp/x/$p" && ar x "/tmp/$p.deb" && tar -xf "$(ar t "/tmp/$p.deb" | grep '^data.tar' | head -1)")
done
U=data/data/com.termux/files/usr
J=app/src/main/jniLibs/arm64-v8a; mkdir -p "$J"
cp "/tmp/x/proot/$U/bin/proot" "$J/libproot.so"
L="$(ls /tmp/x/proot/$U/libexec/proot/loader /tmp/x/proot/$U/libexec/proot/loader32 2>/dev/null | head -1)"
cp "$L" "$J/libproot-loader.so"
TAL="$(ls /tmp/x/libtalloc/$U/lib/libtalloc.so.* | xargs -n1 readlink -f | sort -u | head -1)"
cp "$TAL" "$J/libtalloc.so"
patchelf --replace-needed libtalloc.so.2 libtalloc.so --set-rpath '$ORIGIN' "$J/libproot.so"
patchelf --set-soname libtalloc.so "$J/libtalloc.so"
chmod 755 "$J"/*.so
echo "--- libproot.so dynamic section:"; readelf -d "$J/libproot.so" | grep -E 'NEEDED|RPATH|RUNPATH' || true
ls -l "$J"
