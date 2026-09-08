import unittest,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent / 'backend'))
from vx_kuaishou import parse_page,page_url
class TestKuaishou(unittest.TestCase):
 def page(self,media='https://v4.oskwai.com/test.mp4',pid='abc'):
  return 'window.__APOLLO_STATE__='+json.dumps({'defaultClient':{'VisionVideoDetailPhoto:abc':{'id':pid,'photoUrl':media,'duration':44366,'caption':'Test'},'detail':{'photo':{'id':'VisionVideoDetailPhoto:abc'},'author':{'id':'a'}},'a':{'id':'author','name':'Example'}}})+';</script>'
 def test_valid(self):
  r=parse_page(self.page(),'abc');self.assertEqual(r['duration'],44.366);self.assertEqual(r['uploader'],'Example')
 def test_wrong_id(self):
  with self.assertRaises(ValueError):parse_page(self.page(pid='other'),'abc')
 def test_risk_page(self):
  with self.assertRaises(ValueError):parse_page('{"result":2}','abc')
 def test_untrusted_media(self):
  for u in ['https://oskwai.com.evil.com/test.mp4','http://127.0.0.1/x','https://v4.oskwai.com:999/x']:
   with self.assertRaises(ValueError):parse_page(self.page(media=u),'abc')
 def test_redirect_policy(self):
  for u in ['https://evil.com','http://www.kuaishou.com/x','https://www.kuaishou.com:123/x']:
   with self.assertRaises(ValueError):page_url(u)
if __name__=='__main__':unittest.main()
