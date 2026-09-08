"""Offline contract and media tests; no browser cookies or internet required."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
SRC = Path(__file__).resolve().parent / 'src'
sys.path.insert(0, str(SRC))
import vx_wxchannels as wx
import vx_tiktok as tt
spec = importlib.util.spec_from_file_location('vx', SRC/'vx.py')
vx = importlib.util.module_from_spec(spec); spec.loader.exec_module(vx)

class Response:
    def __init__(self, obj): self.obj = obj
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, *a): return json.dumps(self.obj).encode()

url = 'https://www.tiktok.com/@test/video/123'
valid = {'code':0,'data':{'id':'123','duration':2,'play':'https://media.example/video.mp4'}}
with patch.object(tt.urllib.request, 'urlopen', return_value=Response(valid)) as network:
    assert tt.fetch_tikwm(url)['id'] == '123'
    assert 'Cookie' not in dict(network.call_args.args[0].header_items())
for payload in [{'code':1}, {'code':0,'data':{'id':'999','play':'https://example.com/v'}},
                {'code':0,'data':{'id':'123','images':['one']}},
                {'code':0,'data':{'id':'123','play':'http://example.com/v'}}]:
    with patch.object(tt.urllib.request, 'urlopen', return_value=Response(payload)):
        try: tt.fetch_tikwm(url); raise AssertionError('invalid result accepted')
        except ValueError: pass
print('PASS TikWM identity, collection, API error, HTTPS and no-cookie contract')
share = 'https://weixin.qq.com/sph/test'
assert vx.platform_of(share) == 'wxchannel'
for bad in ['https://evil.test/sph/test','https://weixin.qq.com.evil.test/sph/test','http://weixin.qq.com/sph/test']:
    assert not wx.is_share_url(bad)
feed = {'data':{'feedInfo':{'videoUrl':'https://finder.video.qq.com/v','decodeKey':str(2**64-1),
                          'description':'test'},'authorInfo':{'nickname':'test'}}}
parsed = {'code':0,'data':{'playable_url':'https://channels.weixin.qq.com/finder-preview/pages/feed?eid=e&token=t'}}
with patch.object(wx, 'read_cookie', return_value='secret'), patch.object(wx, 'post_json', side_effect=[parsed, feed]) as request:
    assert wx.fetch_profile(share)['key'] == str(2**64-1)
    assert request.call_args_list[0].args[-1] == 'secret'
    assert len(request.call_args_list[1].args) == 3
with patch.object(wx, 'read_cookie', return_value=''), patch.object(wx, 'post_json') as request:
    try: wx.fetch_profile(share); raise AssertionError('missing auth accepted')
    except ValueError: pass
    request.assert_not_called()
print('PASS WeChat URL scope, uint64 preservation, credentials limited to Yuanbao, missing auth')

with tempfile.TemporaryDirectory() as td:
    root=Path(td); plain=root/'plain.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1',
                    '-c:v','libx264',str(plain)],check=True)
    # Include a tail beyond the encrypted prefix and exercise uint64 boundary seeds.
    blob=(bytes(range(256))*600)+b'end'
    for key in ('0','18446744073709551615'):
        p=root/'vector.bin';p.write_bytes(blob)
        wx.decrypt_file(p,key)
        assert p.read_bytes()[:131072] != blob[:131072]
        assert p.read_bytes()[131072:] == blob[131072:]
        wx.decrypt_file(p,key);assert p.read_bytes()==blob
    encrypted=root/'encrypted.mp4';shutil.copy(plain,encrypted);wx.decrypt_file(encrypted,'18446744073709551615')
    profile={'url':'https://finder.video.qq.com/v','key':'18446744073709551615','title':'Test', 'author':'Author','created':None}
    args=argparse.Namespace(cookies='none',dry_run=False,title=None,author=None,published=None)
    def download(url,dest,**kw):shutil.copyfile(encrypted,dest);return True,None
    def local(path,opts,lib):
        assert path.read_bytes()==plain.read_bytes()
        assert opts.source_url==share and opts.as_platform=='wxchannel'
        return 'ok'
    with patch.object(wx,'fetch_profile',return_value=profile), patch.object(vx,'download_direct',side_effect=download), patch.object(vx,'process_local',side_effect=local):
        assert wx.process_share(share,args,root/'ok',vx)=='ok'
        assert not hasattr(args, 'media_url')
    with patch.object(wx,'fetch_profile',return_value=dict(profile,key='3')),patch.object(vx,'download_direct',side_effect=download),patch.object(vx,'process_local') as archive:
        assert wx.process_share(share,args,root/'bad',vx)=='failed'
        archive.assert_not_called()
    assert not list(root.glob('*/.vx-wx-*'))
print('PASS ISAAC64 uint64 keys, encrypted prefix/tail, real MP4 decode, wrong-key rejection, temp cleanup')

with tempfile.TemporaryDirectory() as td:
    fallback={'id':'123','title':'test','extractor':'tikwm','_vx_play_url':'https://example.com/v'}
    with patch.object(sys,'argv',['vx',url,'--tiktok-backend','auto','--dry-run','--lib',td]),patch.object(vx,'fetch_meta_cached',return_value=(None,'direct failure')),patch.object(tt,'fetch_tikwm',return_value=fallback) as api:
        vx.main()
        api.assert_called_once_with(url)
    with patch.object(sys,'argv',['vx',url,'--dry-run','--lib',td]),patch.object(vx,'fetch_meta_cached',return_value=(None,'direct failure')),patch.object(tt,'fetch_tikwm') as api:
        try: vx.main();raise AssertionError('failure exited successfully')
        except SystemExit as exc: assert exc.code==1
        api.assert_not_called()
print('PASS explicit auto fallback routing; default direct never sends URL to third party')
