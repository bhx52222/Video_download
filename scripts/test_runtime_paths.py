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
    #
    # 这几条必须把 PATH 指到一个空目录再断言。上一版直接断言返回裸名字，
    # 结果在装了全套环境的 Mac 上失败：机器上真有 ~/.vx/bin/yt-dlp 和
    # /opt/homebrew/bin/ffprobe，tool() 找到并返回它们——那正是设计要的行为，
    # 是断言依赖了"跑测试的机器上没装这些工具"。测试不能这样写。
    empty = Path(td) / "empty-path"
    empty.mkdir()
    saved_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(empty)
    try:
        check("PATH 里也没有时返回裸名字", rt.tool("yt-dlp"), "yt-dlp")
        check("包内不可执行的不算数", rt.tool("ffprobe"), "ffprobe")
        try:
            rt.tool("绝对不存在的工具", required=True)
            fail.append("required=True 应该抛 FileNotFoundError，但没抛")
        except FileNotFoundError:
            pass
    finally:
        os.environ["PATH"] = saved_path

    # 不管机器上装没装，都不能把包内那个不可执行的文件当成工具用。
    check("不可执行的文件永远不被选中",
          rt.tool("ffprobe") != str(root / "bin/ffprobe"), True)

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

# ── 6. Windows 规则：在任意平台上都要能测 ──
#
# 平台判断被做成函数参数就是为了这一节。若靠 os.name 分支，
# 这些断言在 macOS 上恒走 POSIX 分支，等于没测；而 Windows 那条路
# 只有真到了 Windows 才第一次执行——那时错了才发现就太晚。
import vx_runtime as vr

check("Windows 解释器在顶层 python.exe",
      vr._python_candidates(Path("/r"), windows=True),
      [Path("/r/python/python.exe"), Path("/r/venv/Scripts/python.exe")])
check("POSIX 解释器在 bin/",
      vr._python_candidates(Path("/r"), windows=False),
      [Path("/r/python/bin/python3"), Path("/r/venv/bin/python")])

# 只按裸名字找，在 Windows 上必然落空然后静默退回 PATH——
# 一体化包里那等于用了用户机器上的 ffmpeg，正是打包要消灭的情况。
check("Windows 优先找 .exe", vr._tool_names("ffmpeg", windows=True), ["ffmpeg.exe", "ffmpeg"])
check("POSIX 不加后缀", vr._tool_names("ffmpeg", windows=False), ["ffmpeg"])

saved_local = os.environ.get("LOCALAPPDATA")
os.environ["LOCALAPPDATA"] = r"C:\Users\tester\AppData\Local"
try:
    check("Windows 状态目录按系统惯例",
          vr._state_default(windows=True), Path(r"C:\Users\tester\AppData\Local") / "Shiying")
finally:
    os.environ.pop("LOCALAPPDATA", None)
    if saved_local is not None:
        os.environ["LOCALAPPDATA"] = saved_local
# 没有 LOCALAPPDATA 也要给得出路径，不能崩
check("缺 LOCALAPPDATA 时退回主目录下的标准位置",
      vr._state_default(windows=True), HOME / "AppData/Local/Shiying")
# 这条是防回归：macOS 已验收的版本靠 ~/.vx，一个字节都不能变
check("POSIX 状态目录仍是 ~/.vx", vr._state_default(windows=False), HOME / ".vx")

fresh()  # 别把环境变量留给后面的测试

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS vx_runtime：POSIX 行为不变、一体化包路径切换、状态与运行时分离、"
      "缺失工具退回 PATH、venv 布局兼容、Windows 布局规则（.exe 后缀、"
      "顶层 python.exe、%LOCALAPPDATA%）")
