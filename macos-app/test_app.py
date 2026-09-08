import importlib.util,plistlib,json,subprocess,tempfile,sys,os,time,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('runner',ROOT/'runner.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.targets('分享 https://weixin.qq.com/sph/abc。\nhttps://weixin.qq.com/sph/abc')==['https://weixin.qq.com/sph/abc']
assert m.targets('bad input')==[]
with tempfile.TemporaryDirectory() as td:
 root=Path(td)
 bookmark=root/'share.webloc';bookmark.write_bytes(plistlib.dumps({'URL':'https://weixin.qq.com/sph/abc'}))
 assert m.targets(str(bookmark))==['https://weixin.qq.com/sph/abc']
 shortcut=root/'share.url';shortcut.write_text('[InternetShortcut]\nURL=https://weixin.qq.com/sph/abc\n')
 assert m.targets(str(shortcut))==['https://weixin.qq.com/sph/abc']
 cmd=m.command('https://youtube.com/watch?v=test',{'folder':td,'max_res':2160,'youtube_cookies':True})
 assert '--youtube-cookies' in cmd and cmd[cmd.index('--max-res')+1]=='2160'
 plain=root/'a $(touch never).mp4'
 subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-c:v','libx264',str(plain)],check=True)
 backend=Path(os.environ.get('SHIYING_TEST_APP',str(ROOT.parent/'outputs/拾影视频下载器-1.4.1测试版.app')))/'Contents/Resources/runner.py'
 payload={'text':str(plain),'folder':str(root/'lib'),'mode':0,'cookies':'none'}
 r=subprocess.run([sys.executable,"-B",str(backend)],input=json.dumps(payload),capture_output=True,text=True,timeout=60)
 assert r.returncode==0,r.stdout+r.stderr
 meta=next((root/'lib').glob('*/meta.json'));d=meta.parent
 assert (d/'.downloaded').exists() and not (d/'.done').exists()
 assert json.loads(meta.read_text())['text']['quality']=='not_requested'
 payload['mode']=2
 r=subprocess.run([sys.executable,"-B",str(backend)],input=json.dumps(payload),capture_output=True,text=True,timeout=60)
 assert r.returncode==0,r.stdout+r.stderr
 assert (d/'.done').exists() and list((d/'frames').glob('*.jpg')), r.stdout+r.stderr
 payload.update(mode=0,redownload=True)
 r=subprocess.run([sys.executable,"-B",str(backend)],input=json.dumps(payload),capture_output=True,text=True,timeout=60)
 assert r.returncode==0,r.stdout+r.stderr
 assert not (d/'.done').exists() and (d/'.downloaded').exists()
 assert list((d/'media/_replaced').rglob('*.mp4'))
 print('PASS app local redownload bypasses completion marker and preserves old media')
 print('PASS app bridge: share parsing, shell-safe paths, download-only -> later OCR completion')
 # Own test process tree: cancellation must stop descendants and return 130.
 fake=root/'fake.py';pidfile=root/'child.pid'
 fake.write_text('import subprocess,sys,time\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(120)"])\nopen('+repr(str(pidfile))+',"w").write(str(p.pid))\ntime.sleep(120)\n')
 boot=root/'boot.py';boot.write_text('import sys\nsys.path.insert(0,'+repr(str(ROOT))+')\nimport runner\nfrom pathlib import Path\nrunner.CORE=Path('+repr(str(fake))+')\nsys.exit(runner.main())\n')
 p=subprocess.Popen([sys.executable,str(boot)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 p.stdin.write(json.dumps({'text':'https://example.com/v','folder':str(root/'cancel'),'cookies':'none'}));p.stdin.close()
 for _ in range(100):
  if pidfile.exists():break
  time.sleep(.05)
 assert pidfile.exists()
 child=int(pidfile.read_text());p.terminate();p.wait(timeout=8)
 assert p.returncode==130,p.stdout.read()
 stat=subprocess.run(['ps','-p',str(child),'-o','stat='],capture_output=True,text=True).stdout.strip()
 assert not stat or stat.startswith('Z'),stat
 print('PASS app cancellation stops subprocess group and reports cancelled')
