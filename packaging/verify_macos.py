"""Exercise the actual bundled runtime under a temporary home and restricted PATH."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('app',type=Path);p.add_argument('--url');a=p.parse_args()
R=a.app.resolve()/'Contents/Resources';py=R/'runtime/bin/python3';tools=R/'tools'
with tempfile.TemporaryDirectory(prefix='shiying-clean-') as td:
    home=Path(td);env={'HOME':td,'PATH':str(tools)+':/usr/bin:/bin','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','LANG':'en_US.UTF-8'}
    def run(args,**kw):return subprocess.run(args,env=env,text=True,capture_output=True,check=True,**kw)
    print(run([str(py),'-I','-B','-c','import sys,yt_dlp,funasr,parakeet_mlx;print(sys.executable)'],timeout=120).stdout,flush=True)
    for tool in ('ffmpeg','ffprobe','deno'):
        run([str(tools/tool),'--version' if tool=='deno' else '-version'],timeout=20)
    media=home/'test space.mp4'
    run([str(tools/'ffmpeg'),'-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-c:v','libx264',str(media)],timeout=20)
    for source,name in [(str(media),'local')]+([(a.url,'network')] if a.url else []):
        payload={'text':source,'folder':str(home/name),'mode':0,'cookies':'none'}
        result=run([str(py),'-B',str(R/'runner.py')],input=json.dumps(payload),timeout=240)
        print(result.stdout,flush=True)
        assert list((home/name).rglob('.downloaded'))
        for video in (home/name).rglob('*.mp4'):
            run([str(tools/'ffmpeg'),'-v','error','-xerror','-i',str(video),'-f','null','-'],timeout=120)
    assert not (home/'.vx').exists(), 'legacy runtime directory was used'
    print('PASS actual bundled runtime: fresh HOME, restricted PATH, local/media validation; no ~/.vx',flush=True)
# Audit every Mach-O object, including Python extension modules.
external=[]
for f in R.rglob('*'):
    if not f.is_file() or f.is_symlink():continue
    with f.open('rb') as h:magic=h.read(4)
    if magic not in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe'):continue
    output=subprocess.check_output(['otool','-L',str(f)],text=True)
    for line in output.splitlines()[1:]:
        if line.rstrip().endswith(':'):continue
        dep=line.strip().split(' (',1)[0]
        if dep.startswith('/') and not dep.startswith(('/usr/lib/','/System/')):external.append((str(f.relative_to(R)),dep))
if external:raise RuntimeError('External dynamic libraries: '+str(external))
subprocess.run(['codesign','--verify','--deep','--strict',str(a.app)],check=True)
print('PASS Mach-O external-path audit and signature')
