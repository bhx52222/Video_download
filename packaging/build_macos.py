"""Build a relocatable macOS App from a validated local build environment."""
import hashlib,json,os,plistlib,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'macos-app'))
from check_backend import require_current
require_current()
PYTHON=Path(os.environ.get('SHIYING_BUILD_PYTHON',str(Path.home()/'.vx/venv/bin/python')))
APP=ROOT/'outputs/拾影视频下载器-1.5独立版.app'
if APP.exists():shutil.rmtree(APP)  # Only the generated build output.
R=APP/'Contents/Resources'; M=APP/'Contents/MacOS'
for p in (R,M):p.mkdir(parents=True,exist_ok=True)
base=Path(subprocess.check_output([str(PYTHON),'-c','import sys;print(sys.base_prefix)'],text=True).strip())
site=Path(subprocess.check_output([str(PYTHON),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip())
shutil.copytree(base,R/'runtime',dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
dest=R/'runtime/lib/python3.12/site-packages'
shutil.copytree(site,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
# yt-dlp's separate uv environment contains EJS and browser-cookie dependencies.
yt=Path.home()/'.local/share/uv/tools/yt-dlp/lib/python3.12/site-packages'
if not yt.exists():
    yt=next((Path.home()/'.local/share/uv/tools/yt-dlp/lib').glob('python*/site-packages'))
shutil.copytree(yt,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(ROOT/'macos-app/backend',R/'backend',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for n in ('runner.py','downie_bridge.py','wx_bridge.py','使用说明.html','视频号连接说明.html'):
    shutil.copy2(ROOT/'macos-app'/n,R/n)
helper=ROOT/'macos-app/external/wx_channels_download'
manifest=json.loads((helper/'provenance.json').read_text())
assert hashlib.sha256((helper/'wx_video_download').read_bytes()).hexdigest()==manifest['binary_sha256']
shutil.copytree(ROOT/'macos-app/external',R/'external',dirs_exist_ok=True)
tools=R/'tools';tools.mkdir(exist_ok=True)
# Copy dynamic dependencies with loader-relative references; never rely on Homebrew at runtime.
seen={}; mapping=[]
def bundle_binary(source,target=None):
    source=Path(source).resolve()
    if source in seen:return seen[source]
    target=target or tools/'lib'/source.name
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and source not in seen and any(v==target for v in seen.values()):raise RuntimeError('dylib name collision: '+str(source))
    shutil.copy2(source,target);target.chmod(0o755);seen[source]=target
    out=subprocess.check_output(['otool','-L',str(source)],text=True)
    subprocess.run(['codesign','--remove-signature',str(target)],capture_output=True)
    for line in out.splitlines()[1:]:
        dep=line.strip().split(' (',1)[0]
        if dep.startswith(('/usr/lib/','/System/')):continue
        resolved=dep
        if dep.startswith('@loader_path/'):
            resolved=str(source.parent/dep[len('@loader_path/'):])
        elif dep.startswith('@rpath/'):
            candidate=source.parent/dep[len('@rpath/'):]
            if not candidate.exists():raise RuntimeError('unresolved dependency: '+dep+' in '+str(source))
            resolved=str(candidate)
        elif not dep.startswith('/'):
            raise RuntimeError('unresolved dependency: '+dep)
        if Path(resolved).resolve()==source:continue
        copied=bundle_binary(resolved)
        rel=os.path.relpath(copied,target.parent)
        subprocess.run(['install_name_tool','-change',dep,'@loader_path/'+rel,str(target)],check=True,capture_output=True)
    subprocess.run(['install_name_tool','-id','@loader_path/'+target.name,str(target)],capture_output=True)
    mapping.append({'file':str(target.relative_to(R)),'build_source':str(source),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    return target
for name in ('ffmpeg','ffprobe','deno'):
    source=shutil.which(name)
    if not source:raise RuntimeError('missing build tool '+name)
    bundle_binary(source,tools/name)
for name in ('visionocr','vx-wx-decrypt'):
    bundle_binary(Path.home()/'.vx/bin'/name,tools/name)
(tools/'yt-dlp').write_text('#!/bin/bash\nexec "$(dirname "$0")/../runtime/bin/python3" -B -m yt_dlp "$@"\n');(tools/'yt-dlp').chmod(0o755)
# Strip build-host-specific paths from distributable manifest.
(R/'runtime-manifest.json').write_text(json.dumps([{k:v for k,v in x.items() if k!='build_source'} for x in mapping],indent=2))
subprocess.run(['xcrun','swiftc','-swift-version','5','-target','arm64-apple-macos14.0','-O','-framework','AppKit',*[str(ROOT/'macos-app'/n) for n in ('App.swift','LinkTools.swift','WxPanel.swift')],'-o',str(M/'Shiying')],check=True)
icon=ROOT/'work/macos-icon';icon.mkdir(parents=True,exist_ok=True)
subprocess.run(['xcrun','swiftc','-framework','AppKit',str(ROOT/'macos-app/Icon.swift'),'-o',str(icon/'builder')],check=True)
subprocess.run([str(icon/'builder'),str(icon/'App.iconset')],check=True)
subprocess.run(['iconutil','-c','icns',str(icon/'App.iconset'),'-o',str(R/'App.icns')],check=True)
info={'CFBundleExecutable':'Shiying','CFBundleIdentifier':'local.beibei.shiying.standalone','CFBundleName':'拾影视频下载器','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.5','CFBundleVersion':'7','CFBundleIconFile':'App','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication'}
(APP/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
# Sign Mach-O objects individually inside-out, then the complete bundle.
for p in sorted(R.rglob('*'),key=lambda p:len(p.parts),reverse=True):
    if not p.is_file() or p.is_symlink():continue
    with p.open('rb') as f:magic=f.read(4)
    if magic in (b'\xcf\xfa\xed\xfe',b'\xce\xfa\xed\xfe',b'\xca\xfe\xba\xbe'):
        identity=subprocess.check_output(['otool','-D',str(p)],text=True).splitlines()
        if len(identity)>1:
            subprocess.run(['install_name_tool','-id','@loader_path/'+p.name,str(p)],check=True,capture_output=True)
        subprocess.run(['codesign','--force','--sign','-',str(p)],check=True,capture_output=True)
subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
print(APP)
