#!/usr/bin/env python3
"""The .NET runtime can fail to start under proot ("Failed to create CoreCLR, HRESULT: 0x8007054F", usually killed right after). This module
1) tests the system features the runtime needs at start-up, 2) tries known workarounds with `dotnet --version`, remembers the first that works,
3) writes a report that says what failed."""
import json, os, shutil, subprocess, sys
from pathlib import Path

DOTNET = Path(os.environ.get('NX2A_TOOLS_DIR') or Path.home() / '.config/nx2android/toolchains') / 'dotnet' / 'dotnet'
SAVED = Path(os.environ.get('NX2A_DOTNET_ENV', '/root/dotnet_env.json'))
SHIM = Path(os.environ.get('NX2A_SHIM', '/root/nxshim.so'))
BASE = {'DOTNET_EnableWriteXorExecute': '0', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1',
        'DOTNET_NOLOGO': '1', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1'}
HEAP = {'DOTNET_GCHeapHardLimit': '0x80000000'}
SEG = {'DOTNET_GCName': 'libclrgc.so'}
SHIM_C = r'''#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdarg.h>
#include <stddef.h>
/* Start-up helpers for the .NET runtime on phones: it asks the kernel for membarrier, and falls back to mlock; both can be refused. */
int mlock(const void *a, size_t l) { return 0; }
int mlock2(const void *a, size_t l, unsigned int f) { return 0; }
int munlock(const void *a, size_t l) { return 0; }
long syscall(long n, ...) {
    va_list ap; va_start(ap, n);
    long a1 = va_arg(ap, long), a2 = va_arg(ap, long), a3 = va_arg(ap, long), a4 = va_arg(ap, long), a5 = va_arg(ap, long), a6 = va_arg(ap, long);
    va_end(ap);
    if (n == 283) { errno = ENOSYS; return -1; }   /* membarrier: report it as missing, the runtime then uses the mlock path */
    static long (*real)(long, ...);
    if (!real) real = (long (*)(long, ...))dlsym(RTLD_NEXT, "syscall");
    return real(n, a1, a2, a3, a4, a5, a6);
}
'''


def find_dotnet(): return DOTNET if DOTNET.is_file() else None


def saved():
    try: return json.loads(SAVED.read_text())
    except (OSError, ValueError): return None


def build_shim():
    if SHIM.is_file(): return str(SHIM)
    cc = shutil.which('clang') or shutil.which('gcc') or shutil.which('cc')
    if not cc: return None
    src = SHIM.with_suffix('.c'); src.write_text(SHIM_C)
    r = subprocess.run([cc, '-shared', '-fPIC', '-O1', '-o', str(SHIM), str(src), '-ldl'], capture_output=True, text=True)
    return str(SHIM) if r.returncode == 0 and SHIM.is_file() else None


def variants():
    v = [('default', {}), ('smaller GC heap', HEAP), ('segment GC', SEG), ('segment GC, smaller heap', {**SEG, **HEAP}),
         ('W^X on', {'DOTNET_EnableWriteXorExecute': '1'})]
    s = build_shim()
    if s:
        v[1:1] = [('start-up shim', {'LD_PRELOAD': s})]
        v += [('shim + smaller GC heap', {'LD_PRELOAD': s, **HEAP}), ('shim + segment GC + smaller heap', {'LD_PRELOAD': s, **SEG, **HEAP}),
              ('shim + W^X on', {'LD_PRELOAD': s, 'DOTNET_EnableWriteXorExecute': '1'}),
              ('shim + no background GC', {'LD_PRELOAD': s, 'DOTNET_gcConcurrent': '0', **HEAP})]
    return v


def try_variant(extra, trace=False):
    env = dict(os.environ); env.update(BASE); env.update(extra)
    if trace: env.update(COREHOST_TRACE='1', COREHOST_TRACE_VERBOSITY='3')
    try: r = subprocess.run([str(DOTNET), '--version'], env=env, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired: return 'timeout', ''
    except OSError as e: return 'error', str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def tune(force=False):
    """Returns report lines. Keeps the saved setting while it still works."""
    if not find_dotnet(): return ['the .NET SDK is not installed yet (Setup, Download missing tools)']
    report = []
    cur = saved()
    if cur is not None and not force:
        rc, out = try_variant(cur)
        if rc == 0: return [f'.NET works with the saved setting {cur or "(default)"}']
        report.append('the saved setting no longer works, trying again')
    for name, extra in variants():
        rc, out = try_variant(extra)
        first = out.splitlines()[0][:90] if out else ''
        report.append(f'{name}: exit {rc}' + (f' ({first})' if first else ''))
        if rc == 0:
            SAVED.write_text(json.dumps(extra)); report.append(f'using: {name}'); return report
    try: SAVED.unlink()
    except OSError: pass
    report.append('no variant worked')
    return report


def system_report():
    import ctypes, errno, fcntl, mmap, resource, threading
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.mlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    libc.syscall.restype = ctypes.c_long
    FAILED = ctypes.c_void_p(-1).value
    out = []

    def row(name, ok, detail=''): out.append(('PASS  ' if ok else 'FAIL  ') + name + (f'  ({detail})' if detail else ''))
    def err(): return os.strerror(ctypes.get_errno())
    def anon(size, prot, flags=0x22):
        ctypes.set_errno(0); return libc.mmap(None, size, prot, flags, -1, 0)

    try:
        st = {k: v.strip() for k, v in (l.split(':\t', 1) for l in Path('/proc/self/status').read_text().splitlines() if ':\t' in l)}
        out.append('process signals: blocked ' + st.get('SigBlk', '?') + ', ignored ' + st.get('SigIgn', '?') + ' | seccomp ' + st.get('Seccomp', '?') + ', no_new_privs ' + st.get('NoNewPrivs', '?'))
    except OSError: pass
    try:
        import server_state
        out.append('signals when the GUI started: ' + str(server_state.before()))
    except Exception: pass
    u = os.uname(); out.append(f'kernel {u.release} {u.machine} | uid {os.geteuid()} | python {sys.version.split()[0]}')
    for n in ('MEMLOCK', 'AS', 'NPROC', 'STACK', 'NOFILE'):
        s, h = resource.getrlimit(getattr(resource, 'RLIMIT_' + n)); f = lambda x: 'unlimited' if x == resource.RLIM_INFINITY else str(x)
        out.append(f'limit {n}: soft {f(s)} hard {f(h)}')
    for f in ('/proc/sys/vm/overcommit_memory', '/proc/sys/vm/max_map_count'):
        try: out.append(f'{f} = {Path(f).read_text().strip()}')
        except OSError as e: out.append(f'{f}: unreadable ({e.strerror})')
    p = anon(4096, 3)
    if p != FAILED:
        ctypes.set_errno(0); r = libc.mlock(p, 4096); row('mlock one page (the runtime needs it when membarrier is refused)', r == 0, err() if r else '')
    else: row('map one page', False, err())
    ctypes.set_errno(0); q = libc.syscall(283, 0, 0); row('membarrier query', q >= 0, f'mask {q:#x}' if q >= 0 else err())
    if q >= 0:
        ctypes.set_errno(0); r = libc.syscall(283, 16, 0); row('membarrier register private expedited', r == 0, err() if r else '')
        ctypes.set_errno(0); r = libc.syscall(283, 8, 0); row('membarrier private expedited', r == 0, err() if r else '')
    for gb in (1, 16, 256, 1024):
        p = anon(gb << 30, 0, 0x22 | 0x4000); row(f'reserve {gb} GB of address space', p != FAILED, err() if p == FAILED else '')
        if p != FAILED: libc.munmap(p, gb << 30)
    p = anon(65536, 7); row('map memory read+write+execute', p != FAILED, err() if p == FAILED else '')
    p = anon(4096, 3)
    if p != FAILED:
        ctypes.set_errno(0); r = libc.mprotect(p, 4096, 5); row('mprotect read+write to read+execute', r == 0, err() if r else '')
    ctypes.set_errno(0); fd = libc.syscall(279, b'nx', 0); row('memfd_create (used when W^X is on)', fd >= 0, err() if fd < 0 else '')
    if fd >= 0: os.close(fd)
    try:
        d = Path('/tmp/.dotnet'); (d / 'shm').mkdir(parents=True, exist_ok=True); (d / 'lockfiles').mkdir(exist_ok=True)
        st = d.stat(); f = open(d / 'lockfiles' / 'probe', 'a'); fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); f.close()
        row('/tmp/.dotnet folders and file locks', True, f'owner uid {st.st_uid}, mode {oct(st.st_mode & 0o7777)}')
    except OSError as e: row('/tmp/.dotnet folders and file locks', False, str(e))
    for f in ('/proc/self/maps', '/proc/meminfo', '/proc/cpuinfo', '/proc/self/cgroup', '/sys/devices/system/cpu/online'):
        try: Path(f).read_bytes(); row(f'read {f}', True)
        except OSError as e: row(f'read {f}', False, e.strerror)
    try: row('readlink /proc/self/exe', bool(os.readlink('/proc/self/exe')), os.readlink('/proc/self/exe'))
    except OSError as e: row('readlink /proc/self/exe', False, e.strerror)
    started = []
    def nap(): started.append(1); threading.Event().wait(0.3)
    try:
        ts = [threading.Thread(target=nap) for _ in range(150)]; [t.start() for t in ts]; [t.join() for t in ts]
        row('start 150 threads', len(started) == 150, f'{len(started)} started')
    except RuntimeError as e: row('start 150 threads', False, str(e))
    return out


def full_report():
    lines = ['== system checks'] + system_report() + ['', '== .NET start-up attempts'] + tune(force=True)
    if saved() is None and find_dotnet():
        rc, out = try_variant({}, trace=True)
        lines += ['', '== host trace of the default start (last lines)'] + out.splitlines()[-22:]
    return lines


if __name__ == '__main__':
    print('\n'.join(full_report() if '--full' in sys.argv else tune(force='--force' in sys.argv)))
