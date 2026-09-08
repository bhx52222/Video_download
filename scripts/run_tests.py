"""Run regression scripts without real network downloads or user-library processing."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parent.parent
runtime = Path.home() / '.vx/venv/bin/python'
ytpython = Path.home() / '.local/share/uv/tools/yt-dlp/bin/python'
if not runtime.exists():
    raise SystemExit('Install the runtime first; see docs/BUILD.md')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
env['PATH'] = ':'.join([str(Path.home()/'.vx/bin'), str(Path.home()/'.local/bin'), '/opt/homebrew/bin', env.get('PATH','')])
for folder in ('scripts', 'macos-app'):
    for test in sorted((ROOT/folder).glob('test_*.py')):
        python = ytpython if test.name == 'test_download_policy.py' else runtime
        print('\nRunning', test.relative_to(ROOT), flush=True)
        subprocess.run([str(python), '-B', str(test)], cwd=test.parent, env=env, check=True)
with tempfile.TemporaryDirectory() as td:
    exe = str(Path(td)/'test-links')
    subprocess.run(['xcrun','swiftc',str(ROOT/'macos-app/LinkTools.swift'),str(ROOT/'macos-app/test_links.swift'),'-o',exe],check=True)
    subprocess.run([exe],check=True)
print('\nAll regression scripts passed.')
