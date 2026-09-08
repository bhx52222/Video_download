import importlib.util,json,sys,tempfile,copy
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
SRC=Path(__file__).resolve().parent/'src'
sys.path.insert(0,str(SRC));s=importlib.util.spec_from_file_location('vx',SRC/'vx.py');vx=importlib.util.module_from_spec(s);s.loader.exec_module(vx)
with tempfile.TemporaryDirectory() as td:
 with patch.object(vx,'run',side_effect=[SimpleNamespace(returncode=1,stderr='Requested format is not available',stdout=''),SimpleNamespace(returncode=0,stderr='',stdout='{"id":"sample"}')]):
  raw,err=vx.fetch_meta_cached('https://www.bilibili.com/video/BV123','chrome',Path(td))
  assert raw['_vx_browser']=='none'
 # Instagram tries none first: specifically exercise authenticated non-global branch too.
 with patch.object(vx,'run',side_effect=[SimpleNamespace(returncode=1,stderr='Requested format is not available',stdout=''),SimpleNamespace(returncode=0,stderr='',stdout='{"id":"sample"}')]):
  raw,err,used=vx.fetch_meta_multi('https://www.douyin.com/video/123','chrome',attempts=1)
  assert used=='none' and raw['_vx_browser']=='none'
assert '--cookies-from-browser' not in vx.ytdlp_base('https://youtube.com/watch?v=x','chrome')
vx.YOUTUBE_COOKIES=True
assert '--cookies-from-browser' in vx.ytdlp_base('https://youtube.com/watch?v=x','chrome')
vx.YOUTUBE_COOKIES=False
print('PASS anonymous fallback propagates to cache/download, explicit YouTube cookie option')
from yt_dlp import YoutubeDL
formats=[
 {'format_id':'h264-1080','height':1080,'width':1920,'vcodec':'avc1.640028','acodec':'none','ext':'mp4','protocol':'https','url':'https://example.com/1080','tbr':2500},
 {'format_id':'vp9-2160','height':2160,'width':3840,'vcodec':'vp9','acodec':'none','ext':'webm','protocol':'https','url':'https://example.com/2160','tbr':7000},
 {'format_id':'hls-1080','height':1080,'vcodec':'avc1','acodec':'mp4a','ext':'mp4','protocol':'m3u8_native','url':'https://example.com/hls','tbr':9000},
 {'format_id':'audio','vcodec':'none','acodec':'mp4a.40.2','ext':'m4a','protocol':'https','url':'https://example.com/a','abr':128}]
for res,expected in [(1080,'h264-1080+audio'),(2160,'vp9-2160+audio')]:
 with YoutubeDL({'quiet':True,'no_warnings':True,'format':vx.build_format_selector(res),'format_sort':[f'proto:https',f'res:{res}','vcodec:h264','acodec:m4a','br']}) as y:
  result=y.process_ie_result({'id':'test','title':'test','formats':copy.deepcopy(formats)},download=False)
  assert result['format_id']==expected,result['format_id']
# Only a 4K direct stream and 1080 HLS: must fall back to HLS, not violate height cap.
with YoutubeDL({'quiet':True,'no_warnings':True,'format':vx.build_format_selector(1080)}) as y:
 result=y.process_ie_result({'id':'test','title':'test','formats':[copy.deepcopy(formats[i]) for i in [1,2,3]]},download=False)
 assert result['height']==1080,result
print('PASS format selection: 1080 H264, 2160 VP9, HLS fallback respects known height cap')
