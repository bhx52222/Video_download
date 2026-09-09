#!/usr/bin/env python3
"""跨平台的子进程组管理。取消任务时必须连子进程一起停掉。

为什么不能直接 proc.terminate()：内核会再拉起 yt-dlp，yt-dlp 又会拉起
ffmpeg。只杀直接子进程，孙子进程会变成孤儿继续下载和写文件——用户点了
取消，磁盘还在涨。所以必须让子进程自成一组，然后整组终止。

两个平台的做法完全不同，没有共同子集：

  POSIX    start_new_session 让子进程成为会话领导，killpg 按进程组号整组发信号
  Windows  没有进程组信号这回事。CREATE_NEW_PROCESS_GROUP 建组，
           终止靠 taskkill /T 遍历进程树

所以这里按平台分支，并把分支规则做成能在任意机器上测的纯函数——
Windows 那条路要是只有到了 Windows 才第一次执行，错了才发现就太晚。
"""
import os
import signal
import subprocess
import sys
from contextlib import contextmanager

WINDOWS = os.name == "nt"

# 非 Windows 的 Python 里没有这个常量，取不到就用 Win32 的定义值。
# 直接写 subprocess.CREATE_NEW_PROCESS_GROUP 会让本模块在 POSIX 上
# import 就炸，而 POSIX 恰恰是现在唯一在跑的平台。
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def spawn_kwargs(windows=WINDOWS):
    """让子进程自成一组，好整组终止。"""
    if windows:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_plan(pid, windows=WINDOWS):
    """终止一棵进程树的步骤，按先礼后兵的顺序。

    每一步是 ("signal", 信号) 或 ("run", 命令行)。
    调用方在两步之间等一会儿，给进程留下收尾的机会——直接强杀会留下
    写了一半的媒体文件。
    """
    if windows:
        # Windows 没有进程组信号。taskkill /T 才会遍历子树；
        # 不带 /F 是请求关闭，带 /F 是强制。
        return [("run", ["taskkill", "/T", "/PID", str(pid)]),
                ("run", ["taskkill", "/T", "/F", "/PID", str(pid)])]
    return [("signal", signal.SIGTERM), ("signal", signal.SIGKILL)]


@contextmanager
def shielded(windows=WINDOWS):
    """在这段期间屏蔽终止信号。

    用于 Popen 前后那一小段：进程已经创建、但 child 变量还没赋值时收到
    SIGTERM，取消逻辑就会漏掉这个子进程，它继续在后台跑。

    Windows 没有对应机制，也没有这个竞态（信号模型完全不同），直接放行。
    """
    if windows or not hasattr(signal, "pthread_sigmask"):
        yield
        return
    blocked = {signal.SIGTERM, signal.SIGINT}
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, mask)


def _clear_inherited_mask():
    """在子进程里、exec 之前把信号掩码清空。

    被阻塞的信号掩码会被子进程继承。父进程为了消除竞态而屏蔽 SIGTERM
    的那一小段里创建的子进程，会带着这份屏蔽跑完一生——之后 killpg 发的
    SIGTERM 对它完全无效，只有杀不掉的 SIGKILL 有用。

    后果不是"杀不死"，是"只能强杀"：用户点取消要白等宽限期，yt-dlp 和
    ffmpeg 没机会收尾，留下写了一半的 .part 文件。实测子进程掩码为
    0000000000004002（SIGTERM+SIGINT），发 SIGTERM 后状态仍是 S。
    """
    signal.pthread_sigmask(signal.SIG_SETMASK, set())


def spawn(cmd, **kwargs):
    """启动一个可以整组终止的子进程。"""
    if not WINDOWS and hasattr(signal, "pthread_sigmask"):
        # 只做一次 pthread_sigmask，是 async-signal-safe 的，
        # preexec_fn 在多线程程序里的那些警告不适用于这种调用。
        kwargs.setdefault("preexec_fn", _clear_inherited_mask)
    with shielded():
        return subprocess.Popen(cmd, **spawn_kwargs(), **kwargs)


def terminate_tree(proc, grace=3, windows=WINDOWS):
    """终止整棵进程树。已经退出的返回 False，动过手的返回 True。"""
    if proc is None or proc.poll() is not None:
        return False
    for index, (kind, payload) in enumerate(kill_plan(proc.pid, windows)):
        try:
            if kind == "signal":
                os.killpg(proc.pid, payload)
            else:
                subprocess.run(payload, capture_output=True, timeout=15)
        except (ProcessLookupError, PermissionError):
            return True          # 已经没了，或者不归我们管，都不必再试
        except (OSError, subprocess.SubprocessError):
            pass                 # 这一步没成，还有下一步兜底
        # 最后一步之后不用再等，调用方自己 wait
        if index + 1 == len(kill_plan(proc.pid, windows)):
            break
        try:
            proc.wait(timeout=grace)
            return True
        except subprocess.TimeoutExpired:
            continue
    return True


def install_handlers(callback):
    """注册终止信号。返回实际注册上的信号名，供诊断用。

    Windows 上 SIGTERM 收不到控制台关闭之类的事件，能注册的很有限；
    注册不上的静默跳过，不能因此让程序起不来。
    """
    installed = []
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, callback)
            installed.append(name)
        except (ValueError, OSError, RuntimeError):
            continue
    return installed


if __name__ == "__main__":
    print(f"平台        {'Windows' if WINDOWS else 'POSIX'} ({sys.platform})")
    print(f"spawn 参数  {spawn_kwargs()}")
    print(f"终止步骤    {kill_plan(12345)}")
