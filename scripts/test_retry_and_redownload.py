import importlib.util,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
SRC=Path(__file__).resolve().parent/'src';sys.path.insert(0,str(SRC))
s=importlib.util.spec_from_file_location('vx',SRC/'vx.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
assert v.parse_target_list(' # comment\nhttps://youtu.be/a # 中文说明\nhttps://example.com/x#t=20\n')==['https://youtu.be/a','https://example.com/x#t=20']
for quote in ["'",'’']:
 with patch.object(v,'throttle'),patch.object(v,'run',side_effect=[SimpleNamespace(returncode=1,stdout='',stderr=f'Sign in to confirm you{quote}re not a bot'),SimpleNamespace(returncode=0,stdout='{"id":"sample"}',stderr='')]) as run:
  raw,err,br=v.fetch_meta_multi('https://youtube.com/watch?v=a','edge',attempts=1)
  assert br=='edge' and raw['_vx_force_cookies'] is True
  assert '--cookies-from-browser' not in run.call_args_list[0].args[0]
  assert '--cookies-from-browser' in run.call_args_list[1].args[0]
  assert '--cookies-from-browser' in v.ytdlp_base('https://youtube.com/watch?v=a',br,raw['_vx_force_cookies'])
with patch.object(v,'throttle'),patch.object(v,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr="Sign in to confirm you’re not a bot")) as run:
 assert v.fetch_meta('https://youtube.com/watch?v=a','none',1)[0] is None
 assert run.call_count==1
v._LAST_REQ.clear()
with patch.object(v.time,'monotonic',side_effect=[100,102,108]),patch.object(v.time,'sleep') as sleep:
 v.throttle('https://bilibili.com/video/a');v.throttle('https://b23.tv/b');sleep.assert_called_once_with(6)
with tempfile.TemporaryDirectory() as td:
 out=Path(td);(out/'media').mkdir()
 for name in ['a.mp4','b.webm','audio.wav']:(out/'media'/name).write_bytes(b'old')
 (out/'.done').write_text('old');(out/'.downloaded').write_text('old')
 moved=v.stash_media(out)
 assert moved.exists() and v.find_media(out) is None
 assert not (out/'.done').exists() and not (out/'.downloaded').exists()
 assert len(list(moved.parent.iterdir()))==5
# End-to-end orchestration with failed network replacement: do not leave old completion markers.
with tempfile.TemporaryDirectory() as td:
 args=SimpleNamespace(lib=td,cookies='none',refresh_meta=False,force=False,dry_run=False,redownload=True,download_only=True,max_res=1080)
 raw={'id':'sample','title':'sample','extractor':'youtube'}
 out=Path(td)/'youtube_sample';(out/'media').mkdir(parents=True);(out/'media/a.mp4').write_bytes(b'old');(out/'.done').touch()
 with patch.object(v,'fetch_meta_cached',return_value=(raw,None)),patch.object(v,'download',return_value=False) as download:
  assert v.process('https://youtube.com/watch?v=sample',args)=='failed'
  assert download.call_count==1
  assert not (out/'.done').exists() and list((out/'media/_replaced').rglob('a.mp4'))
print('PASS bot fallback both quotes, none opt-out, throttle, inline comments, redownload with completion marker and failure backup')
