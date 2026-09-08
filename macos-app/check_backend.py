"""Read-only source/snapshot comparison used before a local App build."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'scripts/src'
FILES = ('vx.py', 'vx_tiktok.py', 'vx_wxchannels.py', 'vx_browser_cookie.py','vx_kuaishou.py', 'vendor/wxdecrypt/main.go', 'vendor/wxdecrypt/decrypt.go', 'vendor/wxdecrypt/LICENSE', 'vendor/wxdecrypt/NOTICE.md')


def compare(source=SOURCE, snapshot=ROOT / 'backend'):
    rows = []
    for name in FILES:
        row = {'file': name}
        for label, root in [('source', source), ('snapshot', snapshot)]:
            try:
                row[label] = hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
            except OSError:
                row[label] = None
        row['matches'] = row['source'] is not None and row['source'] == row['snapshot']
        rows.append(row)
    return {'matches': all(row['matches'] for row in rows), 'files': rows}


def require_current(source=SOURCE, snapshot=ROOT / 'backend'):
    report = compare(source, snapshot)
    if not report['matches']:
        names = ', '.join(row['file'] for row in report['files'] if not row['matches'])
        raise RuntimeError('停止构建：主源码缺失或与 App 快照不同：' + names
                           + '。请审查差异后同步，不能自动覆盖 Claude 的改动。')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'backend')
    args = parser.parse_args()
    report = compare(args.source, args.snapshot)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['matches'] else 1)
