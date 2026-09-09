"""Real POSIX child/grandchild cooperative cancellation; no SIGKILL success path."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent/'src'))
from vx_process import spawn

if os.name == 'nt':
    print('SKIP POSIX signal test on Windows')
    raise SystemExit(0)
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    script=root/'cooperative child.py'
    script.write_text('''import signal,sys,time,subprocess
from pathlib import Path
root=Path(sys.argv[1]); role=sys.argv[2]
def stop(*_):
    (root/(role+'.stopped')).write_text('SIGTERM')
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
if role=='parent':
    subprocess.Popen([sys.executable,__file__,str(root),'grandchild'])
(root/(role+'.ready')).touch()
while True: time.sleep(.05)
''')
    mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
    try:
        p=spawn([sys.executable,str(script),str(root),'parent'],start_new_session=True)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,mask)
    try:
        deadline=time.monotonic()+10
        while not (root/'grandchild.ready').exists() and time.monotonic()<deadline:time.sleep(.02)
        assert (root/'grandchild.ready').exists(), 'children did not start'
        started=time.monotonic();os.killpg(p.pid,signal.SIGTERM)
        p.wait(timeout=2)
        while not (root/'grandchild.stopped').exists() and time.monotonic()-started<2:time.sleep(.02)
        assert p.returncode==0, p.returncode
        assert (root/'parent.stopped').read_text()=='SIGTERM'
        assert (root/'grandchild.stopped').read_text()=='SIGTERM'
        print(f'PASS parent and grandchild handled SIGTERM in {time.monotonic()-started:.3f}s; no SIGKILL')
    finally:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait()
