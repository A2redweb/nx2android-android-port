"""Remember one wireless-debugging pairing and reconnect by itself.

Pairing is done once (adb keeps the key; the phone keeps it authorised until it is revoked). The connect port changes every time Wireless debugging is switched on,
so after the pairing the app looks for the port itself: the one it used last time first, then the open ports on this phone in the range Android picks from."""
import json, socket, subprocess, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STATE = Path('/root/.config/nx2android/adb.json')
RANGE = (30000, 50000)   # Android picks the wireless-debugging port from this range
BAD = {}                 # port -> when it last refused to be an adb port (not tried again for 10 minutes)


def load():
    try: return json.loads(STATE.read_text())
    except (OSError, ValueError): return {}


def save(**kw):
    s = load(); s.update(kw)
    try: STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(s))
    except OSError: pass


def _adb(env, *a, timeout=15):
    return subprocess.run(['adb', *a], capture_output=True, text=True, timeout=timeout, env=env)


def connected(env):
    """Serials adb lists as ready."""
    try: out = _adb(env, 'devices').stdout
    except (OSError, subprocess.TimeoutExpired): return []
    return [ln.split()[0] for ln in out.splitlines()[1:] if ln.split()[-1:] == ['device']]


def open_ports(lo=RANGE[0], hi=RANGE[1], host='127.0.0.1'):
    def t(p):
        s = socket.socket(); s.settimeout(0.3)
        try: return p if s.connect_ex((host, p)) == 0 else None
        except OSError: return None
        finally: s.close()
    with ThreadPoolExecutor(256) as ex: return [p for p in ex.map(t, range(lo, hi + 1)) if p]


def try_connect(env, hostport):
    try: r = _adb(env, 'connect', hostport, timeout=12)
    except (OSError, subprocess.TimeoutExpired): return False
    txt = (r.stdout + r.stderr).lower()
    return 'connected to' in txt and 'failed' not in txt and 'cannot' not in txt and 'unable' not in txt


def auto(env):
    """Connect to this phone's wireless debugging if it is on. Returns (ok, message)."""
    have = connected(env)
    if have: return True, f'connected: {have[0]}'
    last = load().get('connect')
    if last and try_connect(env, last): return True, f'reconnected: {last}'
    now = time.time(); tried = 0
    for p in open_ports():
        if now - BAD.get(p, 0) < 600: continue
        if tried >= 8: break
        tried += 1; hp = f'127.0.0.1:{p}'
        if try_connect(env, hp): save(connect=hp, paired=True); return True, f'connected: {hp}'
        BAD[p] = now
    return False, ('Wireless debugging was not found. Turn it on (Settings > Developer options > Wireless debugging); '
                   + ('the app connects by itself within a minute.' if load().get('paired') else 'pair once first: the app then reconnects by itself.'))


def loop(env, busy):
    """Background: once a pairing is known, keep the connection (a job in progress is never disturbed)."""
    while True:
        time.sleep(20)
        try:
            st = load()
            if not st.get('paired') or st.get('auto') is False or busy(): continue
            ok, msg = auto(env); save(last=msg)
        except Exception: pass
