#!/usr/bin/env python3
"""Copy a finished game data pack into Android/data/<package>/files without adb. Resumable: files that already match in size are skipped."""
import json, shutil, sys
from pathlib import Path

src = Path(sys.argv[1])
man = src / 'nx2a-data.json'
try: pkg = json.loads(man.read_text())['package']
except Exception as e: sys.exit(f'not a data pack (cannot read nx2a-data.json): {e}')
dst = Path('/sdcard/Android/data') / pkg / 'files'
try: dst.mkdir(parents=True, exist_ok=True)
except OSError as e:
    sys.exit(f'Android does not let this app write to {dst}: {e}\nInstall the APK first (it creates the folder), then try again. If it still fails, this Android version blocks it: use the Device tab (wireless debugging) or a file manager that can write to Android/data.')
files = sorted(p for p in src.rglob('*') if p.is_file() and p != man)
total = sum(p.stat().st_size for p in files); done = 0; last = 0
print(f'copying {len(files)} files, {total / 1e9:.2f} GB to {dst}', flush=True)
for p in files:
    t = dst / p.relative_to(src); n = p.stat().st_size
    try:
        t.parent.mkdir(parents=True, exist_ok=True)
        if not (t.exists() and t.stat().st_size == n): shutil.copyfile(p, t)
    except OSError as e: sys.exit(f'failed on {t}: {e}')
    done += n
    if done - last > 256 * 2**20: last = done; print(f'  {done / total * 100:.0f}%  {done / 1e9:.2f} / {total / 1e9:.2f} GB', flush=True)
shutil.copyfile(man, dst / 'nx2a-data.json')
print('done: data copied. Launch the game from your app drawer.', flush=True)
