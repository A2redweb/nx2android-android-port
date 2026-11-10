#!/usr/bin/env python3
"""nx2android phone GUI: a local web app (stdlib only) that drives `python -m porter`. Only the app itself can use it: a random token, a Host check and a same-site cookie guard every request."""
import contextlib, glob, hmac, http.cookies, io, json, os, re, signal, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).parent


def reset_signals():
    """Android's Java process leaves some signals blocked or ignored, and children inherit that. Termux clears them before starting a shell; programs such as
    the .NET runtime assume a normal Unix process. Everything started from here (including every job) inherits the clean state."""
    try:
        signal.pthread_sigmask(signal.SIG_UNBLOCK, signal.valid_signals())
        for s in signal.valid_signals():
            if s in (signal.SIGKILL, signal.SIGSTOP, signal.SIGPIPE): continue
            try:
                if signal.getsignal(s) == signal.SIG_IGN: signal.signal(s, signal.SIG_DFL)
            except (OSError, ValueError, RuntimeError): pass
    except Exception: pass


def sig_state():
    try: return {k: v for k, v in (l.split(':\t', 1) for l in Path('/proc/self/status').read_text().splitlines() if ':\t' in l) if k in ('SigBlk', 'SigIgn', 'SigCgt', 'Seccomp', 'NoNewPrivs')}
    except OSError: return {}


SIG_BEFORE = sig_state()
reset_signals()
os.umask(0o022)
sys.path.insert(0, str(HERE.parent))
import porter_sync   # noqa: E402
import dotnet_probe   # noqa: E402
import prebuilt   # noqa: E402
import server_state   # noqa: E402
server_state.set_before(SIG_BEFORE)
REPO = Path(os.environ.get('NX2A_REPO', Path.home() / 'nx2android'))
PORT = int(os.environ.get('NX2A_PORT', '7331'))
TOKEN = os.environ.get('NX2A_TOKEN', '')
VERSION = os.environ.get('NX2A_VERSION', '0')
HOSTS = {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}
ENV = {k: v for k, v in os.environ.items() if k != 'NX2A_TOKEN'}
ENV.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', DOTNET_EnableWriteXorExecute='0', DOTNET_SYSTEM_GLOBALIZATION_INVARIANT='1')
CFG = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'nx2android' / 'config.json'
GAMES = Path(os.environ.get('NX2A_GAMES', '/root/games'))
OTA = Path(os.environ.get('NX2A_OTA', '/root/ota'))
STATUS = Path(os.environ.get('NX2A_STATUS', '/root/patch_status.txt'))
DEFAULT_OUT = '/sdcard/Switch/Ports'
GAME_EXT = ('.nsp', '.xci', '.nsz', '.xcz')
JOB = {'p': None, 'lines': [], 'done': True, 'code': None, 'kind': '', 'stage': '', 'frac': None, 'seq': 0}
LOCK = threading.Lock()


def cfg():
    try: return json.loads(CFG.read_text())
    except (OSError, ValueError): return {}


def job_env():
    """The base environment plus the .NET workaround the probe found, if any."""
    e = dict(ENV)
    e.update(prebuilt.env())   # the CI-built .NET tools, when they are installed and start
    return e


UPD = {'t': 0, 'msg': 'not checked yet'}


def check_update():
    """Same download-and-verify as the launcher's, so the banner appears without restarting the app."""
    try:
        sys.path.insert(0, os.environ.get('NX2A_DIR', '/nx2a'))
        import launcher
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): got = launcher.update()
        UPD.update(t=time.time(), msg=(buf.getvalue().strip().splitlines() or ['up to date'])[-1])
        return got
    except Exception as e:
        UPD.update(t=time.time(), msg=f'update check failed: {e}'); return False


def auto_porter():
    """Follows upstream's newest commit, but never swaps the porter while a job is running."""
    time.sleep(60)
    while True:
        try:
            if JOB['done']: porter_sync.sync()
        except Exception as e: print('porter follow failed:', e, flush=True)
        time.sleep(6 * 3600)


def auto_update():
    time.sleep(20)
    while True:
        check_update(); time.sleep(300)


def need_prebuilt():
    """The .NET tools built in the cloud with runtimes that start on this phone. Returns True when they are active."""
    try:
        if prebuilt.active(): return True
        prebuilt.install()
        return bool(prebuilt.active())
    except Exception as e: print('prebuilt tools failed:', e, flush=True); return False


def need_dotnet():
    need_prebuilt()   # the standard .NET runtime does not start under proot on these phones; only the ready-made tools are used


def need_porter():
    try:
        if not porter_sync.complete(): porter_sync.sync()
    except Exception as e: print('porter sync failed:', e, flush=True)


def porter(*args, timeout=120):
    need_porter()
    r = subprocess.run([sys.executable, '-m', 'porter', *args], cwd=REPO, env=job_env(), capture_output=True, text=True, timeout=timeout)
    return r.stdout, r.stderr, r.returncode


def start_job(argv, kind=''):
    """Returns at once: the preparation (porter sources, ready-made .NET tools: downloads that can take minutes) runs in the job's own thread, so the screen never waits on it."""
    with LOCK:
        if (JOB['p'] and JOB['p'].poll() is None) or JOB.get('starting'): return False
        JOB.update(lines=[], done=False, code=None, kind=kind, stage='preparing', frac=None, seq=JOB['seq'] + 1, starting=True)

    def run():
        try:
            if kind in ('port', 'tools', 'install'):
                JOB['lines'].append('preparing: the porter...'); need_porter()
            if kind in ('port', 'tools'):
                JOB['lines'].append('preparing: the .NET tools...'); need_dotnet()   # the ready-made tools first: with them active the porter does not download the 1.5 GB .NET SDK
            p = subprocess.Popen(argv, cwd=REPO, env=job_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', start_new_session=True)
        except Exception as e:
            JOB['lines'].append(f'could not start: {e}'); JOB['code'] = 1; JOB['starting'] = False; JOB['done'] = True; return
        JOB['p'] = p; JOB['starting'] = False
        pump(p)

    def pump(p):
        for ln in p.stdout:
            ln = ln.rstrip('\n'); JOB['lines'].append(ln)
            try:
                if ln.startswith('{'):
                    ev = json.loads(ln)
                    if ev.get('ev') == 'stage': JOB['stage'] = f"{ev.get('k')}/{ev.get('n')} {ev.get('name')}"; JOB['frac'] = None
                    elif ev.get('ev') == 'progress' and ev.get('frac') is not None: JOB['frac'] = ev['frac']
                elif ln.strip(): JOB['stage'] = ln.strip()[:70]
            except ValueError: pass
        JOB['code'] = p.wait()
        if JOB['kind'] == 'tools' and JOB['code'] == 0:     # check right away that .NET starts on this phone
            try:
                JOB['lines'].append('ready-made .NET tools:'); JOB['lines'].extend('  ' + l for l in prebuilt.install())
            except Exception as e: JOB['lines'].append(f'.NET check failed: {e}')
        if JOB['kind'] == 'port':
            try:
                txt = '\n'.join(l for l in JOB['lines'] if l.startswith('{"ev": "say"'))
                if JOB.get('fps60') and JOB['code'] == 0 and ('keeps its own frame rate' in txt or 'cannot be applied' in txt):
                    JOB['lines'].append('NOTE: 60 fps was NOT applied to this port: there is no community 60 fps config (FPSLocker-Warehouse) for this exact game version, or it could not be used. The game keeps its own frame rate (see the "60 fps" line above).')
                if ('Oodle' in txt or 'GLSLC' in txt) and JOB['code'] != 0 and ('to push' in txt or 'exit 139' in '\n'.join(JOB['lines'])):
                    JOB['lines'].append('HINT: adb is connected (the game was sent to the phone) but the game crashed there. Send the last lines above. If a line says "[RED] main build ... is not the tested ..." the port used a game version the profile has no fixes for: put the game\'s update NSP (the version named after "tested on") in the same folder as the base game and port again.')
                elif ('Oodle' in txt or 'GLSLC' in txt) and JOB['code'] != 0:
                    JOB['lines'].append('HINT: this game\'s shaders need a device connected over adb. Device tab: pair (Settings > Developer options > Wireless debugging > Pair with code), connect, List devices; then port again.')
            except Exception: pass
        if JOB['kind'] == 'port' and JOB['code'] == 0 and not JOB.get('keep'):
            try:
                res = next((json.loads(l) for l in reversed(JOB['lines']) if l.startswith('{"ev": "result"')), {})
                freed = clean_work((res.get('apk'), res.get('data')))
                JOB['lines'].append(f'Deleted the working files: {freed / 1e9:.1f} GB of the phone storage used by the app is free again. The APK and data are in the output folder.')
            except Exception as e: JOB['lines'].append(f'Could not delete the working files: {e}')
        JOB['done'] = True
    threading.Thread(target=run, daemon=True).start()
    return True


def rm_tree(p):
    """rmtree that also removes read-only files and folders (game extractions often are): the owner may delete them once it makes them writable. Returns the first error or ''."""
    import shutil, stat
    errs = []
    def fix(func, path, exc_info):
        try:
            os.chmod(os.path.dirname(path) or '.', 0o700); os.chmod(path, 0o700) if not os.path.islink(path) else None
            func(path)
        except OSError as e: errs.append(f'{path}: {e}')
    shutil.rmtree(p, onerror=fix)
    return errs[0] if errs else ''


def build_dirs():
    return [d for d in GAMES.glob('*/*_build') if d.is_dir() and not d.is_symlink()]


def dir_size(d):
    n = 0
    for root, _, files in os.walk(d):
        for f in files:
            try: n += os.lstat(os.path.join(root, f)).st_size
            except OSError: pass
    return n


def clean_work(keep_paths=()):
    """Delete the porter's working folders (extracted game, shader work, the copy the APK is built from). The finished APK and data are in the output folder; these only
    take space, and only this app can delete them (they sit in its private storage). Returns the bytes freed."""
    import shutil
    freed = 0
    for d in build_dirs():
        if any(str(k).startswith(str(d) + os.sep) for k in keep_paths if k): continue   # the output sits inside it: leave it alone
        freed += dir_size(d); rm_tree(d)
    return freed


PROTECTED = None


def remove_paths(paths):
    """Delete files and folders chosen in the file manager. Only under the private storage (/root), the internal storage (/sdcard) and SD cards (/storage/<id>); never the
    storage roots, the porter, the tools or the app's own settings. A symlink is removed itself, never what it points to. Returns [(path, 'ok' | error)]."""
    import shutil
    global PROTECTED
    if PROTECTED is None:
        PROTECTED = {Path(x) for x in ('/', '/root', '/sdcard', '/storage', '/root/.config', '/root/games', '/root/prebuilt', '/root/.config/nx2android', '/nx2a')} | {REPO, REPO.parent}
    out = []
    for raw in paths:
        p = Path(os.path.abspath(str(raw)))   # tidies .. and double slashes, does not follow a final symlink
        s = str(p)
        if not s.startswith(('/root/', '/sdcard/', '/storage/')) or p in PROTECTED or (s.startswith('/storage/') and (len(p.parts) < 4 or s.startswith(('/storage/emulated/0/Android', '/storage/self')) and len(p.parts) < 5)) or s in ('/storage/emulated/0', '/storage/emulated/legacy'):
            out.append((s, 'not allowed')); continue
        if any(p == q or q in p.parents for q in (REPO, Path('/root/prebuilt'), Path('/root/.config/nx2android'))):
            out.append((s, 'part of the app: use Update / repair instead')); continue
        try:
            if p.is_symlink() or p.is_file(): p.unlink()
            elif p.is_dir():
                err = rm_tree(p)
                if err: out.append((s, err)); continue
            else: out.append((s, 'not found')); continue
            out.append((s, 'ok'))
        except OSError as e: out.append((s, str(e)))
    return out


def stage_folder(folder):
    """The porter builds next to the game folder and /sdcard cannot run programs: link the game files into internal storage."""
    p = Path(folder)
    if not str(p).startswith(('/sdcard', '/storage')): return str(p)
    slug = re.sub(r'[^A-Za-z0-9._-]+', '_', p.name) or 'game'
    d = GAMES / slug; d.mkdir(parents=True, exist_ok=True)
    for old in d.iterdir():   # links left by an earlier port of this folder: the game files may have been moved or deleted since, and a dangling link crashes the porter
        if old.is_symlink() and old.suffix.lower() in GAME_EXT: old.unlink()
    for f in p.iterdir():
        if f.suffix.lower() in GAME_EXT:
            t = d / f.name
            if t.is_symlink() or t.exists(): t.unlink()
            t.symlink_to(f)
    return str(d)


def stage_driver(path):
    """A custom Vulkan driver (Turnip and the like) for --vulkan-driver: a .so, or a .zip that holds one. Copied to internal storage; checked to be an arm64 ELF library."""
    import shutil, zipfile
    p = Path(path.strip()).expanduser()
    if not p.is_file(): raise ValueError(f'driver not found: {p}')
    d = GAMES / '_drivers'; d.mkdir(parents=True, exist_ok=True)
    if p.suffix.lower() == '.zip':
        with zipfile.ZipFile(p) as z:
            names = [n for n in z.namelist() if n.lower().endswith('.so') and not n.endswith('/')]
            if not names: raise ValueError(f'{p.name}: no .so library inside the zip')
            if len(names) > 1: raise ValueError(f'{p.name}: more than one .so inside ({", ".join(Path(n).name for n in names[:4])}); extract the driver and pick the .so')
            out = d / Path(names[0]).name
            with z.open(names[0]) as r, open(out, 'wb') as f: shutil.copyfileobj(r, f)
    elif p.suffix.lower() == '.so':
        out = d / p.name; shutil.copyfile(p, out)
    else: raise ValueError('the driver must be a .so file (or a .zip that holds one)')
    h = out.read_bytes()[:20]
    if h[:4] != b'\x7fELF' or h[4] != 2 or int.from_bytes(h[18:20], 'little') != 183:
        out.unlink(); raise ValueError(f'{out.name} is not an arm64 (64-bit ARM) library')
    return str(out)


def check_game_folder(folder):
    folder = (folder or '').strip()
    if not folder: raise ValueError('Choose the game folder first (Port tab, Browse).')
    p = Path(folder)
    if not p.is_dir():
        hint = ' The SD card needs the newest APK (Releases, latest) so the app can see it.' if folder.startswith('/storage/') and not folder.startswith('/storage/emulated') else ''
        raise ValueError(f'Folder not found: {folder}.{hint}')
    if not any(f.suffix.lower() in GAME_EXT for f in p.iterdir() if f.is_file() or f.is_symlink()):
        raise ValueError(f'No game files (.nsp .xci .nsz .xcz) directly inside {folder}. Pick the folder that holds them, not a folder above it.')
    return folder


def build_port_args(o):
    o = dict(o, folder=check_game_folder(o.get('folder')))
    a = ['port', stage_folder(o['folder']), '--progress', 'json']
    out = o.get('out') or ('' if cfg().get('out') else DEFAULT_OUT)
    if out: a += ['-o', out]
    if o.get('app_name'): a += ['--app-name', o['app_name']]
    if o.get('language'): a += ['-l', o['language']]
    if o.get('package'): a += ['--package', o['package']]
    for flag in ('touch', 'fps60', 'experimental', 'install', 'replace_signer'):
        if o.get(flag): a.append('--' + flag.replace('_', '-'))
    if o.get('jobs'): a += ['--jobs', str(max(1, int(o['jobs'])))]
    if (o.get('vulkan_driver') or '').strip(): a += ['--vulkan-driver', stage_driver(o['vulkan_driver'])]
    return a


def last_build_log():
    """The newest build log of a port that just ran: what failed is in there, the job output only says which stage."""
    best = None
    for pat in (str(GAMES / '*' / '*_build' / 'logs' / '*.log'), '/sdcard/Switch/**/*_build/logs/*.log'):
        for f in glob.glob(pat, recursive=True):
            try: m = os.path.getmtime(f)
            except OSError: continue
            if not best or m > best[0]: best = (m, f)
    if not best or time.time() - best[0] > 900: return {}
    lines = Path(best[1]).read_text(errors='replace').splitlines()[-60:]
    return {'file': best[1], 'tail': '\n'.join(l[:300] for l in lines)}


def ver(d):
    try: return int(json.loads((d / 'payload.json').read_text())['version'])
    except Exception: return -1


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, body, ctype='application/json', code=200, headers=None):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header('Content-Type', ctype + '; charset=utf-8'); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def j(self, obj, code=200): self.send(json.dumps(obj), code=code)

    def gate(self, path, q, post=False):
        if self.headers.get('Host', '') not in HOSTS: self.send('bad host', 'text/plain', 403); return False
        origin = self.headers.get('Origin')
        if post and origin and urlparse(origin).netloc not in HOSTS: self.send('bad origin', 'text/plain', 403); return False
        if not TOKEN: return True
        try:
            ck = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
            if 'nx2a' in ck and hmac.compare_digest(ck['nx2a'].value, TOKEN): return True
            if path == '/' and hmac.compare_digest(q.get('t', [''])[0], TOKEN): self.set_cookie = True; return True
        except (TypeError, http.cookies.CookieError): pass
        self.send('forbidden', 'text/plain', 403); return False

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        self.set_cookie = False
        if not self.gate(u.path, q): return
        if u.path == '/':
            return self.send((HERE / 'index.html').read_bytes(), 'text/html', headers={'Set-Cookie': f'nx2a={TOKEN}; Path=/; HttpOnly; SameSite=Strict'} if self.set_cookie else None)
        if u.path == '/api/status':
            try: pat = STATUS.read_text()[-400:]
            except OSError: pat = ''
            return self.j({'version': VERSION, 'ota': ver(OTA), 'update_ready': ver(OTA) > int(VERSION or 0), 'patches': pat, 'porter': porter_sync.state(), 'porter_commit': porter_sync.commit(), 'update_msg': UPD['msg']})
        if u.path == '/api/doctor':
            out, err, code = porter('doctor', '--json')
            try: return self.j({'checks': json.loads(out)})
            except ValueError: return self.j({'error': (err or out)[-600:]})
        if u.path == '/api/config': return self.j(cfg())
        if u.path == '/api/lastlog': return self.j(last_build_log())
        if u.path == '/api/work': return self.j({'bytes': sum(dir_size(d) for d in build_dirs()), 'dirs': [d.name for d in build_dirs()]})
        if u.path == '/api/summary': return self.j({'running': not JOB['done'], 'kind': JOB['kind'], 'stage': JOB['stage'], 'frac': JOB['frac'], 'code': JOB['code'], 'seq': JOB['seq']})
        if u.path == '/api/job':
            since = int(q.get('since', ['0'])[0])
            return self.j({'lines': JOB['lines'][since:], 'next': len(JOB['lines']), 'done': JOB['done'], 'code': JOB['code']})
        if u.path == '/api/ls':
            p = Path(q.get('path', ['/sdcard'])[0])
            try:
                items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                return self.j({'path': str(p), 'parent': str(p.parent), 'items': [{'n': x.name, 'd': x.is_dir(), 's': (x.lstat().st_size if x.is_file() and not x.is_symlink() else None), 'l': x.is_symlink()} for x in items if not x.name.startswith('.') or q.get('hidden')][:1000]})
            except OSError as e: return self.j({'path': str(p), 'parent': str(p.parent), 'items': [], 'error': str(e)})
        if u.path == '/api/devices':
            out, err, _ = porter('devices', '--json')
            try: return self.j({'devices': json.loads(out)})
            except ValueError: return self.j({'devices': [], 'error': (err or out)[-300:]})
        self.send('not found', 'text/plain', 404)

    def do_POST(self):
        u = urlparse(self.path); q = {}
        if not self.gate(u.path, q, post=True): return
        n = int(self.headers.get('Content-Length') or 0)
        try: o = json.loads(self.rfile.read(n) or b'{}')
        except ValueError: return self.j({'error': 'bad json'}, 400)
        if u.path == '/api/config':
            if o.get('key') not in ('keys', 'out'): return self.j({'ok': False, 'msg': 'unknown setting'})
            out, err, c = porter('config', o['key'], o['value']); return self.j({'ok': c == 0, 'msg': (err or out)[-300:]})
        if u.path == '/api/tools': return self.j({'started': start_job([sys.executable, str(HERE.parent / 'fast_tools.py')], 'tools')})
        if u.path == '/api/inspect':
            out, err, c = porter('inspect', stage_folder(o['folder']), '--json')
            try: return self.j(json.loads(out))
            except ValueError: return self.j({'error': (err or out)[-600:]})
        if u.path == '/api/port':
            try: args = build_port_args(o)
            except (ValueError, OSError, Exception) as e: return self.j({'started': False, 'error': str(e)})
            JOB['keep'] = bool(o.get('keep_work')); JOB['fps60'] = bool(o.get('fps60'))
            return self.j({'started': start_job([sys.executable, '-m', 'porter', *args], 'port')})
        if u.path == '/api/install':
            a = ['install', o['data'], '--progress', 'json'] + (['--replace-signer'] if o.get('replace_signer') else [])
            return self.j({'started': start_job([sys.executable, '-m', 'porter', *a], 'install')})
        if u.path == '/api/adb':   # wireless debugging to this same phone (optional)
            if o.get('op') not in ('pair', 'connect', 'disconnect'): return self.j({'out': 'bad operation'})
            cmd = ['adb', o['op'], str(o['host'])] + ([str(o['code'])] if o['op'] == 'pair' and o.get('code') else [])
            try: r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=ENV); return self.j({'out': (r.stdout + r.stderr).strip()})
            except (OSError, subprocess.TimeoutExpired) as e: return self.j({'out': str(e)})
        if u.path == '/api/cancel':
            p = JOB['p']
            if p and p.poll() is None: os.killpg(p.pid, signal.SIGKILL)
            return self.j({'ok': True})
        if u.path == '/api/checkupdate':
            got = check_update(); return self.j({'ready': got or ver(OTA) > int(VERSION or 0), 'msg': UPD['msg']})
        if u.path == '/api/expfile':
            t = Path('/sdcard/Switch/nx2android-proot-experiments.txt')
            try: return self.j({'path': str(t), 'age': int(time.time() - t.stat().st_mtime), 'text': t.read_text(errors='replace')})
            except OSError: return self.j({})
        if u.path == '/api/tracefile':
            t = Path('/sdcard/Switch/nx2android-proot-trace.txt')
            try: return self.j({'path': str(t), 'age': int(time.time() - t.stat().st_mtime), 'tail': '\n'.join(t.read_text(errors='replace').splitlines()[-90:])})
            except OSError: return self.j({})
        if u.path == '/api/dotnet':
            rep = dotnet_probe.full_report()
            try: Path('/sdcard/Switch').mkdir(parents=True, exist_ok=True); Path('/sdcard/Switch/nx2android-dotnet-report.txt').write_text('\n'.join(rep))
            except OSError: pass
            return self.j({'report': rep, 'saved': dotnet_probe.saved()})
        if u.path == '/api/rm':
            if (JOB['p'] and JOB['p'].poll() is None) or JOB.get('starting'): return self.j({'error': 'a job is running: wait for it to finish'})
            return self.j({'results': remove_paths(o.get('paths') or [])})
        if u.path == '/api/clean':
            if (JOB['p'] and JOB['p'].poll() is None) or JOB.get('starting'): return self.j({'error': 'a job is running'})
            return self.j({'freed': clean_work()})
        if u.path == '/api/prebuilt':
            need_porter(); rep = prebuilt.install()
            try: Path('/sdcard/Switch').mkdir(parents=True, exist_ok=True); Path('/sdcard/Switch/nx2android-prebuilt-report.txt').write_text('\n'.join(rep))
            except OSError: pass
            return self.j({'report': rep, 'state': prebuilt.state()})
        if u.path == '/api/repair':
            ok, msg = porter_sync.sync(force=True); return self.j({'ok': ok, 'msg': msg, 'porter': porter_sync.state()})
        if u.path == '/api/restart':
            threading.Timer(0.5, lambda: os._exit(75)).start(); return self.j({'ok': True})
        self.send('not found', 'text/plain', 404)


if __name__ == '__main__':
    need_porter()
    threading.Thread(target=auto_update, daemon=True).start()
    threading.Thread(target=auto_porter, daemon=True).start()
    print(f'nx2android GUI {VERSION} on 127.0.0.1:{PORT} (porter: {REPO})', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
