import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parent))
import idm_bridge as b
class Tests(unittest.TestCase):
 def test_resolution_does_not_handoff_watch_page(self):
  core={'ytdlp_base':lambda u,c:['yt-dlp']}
  for result in ({'_type':'playlist','url':'https://cdn.example/a.mp4'},{'url':'file:///tmp/test'}, {'url':'https://name:secret@cdn.example/a.mp4'}):
   with patch.object(b.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result))):
    with self.assertRaises(RuntimeError):b.resolve('https://youtube.com/watch?v=a',{},core)
 def test_resolution_failure_is_failure(self):
  with patch.object(b.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
   with self.assertRaises(RuntimeError):b.resolve('https://youtube.com/watch?v=a',{}, {'ytdlp_base':lambda u,c:[]})
 def test_argv_and_cancel_do_not_report_success(self):
  with tempfile.TemporaryDirectory() as td,patch.object(b,'executable',return_value=Path('IDMan.exe')),patch.object(b,'resolve',return_value=('https://cdn.example/video.mp4?a=1&b=2',{'title':'Example'})),patch.object(b.subprocess,'run') as launch:
   states=iter([False,False,True])
   media,_=b.download('https://youtube.com/watch?v=a',{'folder':td},{},lambda:next(states),lambda x:None)
   self.assertIsNone(media)
   args=launch.call_args.args[0]
   self.assertIn('https://cdn.example/video.mp4?a=1&b=2',args)
   self.assertNotIn('https://youtube.com/watch?v=a',args)
   self.assertNotIn('/q',args)
   self.assertEqual(json.loads(next(Path(td).rglob('source.json')).read_text())['status'],'waiting')
if __name__=='__main__':unittest.main()
