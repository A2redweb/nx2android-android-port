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

# 1b. the same wrapper for C++ (the custom-driver loader libadrenotools is C++): the trimmed NDK has no clang++, use the system one with the NDK sysroot
patch('arm host c++', 'nxnative/dm/android/build.py', 'cxx-arm', [
("""    CXX = str(bin_ / ('clang++.exe' if os.name == 'nt' else 'clang++'))
""", """    CXX = str(bin_ / ('clang++.exe' if os.name == 'nt' else 'clang++'))
    if NX2A_ARM_HOST:
        _sys_cxx = _sh.which('clang++') or (_sys_clang + '++')
        _wrx = _wd / 'cxx-arm'
        _wrx.write_text(f'#!/bin/sh\\nexec {_sys_cxx} --sysroot={_sysroot} -resource-dir={_rd} -rtlib=compiler-rt "$@"\\n')
        _wrx.chmod(_wrx.stat().st_mode | _st0.S_IXUSR)
        CXX = str(_wrx)
"""),
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

# 5. run-time GLSLC shaders (Fire Emblem: Three Houses): upstream captures them by booting the game in the Mac host; here the Android host runs as a program on the connected phone (adb), as it already does for Oodle
patch('device glslc capture', 'porter/pipeline.py', 'NX2A_GLSLC', [
("""        for k in ('glslc_capture', 'ue_legacy') + """, """        self.glslc_why = src['glslc_capture'][1] if src['glslc_capture'][0] else ''   # NX2A_GLSLC
        if self.glslc_why:
            if not self.tools.get('adb'):
                raise BuildError(f"{self.app_name} compiles some shaders at run time with its own GLSLC ({self.glslc_why}): the port captures them by booting the game on the Android device, so it needs adb and the device even without installing. {NO_ADB}; then connect the device (wireless debugging) and port again")
            try: Adb(self.tools['adb'], self.o.device or self.cfg.get('device'), log=say).pick()
            except (AdbError, KeyError) as e: raise BuildError(f"{self.app_name} compiles some shaders at run time with its own GLSLC ({self.glslc_why}): the port captures them by booting the game on the Android device, so connect it (adb) and port again ({e})") from e
        for k in ('ue_legacy',) + """),
("""            if getattr(self, "ue_why", ""): self.device_ue()""", """            if getattr(self, 'glslc_why', ''): self.device_glslc()   # NX2A_GLSLC: the run-time shaders, captured on the device before the split reads them
            if getattr(self, "ue_why", ""): self.device_ue()"""),
("""    # ---- Unreal Engine shader code archives decoded with the game's own Oodle on the device""", r"""    GDEV = '/data/local/tmp/nx2a-glslc'
    def device_glslc(self):
        # the shaders the game compiles at run time with its own GLSLC: the Android host, built as a program without graphics, boots the game on the connected phone with DM_GLSLC_CAPTURE
        # (dm/host/hle_glslc.c) and the outputs come back to <version dir>/glslc_capture, where the split reads them. First with the big RomFS files as empty stand-ins of the right size (the capture
        # happens in the first second of boot), then, if that did not capture everything, with the whole RomFS
        import shlex, time
        want = nsp.glslc_wanted(self.g)
        have = lambda d: (nsp.glslc_done(d / 'glslc_capture') >= want) if want else bool(nsp.glslc_done(d / 'glslc_capture'))
        todo = [v for v in self.versions if not have(self.dirs[v])]
        PROG.add(1); PROG.stage('GLSLC capture')
        if not todo:
            say('reusing the captured run-time shaders'); PROG.end('reused'); return
        if todo != [self.pkg_ver]:
            PROG.end(ok=False)
            raise BuildError(f"the run-time shader capture runs the packed version {self.pkg_ver}'s code; {', '.join(v for v in todo if v != self.pkg_ver)} needs a capture of its own")
        d, G, SECS = self.dirs[self.pkg_ver], self.GDEV, 60
        rom, cap, log = d / 'RomFS', d / 'glslc_capture.partial', self.logs / 'glslc_capture.log'
        adb = Adb(self.tools['adb'], self.o.device or self.cfg.get('device'), log=say); adb.pick()
        host = self.aw / 'host-glslc'
        PROG.set(step='building the host as a tool (no graphics)')
        nsp.run([PY, DM / 'android/build.py', '--game', self.g.id, '--ndk', self.tools['ndk'], '--out', host, '--exe', '--gfx', 'null', '--release', '--jobs', str(self.o.jobs)],
                self.logs / 'android_glslc_host.log', env=self.env)
        big = sorted((p.relative_to(rom).as_posix(), p.stat().st_size) for p in rom.rglob('*') if p.is_file() and p.stat().st_size > (64 << 20))
        rounds = [False, True] if 0 < len(big) <= 200 else [True]
        got, tail = set(), ''
        try:
            for full in rounds:
                PROG.set(step='sending the game to the phone' + ('' if full else ' (big files as empty stand-ins)'))
                adb.shell(f'pkill -f {G}/dmhost; rm -rf {G}/cap {G}/save {G}/temp {G}/mods {G}/dmhost; mkdir -p {G}/mods {G}/RomFS {G}/cap {G}/save {G}/temp', check=False)
                adb.push_file(host / 'dmhost', f'{G}/dmhost')
                adb.push_tree(self.patched, f'{G}/mods')
                adb.push_file(self.g.table('shader_map.tsv'), f'{G}/shader_map.tsv')
                if full:
                    if big: adb.shell('; '.join(f'rm -f {shlex.quote(G + "/RomFS/" + r)}' for r, _ in big), check=False)
                    adb.push_tree(rom, f'{G}/RomFS')
                else:
                    adb.push_tree(rom, f'{G}/RomFS', skip=[r for r, _ in big])
                    adb.shell('; '.join(f'mkdir -p {shlex.quote(os.path.dirname(G + "/RomFS/" + r))}; truncate -s {s} {shlex.quote(G + "/RomFS/" + r)}' for r, s in big))
                PROG.set(step='booting the game on the phone until it has compiled its shaders')
                env = f'DM_ROOT={G} DM_ROMFS={G}/RomFS DM_SAVE={G}/save DM_TEMP={G}/temp DM_GLSLC_CAPTURE={G}/cap DM_NVN_SHMAP={G}/shader_map.tsv'
                adb.shell(f'cd {G} && chmod 755 dmhost && ({env} timeout {SECS} ./dmhost mods > run.log 2>&1 &); sleep 1; echo started')
                t0, last, same = time.time(), -1, 0
                while time.time() - t0 < SECS + 10:
                    time.sleep(2)
                    f = (adb.shell(f'echo $(ls {G}/cap 2>/dev/null | wc -l) $(pidof dmhost | wc -w)', check=False) or '').split()
                    n, alive = (int(f[0]), int(f[1])) if len(f) == 2 and all(x.isdigit() for x in f) else (0, 1)
                    PROG.set(done=n, total=len(want) if want else None, unit='shaders')
                    same = same + 1 if n == last else 0; last = n
                    if (want and n >= len(want)) or not alive or (not want and n and same >= 3): time.sleep(2); break
                adb.shell('pkill -f dmhost', check=False)
                tail = adb.shell(f'tail -n 40 {G}/run.log', check=False) or ''
                log.write_text(tail, encoding='utf-8')
                nsp.rmtree(cap); cap.mkdir(parents=True)
                adb.run('pull', f'{G}/cap/.', str(cap), check=False)
                got = nsp.glslc_done(cap)
                if (got >= want) if want else got: break
                if not full: say(f'[RED] the capture with stand-in files got {len(got)} shaders{f" of {len(want)}" if want else ""}: trying again with the whole RomFS on the phone')
        finally:
            adb.shell(f'pkill -f {G}/dmhost; rm -rf {G}', check=False)
        if not (got >= want if want else got):
            PROG.end(ok=False)
            PROG.say(f'---- the game on the phone, last lines ({log}) ----\n' + tail.rstrip('\n'))
            raise BuildError(f'captured only {len(got)} run-time shaders' + (f', the profile needs {len(want)}' if want else '') + f' (host output: {log})')
        nsp.swap_in(cap, d / 'glslc_capture'); PROG.end(f'{len(got)} shaders captured on the device')

    # ---- Unreal Engine shader code archives decoded with the game's own Oodle on the device"""),
])

# 5b. the null graphics backend does not link as a program: gl_android.c (always compiled) calls two Vulkan present functions that only the Vulkan backend defines
patch('null graphics link', 'nxnative/dm/android/gfx_null.c', 'NX2A_NULLSTUB', [
("""int mtl_has_window(void) { return 0; }
""", """int mtl_has_window(void) { return 0; }
// NX2A_NULLSTUB: gl_android.c's EGL present path names these; a null-graphics program never presents
void *vk_image_from_ahb(void *ahb, uint32_t w, uint32_t h) { (void)ahb; (void)w; (void)h; return 0; }
uint64_t vk_present_vkimg(void *im, double period) { (void)im; (void)period; return 0; }
"""),
])

# 5c. a LINKDATA DATA1.bin with no bytes (Three Houses: one of the DLC / patch folders) made the split's mmap fail ("cannot mmap an empty file") and stopped the whole port: skip it, say which
patch('empty linkdata', 'nxnative/dm/gfx/tools/shader_split.py', 'NX2A_EMPTYDATA', [
("""    if os.path.basename(path) != 'DATA1.bin' or not os.path.exists(idx): return None
""", """    if os.path.basename(path) != 'DATA1.bin' or not os.path.exists(idx): return None
    if os.path.getsize(path) == 0:   # NX2A_EMPTYDATA
        print(f'shader split: {rel} is empty (a LINKDATA archive without data): skipped', file=sys.stderr); return None
"""),
])

# 5d. the survey's instruction census is a report-only step (it feeds survey.md, not the provisional profile) that disassembles every module with Python capstone: minutes to an hour on a phone for a big game
patch('survey census skipped', 'nxnative/scripts/build_ipa_from_nsp.py', 'NX2A_CENSUS', [
("""        run([py, repo / 'dm/tools/insn_census.py', m], logs / f'census_{m.name}.log', env=env)
""", """        (logs / f'census_{m.name}.log').write_text('skipped by the nx2android app: a slow, report-only step (NX2A_CENSUS)\\n')   # NX2A_CENSUS
"""),
])

# 5e. stripping the host library only makes it smaller: the Ubuntu strip could not read the library's architecture for Rune Factory (the build then stopped), so a failed strip is no longer an error
patch('strip optional', 'nxnative/dm/android/build.py', 'NX2A_STRIPOPT', [
("""if NX2A_ARM_HOST else str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=True)""",
 """if NX2A_ARM_HOST else str(bin_ / ('llvm-strip.exe' if os.name == 'nt' else 'llvm-strip')), '--strip-unneeded', str(out / 'libdmhost.so')], check=False)  # NX2A_STRIPOPT"""),
])

# 5f. this app's own Android keys for an experimental port (profiles/<title id>.android.tsv: env rows and the like), added once to the android.tsv the porter writes; a game upstream has an android.tsv for never gets them
patch('profile overlays', 'porter/pipeline.py', 'NX2A_OVERLAY', [
("""        self.use_profile_dir(pdir, first=True)
        g = game.load(tid)
        return g, android_profile.AndroidProfile(g)""", """        _ov = Path('@@DIR@@') / f'{tid.upper()}.android.tsv'   # NX2A_OVERLAY
        if _ov.is_file() and '# nx2android overlay' not in (d / 'android.tsv').read_text(encoding='utf-8'):
            with open(d / 'android.tsv', 'a', encoding='utf-8') as _f: _f.write('\\n# nx2android overlay\\n' + _ov.read_text(encoding='utf-8'))
        self.use_profile_dir(pdir, first=True)
        g = game.load(tid)
        return g, android_profile.AndroidProfile(g)""".replace('@@DIR@@', str(Path(__file__).resolve().parent / 'profiles'))),
])

# 6. when the on-device host fails, keep its whole output (the grep for two words left nothing to read for exit 139)
patch('device host log', 'porter/pipeline.py', "tail -n 30 job.log'", [
("""echo "exit $?"; grep -a -e DM_OODLE_JOB -e RED job.log | tail -5'""", """echo "exit $?"; tail -n 30 job.log'"""),
])

# 5g. the host cuts a big memory pool into fixed 256 MB chunks and a buffer that crosses a chunk's end gets no GPU buffer (Three Houses' field model of the lead): the chunk size can be set per game (DM_VK_ZC_CHUNK_MB, a multiple of 64; 256 = upstream's)
patch('zero-copy chunk size', 'nxnative/dm/android/gfx_vk_core.c', 'NX2A_ZCCHUNK', [
("""#define ZC_CHUNK 0x10000000ull
""", """static uint64_t zc_chunk_sz(void) {   // NX2A_ZCCHUNK
    static uint64_t c; if (c) return c;
    const char *e = getenv("DM_VK_ZC_CHUNK_MB"); long m = e ? atol(e) : 0;
    c = m >= 64 && m <= 512 && !(m & 63) ? (uint64_t)m << 20 : 0x10000000ull; return c;
}
#define ZC_CHUNK zc_chunk_sz()
"""),
])

# 5h. a buffer-to-buffer copy whose destination (or source) crosses the end of a zero-copy chunk found no buffer and was dropped ("buffer copy outside the memory pools"): in Three Houses
# that copy is the lead's field model's vertex data, so the model drew garbage. Any chunk size has the same problem (the game packs its buffers back to back), so the copy is split at the chunk ends
patch('copy across chunks', 'nxnative/dm/android/gfx_vk_core.c', 'NX2A_COPYSPLIT', [
("""void mtl_sub_copy(uint64_t src, uint64_t dst, uint64_t n) {
""", """static void mtl_sub_copy_one(uint64_t src, uint64_t dst, uint64_t n) {
"""),
("""void mtl_sub_fill(uint64_t dst, uint64_t n, uint32_t value) {
""", """void mtl_sub_copy(uint64_t src, uint64_t dst, uint64_t n) {   // NX2A_COPYSPLIT: in pieces that each lie in one chunk of the source's pool and of the destination's
    for (uint64_t done = 0; done < n;) {
        uint64_t s = src + done, d = dst + done, m = n - done;
        vkpool_t *ps = vk_pool_of(s, 1), *pd = vk_pool_of(d, 1);
        if (ps && s + m > ps->hi) m = ps->hi - s;
        if (pd && d + m > pd->hi) m = pd->hi - d;
        mtl_sub_copy_one(s, d, m); done += m;
    }
}
void mtl_sub_fill(uint64_t dst, uint64_t n, uint32_t value) {
"""),
])

sys.exit(1 if failed else 0)
