"""Downie handoff contract. Launching is performed by the native App, not a shell."""
import json,time,uuid,subprocess
from pathlib import Path
from urllib.parse import urlsplit,urlencode
MEDIA={'.mp4','.mkv','.webm','.mov','.m4v'}

def youtube_url(url):
    p=urlsplit(url);host=(p.hostname or '').lower()
    return p.scheme=='https' and not p.username and not p.password and (host=='youtu.be' or host=='youtube.com' or host.endswith('.youtube.com'))

def make_job(url,folder,token):
    if not youtube_url(url):raise ValueError('Downie 备用仅接收 HTTPS YouTube 链接')
    dest=Path(folder).resolve()/'.external-downie'/uuid.uuid4().hex
    dest.mkdir(parents=True,exist_ok=False)
    job={'url':url,'destination':str(dest),'token':token}
    (dest/'source.json').write_text(json.dumps({'url':url,'status':'waiting'},ensure_ascii=False))
    return job

def scheme(job):
    return 'downie://XUOpenURL?'+urlencode({'url':job['url'],'destination':job['destination'],'postprocessing':'mp4'})

def ready_media(folder):
    folder=Path(folder)
    if any(p.suffix.lower() in {'.downiepart','.part','.tmp'} for p in folder.iterdir()):return None
    files=[p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in MEDIA and p.stat().st_size>0]
    return files[0] if len(files)==1 else None

def wait_media(job,cancelled,emit,timeout=600):
    deadline=time.monotonic()+timeout;last=None;stable=0;next_log=0
    while time.monotonic()<deadline and not cancelled():
        p=ready_media(job['destination'])
        key=(str(p),p.stat().st_size,p.stat().st_mtime_ns) if p else None
        stable=stable+1 if key and key==last else 0;last=key
        if stable>=2:
            check=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(p)],capture_output=True,text=True,timeout=20)
            try:valid=check.returncode==0 and any(s['codec_type']=='video' for s in json.loads(check.stdout).get('streams',[]))
            except (ValueError,KeyError):valid=False
            if valid:return p
        if time.monotonic()>=next_log:
            emit('等待 Downie 完成；如弹出画质/字幕选择，请在 Downie 中选择。取消只停止拾影等待。')
            next_log=time.monotonic()+20
        time.sleep(.5)
    return None
