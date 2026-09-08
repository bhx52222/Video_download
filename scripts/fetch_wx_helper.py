"""Download the pinned optional WeChat helper; verify before extracting executable."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'macos-app/external/wx_channels_download'
m = json.loads((DEST / 'provenance.json').read_text())
url = ('https://github.com/ltaoo/wx_channels_download/releases/download/'
       + m['version'] + '/wx_video_download_' + m['version'] + '_darwin_arm64.zip')
with urllib.request.urlopen(url, timeout=60) as r:
    data = r.read(150 * 1024 * 1024 + 1)
if hashlib.sha256(data).hexdigest() != m['archive_sha256']:
    raise SystemExit('Archive SHA-256 mismatch; nothing installed')
with zipfile.ZipFile(io.BytesIO(data)) as z:
    names = [n for n in z.namelist() if Path(n).name == 'wx_video_download' and not n.endswith('/')]
    if len(names) != 1:
        raise SystemExit('Unexpected archive structure')
    binary = z.read(names[0])
if hashlib.sha256(binary).hexdigest() != m['binary_sha256']:
    raise SystemExit('Binary SHA-256 mismatch; nothing installed')
p = DEST / 'wx_video_download'
p.write_bytes(binary)
p.chmod(0o755)
print('Verified helper installed:', p)
