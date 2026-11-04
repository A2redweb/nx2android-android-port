#!/usr/bin/env python3
"""The .NET runtime can fail to start under proot on some phones ("Failed to create CoreCLR"). This tries known workarounds one by one with `dotnet --version`
and remembers the first one that works; every later job runs with it."""
import json, os, subprocess
from pathlib import Path

DOTNET = Path(os.environ.get('NX2A_TOOLS_DIR') or Path.home() / '.config/nx2android/toolchains') / 'dotnet' / 'dotnet'
SAVED = Path(os.environ.get('NX2A_DOTNET_ENV', '/root/dotnet_env.json'))
BASE = {'DOTNET_EnableWriteXorExecute': '0', 'DOTNET_SYSTEM_GLOBALIZATION_INVARIANT': '1', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1',
        'DOTNET_NOLOGO': '1', 'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1'}
VARIANTS = [
    ('default', {}),
    ('smaller GC heap', {'DOTNET_GCHeapHardLimit': '0x80000000'}),
    ('segment GC', {'DOTNET_GCName': 'libclrgc.so'}),
    ('segment GC, smaller heap', {'DOTNET_GCName': 'libclrgc.so', 'DOTNET_GCHeapHardLimit': '0x80000000'}),
    ('no background GC, smaller heap', {'DOTNET_gcConcurrent': '0', 'DOTNET_GCHeapHardLimit': '0x80000000', 'DOTNET_GCgen0size': '0x1000000'}),
    ('no tiered JIT, smaller heap', {'DOTNET_TieredCompilation': '0', 'DOTNET_gcConcurrent': '0', 'DOTNET_GCHeapHardLimit': '0x80000000'}),
]


def find_dotnet(): return DOTNET if DOTNET.is_file() else None


def saved():
    try: return json.loads(SAVED.read_text())
    except (OSError, ValueError): return None


def try_variant(extra):
    env = dict(os.environ); env.update(BASE); env.update(extra)
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
    for name, extra in VARIANTS:
        rc, out = try_variant(extra)
        first = out.splitlines()[0][:90] if out else ''
        report.append(f'{name}: exit {rc}' + (f' ({first})' if first else ''))
        if rc == 0:
            SAVED.write_text(json.dumps(extra)); report.append(f'using: {name}'); return report
    try: SAVED.unlink()
    except OSError: pass
    report.append('no variant worked')
    return report


if __name__ == '__main__':
    print('\n'.join(tune(force='--force' in __import__('sys').argv)))
