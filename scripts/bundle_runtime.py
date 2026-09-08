#!/usr/bin/env python3
"""组装一体化安装包用的自带运行时，输出到 work/runtime/。

目标是让 .app 不再依赖本机 ~/.vx：Python、依赖、ffmpeg、yt-dlp、visionocr
全部放进包内。转写模型不在这里——按约定首次使用时才下载，否则包会到数 GB。

产物布局（与 vx_runtime.py 和 Runtime.swift 约定的一致）：

    work/runtime/
      python/bin/python3        独立发行版，可重定位
      python/lib/.../site-packages/   truststore、yt-dlp 等
      bin/ffmpeg  bin/ffprobe   从本机 Homebrew 拷贝并重定位
      bin/yt-dlp                指向包内 python 的 shell 包装
      bin/visionocr             swiftc 现场编译
      lib/*.dylib               ffmpeg 依赖的非系统库
      manifest.json             记录内容与来源，供验证脚本比对

用法：
    python3 scripts/bundle_runtime.py --check    只报告环境，不下载不写文件
    python3 scripts/bundle_runtime.py --update   联网解析最新 Python 版本，写进 lock
    python3 scripts/bundle_runtime.py            按 lock 组装

版本锁在 macos-app/runtime.lock.json，与 external/wx_channels_download/
provenance.json 是同一套做法：先固定版本和 SHA-256，校验通过才落盘。

只写 work/runtime/。不碰 ~/.vx、不碰系统、不改代理证书。
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "work/runtime"
LOCK = ROOT / "macos-app/runtime.lock.json"
PYTHON_SERIES = "3.12"          # 与 install_runtime.sh 保持一致
RELEASES = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"

# 这些前缀下的库是 macOS 自带的，不拷进包，也不该改引用。
SYSTEM_PREFIXES = ("/usr/lib/", "/System/")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def need(name):
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"缺少 {name}。这一步必须在装了它的 Mac 上跑。")
    return found


# ─────────────────────────────────────────────── 版本锁

def match_asset(tag, names, series=PYTHON_SERIES):
    """在一次发布的资产名里挑出我们要的那个构建。

    上游同一次发布有上百个资产：各种架构、各种优化配置、
    install_only 与完整版、带不带 stripped。挑错一个的后果是
    包里塞进一个跑不起来或者体积翻倍的 Python，所以匹配要严格到底：
    必须是这个 tag、这个 3.x 系列、aarch64-apple-darwin、install_only，
    且不带任何后缀变体。

    多个候选时取版本号最大的（同一发布里可能同时有 3.12.9 和 3.12.11）。
    """
    pattern = re.compile(
        rf"^cpython-({re.escape(series)}\.(\d+))\+{re.escape(tag)}"
        r"-aarch64-apple-darwin-install_only\.tar\.gz$")
    best = None
    for name in names:
        m = pattern.match(name)
        if m and (best is None or int(m.group(2)) > best[1]):
            best = (m.group(1), int(m.group(2)), name)
    return None if best is None else {"python": best[0], "name": best[2]}


def resolve_latest():
    """联网解析最新的 aarch64-apple-darwin install_only 构建。

    不在源码里硬编码版本号：这个上游几乎每月发一版，写死很快就过期，
    而且我们要的是"某次解析的结果被固定下来"，不是"每次构建都取最新"。
    """
    req = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json",
                                                    "User-Agent": "shiying-bundler"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read(8 * 1024 * 1024))
    tag = data["tag_name"]
    assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
    hit = match_asset(tag, assets)
    if hit is None:
        raise SystemExit(f"该版本 {tag} 里没有 {PYTHON_SERIES} 的 aarch64-apple-darwin "
                         f"install_only 构建。改 PYTHON_SERIES 或换一个 tag。")
    return {"tag": tag, "python": hit["python"], "name": hit["name"],
            "url": assets[hit["name"]]}


def update_lock():
    info = resolve_latest()
    print(f"解析到 {info['name']}")
    print("下载并计算 SHA-256（几十 MB，稍等）…")
    with urllib.request.urlopen(info["url"], timeout=300) as r:
        blob = r.read(200 * 1024 * 1024 + 1)
    if len(blob) > 200 * 1024 * 1024:
        raise SystemExit("归档超过 200 MB，不像是预期的构建，已停止。")
    info["sha256"] = hashlib.sha256(blob).hexdigest()
    info["size"] = len(blob)
    LOCK.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    print(f"已写入 {LOCK.relative_to(ROOT)}")
    print(f"  python  {info['python']}")
    print(f"  sha256  {info['sha256']}")
    print("请把这个 lock 一起提交，构建才可复现。")


def load_lock():
    if not LOCK.is_file():
        raise SystemExit(f"没有 {LOCK.relative_to(ROOT)}。先跑一次 --update 固定版本。")
    lock = json.loads(LOCK.read_text())
    for key in ("url", "sha256", "python", "name"):
        if key not in lock:
            raise SystemExit(f"lock 缺字段 {key}，重新跑 --update。")
    return lock


# ─────────────────────────────────────────────── Python

def install_python(lock):
    print(f"[1/5] Python {lock['python']}")
    cache = ROOT / "work/cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / lock["name"]
    if archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest() == lock["sha256"]:
        print("      用缓存的归档")
    else:
        print("      下载中…")
        with urllib.request.urlopen(lock["url"], timeout=600) as r:
            blob = r.read(200 * 1024 * 1024 + 1)
        if hashlib.sha256(blob).hexdigest() != lock["sha256"]:
            raise SystemExit("SHA-256 与 lock 不符，什么都没安装。")
        archive.write_bytes(blob)
    target = OUT / "python"
    if target.exists():
        shutil.rmtree(target)
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(archive) as tf:
            # 归档顶层就是 python/，直接解到临时目录再整体搬过去。
            tf.extractall(td, filter="data")
        extracted = Path(td) / "python"
        if not (extracted / "bin/python3").is_file():
            raise SystemExit("归档结构与预期不符，没有 python/bin/python3。")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(target))
    python = target / "bin/python3"
    result = run([str(python), "-c", "import sys;print(sys.version)"])
    if result.returncode:
        raise SystemExit(f"包内 Python 跑不起来：{result.stderr.strip()[:200]}")
    print(f"      {result.stdout.strip().splitlines()[0]}")
    return python


def install_packages(python):
    print("[2/5] Python 依赖")
    # 只装运行必需的。ASR 那套按约定首次使用时下载，不进包。
    packages = ["yt-dlp", "yt-dlp-ejs"]
    cmd = [str(python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
           "-r", str(ROOT / "requirements.txt"), *packages]
    result = run(cmd)
    if result.returncode:
        raise SystemExit(f"依赖安装失败：\n{result.stdout[-1500:]}\n{result.stderr[-1500:]}")
    check = run([str(python), "-c", "import truststore, yt_dlp; print(yt_dlp.version.__version__)"])
    if check.returncode:
        raise SystemExit(f"装完了但 import 不进来：{check.stderr.strip()[:300]}")
    print(f"      truststore + yt-dlp {check.stdout.strip()}")
    return check.stdout.strip()


def write_ytdlp_shim(bin_dir):
    """yt-dlp 用 shell 包装，不用 pip 生成的 console script。

    pip 生成的脚本 shebang 是写死的绝对路径，指向组装时那个目录；
    .app 装到别人电脑上路径就变了，脚本直接失效。包装脚本按自身位置
    相对定位，搬到哪都对。
    """
    shim = bin_dir / "yt-dlp"
    shim.write_text('#!/bin/sh\n'
                    'here=$(cd "$(dirname "$0")" && pwd)\n'
                    'exec "$here/../python/bin/python3" -m yt_dlp "$@"\n')
    shim.chmod(0o755)
    return shim


# ─────────────────────────────────────────────── ffmpeg 与它的一串依赖

def parse_otool(text):
    """从 otool -L 的输出里挑出需要打包的动态库。

    要排除三类，漏掉任何一类都会出问题：
      /usr/lib/、/System/  系统自带，拷进包反而可能和系统版本冲突
      @ 开头              已经是相对引用（@rpath/@loader_path），不用再动
      第一行              是文件自己的路径，不是依赖
    """
    out = []
    for line in text.splitlines()[1:]:
        path = line.strip().split(" (")[0]
        if path and not path.startswith(SYSTEM_PREFIXES) and not path.startswith("@"):
            out.append(path)
    return out


def relative_ref(consumer_dir, name, lib_dir):
    """引用者该用哪个 @loader_path 相对路径指向 lib/<name>。

    可执行文件在 bin/，要跨一层出去；dylib 自己就在 lib/，同级。
    写反了不会报错，会变成装到别人电脑上才起不来。
    """
    return f"@loader_path/{name}" if consumer_dir == lib_dir else f"@loader_path/../lib/{name}"


def dependencies(binary):
    """otool -L 的输出里，本机自己的动态库（不含系统库和自身 id）。"""
    result = run(["otool", "-L", str(binary)])
    if result.returncode:
        raise SystemExit(f"otool 读不了 {binary}：{result.stderr.strip()[:200]}")
    return parse_otool(result.stdout)


def resign(path):
    """改过 Mach-O 之后原签名失效，必须重签，否则 macOS 拒绝加载。"""
    result = run(["codesign", "--force", "--sign", "-", str(path)])
    if result.returncode:
        raise SystemExit(f"重签失败 {path}：{result.stderr.strip()[:200]}")


def bundle_macho(source, bin_dir, lib_dir, collected):
    """把一个可执行文件连同它的非系统依赖拷进来，引用改成相对路径。

    Homebrew 的 ffmpeg 链接着几十个 /opt/homebrew/... 的 dylib，
    直接拷可执行文件到别人电脑上必然起不来。这里递归收集，
    全部改成 @loader_path 相对引用，包搬到哪都能自洽。
    """
    dest = bin_dir / Path(source).name
    shutil.copy2(source, dest)
    dest.chmod(0o755)
    pending = [dest]
    while pending:
        current = pending.pop()
        for dep in dependencies(current):
            name = Path(dep).name
            target = lib_dir / name
            if name not in collected:
                if not Path(dep).is_file():
                    raise SystemExit(f"{current.name} 依赖 {dep}，但这个文件不存在。")
                shutil.copy2(dep, target)
                target.chmod(0o755)
                collected[name] = dep
                run(["install_name_tool", "-id", f"@loader_path/{name}", str(target)])
                pending.append(target)
            rel = relative_ref(current.parent, name, lib_dir)
            result = run(["install_name_tool", "-change", dep, rel, str(current)])
            if result.returncode:
                raise SystemExit(f"重定位失败 {current.name} → {dep}：{result.stderr.strip()[:200]}")
    return dest


def install_ffmpeg(bin_dir, lib_dir):
    print("[3/5] ffmpeg / ffprobe")
    collected = {}
    for name in ("ffmpeg", "ffprobe"):
        source = need(name)
        bundle_macho(source, bin_dir, lib_dir, collected)
        print(f"      {name} ← {source}")
    for name in sorted(collected):
        resign(lib_dir / name)
    for name in ("ffmpeg", "ffprobe"):
        resign(bin_dir / name)
    print(f"      连带 {len(collected)} 个依赖库")
    return collected


def install_visionocr(bin_dir):
    print("[4/5] visionocr")
    need("xcrun")
    source = ROOT / "scripts/src/visionocr.swift"
    dest = bin_dir / "visionocr"
    result = run(["xcrun", "swiftc", "-O", str(source),
                  "-framework", "Vision", "-framework", "AppKit", "-o", str(dest)])
    if result.returncode:
        raise SystemExit(f"编译失败：\n{result.stderr[-1500:]}")
    print(f"      已编译 → {dest.relative_to(OUT)}")
    return dest


# ─────────────────────────────────────────────── 组装与自检

def manifest(lock, ytdlp_version, libs):
    return {
        "python": lock["python"],
        "python_source": lock["url"],
        "python_sha256": lock["sha256"],
        "yt_dlp": ytdlp_version,
        "ffmpeg_libs": libs,
        "host": platform.mac_ver()[0] or platform.platform(),
        "note": "转写模型不在包内，首次使用时下载。",
    }


def selftest(python, bin_dir):
    """在假装没有 ~/.vx 的条件下，确认包内这套自己能跑起来。

    PATH 清成空目录：只要有一处还在偷偷用本机的 ffmpeg 或 yt-dlp，
    这里就会暴露，而不是等用户在干净的 Mac 上才发现。
    """
    print("[5/5] 自检（PATH 清空，只用包内的东西）")
    with tempfile.TemporaryDirectory() as empty:
        env = dict(os.environ, PATH=empty, VX_RUNTIME=str(OUT))
        checks = [
            ("python", [str(python), "-c", "import truststore, yt_dlp"]),
            ("yt-dlp", [str(bin_dir / "yt-dlp"), "--version"]),
            ("ffmpeg", [str(bin_dir / "ffmpeg"), "-version"]),
            ("ffprobe", [str(bin_dir / "ffprobe"), "-version"]),
        ]
        bad = []
        for name, cmd in checks:
            result = run(cmd, env=env)
            if result.returncode:
                bad.append(f"{name}: {(result.stderr or result.stdout).strip()[:200]}")
            else:
                print(f"      ✓ {name}")
        # 内核也要能在这套运行时下报出正确的路径
        result = run([str(python), str(ROOT / "scripts/src/vx_runtime.py")], env=env)
        if result.returncode:
            bad.append(f"vx_runtime: {result.stderr.strip()[:200]}")
        elif str(bin_dir / "ffmpeg") not in result.stdout:
            bad.append("vx_runtime 没有解析到包内的 ffmpeg：\n" + result.stdout)
        else:
            print("      ✓ vx_runtime 解析到包内工具")
        if bad:
            raise SystemExit("自检未通过：\n  " + "\n  ".join(bad))


def size_of(path):
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return f"{total / 1024 / 1024:.0f} MB"


def check_only():
    print("环境检查（不下载、不写文件）\n")
    print(f"  平台      {platform.platform()}")
    print(f"  机器      {platform.machine()}")
    if platform.system() != "Darwin":
        print("\n  ✗ 组装必须在 macOS 上跑：需要 otool、install_name_tool、codesign、swiftc。")
    for name in ("otool", "install_name_tool", "codesign", "xcrun", "ffmpeg", "ffprobe"):
        found = shutil.which(name)
        print(f"  {'✓' if found else '✗'} {name:18s} {found or '缺失'}")
    print(f"  {'✓' if LOCK.is_file() else '✗'} 版本锁            "
          f"{LOCK.relative_to(ROOT) if LOCK.is_file() else '缺失，先跑 --update'}")
    if LOCK.is_file():
        lock = json.loads(LOCK.read_text())
        print(f"      Python {lock.get('python')}  {lock.get('sha256', '')[:16]}…")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="只报告环境")
    parser.add_argument("--update", action="store_true", help="联网解析并锁定 Python 版本")
    args = parser.parse_args()

    if args.check:
        check_only()
        return 0
    if args.update:
        update_lock()
        return 0

    if platform.system() != "Darwin":
        raise SystemExit("组装必须在 macOS 上跑：需要 otool、install_name_tool、codesign、swiftc。\n"
                         "先用 --check 看环境。")
    for name in ("otool", "install_name_tool", "codesign", "xcrun"):
        need(name)

    lock = load_lock()
    if OUT.exists():
        shutil.rmtree(OUT)
    bin_dir = OUT / "bin"
    lib_dir = OUT / "lib"
    for d in (bin_dir, lib_dir):
        d.mkdir(parents=True)

    python = install_python(lock)
    ytdlp_version = install_packages(python)
    write_ytdlp_shim(bin_dir)
    libs = install_ffmpeg(bin_dir, lib_dir)
    install_visionocr(bin_dir)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest(lock, ytdlp_version, sorted(libs)), ensure_ascii=False, indent=2) + "\n")
    selftest(python, bin_dir)

    print(f"\n运行时已就绪：{OUT}")
    print(f"体积 {size_of(OUT)}（不含转写模型）")
    print("下一步：python3 macos-app/build.py 把它打进 .app。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
