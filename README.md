# nx2android (phone app)

A phone-side front end for [shirai91/nx2android](https://github.com/shirai91/nx2android), the Switch-to-Android compatibility layer. The porter itself is not copied here: the app fetches a pinned upstream commit at first run and patches it for ARM phones. All credit for the porter goes to its authors; this repo's history still contains the fork's original commits.

Ports Switch games to Android **on the phone itself**: no PC, no Termux. The app is a thin shell (WebView + proot + Ubuntu). The GUI, the patches and the porter version live in a small *payload* that updates itself from this repository, so the APK only needs rebuilding when the shell itself changes.

## Build the APK (no PC needed)
1. Every push to `main` runs *build-apk* (Actions tab; on a fork, enable Actions once). The finished APK is published at **Releases → latest** (`nx2android.apk`), and as the `nx2android-apk` artifact.
2. The over-the-air payload is read from this repo (see `app/src/main/assets/nx2a/update.json`), so it must stay public.
3. Optional, for a stable signature so users can update in place: add the repository secrets `KEYSTORE_B64` (base64 of a .jks), `KEYSTORE_PASS`, `KEYSTORE_ALIAS`. Without them the APK is debug-signed.

## What updates over the air (no new APK)
`app/src/main/assets/nx2a/payload/`: `webgui/` (the GUI), `apply_patches.py`, `inner_setup.sh`, and `payload.json` (versions, file hashes, the pinned porter commit `porter_sha`).
To ship a change: edit the files → `python3 tools/make_manifest.py --bump` → commit and push. The workflow refuses to build if `payload.json` is stale. Users see "An update is ready, Restart to apply". Downloads are checked against the hashes in `payload.json`; a payload that fails its hashes, or crashes twice at start, is dropped and the bundled one runs. Versions go 1, 3, 5, ...
- To move to a newer porter: change `porter_sha`, bump. To add system packages: edit `inner_setup.sh`, then `make_manifest.py --setup --bump`.

## What needs a new APK
`launcher.py`, the Java files, the manifest, the proot build, the bundled Ubuntu release.

## Using it
Open the app: first start unpacks Ubuntu (a minute or two) and installs the tools (about 10 minutes, needs internet; keep the app open). Then Setup → set prod.keys and tap *Download missing tools* (about 1.5 GB), Port → pick the game folder → Port. When it finishes: *Install APK*, then *Copy data*.
Free space: about 6 GB, plus twice the size of each game.

## Notes for users
- Android 14 and newer: Developer options → *Disable child process restrictions*, or Android may kill long builds. Set the app's battery usage to *Unrestricted*.
- The app targets an old Android API on purpose (proot cannot run programs from app storage on newer targets). That means no Google Play; use the APK from Releases/Actions.
- You need your own prod.keys and game dumps. Nothing is included.
- The GUI only listens on 127.0.0.1, and every request needs a random per-launch token, so other apps on the phone cannot drive it.

## Copying the game data
Android stops apps from writing into another app's `Android/data`, so the data folder is copied by hand: see [docs/COPY_DATA.md](docs/COPY_DATA.md) (rooted and Shizuku).

## Not yet tested on a real device
The proot build taken from the Termux repository, the Ubuntu release download, and first-run setup on devices other than the author's. If the first start fails, tap *Copy log* and open an issue with it.
