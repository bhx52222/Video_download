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
    # ${0%/*} 是 shell 内建的参数展开，不需要 dirname 之类的外部命令。
    # 上一版用 $(dirname "$0")，自检把 PATH 清空后就 command not found。
    shim.write_text('#!/bin/sh\n'
                    'here=${0%/*}\n'
                    'exec "$here/../python/bin/python3" -m yt_dlp "$@"\n')
    shim.chmod(0o755)
    return shim


# ─────────────────────────────────────────────── ffmpeg 与它的一串依赖

def parse_otool(text):
    """从 otool -L 的输出里挑出需要处理的依赖引用，原样返回。

    只排除两类：
      /usr/lib/、/System/  系统自带，拷进包反而可能和系统版本冲突
      第一行               是文件自己的路径，不是依赖

    **@ 开头的不能跳过。** 上一版跳过了它们，理由写的是"已经是相对引用"，
    这个判断只对 @loader_path 成立。@rpath/X 靠二进制里的 LC_RPATH 搜索
    路径才解析得出来，拷进包之后那些路径不再有效——实测 Homebrew 的
    libwebp.7.dylib 用 @rpath 引用 libsharpyuv.0.dylib，跳过它的结果是
    libsharpyuv 根本没被拷进来，ffmpeg 一启动就 Library not loaded。
    而 @loader_path 相对的是文件原来的位置，搬进 lib/ 之后同样要重算。
    """
    out = []
    for line in text.splitlines()[1:]:
        path = line.strip().split(" (")[0]
        if path and not path.startswith(SYSTEM_PREFIXES):
            out.append(path)
    return out


def parse_rpaths(text):
    """从 otool -l 的输出里读出 LC_RPATH。解析 @rpath/X 要靠它。

    加载命令的形态是三行一组：
        cmd LC_RPATH
        cmdsize 40
        path /opt/homebrew/lib (offset 12)
    """
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "cmd LC_RPATH":
            for follow in lines[i + 1:i + 4]:
                m = re.match(r"\s*path (.+?) \(offset \d+\)\s*$", follow)
                if m:
                    out.append(m.group(1))
                    break
    return out


def expand_ref(ref, source, rpaths):
    """把 otool 里的一条引用解析成真实文件路径，解析不出返回 None。

    source 必须是**依赖它的那个文件原来的位置**，不是拷贝之后的位置：
    @loader_path 和 @rpath 里的 @loader_path 都相对于原始目录，
    用拷贝后的位置去解析会全部落空。
    """
    source_dir = Path(source).parent

    def substitute(text):
        return (text.replace("@loader_path", str(source_dir))
                    .replace("@executable_path", str(source_dir)))

    if ref.startswith("@rpath/"):
        tail = ref[len("@rpath/"):]
        for entry in rpaths:
            candidate = Path(substitute(entry)) / tail
            if candidate.is_file():
                return candidate.resolve()
        return None
    if ref.startswith(("@loader_path/", "@executable_path/")):
        candidate = Path(substitute(ref))
        return candidate.resolve() if candidate.is_file() else None
    candidate = Path(ref)
    return candidate.resolve() if candidate.is_file() else None


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


def discover(sources):
    """从**原始位置**递归发现所有要打包的依赖。

    必须在原始位置做：@loader_path 和 @rpath 里的路径都相对于文件原来的
    目录，在拷贝后的文件上解析会全部落空——上一版就是这么错的。

    返回 (found, refs)：
      found  name -> 原始路径，需要拷进 lib/ 的库
      refs   原始路径 -> [(引用原文, 解析出的 name)]，改写时要按原文去 -change
    """
    found = {}
    refs = {}
    pending = [Path(s).resolve() for s in sources]
    roots = {str(p) for p in pending}
    seen = set()
    while pending:
        current = pending.pop()
        key = str(current)
        if key in seen:
            continue
        seen.add(key)
        listing = run(["otool", "-L", key])
        if listing.returncode:
            raise SystemExit(f"otool -L 读不了 {key}：{listing.stderr.strip()[:200]}")
        commands = run(["otool", "-l", key])
        if commands.returncode:
            raise SystemExit(f"otool -l 读不了 {key}：{commands.stderr.strip()[:200]}")
        rpaths = parse_rpaths(commands.stdout)
        entries = []
        for ref in parse_otool(listing.stdout):
            real = expand_ref(ref, current, rpaths)
            if real is None:
                raise SystemExit(
                    f"{Path(key).name} 依赖 {ref}，解析不到实际文件。\n"
                    f"  该文件的 LC_RPATH：{rpaths or '（没有）'}\n"
                    f"  这条依赖没打进包的话，装到别人电脑上会 Library not loaded。")
            entries.append((ref, real.name))
            if real.name not in found and str(real) not in roots:
                found[real.name] = real
                pending.append(real)
        refs[key] = entries
    return found, refs


def install_ffmpeg(bin_dir, lib_dir):
    """把 ffmpeg/ffprobe 连同非系统依赖拷进来，引用全改成相对路径。

    Homebrew 的 ffmpeg 链着几十个 /opt/homebrew/... 的库，还有一层
    @rpath 引用；只拷可执行文件在别人机器上必然起不来。这里把 lib/
    做成扁平自洽的一层：所有库放同一个目录，互相之间 @loader_path/<名字>，
    可执行文件 @loader_path/../lib/<名字>。
    """
    print("[3/5] ffmpeg / ffprobe")
    sources = []
    for name in ("ffmpeg", "ffprobe"):
        source = Path(need(name)).resolve()
        sources.append(source)
        print(f"      {name} ← {source}")
    found, refs = discover(sources)

    mapping = {}
    for source in sources:
        dest = bin_dir / source.name
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        mapping[str(source)] = dest
    for name, source in found.items():
        dest = lib_dir / name
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        mapping[str(source)] = dest

    for original, entries in refs.items():
        dest = mapping[original]
        if dest.parent == lib_dir:
            # 自身 id 也要改，否则别的库仍按旧的绝对路径找它
            result = run(["install_name_tool", "-id", f"@loader_path/{dest.name}", str(dest)])
            if result.returncode:
                raise SystemExit(f"改 id 失败 {dest.name}：{result.stderr.strip()[:200]}")
        for ref, name in entries:
            result = run(["install_name_tool", "-change", ref,
                          relative_ref(dest.parent, name, lib_dir), str(dest)])
            if result.returncode:
                raise SystemExit(f"重定位失败 {dest.name} → {ref}：{result.stderr.strip()[:200]}")

    for dest in mapping.values():
        resign(dest)
    print(f"      连带 {len(found)} 个依赖库，全部改为 @loader_path 相对引用")
    return sorted(found)


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
    print("[5/5] 自检（PATH 只留系统目录，模拟没装过任何东西的 Mac）")
    # 用 /usr/bin:/bin 而不是空目录：要验的是"不依赖 Homebrew 和 ~/.vx"，
    # 不是"不依赖 macOS 自带命令"。任何 Mac 都有 /usr/bin，清掉它反而
    # 制造出真实环境里不存在的失败（上一版就因此误报了 shim 的问题）。
    if True:
        env = dict(os.environ, PATH="/usr/bin:/bin", VX_RUNTIME=str(OUT))
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
