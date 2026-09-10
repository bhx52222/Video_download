"""Spawn with usable termination signals, including while the parent masks them.

The caller keeps its mask until it has registered the returned process. On POSIX
an exec trampoline clears inherited masks before executing the real command.
This avoids Python preexec_fn callbacks after fork in a threaded process.
"""
import os
import subprocess
import sys

_UNMASK_EXEC = (
    "import os,signal,sys; "
    "signal.pthread_sigmask(signal.SIG_SETMASK, set()); "
    "os.execv(sys.argv[1], sys.argv[1:])"
)


def spawn(cmd, **kwargs):
    if os.name != 'nt':
        # The runner passes an absolute interpreter path; preserve argv verbatim.
        cmd = [sys.executable, '-I', '-B', '-c', _UNMASK_EXEC, *cmd]
    return subprocess.Popen(cmd, **kwargs)
