from pathlib import Path
import sys,time
R=Path(sys.executable).resolve().parent.parent
sys.path.insert(0,str(R/'backend'))
from vx_runtime import configure
assert configure(R)
from vx import asr_parakeet
started=time.monotonic()
segments=asr_parakeet(Path(sys.argv[1]))
text=' '.join(s[2] for s in segments)
assert 'video' in text.lower() and 'english' in text.lower(),text
print('PASS actual bundled Windows English ASR:',text,'seconds=',round(time.monotonic()-started,1),flush=True)
