#!/usr/bin/env python3
"""Write docs/SUPPORTED_GAMES.md from a checkout of the upstream porter (shirai91/nx2android): python3 tools/make_games_doc.py <porter checkout>.
The table of upstream's games is generated from its dm/games/*/android.tsv; the games this app adds are listed in ADDED below."""
import glob, os, sys
from pathlib import Path

ADDED = [   # (name, title id, status, what this app adds, what you need)
    ('Fire Emblem: Three Houses', '010055D009F78000', 'experimental',
     'Upstream has the game profile but no Android profile and no way to make its 9 run-time shaders off a Mac. The port runs that step on your phone over adb (payload patch "device glslc capture"), and the empty LINKDATA archive in the game folders no longer stops the shader split.',
     'Base game + update 1.2.0 (v327680); Experimental checked; adb connected (Device tab). Runs at 30 fps: the community 60 fps config cannot be used.'),
]
CANDIDATES = [   # asked for, no profile anywhere yet
    ('Rune Factory: Guardians of Azuma', 'no game profile upstream or in nxnative (the iOS project upstream is ported from)',
     'Port it with Experimental checked: the porter surveys the game and guesses a profile. Send the log and this app can carry the profile it makes (see below).'),
]

def tsv(path):
    d, reqs = {}, []
    for ln in open(path, encoding='utf-8'):
        if ln.startswith('#') or '\t' not in ln: continue
        k, v = ln.rstrip('\n').split('\t', 1)
        if k == 'requires': reqs.append(v)
        else: d.setdefault(k, v)
    return d, reqs

def main(root):
    games = Path(root) / 'nxnative/dm/games'
    rows = []
    for a in sorted(glob.glob(str(games / '*/android.tsv'))):
        d = os.path.dirname(a); g, _ = tsv(d + '/game.tsv'); an, reqs = tsv(a)
        rows.append((g.get('name', os.path.basename(d)), os.path.basename(d), an.get('status', ''), an.get('tested', ''), ', '.join(reqs)))
    rows.sort(key=lambda r: r[0].lower())
    n = {s: sum(1 for r in rows if r[2] == s) for s in ('playable', 'boots', 'wip', 'experimental')}
    out = ['# Games', '',
           'What this app can port. **Upstream first:** a game that upstream (`shirai91/nx2android`) already supports is ported with upstream\'s own profile, untouched. Only when upstream has nothing for a game does this app add its own fix, and each such game is listed below.',
           '', 'You need the game files (base game, plus the update the profile was tested on, plus any DLC) and your own `prod.keys`. The phone\'s GPU must read BC-compressed textures: Adreno and Xclipse do, Mali (this includes MediaTek Dimensity phones) and PowerVR do not, and the games are expected to crash.', '',
           '## Added by this app', '', '| Game | Status | What this app adds | What you need |', '|---|---|---|---|']
    for name, tid, st, what, need in ADDED: out.append(f'| {name} (`{tid}`) | {st} | {what} | {need} |')
    out += ['', '### Asked for, not available yet', '', '| Game | Why | What to do |', '|---|---|---|']
    for name, why, todo in CANDIDATES: out.append(f'| {name} | {why} | {todo} |')
    out += ['', 'A profile for a new game needs the game itself: its build IDs, shader tables and fixes come from running it on a phone, so they cannot be written without the game files. The route is a few rounds of: port with Experimental, run, send the log. When it plays, the profile is added here (and offered upstream, which wins once it has its own).', '',
            f'## Supported by upstream ({len(rows)} games)', '',
            f'{n["playable"]} playable, {n["boots"]} boot, {n["wip"]} in progress, {n["experimental"]} experimental. Generated from upstream\'s Android profiles by `tools/make_games_doc.py`; "tested on" is what upstream recorded (game version and device), not a promise for every phone.', '',
            '| Game | Title ID | Status | Tested on | Needs |', '|---|---|---|---|---|']
    for name, tid, st, tested, req in rows: out.append(f'| {name} | `{tid}` | {st} | {tested or "-"} | {"BC textures" if req == "bcn" else req or "-"} |')
    out += ['', 'Games upstream lists a profile for but not for Android yet (for example Fire Emblem: Three Houses until this app added it) can be tried with *Experimental*; they may not start.', '']
    Path(__file__).resolve().parent.parent.joinpath('docs/SUPPORTED_GAMES.md').write_text('\n'.join(out), encoding='utf-8')

if __name__ == '__main__': main(sys.argv[1])
