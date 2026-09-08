"""Run on Windows x64 with Python 3.12; produce a self-contained per-user installer."""
import hashlib,json,os,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'macos-app'))
from check_backend import require_current
require_current()
if sys.platform!='win32':raise SystemExit('Windows build host required')
# Keep dependency paths below legacy Windows installer path limits.
OUT=Path(os.environ['RUNNER_TEMP'])/'sy' if os.environ.get('RUNNER_TEMP') else ROOT/'outputs/Shiying-Windows'
R=OUT/'resources';R.mkdir(parents=True,exist_ok=True)
CACHE=ROOT/'work/downloads';CACHE.mkdir(parents=True,exist_ok=True)
provenance=[]
def download(url,name):
    p=CACHE/name
    if not p.exists():
        with urllib.request.urlopen(url,timeout=120) as r,p.open('wb') as f:shutil.copyfileobj(r,f)
    provenance.append({'url':url,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return p
py=download('https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip','python-embed.zip')
with zipfile.ZipFile(py) as z:z.extractall(R/'runtime')
(R/'runtime/python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\n../backend\nimport site\n')
site=R/'runtime/Lib/site-packages'
subprocess.run([sys.executable,'-m','pip','install','--target',str(site),'truststore','yt-dlp[default]','funasr','modelscope','faster-whisper','rapidocr-onnxruntime','pillow','srt','rich','tqdm','requests','soundfile'],check=True)
subprocess.run([sys.executable,'-m','pip','install','--upgrade','--target',str(site),'torch','torchaudio','--index-url','https://download.pytorch.org/whl/cpu'],check=True)
shutil.copytree(ROOT/'macos-app/backend',R/'backend',dirs_exist_ok=True)
for n in ('runner.py','downie_bridge.py','idm_bridge.py','wx_bridge.py'):
    shutil.copy2(ROOT/'macos-app'/n,R/n)
tools=R/'tools';tools.mkdir(exist_ok=True)
shutil.copy2(ROOT/'windows-app/visionocr.py',tools/'visionocr.py')
ff=download('https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip','ffmpeg.zip')
with zipfile.ZipFile(ff) as z:
    for n in z.namelist():
        if Path(n).name in ('ffmpeg.exe','ffprobe.exe'):(tools/Path(n).name).write_bytes(z.read(n))
        elif 'LICENSE' in n.upper() and not n.endswith('/'):
            (R/'licenses').mkdir(exist_ok=True);(R/'licenses'/('ffmpeg-'+Path(n).name)).write_bytes(z.read(n))
deno=download('https://github.com/denoland/deno/releases/download/v2.3.0/deno-x86_64-pc-windows-msvc.zip','deno.zip')
with zipfile.ZipFile(deno) as z:(tools/'deno.exe').write_bytes(z.read('deno.exe'))
wx=download('https://github.com/ltaoo/wx_channels_download/releases/download/v260907/wx_video_download_v260907_windows_x86_64.zip','wx.zip')
external=R/'external/wx_channels_download';external.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(wx) as z:
    candidates=[n for n in z.namelist() if Path(n).name=='wx_video_download.exe']
    if len(candidates)!=1:raise RuntimeError('Unexpected WX archive')
    binary=z.read(candidates[0]);(external/'wx_video_download.exe').write_bytes(binary)
shutil.copy2(ROOT/'macos-app/external/wx_channels_download/LICENSE',external/'LICENSE')
(external/'provenance.json').write_text(json.dumps({'version':'v260907','binary_sha256':hashlib.sha256(binary).hexdigest()}))
subprocess.run(['go','build','-o',str(tools/'vx-wx-decrypt.exe'),str(ROOT/'scripts/src/vendor/wxdecrypt/main.go'),str(ROOT/'scripts/src/vendor/wxdecrypt/decrypt.go')],check=True)
csc=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
subprocess.run([str(csc),'/nologo','/target:winexe','/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll','/out:'+str(OUT/'Shiying.exe'),str(ROOT/'windows-app/Shiying.cs')],check=True)
subprocess.run([str(csc),'/nologo','/target:exe','/out:'+str(tools/'yt-dlp.exe'),str(ROOT/'windows-app/ToolLauncher.cs')],check=True)
shutil.copy2(ROOT/'packaging/smoke_windows.py',R/'smoke_windows.py')
shutil.copytree(ROOT/'docs',R/'docs',dirs_exist_ok=True)
shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',R/'THIRD_PARTY_NOTICES.md')
(R/'provenance.json').write_text(json.dumps(provenance,indent=2))
iscc=Path(os.environ.get('ISCC',r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'))
subprocess.run([str(iscc),'/DBundleRoot='+str(OUT.resolve()),str(ROOT/'windows-app/installer.iss')],check=True)
