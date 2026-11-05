import tempfile,sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent));import downie_bridge as d
from urllib.parse import urlsplit,parse_qs
with tempfile.TemporaryDirectory() as td:
 url='https://www.youtube.com/watch?v=jNQXAC9IVRw&t=2'
 job=d.make_job(url,td,'nonce');assert parse_qs(urlsplit(d.scheme(job)).query)['url']==[url]
 folder=Path(job['destination']);(folder/'fake.html').write_text('not media');assert d.ready_media(folder) is None
 media=folder/'sample.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=160x120:d=0.1','-c:v','libx264',str(media)],check=True)
 partial=folder/'sample.downiepart';partial.touch();assert d.ready_media(folder) is None;partial.unlink()
 assert d.wait_media(job,lambda:False,lambda m:None,timeout=5)==media
 assert d.wait_media(job,lambda:True,lambda m:None,timeout=5) is None
for u in ['http://youtube.com/watch?v=a','https://youtube.com.evil.test/v','https://youtube.com@evil.test/v','file:///tmp/test']:
 assert not d.youtube_url(u),u
print('PASS Downie URL encoding, source binding, partial/html exclusion, real media validation and cancellation')

# Integration contract: failed core -> handoff -> import; successful core never hands off.
import runner as r,io,contextlib
from unittest.mock import patch
for codes,expected_handoffs in [([1,0],1),([0],0),([1,1],1)]:
 with tempfile.TemporaryDirectory() as td:
  processes=[]
  class Process:
   def __init__(self,*a,**kw):
    self.stdout=io.StringIO('');self.code=codes[len(processes)];processes.append(a[0])
   def wait(self):return self.code
  media=Path(td)/'sample.mp4';media.touch()
  payload={'text':'https://youtu.be/test','folder':td,'youtube_backend':'auto','handoff_token':'nonce'}
  r.cancelled=False
  with patch.object(sys,'stdin',io.StringIO(json.dumps(payload))),patch.object(r.subprocess,'Popen',Process),patch.object(d,'wait_media',return_value=media) as wait,contextlib.redirect_stdout(io.StringIO()):
   result=r.main()
  assert wait.call_count==expected_handoffs
  assert result==(0 if codes[-1]==0 else 1)
  if expected_handoffs:
   cmd=processes[-1];assert cmd[cmd.index('--source-url')+1]==payload['text']
   assert cmd[cmd.index('--tool')+1]=='Downie 4'
print('PASS auto fallback only after failure; source preserved; failed import remains failed')

# 列表链接（内核退出码 3）不是下载失败，不能转交 Downie；列表选择按所选方式路由。
for selections,codes,expect_cmd in [
  ({},[3],'https://www.youtube.com/playlist?list=L'),
  ({'https://www.youtube.com/playlist?list=L':{'source_url':'https://www.youtube.com/playlist?list=L','choice':'single','current_url':'https://www.youtube.com/watch?v=a'}},[0],'https://www.youtube.com/watch?v=a'),
]:
 with tempfile.TemporaryDirectory() as td:
  processes=[]
  class Process:
   def __init__(self,*a,**kw):
    self.stdout=io.StringIO('');self.code=codes[len(processes)];processes.append(a[0])
   def wait(self):return self.code
  payload={'text':'https://www.youtube.com/playlist?list=L','folder':td,'youtube_backend':'auto','handoff_token':'nonce','playlists':list(selections.values())}
  r.cancelled=False
  with patch.object(sys,'stdin',io.StringIO(json.dumps(payload))),patch.object(r.subprocess,'Popen',Process),patch.object(d,'wait_media') as wait,patch.object(d,'make_job') as make,contextlib.redirect_stdout(io.StringIO()):
   result=r.main()
  assert not make.called and not wait.called,'列表不能转交 Downie'
  assert expect_cmd in processes[0],processes[0]
  assert result==(1 if codes[0] else 0)
with tempfile.TemporaryDirectory() as td:
 processes=[]
 class Process:
  def __init__(self,*a,**kw):self.stdout=io.StringIO('');processes.append(a[0])
  def wait(self):return 0
 entry={'index':1,'id':'a','title':'t','duration':1,'url':'https://www.youtube.com/watch?v=a','unavailable':False}
 playlist={'source_url':'https://www.youtube.com/playlist?list=L','platform':'youtube','id':'L','title':'T','uploader':'U','count':1,'entries':[entry],'choice':'all','selected':[1]}
 payload={'text':playlist['source_url'],'folder':td,'youtube_backend':'downie','handoff_token':'nonce','playlists':[playlist]}
 r.cancelled=False
 with patch.object(sys,'stdin',io.StringIO(json.dumps(payload))),patch.object(r.subprocess,'Popen',Process),patch.object(d,'make_job') as make,contextlib.redirect_stdout(io.StringIO()):
  assert r.main()==0
 assert not make.called and '--playlist-job' in processes[0]
 assert Path(processes[0][processes[0].index('--playlist-job')+1]).name=='job.json'
print('PASS collection never handed to Downie; single/all selections routed through the core')
