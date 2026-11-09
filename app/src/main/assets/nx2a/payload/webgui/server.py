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
    if kind in ('port', 'tools', 'install'): need_porter()
    if kind == 'port': need_dotnet()
    with LOCK:
        if JOB['p'] and JOB['p'].poll() is None: return False
        JOB.update(lines=[], done=False, code=None, kind=kind, stage='', frac=None, seq=JOB['seq'] + 1)
        p = subprocess.Popen(argv, cwd=REPO, env=job_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', start_new_session=True)
        JOB['p'] = p

    def pump():
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
        JOB['done'] = True
    threading.Thread(target=pump, daemon=True).start()
    return True


def stage_folder(folder):
    """The porter builds next to the game folder and /sdcard cannot run programs: link the game files into internal storage."""
    p = Path(folder)
    if not str(p).startswith(('/sdcard', '/storage')): return str(p)
    slug = re.sub(r'[^A-Za-z0-9._-]+', '_', p.name) or 'game'
    d = GAMES / slug; d.mkdir(parents=True, exist_ok=True)
    for f in p.iterdir():
        if f.suffix.lower() in GAME_EXT:
            t = d / f.name
            if t.is_symlink() or t.exists(): t.unlink()
            t.symlink_to(f)
    return str(d)


def build_port_args(o):
    a = ['port', stage_folder(o['folder']), '--progress', 'json']
    out = o.get('out') or ('' if cfg().get('out') else DEFAULT_OUT)
    if out: a += ['-o', out]
    if o.get('app_name'): a += ['--app-name', o['app_name']]
    if o.get('language'): a += ['-l', o['language']]
    if o.get('package'): a += ['--package', o['package']]
    for flag in ('touch', 'fps60', 'experimental', 'install', 'replace_signer'):
        if o.get(flag): a.append('--' + flag.replace('_', '-'))
    if o.get('jobs'): a += ['--jobs', str(max(1, int(o['jobs'])))]
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
        if u.path == '/api/summary': return self.j({'running': not JOB['done'], 'kind': JOB['kind'], 'stage': JOB['stage'], 'frac': JOB['frac'], 'code': JOB['code'], 'seq': JOB['seq']})
        if u.path == '/api/job':
            since = int(q.get('since', ['0'])[0])
            return self.j({'lines': JOB['lines'][since:], 'next': len(JOB['lines']), 'done': JOB['done'], 'code': JOB['code']})
        if u.path == '/api/ls':
            p = Path(q.get('path', ['/sdcard'])[0])
            try:
                items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                return self.j({'path': str(p), 'parent': str(p.parent), 'items': [{'n': x.name, 'd': x.is_dir()} for x in items if not x.name.startswith('.')][:500]})
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
        if u.path == '/api/port': return self.j({'started': start_job([sys.executable, '-m', 'porter', *build_port_args(o)], 'port')})
        if u.path == '/api/copydata': return self.j({'started': start_job([sys.executable, str(HERE / 'copydata.py'), o['data']], 'copy')})
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
