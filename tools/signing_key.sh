#!/usr/bin/env bash
# Gives the build a stable release key without any repository secret: it is created once and kept in a draft release named "signing-key",
# which only people with write access to the repository can see. Later builds download the same key, so the app can update in place.
# This script never fails the build: if the key cannot be read or stored it falls back to a one-off key and says so in $SIGN_LOG.
set -uo pipefail
REPO="$GITHUB_REPOSITORY"; D="${RUNNER_TEMP:-/tmp}/sign"; mkdir -p "$D"; cd "$D"; LOG="$D/signing.log"; : > "$LOG"
say() { echo "$*" | tee -a "$LOG"; }
stored() {   # 0 = key downloaded, 2 = no key stored yet, 1 = could not read
  ID="$(gh api "repos/$REPO/releases?per_page=100" --jq '[.[] | select(.draft==true and (.name | startswith("signing-key")))] | sort_by(.created_at) | .[0].id // empty' 2>>"$LOG")" || return 1
  [ -n "$ID" ] || return 2
  for n in nx2android-release.p12 pass.txt; do
    AID="$(gh api "repos/$REPO/releases/$ID" --jq ".assets[] | select(.name==\"$n\") | .id" 2>>"$LOG")"
    [ -n "$AID" ] || { echo "asset $n missing in the stored release" >> "$LOG"; return 1; }
    gh api -H "Accept: application/octet-stream" "repos/$REPO/releases/assets/$AID" > "$n" 2>>"$LOG" || return 1
  done
  [ -s nx2android-release.p12 ] && [ -s pass.txt ]
}
make_key() { openssl rand -hex 12 > pass.txt && keytool -genkeypair -keystore nx2android-release.p12 -storetype PKCS12 -alias nx2android -keyalg RSA -keysize 4096 -validity 36500 \
    -storepass "$(cat pass.txt)" -keypass "$(cat pass.txt)" -dname "CN=nx2android" >>"$LOG" 2>&1; }
stored; rc=$?
if [ $rc -eq 0 ]; then say "signing: using the stored release key"
elif [ $rc -eq 2 ]; then
  say "signing: no stored key yet, creating one"
  if make_key; then
    gh release create signing-key -R "$REPO" --draft --target "$GITHUB_SHA" --title "signing-key (private: the app's release key)" \
      --notes "Created by the build. Keep it: an app signed with another key cannot update this one." nx2android-release.p12 pass.txt >>"$LOG" 2>&1 \
      && say "signing: key created and stored" || say "signing: WARNING the key could not be stored; this build uses a one-off key"
  else say "signing: WARNING key creation failed"; fi
else say "signing: WARNING the stored key could not be read; this build uses a one-off key"; fi
if [ ! -s nx2android-release.p12 ] || [ ! -s pass.txt ]; then
  say "signing: using a one-off key"; rm -f nx2android-release.p12; make_key || say "signing: ERROR no key"
fi
echo "::add-mask::$(cat pass.txt)"
{ echo "KS_FILE=$D/nx2android-release.p12"; echo "KS_PASS=$(cat pass.txt)"; echo "KS_ALIAS=nx2android"; echo "SIGN_LOG=$LOG"; } >> "$GITHUB_ENV"
exit 0
