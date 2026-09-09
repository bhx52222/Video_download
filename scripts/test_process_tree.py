#!/usr/bin/env python3
"""vx_process 的回归。POSIX 分支真起进程验证，Windows 分支验规则。

最要紧的一条是"孙子进程不会变孤儿"：内核会拉起 yt-dlp，yt-dlp 又拉起
ffmpeg。只杀直接子进程的话，用户点了取消，ffmpeg 还在后台写文件。
这一条在 POSIX 上真起一棵进程树来验，不是模拟。

Windows 分支没法在这里执行，但它的规则是纯函数，照样测得了——
按 CLAUDE.md 硬规则 5，不能等到了 Windows 才第一次执行那条路。
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import vx_process

fail = []


def check(name, got, want):
    if got != want:
        fail.append(f"{name}\n    got  {got!r}\n    want {want!r}")


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── 1. 两个平台的 spawn 参数 ──
check("POSIX 用 start_new_session", vx_process.spawn_kwargs(windows=False),
      {"start_new_session": True})
check("Windows 用 CREATE_NEW_PROCESS_GROUP", vx_process.spawn_kwargs(windows=True),
      {"creationflags": vx_process.CREATE_NEW_PROCESS_GROUP})
# 常量取不到时要有正确的兜底值，不能是 0——那等于没建组
check("进程组标志不是 0", vx_process.CREATE_NEW_PROCESS_GROUP, 0x00000200)

# ── 2. 终止步骤：先礼后兵，两步都要有 ──
check("POSIX 先 TERM 后 KILL", vx_process.kill_plan(999, windows=False),
      [("signal", signal.SIGTERM), ("signal", signal.SIGKILL)])
# /T 是关键：不带它 taskkill 只杀这一个进程，子树照样活着
plan = vx_process.kill_plan(999, windows=True)
check("Windows 两步都带 /T", [step[1][:2] for step in plan],
      [["taskkill", "/T"], ["taskkill", "/T"]])
check("Windows 第二步才强制", "/F" in plan[0][1], False)
check("Windows 第二步是强制", "/F" in plan[1][1], True)
check("Windows 带上 pid", plan[0][1][-1], "999")

# ── 3. shielded 不能吞掉异常，也要还原信号掩码 ──
try:
    with vx_process.shielded():
        raise ValueError("穿过去")
    fail.append("shielded 吞掉了异常")
except ValueError:
    pass
if hasattr(signal, "pthread_sigmask"):
    before = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    with vx_process.shielded(windows=False):
        pass
    check("信号掩码被还原", signal.pthread_sigmask(signal.SIG_BLOCK, set()), before)
    # 声明成 Windows 时不能去碰 POSIX 的信号掩码
    with vx_process.shielded(windows=True):
        inside = signal.pthread_sigmask(signal.SIG_BLOCK, set())
    check("Windows 分支不动掩码", inside, before)

# ── 4. 真起一棵进程树，确认孙子进程也被带走 ──
if os.name != "nt":
    with tempfile.TemporaryDirectory() as td:
        pidfile = Path(td) / "grandchild.pid"
        # sh 是子进程，它 fork 出的 sleep 是孙子。只 terminate 子进程的话
        # 孙子会被 init 收养并继续跑——那正是要防的情况。
        script = f'sleep 300 & echo $! > {pidfile}; sleep 300'
        proc = vx_process.spawn(["sh", "-c", script],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if pidfile.is_file() and pidfile.read_text().strip():
                break
            time.sleep(0.05)
        grandchild = int(pidfile.read_text().strip())
        check("孙子进程起来了", alive(grandchild), True)

        acted = vx_process.terminate_tree(proc, grace=1)
        check("对活着的进程动了手", acted, True)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            fail.append("子进程没有在 10 秒内退出")

        for _ in range(100):
            if not alive(grandchild):
                break
            time.sleep(0.05)
        check("孙子进程也被带走了（不会变成孤儿继续下载）", alive(grandchild), False)

    # 这一条单独针对信号掩码继承：只发 SIGTERM，不给 SIGKILL 兜底。
    # 掩码泄漏时子进程对 SIGTERM 免疫，这里就会超时——而上面那条
    # "孙子被带走" 有 SIGKILL 兜底，抓不到"只能强杀"这种降级。
    proc = vx_process.spawn(["sleep", "300"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
        terminated = True
    except subprocess.TimeoutExpired:
        terminated = False
        proc.kill(); proc.wait()
    check("单靠 SIGTERM 就能终止（信号掩码没有泄漏给子进程）", terminated, True)

    with tempfile.TemporaryDirectory() as td2:
        pidfile2 = Path(td2) / "g2.pid"
        proc = vx_process.spawn(["sh", "-c", f'sleep 300 & echo $! > {pidfile2}; sleep 300'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        proc.kill(); proc.wait()
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        # 已经退出的进程不该被再动一次
        check("对已退出的进程返回 False", vx_process.terminate_tree(proc), False)
    check("None 不炸", vx_process.terminate_tree(None), False)

# ── 5. 信号注册：注册不上的静默跳过，不能让程序起不来 ──
installed = vx_process.install_handlers(signal.SIG_DFL)
check("至少注册上 SIGTERM", "SIGTERM" in installed, True)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
signal.signal(signal.SIGINT, signal.default_int_handler)

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS vx_process：两平台 spawn 参数与终止步骤、taskkill /T 子树遍历、"
      "信号掩码屏蔽与还原、真实进程树终止（孙子进程不留孤儿）、信号注册降级")
