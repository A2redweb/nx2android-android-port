#!/usr/bin/env python3
"""Bundles proot from the Termux repository together with every library it needs. The needed libraries are found by following the NEEDED entries of the binaries, so nothing has to be listed by hand."""
import re, shutil, subprocess, sys, urllib.request
from pathlib import Path

B = 'https://packages.termux.dev/apt/termux-main'
OUT = Path('app/src/main/jniLibs/arm64-v8a')
WORK = Path('/tmp/x')
SYSTEM = {'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libz.so', 'libandroid.so', 'libstdc++.so'}   # on every Android device


def get(url): return urllib.request.urlopen(url, timeout=120).read()
def sh(*a, **k): return subprocess.run(a, check=True, capture_output=True, text=True, **k).stdout


def parse_index(text):
    pk = {}
    for stanza in text.split('\n\n'):
        d = {}
        for line in stanza.split('\n'):
            if line[:1] not in ' \t' and ': ' in line:
                k, v = line.split(': ', 1); d[k] = v
        if 'Package' in d: pk[d['Package']] = d
    return pk


def dep_names(depends):
    out = []
    for dep in depends.split(','):
        n = re.split(r'[ (]', dep.split('|')[0].strip())[0]
        if n: out.append(n)
    return out


def needed(path):
    return re.findall(r'\(NEEDED\)\s+Shared library: \[(.+?)\]', sh('readelf', '-d', str(path)))


def main():
    shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    pk = parse_index(get(B + '/dists/stable/main/binary-aarch64/Packages').decode())
    seen, order = set(), []

    def fetch_pkg(name):
        if name in seen: return
        if name not in pk: sys.exit(f'package {name} is not in the Termux repository')
        seen.add(name); order.append(name)
        deb = WORK / f'{name}.deb'; deb.write_bytes(get(f"{B}/{pk[name]['Filename']}"))
        dst = WORK / name; dst.mkdir()
        data = next(m for m in sh('ar', 't', str(deb)).split() if m.startswith('data.tar'))
        sh('ar', 'x', str(deb), data, cwd=dst); sh('tar', '-xf', data, cwd=dst)
        for d in dep_names(pk[name].get('Depends', '')):
            if d.startswith('lib'): fetch_pkg(d)     # library packages only; tools such as termux-exec are not needed

    fetch_pkg('proot')
    print('packages fetched:', ', '.join(order))
    prefix = 'data/data/com.termux/files/usr'
    libs = {}
    for name in order:
        for p in (WORK / name / prefix / 'lib').glob('*.so*'):
            libs[p.name] = p.resolve()
    proot = WORK / 'proot' / prefix / 'bin/proot'
    loader = next(p for p in (WORK / 'proot' / prefix / 'libexec/proot').glob('loader*') if p.name in ('loader', 'loader32'))
    shutil.copy(proot, OUT / 'libproot.so')
    shutil.copy(WORK / 'proot' / prefix / 'libexec/proot/loader', OUT / 'libproot-loader.so')

    renames, queue = {}, [OUT / 'libproot.so']
    while queue:
        f = queue.pop()
        for n in needed(f):
            if n in SYSTEM or n in renames: continue
            if n not in libs: sys.exit(f'{f.name} needs {n}, which none of the fetched Termux packages provide')
            base = n.split('.so')[0] + '.so'          # libtalloc.so.2 -> libtalloc.so (Android only unpacks lib*.so files)
            renames[n] = base
            shutil.copy(libs[n], OUT / base); queue.append(OUT / base)
    for f in [OUT / 'libproot.so'] + [OUT / b for b in renames.values()]:
        for old, new in renames.items():
            if old != new: sh('patchelf', '--replace-needed', old, new, str(f))
        sh('patchelf', '--set-rpath', '$ORIGIN', str(f))
        if f.name != 'libproot.so': sh('patchelf', '--set-soname', f.name, str(f))
        f.chmod(0o755)
    (OUT / 'libproot-loader.so').chmod(0o755)
    print('bundled:')
    for f in sorted(OUT.glob('*.so')):
        print(' ', f.name, f.stat().st_size, 'needs', needed(f) if f.name != 'libproot-loader.so' else '(static loader)')


if __name__ == '__main__': main()
