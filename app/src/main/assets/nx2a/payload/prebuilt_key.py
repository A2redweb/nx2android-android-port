#!/usr/bin/env python3
"""Identifies the sources of the porter's two .NET tools (the extractor and the shader translator). The same function runs in CI (to name the prebuilt tools)
and on the phone (to find the ones that belong to the porter it has), so both always agree."""
import hashlib, sys
from pathlib import Path


def compute(repo):
    repo = Path(repo)
    nx = repo / 'nxnative/dm/tools/nx_extract'
    xl = repo / 'nxnative/dm/gfx/tools/dmsh_xlate'
    ry = repo / 'nxnative/dm/third_party/ryujinx'
    files = [*nx.glob('*.cs'), *nx.glob('*.csproj'), *xl.glob('*.cs'), *xl.glob('*.csproj'), *ry.glob('*.props')]
    files += [p for p in (ry / 'src').rglob('*') if p.suffix in ('.cs', '.csproj', '.props') and not {'bin', 'obj'} & set(p.relative_to(ry).parts)]
    h = hashlib.sha256()
    for p in sorted(set(files)):
        h.update(p.relative_to(repo).as_posix().encode() + b'\0' + p.read_bytes() + b'\0')
    return h.hexdigest()[:20]


if __name__ == '__main__': print(compute(sys.argv[1]))
