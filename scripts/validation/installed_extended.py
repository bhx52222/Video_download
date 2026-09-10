from pathlib import Path
import sys,subprocess,tempfile,json
R=Path(sys.executable).resolve().parent.parent
sys.path.insert(0,str(R/'backend'))
from vx_runtime import configure
assert configure(R)
subprocess.run([str(R/"tools/deno.exe"),"--version"],check=True,timeout=30)
subprocess.run([str(R/"tools/yt-dlp.exe"),"--version"],check=True,timeout=30)
from PIL import Image,ImageDraw,ImageFont
with tempfile.TemporaryDirectory(prefix='Shiying-acceptance-') as td:
 root=Path(td); frame=root/'ocr.png'
 im=Image.new('RGB',(1280,720),'white');draw=ImageDraw.Draw(im)
 font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',48)
 draw.text((80,510),'VIDEO DOWNLOAD TEST 12345',font=font,fill='black');im.save(frame)
 p=subprocess.run([sys.executable,'-X','utf8','-B',str(R/'tools/visionocr.py'),'--roi','0,0,1,0.35',str(frame)],capture_output=True,text=True,encoding='utf-8',timeout=180)
 assert p.returncode==0,p.stderr
 data=json.loads(p.stdout);words=' '.join(row['text'] for row in data[0]['lines'])
 assert 'DOWNLOAD' in words and '12345' in words,words
 print('PASS actual OCR recognition and bottom ROI:',words,flush=True)
 chinese=root/'chinese.png'
 im=Image.new('RGB',(1280,720),'white')
 ImageDraw.Draw(im).text((80,510),'视频下载测试 12345',font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',48),fill='black');im.save(chinese)
 p=subprocess.run([sys.executable,'-X','utf8','-B',str(R/'tools/visionocr.py'),'--roi','0,0,1,0.35',str(chinese)],capture_output=True,text=True,encoding='utf-8',timeout=180)
 assert p.returncode==0,p.stderr
 words=' '.join(row['text'] for row in json.loads(p.stdout)[0]['lines'])
 assert '下载' in words and '12345' in words,words
 print('PASS actual Chinese OCR:',words,flush=True)
 payload={'text':'https://www.kuaishou.com/f/X-8YjOXuCJVPO1ig','folder':str(root/'network'),'mode':0,'cookies':'none'}
 p=subprocess.run([sys.executable,'-X','utf8','-B',str(R/'runner.py')],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',timeout=300)
 print(p.stdout,flush=True)
 assert p.returncode==0,p.stderr
 assert list((root/'network').rglob('.downloaded'))
 for video in (root/'network').rglob('*.mp4'):
  subprocess.run([str(R/'tools/ffmpeg.exe'),'-v','error','-xerror','-i',str(video),'-f','null','-'],check=True,timeout=120)
 print('PASS fresh Kuaishou download and full decode',flush=True)
