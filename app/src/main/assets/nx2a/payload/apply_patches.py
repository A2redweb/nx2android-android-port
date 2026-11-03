#!/usr/bin/env python3
"""Patches a nx2android checkout for an aarch64 phone. Idempotent; each patch reports ok / already / FAILED (upstream text changed)."""
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else '.').resolve()
failed = 0


def patch(name, rel, marker, edits):
    global failed
    f = repo / rel
    try: s = f.read_text()
    except OSError as e: print(f'{name}: FAILED (cannot read {rel}: {e})'); failed += 1; return
    if marker in s: print(f'{name}: already'); return
    for old, new in edits:
        if s.count(old) != 1: print(f'{name}: FAILED (upstream changed: {old[:50]!r})'); failed += 1; return
        s = s.replace(old, new)
    f.write_text(s); print(f'{name}: ok')


# 1. the NDK's own tools are x86-64: use the system clang/glslc with the NDK sysroot, the system clang's headers and the NDK's runtime libraries
patch('arm host build', 'nxnative/dm/android/build.py', 'NX2A_ARM_HOST', [
("""host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64' if sys.platform.startswith('linux') else 'darwin-x86_64'
bin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'
CC = str(bin_ / ('clang.exe' if os.name == 'nt' else 'clang'))
""", """import platform as _pf, shutil as _sh, stat as _st0
NX2A_ARM_HOST = sys.platform.startswith('linux') and _pf.machine().lower() in ('aarch64', 'arm64')
host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64' if sys.platform.startswith('linux') else 'darwin-x86_64'
bin_ = Path(a.ndk) / 'toolchains/llvm/prebuilt' / host / 'bin'
CC = str(bin_ / ('clang.exe' if os.name == 'nt' else 'clang'))
if NX2A_ARM_HOST:
    _sysroot = next(Path(a.ndk).glob('toolchains/llvm/prebuilt/*/sysroot'), None)
    _ndkres = next(iter(sorted(Path(a.ndk).glob('toolchains/llvm/prebuilt/*/lib/clang/*'))), None)
    _sys_clang = _sh.which('clang')
    if not (_sysroot and _ndkres and _sys_clang): sys.exit('aarch64 host: need the NDK download (its sysroot) and the system clang (apt install clang lld)')
    _sysres = Path(subprocess.check_output([_sys_clang, '-print-resource-dir'], text=True).strip())
    _wd = Path(a.out if a.out else DM / 'android/out'); _wd.mkdir(parents=True, exist_ok=True)
    _rd = _wd / 'resdir'; _rd.mkdir(exist_ok=True)
    for _n, _t in (('include', _sysres / 'include'), ('lib', _ndkres / 'lib')):
        _l = _rd / _n
        if _l.is_symlink() or _l.exists(): _l.unlink()
        _l.symlink_to(_t)
    _wrap = _wd / 'cc-arm'
    _wrap.write_text(f'#!/bin/sh\\nexec {_sys_clang} --sysroot={_sysroot} -resource-dir={_rd} -rtlib=compiler-rt "$@"\\n')
    _wrap.chmod(_wrap.stat().st_mode | _st0.S_IXUSR)
    CC = str(_wrap)
"""),
("GLSLC = Path(a.ndk) / 'shader-tools' / host / ('glslc.exe' if os.name == 'nt' else 'glslc')\n",
 "GLSLC = Path(a.ndk) / 'shader-tools' / host / ('glslc.exe' if os.name == 'nt' else 'glslc')\nif NX2A_ARM_HOST: GLSLC = Path(_sh.which('glslc') or sys.exit('aarch64 host: apt install glslc'))\n"),
("subprocess.run([str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=True)",
 "subprocess.run([str(_sh.which('llvm-strip') or _sh.which('llvm-strip-18') or 'strip') if NX2A_ARM_HOST else str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=True)"),
])

# 2. games like Dark Souls Remastered create thousands of GPU memory pools: raise the limit and keep the lookup order incrementally
patch('memory pool limit', 'nxnative/dm/android/gfx_vk_core.c', 'pool_ord_insert', [
('#define MAXPOOL 4096', '#define MAXPOOL 32768'),
('static void pool_ord_make(void) {', '''static void pool_ord_insert(void) {   // the pool just added at g_npool - 1 goes into the order by lo (the order was valid for the others)
    int n = g_npool - 1, a = 0, b = n; uint64_t k = g_pool[n].lo;
    while (a < b) { int m = (a + b) / 2; if (g_pool[g_pool_ord[m]].lo <= k) a = m + 1; else b = m; }
    memmove(&g_pool_ord[a + 1], &g_pool_ord[a], (size_t)(n - a) * sizeof *g_pool_ord); g_pool_ord[a] = (uint16_t)n;
}
static void pool_ord_make(void) {'''),
('g_npool++; pool_ord_make();', 'g_npool++; pool_ord_insert();'),
])

# 3. every port gets the package unknownnone.nx2android.<game name> unless --package is given
patch('package names', 'porter/pipeline.py', "'unknownnone.nx2android.'", [
('self.package = o.package or ap.package',
 "self.package = o.package or 'unknownnone.nx2android.' + (re.sub(r'^[^a-z]+|[^a-z0-9]', '', ap.name.lower()) or 'game')"),
])
sys.exit(1 if failed else 0)
