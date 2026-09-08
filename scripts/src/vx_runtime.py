#!/usr/bin/env python3
"""运行时定位：内核要用的 Python、二进制和状态目录在哪。

为什么单独一个模块：这些路径原来硬编码在五个文件里（vx.py、vx_wxchannels.py、
vx_grab.py、App.swift、WxPanel.swift），全部写死 `~/.vx`。要做「下载即用」的
一体化安装包，App 内自带一份运行时，这些路径就得能整体换掉。

分两类，不要混：

  运行时（只读）  Python、ffmpeg、yt-dlp、visionocr、vx-wx-decrypt
                 一体化包里在 .app 内；否则在 ~/.vx。由 VX_RUNTIME 指定。

  状态（可写）    抓流候选清单、命令入口
                 永远在 ~/.vx，因为 .app 内部不可写，而且用户重装 App 不该
                 丢掉这些。由 VX_STATE 指定。

默认行为和改造前一致：两个环境变量都不设时，全部落在 ~/.vx。
"""
import os
import shutil
from pathlib import Path

# 一体化包由 App 设置 VX_RUNTIME 指向 .app/Contents/Resources/runtime。
# 不设就是老路径，行为与改造前完全相同。
_DEFAULT = Path.home() / ".vx"


def runtime_home():
    """只读运行时的根目录。"""
    value = os.environ.get("VX_RUNTIME")
    return Path(value).expanduser() if value else _DEFAULT


def state_home():
    """可写状态目录。永远不在 .app 内部——那里不可写。"""
    value = os.environ.get("VX_STATE")
    return Path(value).expanduser() if value else _DEFAULT


def bin_dir():
    return runtime_home() / "bin"


def tool(name, required=False):
    """找一个可执行文件。

    顺序：运行时的 bin/ → PATH。返回可直接交给 subprocess 的字符串。

    找不到时，required=False 就原样返回名字——让 subprocess 自己去 PATH 里碰运气，
    报错信息比这里提前抛更贴近现场（用户看到的是 ffmpeg 自己的报错）。
    required=True 才抛，用于确实无法降级的场合。
    """
    candidate = bin_dir() / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    if required:
        raise FileNotFoundError(
            f"找不到 {name}。一体化包应在 {bin_dir()} 内自带；"
            f"依赖本机环境的版本请按 docs/ENVIRONMENT.md 安装。")
    return name


def python():
    """跑内核用的 Python。

    一体化包内自带一份；否则回退到 ~/.vx/venv/bin/python。
    """
    for candidate in (runtime_home() / "python/bin/python3",
                      runtime_home() / "venv/bin/python"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return str(_DEFAULT / "venv/bin/python")


def cookie_python():
    """读浏览器 Cookie 的那个子进程用的 Python。

    它需要 import yt_dlp。一体化包里主运行时就装了 yt-dlp，直接用；
    依赖本机环境时，yt-dlp 装在 uv 的工具环境里，是另一个解释器。
    """
    bundled = runtime_home() / "python/bin/python3"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return str(bundled)
    return str(Path.home() / ".local/share/uv/tools/yt-dlp/bin/python")


def describe():
    """给诊断脚本和"环境检查"用的一张表。不做判断，只报事实。"""
    rows = {
        "runtime_home": str(runtime_home()),
        "state_home": str(state_home()),
        "bundled": os.environ.get("VX_RUNTIME") is not None,
        "python": python(),
        "cookie_python": cookie_python(),
    }
    for name in ("ffmpeg", "ffprobe", "yt-dlp", "visionocr", "vx-wx-decrypt"):
        resolved = tool(name)
        rows[name] = resolved if os.path.sep in resolved else f"{resolved}（未找到，靠 PATH）"
    return rows


if __name__ == "__main__":
    for key, value in describe().items():
        print(f"{key:16s} {value}")
