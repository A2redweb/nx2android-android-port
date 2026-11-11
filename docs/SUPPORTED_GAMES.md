# Games

What this app can port. **Upstream first:** a game that upstream (`shirai91/nx2android`) already supports is ported with upstream's own profile, untouched. Only when upstream has nothing for a game does this app add its own fix, and each such game is listed below.

You need the game files (base game, plus the update the profile was tested on, plus any DLC) and your own `prod.keys`. The phone's GPU must read BC-compressed textures: Adreno and Xclipse do, Mali (this includes MediaTek Dimensity phones) and PowerVR do not, and the games are expected to crash.

## Added by this app

| Game | Status | What this app adds | What you need |
|---|---|---|---|
| Fire Emblem: Three Houses (`010055D009F78000`) | experimental | Upstream has the game profile but no Android profile and no way to make its 9 run-time shaders off a Mac. The port runs that step on your phone over adb (payload patch "device glslc capture"), the empty LINKDATA archive in the game folders no longer stops the shader split, and a host setting (`DM_VK_ZEROCOPY_MAX_MB=512`, `payload/profiles/`) fixes the lead character's model drawing as garbage in the field (a vertex buffer crossing a memory-chunk boundary). | Base game + update 1.2.0 (v327680); Experimental checked; adb connected (Device tab). Runs at 30 fps: the community 60 fps config cannot be used. |

### Asked for, not available yet

| Game | Why | What to do |
|---|---|---|
| Rune Factory: Guardians of Azuma | no game profile upstream or in nxnative (the iOS project upstream is ported from) | Port it with Experimental checked: the porter surveys the game and guesses a profile. Send the log and this app can carry the profile it makes (see below). |

A profile for a new game needs the game itself: its build IDs, shader tables and fixes come from running it on a phone, so they cannot be written without the game files. The route is a few rounds of: port with Experimental, run, send the log. When it plays, the profile is added here (and offered upstream, which wins once it has its own).

## Supported by upstream (46 games)

38 playable, 2 boot, 2 in progress, 4 experimental. Generated from upstream's Android profiles by `tools/make_games_doc.py`; "tested on" is what upstream recorded (game version and device), not a promise for every phone.

| Game | Title ID | Status | Tested on | Needs |
|---|---|---|---|---|
| 13 Sentinels: Aegis Rim | `01003FC01670C000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | BC textures |
| Advance Wars 1+2: Re-Boot Camp | `0100300012F2A000` | playable | v0 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Animal Crossing: New Horizons | `01006F8002326000` | playable | v2228224 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Blasphemous 2 | `010040801A4C8000` | playable | v524288 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Captain Toad: Treasure Tracker | `01009BF0072D4000` | playable | v393216 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Castlevania: Belmont's Curse | `0100BA4026E94000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Celeste | `01002B30028F6000` | playable | v589824 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| DARK SOULS: REMASTERED | `01004AB00A260000` | playable | v196608 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Donkey Kong Country Returns HD | `01009D901BC56000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| FINAL FANTASY RESONANCE | `0100606026F12000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| FINAL FANTASY TACTICS - The Ivalice Chronicles | `010038B015560000` | experimental | - | - |
| FM24 Touch | `01008B101B87A000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Football Manager 26 Touch | `0100D4A023450000` | playable | v131072 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Graveyard Keeper 2 | `0100005027A18000` | playable | v262144 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Hades II | `0100A00019DE0000` | playable | v655360 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Hollow Knight: Silksong | `010013C00E930000` | playable | v655360 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Kirby and the Forgotten Land | `01004D300C5AE000` | playable | v65536 AYN Thor (Snapdragon 8 Gen 2, Adreno 740, Android 13) | BC textures |
| Lonely Mountains: Downhill | `0100A0C00E0DE000` | playable | v0 Retroid Pocket 6 (QCS8550, Adreno 740, Android 13); PurpleVK-public git-62ac221a33 | - |
| Mario vs. Donkey Kong | `0100B99019412000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Metroid Dread | `010093801237C000` | playable | v327680 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| NEO: The World Ends with You | `010043B013C5C000` | playable | v196608 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | BC textures |
| OCTOPATH TRAVELER | `010057D006492000` | boots | v327680 Red Magic Astra NP05J (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| OCTOPATH TRAVELER 0 | `01005270232F2000` | playable | v327680 AYN Thor (Snapdragon 8 Gen 2, Adreno 740, Android 13) | BC textures |
| Paper Mario: The Origami King | `0100A3900C3E2000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Paper Mario: The Thousand-Year Door | `0100ECD018EBE000` | wip | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Picross S＋ | `0100D7B01AE58000` | playable | v65536 Retroid Pocket 6 (Adreno 740, Android 13); PurpleVK-public git-62ac221a33 | - |
| Pokémon Legends: Arceus | `01001F5010DFA000` | playable | v262144 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Pokémon Legends: Z-A | `0100F43008C44000` | playable | v393216 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Pokémon Scarlet | `0100A3D008C5C000` | experimental | 4.0.0 RedMagic NX809J (Adreno 840, Android 16) | BC textures |
| South Park™: The Stick Of Truth™ | `010043600B6A6000` | playable | v0 Xiaomi Pad 5 21051182G (Snapdragon 860, Adreno 640, Android 13) | - |
| Super Mario 3D World + Bowser's Fury | `010028600EBDA000` | playable | v262144 AYN Thor (Snapdragon 8 Gen 2, Adreno 740, Android 13) | BC textures |
| Super Mario Bros. Wonder | `010015100B514000` | playable | v327680 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Super Mario Odyssey | `0100000000010000` | playable | v393216 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Tales of Eternia Remastered | `010006E0230AC000` | playable | v65536 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| The Legend of Zelda: Echoes of Wisdom | `01008CF01BAAC000` | playable | v196608 Retroid Pocket 6 (Adreno 740, PurpleVK) | - |
| The Legend of Zelda: Tears of the Kingdom | `0100F2C0115B6000` | experimental | v720896 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| The World Ends with You -Final Remix- | `0100C1500B82E000` | playable | v0 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Tomodachi Life: Living the Dream | `010051F0207B2000` | playable | v262144 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| UNDER NIGHT IN-BIRTH Exe:Late[cl-r] | `010038C00EC34000` | playable | v131072 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| UNDER NIGHT IN-BIRTH II Sys:Celes | `0100BD401D18A000` | playable | v1179648 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Unicorn Overlord | `010069401ADB8000` | boots | v262144 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | BC textures |
| Unicorn Overlord (Asia) | `010054B01AD92000` | experimental | v262144 Lenovo Legion Y700 TB320FC (Snapdragon 8+ Gen 1, Adreno 730, Vulkan 1.1, Android 15) | BC textures |
| Unpacking | `0100701015846000` | playable | v327680 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Untitled Goose Game | `010082400BCC6000` | playable | v458752 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Viractal | `0100FD501F95A000` | playable | v131072 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |
| Xenoblade Chronicles 3 | `010074F013262000` | wip | v655360 Lenovo Legion Y700 TB322FC (Snapdragon 8 Elite, Adreno 830, Android 16) | - |

Games upstream lists a profile for but not for Android yet (for example Fire Emblem: Three Houses until this app added it) can be tried with *Experimental*; they may not start.
