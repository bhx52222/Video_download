#!/usr/bin/env python3
"""验证「自动获取链接」修复：直接检查构建好的 App 包，不联网、不下载。

为什么查 App 包而不是主源码：主源码正确不代表打包进去的那份也正确。
backend 快照、build.py 的拷贝清单、bundle 里的 sys.path 都可能漏，
而用户实际运行的是 App 包里的那份。

用法：
    python3 scripts/verify_link_fix.py
    python3 scripts/verify_link_fix.py --app /path/to/某个.app
    python3 scripts/verify_link_fix.py --source   # 只验主源码，不需要先构建
"""
import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP = ROOT / 'outputs/拾影视频下载器-1.5.1独立版.app'

# 每条都是改动前会出错的真实形态。
# (输入, 期望队列, 这条在验什么)
CASES = [
    ('https://www.douyin.com/jingxuan?modal_id=7681863407733165321',
     ['https://www.douyin.com/video/7681863407733165321'],
     '抖音精选页规范化（原样送进 yt-dlp 会报 Unsupported URL）'),
    ('看这个 https://www.bilibili.com/video/BV15PtJ6JEBh？',
     ['https://www.bilibili.com/video/BV15PtJ6JEBh'],
     '尾部问号不吃进 URL'),
    ('【标题】https://x.com/user/status/1234567890】',
     ['https://x.com/user/status/1234567890'],
     'X 链接可入队，方括号不吃进 URL'),
    ('https://vimeo.com/123456789',
     ['https://vimeo.com/123456789'],
     '未知站点交给内核通用兜底，不丢弃'),
    ('#注释行\n\n https://youtu.be/x1 \n重复 https://youtu.be/x1',
     ['https://youtu.be/x1'],
     '注释行跳过、去重'),
    ('分享 https://weixin.qq.com/sph/abc。\nhttps://weixin.qq.com/sph/abc',
     ['https://weixin.qq.com/sph/abc'],
     '视频号 sph 链接与句号剥离'),
    ('bad input', [], '没有网址时返回空队列'),
]


def load_runner(folder):
    """从给定目录加载 runner.py，并让它能找到同目录的 downie_bridge。"""
    path = folder / 'runner.py'
    if not path.is_file():
        raise FileNotFoundError(f'找不到 {path}')
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location('runner_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--app', type=Path, default=DEFAULT_APP, help='要检查的 .app 路径')
    parser.add_argument('--source', action='store_true', help='检查主源码而不是 App 包')
    args = parser.parse_args()

    problems = []

    if args.source:
        folder = ROOT / 'macos-app'
        print(f'检查主源码：{folder}\n')
    else:
        resources = args.app / 'Contents/Resources'
        if not resources.is_dir():
            print(f'✗ 找不到 App 包：{args.app}')
            print('  先构建：python3 macos-app/build.py')
            return 1
        folder = resources
        print(f'检查 App 包：{args.app}\n')

        # 1. vx_link.py 必须真的被打包进去，且与主源码一致。
        packaged = resources / 'backend/vx_link.py'
        source = ROOT / 'scripts/src/vx_link.py'
        if not packaged.is_file():
            problems.append('App 包里没有 backend/vx_link.py；build.py 的拷贝清单漏了')
            print('✗ backend/vx_link.py  未打包')
        elif sha256(packaged) != sha256(source):
            problems.append('App 包里的 vx_link.py 与 scripts/src/vx_link.py 不一致')
            print('✗ backend/vx_link.py  与主源码不一致')
        else:
            print(f'✓ backend/vx_link.py  已打包，与主源码一致（{sha256(source)[:16]}…）')

    # 2. 用被测那份 runner.py 跑队列解析。这一步不联网。
    try:
        runner = load_runner(folder)
    except Exception as exc:
        print(f'✗ 无法加载 runner.py：{type(exc).__name__}: {exc}')
        return 1
    print()

    for text, want, why in CASES:
        try:
            got = runner.targets(text)
        except Exception as exc:
            got = f'{type(exc).__name__}: {exc}'
        if got == want:
            print(f'✓ {why}')
        else:
            problems.append(why)
            print(f'✗ {why}')
            print(f'    输入 {text!r}')
            print(f'    实得 {got!r}')
            print(f'    应为 {want!r}')

    print()
    if problems:
        print(f'{len(problems)} 项不符：')
        for item in problems:
            print(f'  · {item}')
        return 1
    print(f'全部通过（{len(CASES)} 条队列解析'
          + ('' if args.source else ' + 打包一致性') + '）。')
    print('注意：这里只验队列解析，剪贴板按钮与真实下载仍需在界面上实测。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
