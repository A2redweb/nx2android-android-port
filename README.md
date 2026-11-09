# nx2android (phone app)

A phone-side front end for [shirai91/nx2android](https://github.com/shirai91/nx2android), the Switch-to-Android compatibility layer. The porter itself is not copied here: the app downloads upstream's newest commit (falling back to a known-good pinned one) and patches it for ARM phones. All credit for the porter goes to its authors; this repo's history still contains the fork's original commits.

Ports Switch games to Android **on the phone itself**: no PC, no Termux. The app is a thin shell (WebView + proot + Ubuntu). The GUI, the patches and the porter version live in a small *payload* that updates itself from this repository, so the APK only needs rebuilding when the shell itself changes.

## Build the APK (no PC needed)
1. Every push to `main` runs *build-apk* (Actions tab; on a fork, enable Actions once). The finished APK is published at **Releases → latest** (`nx2android.apk`), and as the `nx2android-apk` artifact.
2. The over-the-air payload is read from this repo (see `app/src/main/assets/nx2a/update.json`), so it must stay public.
3. Optional, for a stable signature so users can update in place: add the repository secrets `KEYSTORE_B64` (base64 of a .jks), `KEYSTORE_PASS`, `KEYSTORE_ALIAS`. Without them the APK is debug-signed.

## What updates over the air (no new APK)
`app/src/main/assets/nx2a/payload/`: `webgui/` (the GUI), `apply_patches.py`, `inner_setup.sh`, `prebuilt.py`, `porter_sync.py` and `payload.json` (versions, file hashes, the pinned porter commit `porter_sha`).
To ship a change: edit the files → `python3 tools/make_manifest.py --bump` → commit and push. The workflow refuses to build if `payload.json` is stale. Users see "An update is ready, Restart to apply". Downloads are checked against the hashes in `payload.json`; a payload that fails its hashes, or crashes twice at start, is dropped and the bundled one runs. Versions go 1, 3, 5, ...
- The porter follows upstream's `main` (`porter_track: main`, checked at start and every 6 hours, never during a port). Before swapping it in, our patches are applied to it; if they no longer fit, the working porter is kept. `porter_sha` is the pinned fallback: to pin, remove `porter_track` and change `porter_sha`, then bump. To add system packages: edit `inner_setup.sh`, then `make_manifest.py --setup --bump`.

## What needs a new APK
`launcher.py`, the Java files, the manifest, the proot build, the bundled Ubuntu release.

## Using it
Open the app: first start unpacks Ubuntu (a minute or two) and installs the tools (about 10 minutes, needs internet; keep the app open). Then Setup → set prod.keys and tap *Download missing tools* (the trimmed NDK, about 0.3 GB, plus the ready-made .NET tools), Port → pick the game folder → Port. When it finishes: *Install APK*, then copy the data folder by hand (see below).
Free space: about 6 GB, plus twice the size of each game.

## Credits
Maintained by [A2redweb](https://github.com/A2redweb), built together with Claude (Anthropic). The porter is [shirai91/nx2android](https://github.com/shirai91/nx2android); see the credits there.

## Notes for users
- Android 14 and newer: Developer options → *Disable child process restrictions*, or Android may kill long builds. Set the app's battery usage to *Unrestricted*.
- The app targets an old Android API on purpose (proot cannot run programs from app storage on newer targets). That means no Google Play; use the APK from Releases/Actions.
- You need your own prod.keys and game dumps. Nothing is included.
- The GUI only listens on 127.0.0.1, and every request needs a random per-launch token, so other apps on the phone cannot drive it.

## Storage
While porting, the porter keeps its working files (the extracted game, shader work) in the app's private storage, which only this app can delete. After a successful port the app deletes them for you (tick *Keep the working files* to keep them for a faster re-port). Port tab → *Free space* shows what is left over from earlier or failed ports and deletes it.

## Copying the game data
Android stops apps from writing into another app's `Android/data`, so the data folder is copied by hand: see [docs/COPY_DATA.md](docs/COPY_DATA.md) (rooted and Shizuku).

## The .NET tools
The porter needs two C# tools (the extractor and the shader translator). The standard .NET runtime fails to start under proot on some phones ("Failed to create CoreCLR"), so CI builds them as NativeAOT arm64 programs instead, and the app downloads those. The *prebuilt* job (every 6 hours, and on each push) builds them for upstream's newest commit and for the pinned one, starts each for real, and publishes them in **Releases → prebuilt** with a report in the release notes. On the phone, Setup → *Install / check the ready-made tools* downloads, tests and activates them; if there is no build for the phone's exact porter, the newest build is used. Downloads are retried on GitHub's occasional 502/503/504.

## Releases
- `latest`: the APK.
- `tools`: the trimmed Android NDK (made once by `tools/make_ndk_lite.sh`).
- `prebuilt`: the NativeAOT .NET tools.

## Status
A full port of Dark Souls: Remastered has completed on a Poco X6 with these tools. Copying the data and running the game are still being checked. Game-specific patches (e.g. Dark Souls Remastered) are not kept here: upstream's own profile is used.

## Not yet tested on a real device
The proot build taken from the Termux repository, the Ubuntu release download, and first-run setup on devices other than the author's. If the first start fails, tap *Copy log* and open an issue with it.
