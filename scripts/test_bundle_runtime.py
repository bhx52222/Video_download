#!/usr/bin/env python3
"""bundle_runtime 里纯逻辑部分的回归。不联网、不调用 macOS 工具。

组装脚本本身只能在 Mac 上跑，但它出错最隐蔽的三处都是纯字符串逻辑，
而且都属于"不报错、装到别人电脑上才起不来"那一类：

  match_asset    挑错构建 → 包里塞进跑不起来或体积翻倍的 Python
  parse_otool    漏掉一类 → 该拷的库没拷，或者把系统库拷进来冲突
  relative_ref   写反一层 → 本机测着好好的，换台电脑就找不到 dylib

所以这三处在这里测干净，Mac 上那一趟只需要验真实执行。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_runtime import match_asset, parse_otool, relative_ref

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
check("只留需要打包的库", parse_otool(OTOOL), [
    "/opt/homebrew/opt/x264/lib/libx264.164.dylib",
    "/opt/homebrew/opt/lame/lib/libmp3lame.0.dylib",
])
check("空输出不炸", parse_otool(""), [])
check("只有自身一行时无依赖", parse_otool("/opt/homebrew/bin/ffmpeg:\n"), [])

# ── 3. 相对引用：写反一层，本机好好的，换台电脑就起不来 ──
lib = Path("/x/runtime/lib")
check("可执行文件要跨出 bin/", relative_ref(Path("/x/runtime/bin"), "libx264.164.dylib", lib),
      "@loader_path/../lib/libx264.164.dylib")
check("dylib 之间是同级", relative_ref(lib, "libx264.164.dylib", lib),
      "@loader_path/libx264.164.dylib")

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS bundle_runtime：资产匹配（干扰项、多补丁版本、系列前缀）、"
      "otool 解析（系统库与 @ 引用排除）、dylib 相对引用层级")
