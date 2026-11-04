#!/usr/bin/env bash
# Gives the build a stable release key without any repository secret: it is created once and kept in a draft release named "signing-key",
# which only people with write access to the repository can see. Later builds download the same key, so the app can update in place.
set -euo pipefail
REPO="$GITHUB_REPOSITORY"; D="${RUNNER_TEMP:-/tmp}/sign"; mkdir -p "$D"; cd "$D"
ID="$(gh api "repos/$REPO/releases?per_page=100" --jq '[.[] | select(.draft==true and .name=="signing-key")][0].id // empty')"
if [ -n "$ID" ]; then
  echo "using the stored signing key"
  for n in nx2android-release.p12 pass.txt; do
    AID="$(gh api "repos/$REPO/releases/$ID" --jq ".assets[] | select(.name==\"$n\") | .id")"
    gh api -H "Accept: application/octet-stream" "repos/$REPO/releases/assets/$AID" > "$n"
  done
else
  echo "creating the signing key (first build)"
  openssl rand -base64 30 | tr -d '/+=\n' | head -c 24 > pass.txt
  keytool -genkeypair -keystore nx2android-release.p12 -storetype PKCS12 -alias nx2android -keyalg RSA -keysize 4096 -validity 36500 \
    -storepass "$(cat pass.txt)" -keypass "$(cat pass.txt)" -dname "CN=nx2android"
  gh release create signing-key --draft --title "signing-key (private: the app's release key)" \
    --notes "Created by the build. Keep it: an app signed with another key cannot update this one." nx2android-release.p12 pass.txt
fi
echo "::add-mask::$(cat pass.txt)"
{ echo "KS_FILE=$D/nx2android-release.p12"; echo "KS_PASS=$(cat pass.txt)"; echo "KS_ALIAS=nx2android"; } >> "$GITHUB_ENV"
