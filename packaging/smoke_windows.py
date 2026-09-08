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
    p=subprocess.run([sys.executable,'-X','utf8','-B',str(R/'runner.py')],input=json.dumps(payload),text=True,encoding='utf-8',capture_output=True,timeout=90)
    assert p.returncode==0,p.stdout+p.stderr
    assert list((root/'library').rglob('.downloaded'))
    for video in (root/'library').rglob('*.mp4'):
        subprocess.run([str(R/'tools/ffmpeg.exe'),'-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    from PIL import Image,ImageDraw,ImageFont
    frame=root/'ocr.png'
    im=Image.new('RGB',(1280,720),'white')
    ImageDraw.Draw(im).text((80,510),'VIDEO DOWNLOAD TEST 12345',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48),fill='black')
    im.save(frame)
    p=subprocess.run([sys.executable,'-X','utf8','-B',str(R/'tools/visionocr.py'),'--roi','0,0,1,0.35',str(frame)],capture_output=True,text=True,encoding='utf-8',timeout=180)
    assert p.returncode==0,p.stderr
    words=' '.join(row['text'] for row in json.loads(p.stdout)[0]['lines'])
    assert 'DOWNLOAD' in words and '12345' in words,words
print('PASS installed runtime imports, bundled FFmpeg, Unicode local import, full decode and actual OCR recognition')
