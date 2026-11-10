# Copying the game data to `Android/data`

Easiest: in the app, pair wireless debugging (Device tab) and tap **Copy data**. The rest of this page is for copying without adb.

The app builds two things for each game: the **APK** and a **data folder** (for example `/sdcard/Switch/Ports/Dark_Souls-data`).
The APK installs from the app. The data folder has to go to

```
/sdcard/Android/data/<package>/files/
```

by hand, because Android 11 and newer stop normal apps (including this one) from writing into another app's `Android/data` folder.
`<package>` is the game's package name. It is shown after the port finishes, and it is also written in `nx2a-data.json` inside the data folder (the `"package"` field).
Example: `unknownnone.nx2android.darksouls`.

## Before you copy (everyone)

1. Install the game's APK first.
2. Open the game once and close it. That makes Android create `Android/data/<package>/`. (It may show a black screen or close straight away. That is fine, the data is not there yet.)
3. Copy **everything inside** the data folder, including `nx2a-data.json`, into `Android/data/<package>/files/`. Copy `nx2a-data.json` last if you can.
   The result should look like `Android/data/<package>/files/nx2a-data.json` (not `files/<Game>-data/nx2a-data.json`).
4. Do not rename any file or folder.

Allow plenty of space: you need free space for a second copy of the data until you delete the one in `Switch/Ports`.

## Not rooted: Shizuku

[Shizuku](https://shizuku.rikka.app/) lets an app act with adb-level permission, and adb is allowed to write to `Android/data`.

1. Install Shizuku and start it (Settings → Developer options → Wireless debugging; Shizuku's own guide walks you through pairing and starting it on the phone itself. It must be started again after every reboot).
2. Use a file manager that supports Shizuku for `Android/data`. File managers such as **MT Manager** do; which apps support it, and how you enable it, changes between versions, so check the file manager's own settings for "Shizuku".
3. In that file manager, grant it Shizuku access, then copy the contents of the data folder into `Android/data/<package>/files/` (see above).

I could not test this on every phone. If a step differs on yours, the file manager's own Shizuku instructions win.

### Alternative without Shizuku: adb from a computer

With USB debugging (or wireless debugging) on and a computer with adb:

```
adb push "<data folder>/." /sdcard/Android/data/<package>/files/
```

adb runs as the shell user, which may write to `Android/data`.

## Rooted

Any root file manager works: give it root, then copy as above.

From a root shell (`su`) instead:

```
PKG=<package>
SRC="/sdcard/Switch/Ports/<Game>-data"
DST="/data/media/0/Android/data/$PKG/files"
mkdir -p "$DST"
cp -r "$SRC"/. "$DST"/
# give the files to the game, not to root
UID_=$(stat -c %u /data/data/$PKG)
chown -R $UID_:$UID_ "$DST"   # on some phones the group is 'ext_data_rw' or 'media_rw'. If the game cannot read the files, copy the owner of other files in that folder's parent.
restorecon -R "$DST"
```

`/data/media/0` is the same storage as `/sdcard`, reached without Android's `Android/data` restriction.
These commands are written from how Android normally works and have not been checked on every ROM.

## If the game does not start or shows a black screen

- Check that the path ends in `Android/data/<package>/files/` and that `nx2a-data.json` is directly inside `files`.
- Check that all files were copied (the sizes of the two folders should match).
- Send the port log and, if you can, the phone's `adb logcat` output.
