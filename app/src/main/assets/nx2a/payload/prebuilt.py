#!/usr/bin/env python3
"""The porter's two .NET tools, prebuilt in CI with runtimes that start on phones where the standard .NET runtime does not ("Failed to create CoreCLR").
install() fetches the build that belongs to the porter on this phone, tries each variant with a real start, and keeps the first that works."""
import hashlib, json, os, re, shutil, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prebuilt_key   # noqa: E402

ROOT = Path(os.environ.get('NX2A_PREBUILT_DIR', '/root/prebuilt'))
REPO = Path(os.environ.get('NX2A_REPO', Path.home() / 'nx2android'))
NAME = 'nx-tools-{}.tar.xz'


def key():
    try: return prebuilt_key.compute(REPO)
    except OSError: return ''


def active():
    try: a = json.loads((ROOT / 'active.json').read_text())
    except (OSError, ValueError): return None
    return a if a.get('key') == key() and Path(a.get('dir', '')).is_dir() and Path(a.get('wrapper', '')).is_file() else None


def env():
    a = active()
    return {'NX2A_PREBUILT': a['dir'], 'NX2A_PREBUILT_DOTNET': a['wrapper']} if a else {}


def state():
    a = active()
    return f"active: {a['variant']}" if a else 'not active'


def _base():
    if os.environ.get('NX2A_PREBUILT_BASE'): return os.environ['NX2A_PREBUILT_BASE']
    repo = json.loads((Path(os.environ.get('NX2A_DIR', '/nx2a')) / 'update.json').read_text())['repo']
    return f'https://github.com/{repo}/releases/download/prebuilt'


def _smoke(d):
    """Starts both tools for real. Returns (ok, detail)."""
    env_ = dict(os.environ, DOTNET_SYSTEM_GLOBALIZATION_INVARIANT='1')
    try:
        r = subprocess.run([str(d / 'dmsh_xlate' / 'dmsh_xlate'), '--source-sha'], capture_output=True, text=True, timeout=120, env=env_)
        if r.returncode != 0 or not re.match(r'^[0-9a-f]{16}', r.stdout.strip()): return False, f'translator: exit {r.returncode} {(r.stdout + r.stderr).strip()[:160]}'
        r = subprocess.run([str(d / 'nx_extract' / 'nx_extract')], capture_output=True, text=True, timeout=120, env=env_)
        if 'usage' not in (r.stdout + r.stderr).lower(): return False, f'extractor: exit {r.returncode} {(r.stdout + r.stderr).strip()[:160]}'
    except (OSError, subprocess.TimeoutExpired) as e: return False, str(e)
    return True, 'both tools start'


def _fetch(base, name, d):
    want = urllib.request.urlopen(f'{base}/{name}.sha256', timeout=30).read().decode().split()[0]
    ROOT.mkdir(parents=True, exist_ok=True)
    tgz = ROOT / name; h = hashlib.sha256()
    with urllib.request.urlopen(f'{base}/{name}', timeout=120) as r, open(tgz, 'wb') as f:
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); h.update(b)
    if h.hexdigest() != want: tgz.unlink(); raise ValueError('the download does not match its checksum')
    tmp = ROOT / (d.name + '.tmp'); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    subprocess.run(['tar', '-xJf', str(tgz), '-C', str(tmp)], check=True); tgz.unlink()
    shutil.rmtree(d, ignore_errors=True); tmp.rename(d)


def install():
    """Returns report lines."""
    k = key()
    if not k: return ['the porter is not installed yet']
    out = []
    d = ROOT / k
    if not (d / 'manifest.json').is_file():
        base = _base(); errs = []
        for how in ('exact', 'latest'):
            try:
                if how == 'exact': name = NAME.format(k)
                else: name = json.loads(urllib.request.urlopen(f'{base}/latest.json', timeout=30).read().decode())['file']
                _fetch(base, name, d)
                out.append(f'downloaded the ready-made tools ({"built for this porter" if how == "exact" else "newest build; none was made for porter sources " + k})')
                break
            except Exception as e: errs.append(f'{how}: {e}')
        else: return [f'ready-made tools not available ({"; ".join(errs)}). They are built in the cloud every 6 hours; try again later.']
    manifest = json.loads((d / 'manifest.json').read_text())
    for v in manifest.get('variants', []):
        ok, detail = _smoke(d / v)
        out.append(f'{v}: {"works" if ok else "does not start"} ({detail})')
        if ok:
            wrapper = ROOT / 'dotnet-wrapper.sh'
            wrapper.write_text(f'#!/bin/sh\n# stands in for `dotnet <dmsh_xlate.dll> <args>`: runs the prebuilt translator directly\nshift\nexec "{d / v / "dmsh_xlate" / "dmsh_xlate"}" "$@"\n')
            wrapper.chmod(0o755)
            (ROOT / 'active.json').write_text(json.dumps({'key': k, 'variant': v, 'dir': str(d / v), 'wrapper': str(wrapper)}))
            out.append(f'using: {v}')
            return out
    try: (ROOT / 'active.json').unlink()
    except OSError: pass
    out.append('no prebuilt variant starts on this phone')
    return out


if __name__ == '__main__': print('\n'.join(install()))
