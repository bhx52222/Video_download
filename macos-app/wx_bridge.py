"""Local API adapter. Does not change system proxies, trust certificates or log in."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 2_000_000

class BridgeError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def api(path, port=2022):
    if type(port) is not int or not 1 <= port <= 65535:
        raise BridgeError('invalid_port', '请输入有效的本机 API 端口')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open('http://127.0.0.1:'+str(port)+path, timeout=15) as response:
            raw = response.read(MAX_BYTES+1)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise BridgeError('http_error', f'连接服务返回 HTTP {exc.code}') from exc
    except (urllib.error.URLError, OSError) as exc:
        raise BridgeError('service_unavailable', '未连接到服务，请先启动连接服务或检查 API 端口') from exc
    if len(raw)>MAX_BYTES:
        raise BridgeError('invalid_response', '接口响应过大')
    try: data=json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise BridgeError('invalid_response', '该端口没有返回兼容的 JSON 接口') from exc
    if not isinstance(data,dict) or type(data.get('code')) is not int:
        raise BridgeError('invalid_response', '该端口不是兼容的视频号 API')
    if data['code']!=0:
        raise BridgeError('page_error', '页面请求未完成，请保持视频号页面打开并检查连接')
    return data

def mapping(value):
    if not isinstance(value,dict):raise BridgeError('invalid_response','接口字段格式不符合预期')
    return value

def object_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,20}',value) or not 0<int(value)<2**64:
        raise BridgeError('invalid_id','没有有效的视频号作品 ID')
    return value

def status(port=2022):
    data=mapping(api('/api/status',port).get('data'))
    if not isinstance(data.get('version'),str) or not isinstance(data.get('api'),dict):
        raise BridgeError('invalid_response','服务身份无法确认')
    page=mapping(api('/api/channels/status',port).get('data'))
    if type(page.get('available')) is not bool:
        raise BridgeError('invalid_response','无法确认页面连接状态')
    connected=page['available']
    return {'status':'page_connected' if connected else 'page_disconnected', 'version':data['version'],
            'message':'页面已连接，可读取最近观看的作品' if connected else '服务已启动，微信页面尚未接入；仅打开视频还不够，请查看连接说明',
            'end_to_end_verified':False}

def page_data(payload):
    data=mapping(payload.get('data'))
    if type(data.get('errCode')) is not int or data['errCode']!=0:
        raise BridgeError('page_error','微信页面返回失败')
    result=mapping(data.get('data'))
    for field in ('BaseResponse','baseresponse'):
        if field in result and mapping(result[field]).get('Ret')!=0:
            raise BridgeError('page_error','微信拒绝了本次请求')
    return data,result

def history(port=2022):
    if status(port)['status']!='page_connected':raise BridgeError('page_disconnected','微信页面尚未接入')
    _,result=page_data(api('/api/channels/play/history',port))
    objects=result.get('objects')
    if not isinstance(objects,list):raise BridgeError('invalid_response','观看记录格式无法识别')
    items=[];seen=set()
    for obj in objects[:50]:
        obj=mapping(obj);oid=object_id(obj.get('id'))
        if oid in seen:continue
        seen.add(oid)
        contact=mapping(obj.get('contact') or {});desc=mapping(obj.get('objectDesc') or {})
        items.append({'id':oid,'author':str(contact.get('nickname') or '未提供作者')[:100],
                      'title':str(desc.get('description') or '未提供标题')[:200]})
    return {'status':'history_loaded' if items else 'history_empty','items':items,
            'message':f'读到 {len(items)} 条记录；请选择目标作品，不会自动下载。记录可能来自页面缓存。', 'end_to_end_verified':False}

def share(oid,port=2022):
    oid=object_id(oid)
    if status(port)['status']!='page_connected':raise BridgeError('page_disconnected','微信页面连接已断开')
    data,result=page_data(api('/api/channels/feed/share_url?'+urllib.parse.urlencode({'oid':oid}),port))
    link=result.get('feedH5Url')
    if not isinstance(link,str) or not re.fullmatch(r'https://weixin\.qq\.com/sph/[A-Za-z0-9_-]+/?',link):
        raise BridgeError('invalid_response','未返回有效的 sph 分享网址')
    entries=result.get('urlList')
    if (str(mapping(data.get('payload')).get('objectId'))!=oid or not isinstance(entries,list)
        or not any(isinstance(x,dict) and str(x.get('objectId'))==oid and x.get('feedH5Url')==link for x in entries)):
        raise BridgeError('identity_unverified','返回链接无法与所选作品对应，未加入队列')
    return {'status':'share_resolved','share_url':link,'object_id':oid,
            'message':'已取得对应分享链接，加入拾影队列后点击开始下载。下载是否成功以媒体验收为准。','end_to_end_verified':False}

def service_config(state,port):
    state=Path(state).resolve()
    # JSON is valid YAML. Explicitly disable all system integration and remote bridges.
    return {'workdir':str(state),'api':{'protocol':'http','hostname':'127.0.0.1','port':port},
      'proxy':{'enabled':False,'system':False,'tun':False,'skipInstallRootCert':True},
      'mcp':{'enabled':False},'bridge':{'enabled':False},
      'download':{'dir':str(state/'downloads'),'playDoneAudio':False,'maxRunning':1},
      'update':{'sources':[]}}

def serve(state,port):
    if type(port) is not int or not 1<=port<=65535:raise BridgeError('invalid_port','无效端口')
    # Refuse to reuse or stop a service owned by another process.
    with socket.socket() as sock:
        try:sock.bind(('127.0.0.1',port))
        except OSError as exc:raise BridgeError('port_busy','API 端口已占用，请直接检查连接或更换端口') from exc
    root=ROOT/'external/wx_channels_download';binary=root/'wx_video_download'
    manifest=json.loads((root/'provenance.json').read_text())
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=manifest['binary_sha256']:
        raise BridgeError('helper_changed','连接组件校验失败，请重新构建或恢复原始组件')
    state=Path(state).resolve();state.mkdir(parents=True,exist_ok=True)
    config=state/'server.json';config.write_text(json.dumps(service_config(state,port)))
    os.execv(str(binary),[str(binary),'server','--config',str(config),'--workdir',str(state)])

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['status','history','share','serve']);p.add_argument('--port',type=int,default=2022);p.add_argument('--oid');p.add_argument('--state',type=Path)
    args=p.parse_args()
    try:
        if args.action=='serve':
            if args.state is None:p.error('serve requires --state')
            serve(args.state,args.port)
        result=status(args.port) if args.action=='status' else history(args.port) if args.action=='history' else share(args.oid,args.port)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (BridgeError,OSError,ValueError) as exc:
        print(json.dumps({'status':getattr(exc,'status','failed'),'message':str(exc),'end_to_end_verified':False},ensure_ascii=False));return 1

if __name__=='__main__':sys.exit(main())
