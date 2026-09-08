import os,sys,subprocess,tempfile,json
from pathlib import Path
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'backend'))
from vx_runtime import configure
assert configure(R)
assert '.vx' not in sys.executable
import yt_dlp,truststore,funasr,faster_whisper,rapidocr_onnxruntime
with tempfile.TemporaryDirectory() as td:
    root=Path(td);media=root/'测试 & space.mp4'
    subprocess.run([str(R/'tools/ffmpeg.exe'),'-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-c:v','libx264',str(media)],check=True)
    payload={'text':str(media),'folder':str(root/'library'),'mode':0,'cookies':'none'}
    p=subprocess.run([sys.executable,'-B',str(R/'runner.py')],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,timeout=90)
    assert p.returncode==0,p.stdout+p.stderr
    assert list((root/'library').rglob('.downloaded'))
print('PASS installed runtime imports, bundled FFmpeg, Unicode local import and media validation')
