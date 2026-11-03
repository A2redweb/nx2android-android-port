#!/usr/bin/env python3
"""Rewrites payload.json (file hashes). Run after editing anything in payload/.  --bump  raises the version by 2 (versions stay odd);  --setup  raises the setup number (forces inner_setup.sh to run again)."""
import hashlib, json, sys
from pathlib import Path

d = Path(__file__).resolve().parent.parent / 'app/src/main/assets/nx2a/payload'
f = d / 'payload.json'
m = json.loads(f.read_text()) if f.exists() else {'version': 1, 'setup': 1, 'porter_sha': '8e030b41caa05b109d497f486cea5f4abd1c7d73'}
if '--bump' in sys.argv: m['version'] = int(m['version']) + 2
if '--setup' in sys.argv: m['setup'] = int(m['setup']) + 2
m['files'] = {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob('*')) if p.is_file() and p.name != 'payload.json' and '__pycache__' not in p.parts}
f.write_text(json.dumps(m, indent=1) + '\n'); print('payload version', m['version'], 'setup', m['setup'], len(m['files']), 'files')
