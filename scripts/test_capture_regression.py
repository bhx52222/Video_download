import importlib.util, tempfile, threading, subprocess, json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
P=Path(__file__).resolve().parent/'src'
def module(name):
 s=importlib.util.spec_from_file_location(name,P/(name+'.py')); m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
listener=module('vx_listener')
with tempfile.TemporaryDirectory() as td:
 root=Path(td).resolve(); listener.STORE=root/'captures.jsonl'
 (root/'sub.srt').write_text('1\n00:00:00,000 --> 00:00:02,000\nThis is a reproducible capture pipeline test.\n\n2\n00:00:02,000 --> 00:00:04,000\nThe embedded subtitle must survive download.\n')
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=25','-f','lavfi','-i','sine=frequency=440','-i',str(root/'sub.srt'),'-t','4','-c:v','libx264','-c:a','aac','-c:s','mov_text','-metadata:s:s:0','language=eng',str(root/'media.mp4')],check=True)
 data=(root/'media.mp4').read_bytes(); listener.MIN_BYTES=10000
 class H(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_HEAD(self):self.send_error(405)
  def do_GET(self):
   if self.headers.get('User-Agent')!='vx-test-agent':self.send_error(403);return
   partial=bool(self.headers.get('Range'));body=data[:2] if partial else data
   self.send_response(206 if partial else 200);self.send_header('Content-Type','video/mp4');self.send_header('Content-Length',str(len(body)))
   if self.path.startswith('/encrypted'): self.send_header('X-encflag','1')
   if partial:self.send_header('Content-Range',f'bytes 0-1/{len(data)}')
   self.end_headers();self.wfile.write(body)
 server=ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
 url=f'http://127.0.0.1:{server.server_port}/media.mp4'
 for sig in ('old','new'):listener.record({'url':url+'?sig='+sig,'ua':'vx-test-agent'})
 rows=[json.loads(x) for x in listener.STORE.read_text().splitlines()];assert len(rows)==1 and 'sig=new' in rows[0]['url'];print('PASS HEAD 405 fallback, Range total size, refreshed signature')
 vx=module('vx'); target=root/'encrypted.mp4'
 ok,reason=vx.download_direct(url.replace('/media.mp4','/encrypted.mp4'),target,user_agent='vx-test-agent')
 assert not ok and 'X-encflag' in reason and not target.exists()
 print('PASS encrypted response rejected before media is accepted')
 cmd=[str(Path.home()/'.vx/venv/bin/python'),str(P/'vx.py'),'--media-url',url,'--user-agent','vx-test-agent','--as','kuaishou','--title','Capture test','--lang','en','--no-frames','--lib',str(root/'library')]
 for i in range(2):
  r=subprocess.run(cmd,text=True,capture_output=True);print(r.stdout);print(r.stderr[-1000:]);assert r.returncode==0
 dirs=list((root/'library').glob('kuaishou_*'));assert len(dirs)==1
 out=dirs[0];assert (out/'.done').exists();assert (out/'subs/transcript.srt').exists()
 meta=json.loads((out/'meta.json').read_text());assert meta['url']==url and meta['published_at'] is None
 assert len((root/'library/index.csv').read_text().splitlines())==2
 print('PASS real HTTP download -> ffprobe -> embedded subtitles -> metadata/index/.done; repeated capture deduplicated')
 server.shutdown()
