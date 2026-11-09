#!/usr/bin/env bash
# Builds the porter's two .NET tools (nx_extract, dmsh_xlate) for linux-arm64 as NativeAOT (no .NET runtime needed on the phone), checks that they really start,
# and publishes nx-tools-<sources key>.tar.xz in the "prebuilt" release. Built for upstream's newest commit AND for the commit the app pins, so a phone that has
# not updated its porter yet still finds its tools. latest.json names the newest build: the phone falls back to it when its exact key has no build.
set -uo pipefail
R="$GITHUB_REPOSITORY"; W=/tmp/pb; rm -rf "$W"; mkdir -p "$W"; cd "$W"
LOG="$W/report.txt"; : > "$LOG"; say() { echo "$*" | tee -a "$LOG"; }
PINNED="$(python3 -c "import json,sys; print(json.load(open('$GITHUB_WORKSPACE/app/src/main/assets/nx2a/payload/payload.json'))['porter_sha'])")"
HEAD_SHA="$(curl -fsSL -H 'Accept: application/vnd.github.sha' -H 'User-Agent: nx2android-ci' https://api.github.com/repos/shirai91/nx2android/commits/main)" || { say "cannot read upstream's newest commit"; HEAD_SHA=""; }
gh release view prebuilt -R "$R" >/dev/null 2>&1 || gh release create prebuilt -R "$R" --prerelease --title "Prebuilt .NET tools" --notes "starting"
sudo apt-get install -y -qq clang zlib1g-dev >/dev/null 2>&1

build_for() {   # $1 = upstream commit; prints the key on success
  local SHA="$1" D="$W/$1"; mkdir -p "$D/src" "$D/out"
  curl -fsSL -o "$D/up.tgz" "https://codeload.github.com/shirai91/nx2android/tar.gz/$SHA" && tar -xzf "$D/up.tgz" -C "$D/src" --strip-components=1 || { say "cannot download upstream $SHA"; return 1; }
  local KEY NAME; KEY="$(python3 "$GITHUB_WORKSPACE/app/src/main/assets/nx2a/payload/prebuilt_key.py" "$D/src")"; NAME="nx-tools-$KEY.tar.xz"
  say "upstream ${SHA:0:9}, tool sources $KEY"
  if gh release download prebuilt -R "$R" --pattern "$NAME.sha256" -O /tmp/have.sha --clobber >/dev/null 2>&1; then say "  already built"; LAST_KEY="$KEY"; return 0; fi
  local n=aot; mkdir -p "$D/out/$n"
  ( cd "$D" && dotnet publish src/nxnative/dm/tools/nx_extract -c Release -r linux-arm64 -o "out/$n/nx_extract" -nologo -v quiet --self-contained true -p:PublishAot=true -p:InvariantGlobalization=true \
    && dotnet publish src/nxnative/dm/gfx/tools/dmsh_xlate -c Release -r linux-arm64 -o "out/$n/dmsh_xlate" -nologo -v quiet --self-contained true -p:PublishAot=true -p:InvariantGlobalization=true ) > "$D/build.log" 2>&1 \
    || { say "  BUILD FAILED: $(grep -E 'error' "$D/build.log" | head -3 | tr '\n' ' ' | cut -c1-500)"; return 1; }
  [ -f "$D/out/$n/dmsh_xlate/dmsh_xlate.dll" ] || : > "$D/out/$n/dmsh_xlate/dmsh_xlate.dll"
  "$D/out/$n/dmsh_xlate/dmsh_xlate" --source-sha > "$D/t1" 2>&1; "$D/out/$n/nx_extract/nx_extract" > "$D/t2" 2>&1   # no pipes: pipefail would count the usage exit code as a failure
  if ! { grep -qE '^[0-9a-f]{16}' "$D/t1" && grep -qi usage "$D/t2"; }; then say "  built but does not start: $(head -c 200 "$D/t1" | tr '\n' ' ') / $(head -c 200 "$D/t2" | tr '\n' ' ')"; return 1; fi
  python3 -c "import json; json.dump({'key': '$KEY', 'upstream': '$SHA', 'variants': ['$n']}, open('$D/out/manifest.json', 'w'))"
  ( cd "$D/out" && XZ_OPT='-9e -T0' tar -cJf "/tmp/$NAME" manifest.json $n ) && ( cd /tmp && sha256sum "$NAME" > "$NAME.sha256" ) || return 1
  gh release upload prebuilt -R "$R" "/tmp/$NAME" "/tmp/$NAME.sha256" --clobber && say "  published $NAME ($(du -h "/tmp/$NAME" | cut -f1))" || return 1
  LAST_KEY="$KEY"
}

LATEST_KEY=""
for S in $HEAD_SHA $PINNED; do LAST_KEY=""; build_for "$S" && { [ -z "$LATEST_KEY" ] && LATEST_KEY="$LAST_KEY"; }; done   # the first success (upstream's newest if it built) is "latest"
if [ -n "$LATEST_KEY" ]; then echo "{\"key\": \"$LATEST_KEY\", \"file\": \"nx-tools-$LATEST_KEY.tar.xz\"}" > /tmp/latest.json; gh release upload prebuilt -R "$R" /tmp/latest.json --clobber && say "latest: $LATEST_KEY"; fi
gh release edit prebuilt -R "$R" --notes-file "$LOG" >/dev/null 2>&1 || true
exit 0
