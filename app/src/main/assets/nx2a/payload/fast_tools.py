#!/usr/bin/env python3
"""Tool setup, the fast way: a trimmed Android NDK (just what the ARM host build reads, from this repo's 'tools' release) instead of the 1.4 GB official download, then the porter's own downloader for what is still missing (the .NET SDK)."""
import hashlib, json, os, subprocess, sys, urllib.request
from pathlib import Path

D = Path(os.environ.get('NX2A_DIR', '/nx2a'))
ROOT = Path(os.environ.get('NX2A_TOOLS_DIR') or Path.home() / '.config/nx2android/toolchains')
ASSET = 'ndk-lite-r27c.tar.xz'


def have_ndk(): return any((p / 'source.properties').is_file() for p in ROOT.glob('android-ndk-*'))


def seed_ndk():
    repo = json.loads((D / 'update.json').read_text())['repo']
    base = os.environ.get('NX2A_TOOLS_BASE') or f'https://github.com/{repo}/releases/download/tools'
    want = urllib.request.urlopen(f'{base}/{ASSET}.sha256', timeout=30).read().decode().split()[0]
    ROOT.mkdir(parents=True, exist_ok=True)
    dest = ROOT / ASSET; h = hashlib.sha256(); got = 0; last = -1
    print('Android NDK: downloading the trimmed copy...', flush=True)
    with urllib.request.urlopen(f'{base}/{ASSET}', timeout=60) as r, open(dest, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); h.update(b); got += len(b)
            pct = got * 10 // total if total else -1
            if pct != last: last = pct; print(f'  {got / 1e6:.0f} MB' + (f' of {total / 1e6:.0f} MB' if total else ''), flush=True)
    if h.hexdigest() != want: dest.unlink(); raise ValueError('the download does not match its checksum')
    print('Android NDK: unpacking...', flush=True)
    subprocess.run(['tar', '-xJf', str(dest), '-C', str(ROOT)], check=True); dest.unlink()
    print('Android NDK: ready', flush=True)


if not have_ndk():
    try: seed_ndk()
    except Exception as e: print(f'trimmed NDK not available ({e}); using the official download instead', flush=True)
os.execv(sys.executable, [sys.executable, '-m', 'porter', 'tools', '--download', '--progress', 'json'])
