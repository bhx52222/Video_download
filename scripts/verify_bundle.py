#!/usr/bin/env python3
"""验证构建好的 .app 是不是真的自带运行时、且不依赖本机环境。

关键是"不依赖"这件事只能反证：在把 Homebrew、~/.vx、uv 全部移出 PATH 的
条件下，用包内的 Python 和工具跑一遍，能跑通才算数。在开发机上按平常方式
跑是测不出来的——本机什么都有，漏打包的东西照样能被找到。

用法：
    python3 scripts/verify_bundle.py
    python3 scripts/verify_bundle.py --app /path/to/某个.app
"""
import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP = ROOT / "outputs/拾影视频下载器-1.4.1测试版.app"
# 只留 macOS 自带目录：任何 Mac 都有，但 Homebrew、~/.vx、uv 都不在里面。
CLEAN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

problems = []


def bad(message):
    problems.append(message)
    print(f"✗ {message}")


def ok(message):
    print(f"✓ {message}")


def run(cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    args = parser.parse_args()

    resources = args.app / "Contents/Resources"
    if not resources.is_dir():
        print(f"✗ 找不到 App 包：{args.app}")
        print("  先构建：python3 macos-app/build.py")
        return 1
    print(f"检查 App 包：{args.app}\n")

    runtime = resources / "runtime"
    python = runtime / "python/bin/python3"
    if not python.is_file():
        print("✗ 包内没有 runtime/python/bin/python3，这不是一体化包。")
        print("  组装运行时：python3 scripts/bundle_runtime.py")
        print("  再构建：python3 macos-app/build.py")
        return 1

    manifest_path = runtime / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    if manifest:
        ok(f"清单：Python {manifest.get('python')}、yt-dlp {manifest.get('yt_dlp')}、"
           f"{len(manifest.get('ffmpeg_libs', []))} 个依赖库")
    else:
        bad("包内没有 runtime/manifest.json")

    # ── 该在包里的东西 ──
    for relative in ("bin/ffmpeg", "bin/ffprobe", "bin/yt-dlp", "bin/visionocr",
                     "python/bin/python3"):
        target = runtime / relative
        if target.is_file() and os.access(target, os.X_OK):
            ok(f"runtime/{relative}")
        else:
            bad(f"缺少或不可执行：runtime/{relative}")

    # ── 干净 PATH 下真的能跑 ──
    print(f"\n在干净 PATH 下执行（{CLEAN_PATH}）：")
    env = dict(os.environ, PATH=CLEAN_PATH, VX_RUNTIME=str(runtime))
    env.pop("VX_STATE", None)
    checks = [
        ("包内 Python 能 import 依赖",
         [str(python), "-c", "import truststore, yt_dlp"]),
        ("yt-dlp 可执行", [str(runtime / "bin/yt-dlp"), "--version"]),
        ("ffmpeg 可执行（92 个 dylib 全部找得到）",
         [str(runtime / "bin/ffmpeg"), "-version"]),
        ("ffprobe 可执行", [str(runtime / "bin/ffprobe"), "-version"]),
    ]
    for name, cmd in checks:
        result = run(cmd, env)
        if result.returncode:
            bad(f"{name}：{(result.stderr or result.stdout).strip()[:300]}")
        else:
            ok(name)

    # ── 包内的内核要解析到包内的工具，不能落回本机 ──
    backend = resources / "backend"
    result = run([str(python), str(backend / "vx_runtime.py")], env)
    if result.returncode:
        bad(f"包内 vx_runtime 跑不起来：{result.stderr.strip()[:300]}")
    else:
        rows = dict(line.split(None, 1) for line in result.stdout.strip().splitlines()
                    if len(line.split(None, 1)) == 2)
        for tool in ("ffmpeg", "ffprobe"):
            value = rows.get(tool, "")
            if str(runtime / "bin" / tool) in value:
                ok(f"内核解析到包内 {tool}")
            else:
                bad(f"内核没解析到包内 {tool}，实得 {value}")
        # 可写状态必须留在 ~/.vx：.app 内部不可写，进去了迟早出错
        state = rows.get("state_home", "")
        if str(runtime) in state:
            bad(f"可写状态被放进了 .app 内部：{state}")
        else:
            ok(f"可写状态在包外：{state}")

    # ── 真的跑一次内核，确认不是只有路径对 ──
    result = run([str(python), "-B", str(backend / "vx.py"), "--help"], env)
    if result.returncode:
        bad(f"包内内核跑不起来：{(result.stderr or result.stdout).strip()[:300]}")
    else:
        ok("包内内核可启动")

    # ── 签名 ──
    result = run(["codesign", "--verify", "--deep", "--strict", str(args.app)])
    if result.returncode:
        bad(f"签名校验失败：{result.stderr.strip()[:300]}")
    else:
        ok("codesign --verify --deep --strict")

    plist = args.app / "Contents/Info.plist"
    if plist.is_file():
        version = plistlib.loads(plist.read_bytes()).get("CFBundleShortVersionString")
        ok(f"版本 {version}")

    total = sum(f.stat().st_size for f in args.app.rglob("*") if f.is_file())
    print(f"\n包体积 {total / 1024 / 1024:.0f} MB")

    if problems:
        print(f"\n{len(problems)} 项不符：")
        for item in problems:
            print(f"  · {item}")
        return 1
    print("\n全部通过。这个包不依赖本机 Homebrew、~/.vx 或 uv。")
    print("注意：这里验的是能否启动与自洽，真实下载与 GUI 仍需实测；"
          "语音转写模型按约定首次使用时下载，不在包内。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
