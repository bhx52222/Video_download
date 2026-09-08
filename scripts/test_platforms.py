import importlib.util,sys,tempfile,subprocess,json
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parent/'src/vx.py'
spec=importlib.util.spec_from_file_location('vx',P);vx=importlib.util.module_from_spec(spec);spec.loader.exec_module(vx)
for url,expected in {
 'https://www.instagram.com/reel/abc/':'instagram','https://instagram.com/p/abc/':'instagram',
 'https://vm.tiktok.com/abc/':'tiktok','https://vt.tiktok.com/abc/':'tiktok','https://www.tiktokv.com/share/video/123/':'tiktok',
 'https://www.tiktok.com/@a/video/123':'tiktok','https://mp.weixin.qq.com/s/abc':'wxarticle',
 'https://channels.weixin.qq.com/x':'wxchannel','https://m.weibo.cn/1':'weibo',
 'https://example.com/?next=https://www.tiktok.com':'example','https://notinstagram.com/a':'notinstagram'
}.items():assert vx.platform_of(url)==expected,(url,vx.platform_of(url))
assert vx.guess_lang({'platform':'tiktok','title':'English caption'})=='en'
assert vx.guess_lang({'platform':'instagram','title':'中文标题'})=='zh'
assert '--user-agent' not in vx.ytdlp_base('https://www.tiktok.com/@a/video/123','none')
assert '--user-agent' in vx.ytdlp_base('https://www.bilibili.com/video/BV123','none')
print('PASS platform domains, short links, misleading URL rejection, language routing')
with tempfile.TemporaryDirectory() as td:
 root=Path(td); f=root/'batch.txt';f.write_text('   # comment\n'+'\n'.join('https://example.com/'+str(i) for i in range(12))+'\nhttps://example.com/0\n')
 def process(url,args):return 'failed' if url.endswith('/5') else 'skipped'
 with patch.object(sys,'argv',['vx','-f',str(f),'--lib',str(root/'batch'),'--sleep','0']),patch.object(vx,'process',side_effect=process) as mocked:
  try:vx.main()
  except SystemExit as e:assert e.code==1
  assert mocked.call_count==12
 report=json.loads(next((root/'batch/.runs').glob('*.json')).read_text());assert report['tally']=={'skipped':11,'failed':1}
 print('PASS 12-item batch: dedup, comments, failure isolation, nonzero exit, JSON result')
 silent=root/'silent.mp4'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=2','-c:v','libx264',str(silent)],check=True)
 r=subprocess.run([sys.executable,str(P),str(silent),'--lib',str(root/'silentlib'),'--interval','1'],capture_output=True,text=True)
 assert r.returncode==0,r.stdout+r.stderr
 meta=json.loads(next((root/'silentlib').glob('*/meta.json')).read_text())
 assert meta['text']['quality']=='unavailable' and meta['text']['source']=='none'
 assert len(list((root/'silentlib').glob('*/frames/*.jpg')))>0
 print('PASS silent video: archived with frames, unavailable text honestly recorded')
