#!/usr/bin/env python3
"""vx_runtime 的回归测试。不联网、不碰真实 ~/.vx。

重点是两条：
  1. 不设环境变量时，结果必须和"写死 ~/.vx"的老行为完全一致——
     这条守住了，一体化包的改造就不会弄坏现有依赖本机环境的版本。
  2. 设了 VX_RUNTIME 之后，只读运行时整体搬走，可写状态仍留在 ~/.vx。
     .app 内部不可写，状态跟着进去必然出错。
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

fail = []


def check(name, got, want):
    if got != want:
        fail.append(f"{name}\n    got  {got!r}\n    want {want!r}")


def fresh(**env):
    """用指定环境变量重新导入模块。模块级读环境变量的写法必须这样测。"""
    for key in ("VX_RUNTIME", "VX_STATE"):
        os.environ.pop(key, None)
    os.environ.update(env)
    import vx_runtime
    return importlib.reload(vx_runtime)


HOME = Path.home()

# ── 1. 默认：与改造前写死 ~/.vx 的行为一致 ──
rt = fresh()
check("默认 runtime_home", rt.runtime_home(), HOME / ".vx")
check("默认 state_home", rt.state_home(), HOME / ".vx")
check("默认 bin_dir", rt.bin_dir(), HOME / ".vx/bin")
check("默认 python", rt.python(), str(HOME / ".vx/venv/bin/python"))
check("默认 cookie_python", rt.cookie_python(),
      str(HOME / ".local/share/uv/tools/yt-dlp/bin/python"))
check("默认 describe 不标记打包", rt.describe()["bundled"], False)

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "runtime"
    (root / "bin").mkdir(parents=True)
    (root / "python/bin").mkdir(parents=True)
    fake_ffmpeg = root / "bin/ffmpeg"
    fake_ffmpeg.write_text("#!/bin/sh\n")
    fake_ffmpeg.chmod(0o755)
    fake_python = root / "python/bin/python3"
    fake_python.write_text("#!/bin/sh\n")
    fake_python.chmod(0o755)
    # 不可执行的同名文件不能被当成工具
    (root / "bin/ffprobe").write_text("not executable")

    # ── 2. 一体化包：只读运行时搬走，可写状态留在 ~/.vx ──
    rt = fresh(VX_RUNTIME=str(root))
    check("打包 runtime_home", rt.runtime_home(), root)
    check("打包后状态仍在 ~/.vx", rt.state_home(), HOME / ".vx")
    check("打包 python 用包内的", rt.python(), str(fake_python))
    check("打包 cookie_python 用包内的", rt.cookie_python(), str(fake_python))
    check("打包 ffmpeg 用包内的", rt.tool("ffmpeg"), str(fake_ffmpeg))
    check("describe 标记为打包", rt.describe()["bundled"], True)

    # ── 3. 包内没有的工具退回 PATH，不硬失败 ──
    check("缺失工具返回裸名字", rt.tool("yt-dlp"), "yt-dlp")
    check("不可执行的不算数", rt.tool("ffprobe"), "ffprobe")
    try:
        rt.tool("绝对不存在的工具", required=True)
        fail.append("required=True 应该抛 FileNotFoundError，但没抛")
    except FileNotFoundError:
        pass

    # ── 4. 状态目录可单独指定（测试和多用户场景要用）──
    with tempfile.TemporaryDirectory() as sd:
        rt = fresh(VX_RUNTIME=str(root), VX_STATE=sd)
        check("VX_STATE 生效", rt.state_home(), Path(sd))
        check("VX_STATE 不影响 runtime", rt.runtime_home(), root)

    # ── 5. venv 布局也认（依赖本机环境的版本用的就是这个）──
    venv_root = Path(td) / "vxhome"
    (venv_root / "venv/bin").mkdir(parents=True)
    venv_python = venv_root / "venv/bin/python"
    venv_python.write_text("#!/bin/sh\n")
    venv_python.chmod(0o755)
    rt = fresh(VX_RUNTIME=str(venv_root))
    check("venv 布局的 python", rt.python(), str(venv_python))

fresh()  # 别把环境变量留给后面的测试

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS vx_runtime：默认行为不变、一体化包路径切换、状态与运行时分离、"
      "缺失工具退回 PATH、venv 布局兼容")
