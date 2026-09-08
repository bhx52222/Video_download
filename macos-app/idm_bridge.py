"""IDM handoff uses a resolved progressive media URL, never a watch-page URL."""
import json,os,subprocess,time,uuid
from pathlib import Path
from urllib.parse import urlsplit

def executable():
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        for key in (r'Software\DownloadManager',r'Software\WOW6432Node\DownloadManager'):
            try:
                with winreg.OpenKey(hive,key) as k:
                    p=Path(winreg.QueryValueEx(k,'ExePath')[0])
                    if p.is_file() and p.name.lower()=='idman.exe':return p
            except OSError:pass
    for var in ('ProgramFiles(x86)','ProgramFiles'):
        p=Path(os.environ.get(var,''))/'Internet Download Manager/IDMan.exe'
        if p.is_file():return p
    raise RuntimeError('未找到 IDM，请先安装并激活 IDM；拾影不包含 IDM 授权。')

def resolve(source, config, core):
    cmd=core['ytdlp_base'](source,config.get('cookies','none'))+['--dump-single-json','--skip-download','--no-playlist','-f',f'b[protocol^=http][height<=?{int(config.get("max_res",1080))}]',source]
    r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=90)
    if r.returncode:raise RuntimeError('无法解析可供 IDM 下载的单文件音视频直链；IDM 不具备 Downie 的页面解析能力。')
    data=json.loads(r.stdout);url=data.get('url','');p=urlsplit(url)
    if p.scheme not in ('https','http') or not p.hostname or p.username or data.get('_type') in ('playlist','multi_video'):
        raise RuntimeError('未取得有效的单作品媒体地址')
    return url,data

def download(source,config,core,cancelled,emit):
    exe=executable();url,metadata=resolve(source,config,core)
    folder=Path(config['folder']).resolve()/'.external-idm'/uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'source.json').write_text(json.dumps({'url':source,'status':'waiting'}),encoding='utf-8')
    media=folder/'video.mp4'
    # No /q: do not shut down the user's IDM. Passing argv avoids shell expansion.
    subprocess.run([str(exe),'/d',url,'/p',str(folder),'/f',media.name,'/n'],check=True,timeout=30)
    last=None;stable=0;end=time.monotonic()+600
    emit('已发送 IDM 请求，等待有效视频。取消仅停止拾影等待，不取消 IDM 下载。')
    while time.monotonic()<end and not cancelled():
        key=(media.stat().st_size,media.stat().st_mtime_ns) if media.is_file() else None
        stable=stable+1 if key and key==last else 0;last=key
        if stable>=4:
            r=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(media)],capture_output=True,text=True,timeout=20)
            try:
                d=json.loads(r.stdout);types={s['codec_type'] for s in d['streams']}
                if r.returncode==0 and 'video' in types and float(d['format']['duration'])>0:return media,metadata
            except (ValueError,KeyError):pass
        time.sleep(.5)
    return None,metadata
