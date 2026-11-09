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

# 2. every port gets the package unknownnone.nx2android.<game name> unless --package is given
patch('package names', 'porter/pipeline.py', "'unknownnone.nx2android.'", [
('self.package = o.package or ap.package',
 "self.package = o.package or 'unknownnone.nx2android.' + (re.sub(r'^[^a-z]+|[^a-z0-9]', '', ap.name.lower()) or 'game')"),
])
# 3. prebuilt .NET tools (CI-built, a runtime that starts under proot): used when the app has installed and tested them (NX2A_PREBUILT)
patch('prebuilt extractor', 'nxnative/scripts/build_ipa_from_nsp.py', 'NX2A_PREBUILT', [
("""    nx = work / 'tools/nx_extract' / exe
""", """    nx = work / 'tools/nx_extract' / exe
    if os.environ.get('NX2A_PREBUILT') and (Path(os.environ['NX2A_PREBUILT']) / 'nx_extract' / 'nx_extract').is_file():   # NX2A_PREBUILT: the app's prebuilt tools
        rmtree(nx.parent); shutil.copytree(Path(os.environ['NX2A_PREBUILT']) / 'nx_extract', nx.parent); return nx
"""),
])
patch('prebuilt translator', 'porter/pipeline.py', 'NX2A_PREBUILT', [
("""        src = DM / 'gfx/tools/dmsh_xlate'; ryu = DM / 'third_party/ryujinx'
""", """        if os.environ.get('NX2A_PREBUILT') and (Path(os.environ['NX2A_PREBUILT']) / 'dmsh_xlate' / 'dmsh_xlate').is_file():   # NX2A_PREBUILT: the app's prebuilt tools
            return Path(os.environ['NX2A_PREBUILT']) / 'dmsh_xlate' / 'dmsh_xlate.dll', 'prebuilt'
        src = DM / 'gfx/tools/dmsh_xlate'; ryu = DM / 'third_party/ryujinx'
"""),
])
patch('prebuilt dotnet check', 'porter/toolchain.py', 'NX2A_PREBUILT', [
("""    cfg = cfg if cfg is not None else config.load()
    if cfg.get('dotnet') and Path(cfg['dotnet']).is_file(): return Path(cfg['dotnet'])
""", """    cfg = cfg if cfg is not None else config.load()
    if os.environ.get('NX2A_PREBUILT_DOTNET') and Path(os.environ['NX2A_PREBUILT_DOTNET']).is_file(): return Path(os.environ['NX2A_PREBUILT_DOTNET'])   # NX2A_PREBUILT
    if cfg.get('dotnet') and Path(cfg['dotnet']).is_file(): return Path(cfg['dotnet'])
"""),
("""def dotnet_sdks(dotnet):   # {'10.0.402': '/usr/local/share/dotnet/sdk', ...}
""", """def dotnet_sdks(dotnet):   # {'10.0.402': '/usr/local/share/dotnet/sdk', ...}
    if os.environ.get('NX2A_PREBUILT_DOTNET') and str(dotnet) == os.environ['NX2A_PREBUILT_DOTNET']: return {'10.0.0': '/nx2a-prebuilt/sdk'}   # stands in for the SDK: the tools are prebuilt
"""),
])
sys.exit(1 if failed else 0)
