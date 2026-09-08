import contextlib,copy,io,json,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import wx_bridge as w

OID='14545102784038246591';LINK='https://weixin.qq.com/sph/TestOnly'
STATUS={'code':0,'data':{'version':'260907','api':{'listening':True}}}
PAGE={'code':0,'data':{'available':True}}
HISTORY={'code':0,'data':{'errCode':0,'data':{'objects':[{'id':OID,'contact':{'nickname':'测试作者'},'objectDesc':{'description':'测试作品'}}]}}}
SHARE={'code':0,'data':{'errCode':0,'payload':{'objectId':OID},'data':{'feedH5Url':LINK,'urlList':[{'objectId':OID,'feedH5Url':LINK}]}}}

@contextlib.contextmanager
def server(payloads):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            data=payloads.get(self.path)
            self.send_response(200 if data is not None else 404);self.end_headers();self.wfile.write(json.dumps(data).encode())
        def log_message(self,*args):pass
    s=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=s.serve_forever,kwargs={'poll_interval':.01});t.start()
    try:yield s.server_port,seen
    finally:s.shutdown();s.server_close();t.join()

class Tests(unittest.TestCase):
    def routes(self):return {'/api/status':STATUS,'/api/channels/status':PAGE,'/api/channels/play/history':HISTORY,'/api/channels/feed/share_url?oid='+OID:SHARE}
    def test_http_select_and_resolve(self):
        with server(self.routes()) as (port,seen),patch.dict('os.environ',{'http_proxy':'http://127.0.0.1:1','no_proxy':''}):
            self.assertEqual(w.status(port)['status'],'page_connected')
            items=w.history(port)['items'];self.assertEqual(items[0]['id'],OID)
            result=w.share(items[0]['id'],port);self.assertEqual(result['share_url'],LINK);self.assertFalse(result['end_to_end_verified'])
            self.assertNotIn('media',items[0]);self.assertIn('/api/channels/feed/share_url?oid='+OID,seen)
    def test_disconnected_never_reads_history_or_shares(self):
        routes=self.routes();routes['/api/channels/status']={'code':0,'data':{'available':False}}
        with server(routes) as (port,seen):
            self.assertEqual(w.status(port)['status'],'page_disconnected')
            for fn in [lambda:w.history(port),lambda:w.share(OID,port)]:
                with self.assertRaises(w.BridgeError):fn()
            self.assertNotIn('/api/channels/play/history',seen)
    def test_wrong_identity_and_url(self):
        for mutate in [lambda p:p['data']['payload'].update(objectId='1'),lambda p:p['data']['data'].update(feedH5Url='https://evil.test/'),lambda p:p['data']['data'].update(urlList=[])]:
            routes=self.routes();data=copy.deepcopy(SHARE);mutate(data);routes['/api/channels/feed/share_url?oid='+OID]=data
            with server(routes) as (port,_),self.assertRaises(w.BridgeError):w.share(OID,port)
    def test_invalid_status(self):
        for payload in [None,[],{'code':False},{'code':0,'data':{}}, {'code':0,'data':{'version':'x','api':[]}}]:
            routes=self.routes();routes['/api/status']=payload
            with server(routes) as (port,_),self.assertRaises(w.BridgeError):w.status(port)
    def test_no_system_mutation_config(self):
        c=w.service_config(Path('/tmp/shiying-test'),2022)
        self.assertEqual(c['api']['hostname'],'127.0.0.1')
        for key in ('enabled','system','tun'):self.assertFalse(c['proxy'][key])
        self.assertTrue(c['proxy']['skipInstallRootCert']);self.assertFalse(c['bridge']['enabled'])
    def test_empty_history_is_not_error(self):
        routes=self.routes();routes['/api/channels/play/history']={'code':0,'data':{'errCode':0,'data':{'objects':[]}}}
        with server(routes) as (port,_):self.assertEqual(w.history(port)['status'],'history_empty')
    def test_bad_ids(self):
        for oid in [None,True,OID+'x','0',str(2**64),123]:
            with self.assertRaises(w.BridgeError):w.object_id(oid)

if __name__=='__main__':unittest.main(verbosity=2)
