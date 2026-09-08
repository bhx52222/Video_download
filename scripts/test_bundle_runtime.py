#!/usr/bin/env python3
"""bundle_runtime 里纯逻辑部分的回归。不联网、不调用 macOS 工具。

组装脚本本身只能在 Mac 上跑，但它出错最隐蔽的三处都是纯字符串逻辑，
而且都属于"不报错、装到别人电脑上才起不来"那一类：

  match_asset               挑错构建 → 包里塞进跑不起来或体积翻倍的 Python
  parse_otool / parse_rpaths / expand_ref
                            漏掉一类引用 → 该拷的库没拷，启动就 Library not loaded
  relative_ref              写反一层 → 本机测着好好的，换台电脑就找不到 dylib

所以这些在这里测干净，Mac 上那一趟只需要验真实执行。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_runtime import match_asset, parse_otool, parse_rpaths, expand_ref, relative_ref

fail = []


def check(name, got, want):
    if got != want:
        fail.append(f"{name}\n    got  {got!r}\n    want {want!r}")


# ── 1. 资产匹配：真实发布里一次有上百个资产，形态都很像 ──
TAG = "20260115"
ASSETS = [
    # 要的就是这个
    f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
    # 同发布里的干扰项，每一条都差一点点
    f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only_stripped.tar.gz",
    f"cpython-3.12.9+{TAG}-x86_64-apple-darwin-install_only.tar.gz",
    f"cpython-3.12.9+{TAG}-aarch64-unknown-linux-gnu-install_only.tar.gz",
    f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-pgo+lto-full.tar.zst",
    f"cpython-3.13.1+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
    f"cpython-3.11.11+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
    f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only.tar.gz.sha256",
    f"cpython-3.12.9+20251201-aarch64-apple-darwin-install_only.tar.gz",  # 别的 tag
]
hit = match_asset(TAG, ASSETS)
check("挑中正确的构建", hit and hit["name"],
      f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only.tar.gz")
check("解析出版本号", hit and hit["python"], "3.12.9")

# 同一发布里有多个补丁版本时取最大的，不是取第一个碰到的
check("多个补丁版本取最大",
      match_asset(TAG, [
          f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
          f"cpython-3.12.11+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
          f"cpython-3.12.10+{TAG}-aarch64-apple-darwin-install_only.tar.gz",
      ])["python"], "3.12.11")

# 没有匹配项要返回 None 让调用方报错，不能瞎挑一个
check("没有 arm64 构建时返回 None",
      match_asset(TAG, [f"cpython-3.12.9+{TAG}-x86_64-apple-darwin-install_only.tar.gz"]), None)
check("空列表返回 None", match_asset(TAG, []), None)
# 系列号不能被当作前缀匹配：3.1 不该匹配上 3.12
check("3.1 不匹配 3.12",
      match_asset(TAG, [f"cpython-3.12.9+{TAG}-aarch64-apple-darwin-install_only.tar.gz"],
                  series="3.1"), None)

# ── 2. otool 输出解析：格式取自真实 ffmpeg 的依赖 ──
OTOOL = """/opt/homebrew/bin/ffmpeg:
\t/opt/homebrew/opt/x264/lib/libx264.164.dylib (compatibility version 0.0.0, current version 0.0.0)
\t/opt/homebrew/opt/lame/lib/libmp3lame.0.dylib (compatibility version 1.0.0, current version 1.0.0)
\t@rpath/libSomething.dylib (compatibility version 1.0.0, current version 1.0.0)
\t@loader_path/../lib/libOther.dylib (compatibility version 1.0.0, current version 1.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1345.100.2)
\t/System/Library/Frameworks/CoreVideo.framework/Versions/A/CoreVideo (compatibility version 1.2.0, current version 1.2.0)
"""
# @rpath 和 @loader_path 都必须留下来交给 expand_ref 解析。
# 上一版在这里把它们过滤掉了，结果 libwebp 用 @rpath 引的 libsharpyuv
# 根本没被拷进包，ffmpeg 一启动就 Library not loaded——真机实测暴露的。
check("@ 引用不能被过滤掉", parse_otool(OTOOL), [
    "/opt/homebrew/opt/x264/lib/libx264.164.dylib",
    "/opt/homebrew/opt/lame/lib/libmp3lame.0.dylib",
    "@rpath/libSomething.dylib",
    "@loader_path/../lib/libOther.dylib",
])
check("空输出不炸", parse_otool(""), [])
check("只有自身一行时无依赖", parse_otool("/opt/homebrew/bin/ffmpeg:\n"), [])

# ── 3. 相对引用：写反一层，本机好好的，换台电脑就起不来 ──
lib = Path("/x/runtime/lib")
check("可执行文件要跨出 bin/", relative_ref(Path("/x/runtime/bin"), "libx264.164.dylib", lib),
      "@loader_path/../lib/libx264.164.dylib")
check("dylib 之间是同级", relative_ref(lib, "libx264.164.dylib", lib),
      "@loader_path/libx264.164.dylib")

# ── 4. LC_RPATH 解析：形态取自真实 otool -l 输出 ──
OTOOL_L = """/opt/homebrew/lib/libwebp.7.dylib:
Load command 12
      cmd LC_LOAD_DYLIB
  cmdsize 56
     name /usr/lib/libSystem.B.dylib (offset 24)
Load command 13
          cmd LC_RPATH
      cmdsize 40
         path /opt/homebrew/lib (offset 12)
Load command 14
          cmd LC_RPATH
      cmdsize 48
         path @loader_path/../lib (offset 12)
"""
check("读出两条 LC_RPATH", parse_rpaths(OTOOL_L),
      ["/opt/homebrew/lib", "@loader_path/../lib"])
check("没有 LC_RPATH 时为空", parse_rpaths("x:\nLoad command 0\n  cmd LC_UUID\n"), [])

# ── 5. 引用解析：@rpath / @loader_path / 绝对路径 ──
with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    (root / "opt/lib").mkdir(parents=True)
    (root / "cellar").mkdir()
    target = root / "opt/lib/libsharpyuv.0.dylib"
    target.write_text("x")
    source = root / "cellar/libwebp.7.dylib"
    source.write_text("x")

    # 这一条正是真机上炸掉的那种：libwebp 用 @rpath 引 libsharpyuv
    check("@rpath 按 LC_RPATH 解析",
          expand_ref("@rpath/libsharpyuv.0.dylib", source, [str(root / "opt/lib")]), target)
    check("@rpath 解析不到返回 None",
          expand_ref("@rpath/libnothing.dylib", source, [str(root / "opt/lib")]), None)
    check("没有 rpath 时 @rpath 返回 None",
          expand_ref("@rpath/libsharpyuv.0.dylib", source, []), None)

    # LC_RPATH 自己也可能写成 @loader_path/...，要先按源文件位置展开
    sibling = root / "cellar/libsibling.dylib"
    sibling.write_text("x")
    check("LC_RPATH 里的 @loader_path 要先展开",
          expand_ref("@rpath/libsibling.dylib", source, ["@loader_path"]), sibling)

    check("@loader_path 相对源文件原始位置",
          expand_ref("@loader_path/libsibling.dylib", source, []), sibling)
    check("绝对路径直接用", expand_ref(str(target), source, []), target)
    check("不存在的绝对路径返回 None",
          expand_ref(str(root / "nope.dylib"), source, []), None)

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS bundle_runtime：资产匹配（干扰项、多补丁版本、系列前缀）、"
      "otool 解析（保留 @ 引用）、LC_RPATH 读取、"
      "@rpath/@loader_path 按原始位置解析、dylib 相对引用层级")
