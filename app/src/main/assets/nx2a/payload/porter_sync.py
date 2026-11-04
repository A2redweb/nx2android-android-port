#!/usr/bin/env python3
"""Keeps /root/nx2android complete, at the pinned commit and patched. Safe to call often: it only downloads when files are missing or the pinned commit changed.
The old tree is renamed aside before the new one goes in, so a failed step can never leave a half-deleted porter behind."""
import io, json, os, shutil, subprocess, sys, tarfile, time, urllib.request
from pathlib import Path

REPO = Path(os.environ.get('NX2A_REPO', Path.home() / 'nx2android'))
HERE = Path(__file__).resolve().parent
STATUS = Path(os.environ.get('NX2A_STATUS', '/root/patch_status.txt'))
REQUIRED = ['porter/cli.py', 'porter/pipeline.py', 'porter/upstream.py', 'nxnative/dm/android/tools/android_profile.py', 'nxnative/dm/android/build.py',
            'nxnative/dm/android/gfx_vk_core.c', 'nxnative/dm/games/game.py', 'nxnative/dm/tools/nacp.py']


def missing(root=None):
    root = Path(root or REPO)
    return [f for f in REQUIRED if not (root / f).is_file()]


def complete(): return not missing()


def state():
    m = missing()
    return 'ok' if not m else 'incomplete: missing ' + ', '.join(m[:3]) + (' ...' if len(m) > 3 else '')


def _want():
    return json.loads((HERE / 'payload.json').read_text()).get('porter_sha')


def _download(url):
    last = None
    for _ in range(3):
        try: return urllib.request.urlopen(url, timeout=60).read()
        except Exception as e: last = e; time.sleep(2)
    raise last


def patch():
    r = subprocess.run([sys.executable, str(HERE / 'apply_patches.py'), str(REPO)], capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    try: STATUS.write_text(out + f'\nexit {r.returncode}\n')
    except OSError: pass
    return out


def sync(force=False, log=print):
    """Returns (ok, message)."""
    want = _want()
    mark = REPO / '.nx2a_sha'
    try: have = mark.read_text().strip()
    except OSError: have = ''
    if not force and complete() and (not want or have == want):
        patch(); return True, 'porter ready'
    log(f'downloading the porter ({(want or "latest")[:9]})')
    tmp = REPO.with_name(REPO.name + '.new')
    try:
        data = _download(os.environ.get('NX2A_PORTER_URL') or f'https://codeload.github.com/shirai91/nx2android/tar.gz/{want}')
        shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
            t.extractall(tmp, filter='data') if hasattr(tarfile, 'data_filter') else t.extractall(tmp)
        kids = list(tmp.iterdir())
        src = kids[0] if len(kids) == 1 and kids[0].is_dir() else tmp
        bad = missing(src)
        if bad: raise RuntimeError('the download is incomplete, missing ' + ', '.join(bad[:3]))
        (src / '.nx2a_sha').write_text(want or '')
        old = None
        if REPO.exists():
            old = REPO.with_name(f'{REPO.name}.old{int(time.time())}'); REPO.rename(old)
        try: src.rename(REPO)
        except OSError:
            if old is not None: old.rename(REPO)
            raise
        shutil.rmtree(tmp, ignore_errors=True)
        if old is not None: shutil.rmtree(old, ignore_errors=True)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        msg = f'porter download failed: {e}'; log(msg)
        try: STATUS.write_text(msg + '\n')
        except OSError: pass
        return complete(), msg
    patch()
    return True, 'porter downloaded and patched'


if __name__ == '__main__':
    ok, msg = sync(force='--force' in sys.argv); print(msg); sys.exit(0 if ok else 1)
