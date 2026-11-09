#!/usr/bin/env bash
# Builds the porter's two .NET tools (nx_extract, dmsh_xlate) for linux-arm64 with runtimes other than the standard CoreCLR, checks that each really starts,
# and publishes the ones that do as nx-tools-<sources key>.tar.xz in the "prebuilt" release. The release notes carry the report of every attempt.
set -uo pipefail
R="$GITHUB_REPOSITORY"; W=/tmp/pb; rm -rf "$W"; mkdir -p "$W/src" "$W/out"; cd "$W"
LOG="$W/report.txt"; : > "$LOG"; say() { echo "$*" | tee -a "$LOG"; }
SHA="$(curl -fsSL -H 'Accept: application/vnd.github.sha' -H 'User-Agent: nx2android-ci' https://api.github.com/repos/shirai91/nx2android/commits/main)" || { say "cannot read upstream's newest commit"; exit 0; }
curl -fsSL -o up.tgz "https://codeload.github.com/shirai91/nx2android/tar.gz/$SHA" && tar -xzf up.tgz -C src --strip-components=1 || { say "cannot download upstream $SHA"; exit 0; }
KEY="$(python3 "$GITHUB_WORKSPACE/app/src/main/assets/nx2a/payload/prebuilt_key.py" src)"; NAME="nx-tools-$KEY.tar.xz"
say "upstream $SHA, tool sources $KEY"
gh release view prebuilt -R "$R" >/dev/null 2>&1 || gh release create prebuilt -R "$R" --prerelease --title "Prebuilt .NET tools" --notes "starting"
if gh release download prebuilt -R "$R" --pattern "$NAME.sha256" -O /tmp/have.sha >/dev/null 2>&1; then say "already built for these sources"; exit 0; fi
NX=src/nxnative/dm/tools/nx_extract; XL=src/nxnative/dm/gfx/tools/dmsh_xlate
build() {
  local n="$1"; shift
  mkdir -p "out/$n"
  ( dotnet publish "$NX" -c Release -r linux-arm64 -o "out/$n/nx_extract" -nologo -v quiet "$@" && dotnet publish "$XL" -c Release -r linux-arm64 -o "out/$n/dmsh_xlate" -nologo -v quiet "$@" ) > "out/$n.log" 2>&1 \
    || { say "$n: BUILD FAILED: $(grep -E 'error|Error' "out/$n.log" | head -3 | tr '\n' ' ' | cut -c1-500)"; rm -rf "out/$n"; return 1; }
  [ -f "out/$n/dmsh_xlate/dmsh_xlate.dll" ] || : > "out/$n/dmsh_xlate/dmsh_xlate.dll"
  # the CI machine is arm64 too: start both tools for real
  "out/$n/dmsh_xlate/dmsh_xlate" --source-sha > "out/$n.t1" 2>&1; "out/$n/nx_extract/nx_extract" > "out/$n.t2" 2>&1   # no pipes: pipefail would count nx_extract's exit code 2 (usage) as a failure
  if grep -qE '^[0-9a-f]{16}' "out/$n.t1" && grep -qi usage "out/$n.t2"; then
    say "$n: built and starts (translator prints $(head -c 16 "out/$n.t1"))"
  else say "$n: built but does not start: translator: $(head -c 200 "out/$n.t1" | tr '\n' ' ') extractor: $(head -c 200 "out/$n.t2" | tr '\n' ' ')"; rm -rf "out/$n"; fi
}
sudo apt-get install -y -qq clang zlib1g-dev >/dev/null 2>&1
build aot --self-contained true -p:PublishAot=true -p:InvariantGlobalization=true
VARS=""; for v in aot; do [ -d "out/$v" ] && VARS="$VARS $v"; done
if [ -n "$VARS" ]; then
  python3 - "$KEY" "$SHA" $VARS <<'PY'
import json, sys
json.dump({'key': sys.argv[1], 'upstream': sys.argv[2], 'variants': sys.argv[3:]}, open('/tmp/pb/out/manifest.json', 'w'))
PY
  ( cd out && XZ_OPT='-9e -T0' tar -cJf "/tmp/$NAME" manifest.json $VARS ) && ( cd /tmp && sha256sum "$NAME" > "$NAME.sha256" )
  gh release upload prebuilt -R "$R" "/tmp/$NAME" "/tmp/$NAME.sha256" --clobber && say "published $NAME ($(du -h "/tmp/$NAME" | cut -f1)) with:$VARS"
else say "no variant could be published"; fi
gh release edit prebuilt -R "$R" --notes-file "$LOG" >/dev/null 2>&1 || true
exit 0
