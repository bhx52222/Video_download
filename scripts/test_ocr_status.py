import importlib.util,sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
src=Path(__file__).resolve().parent/'src';sys.path.insert(0,str(src));sp=importlib.util.spec_from_file_location('vx',src/'vx.py');v=importlib.util.module_from_spec(sp);sp.loader.exec_module(v)
frames=[(0,Path('/tmp/frame.jpg'))]
for result in [SimpleNamespace(returncode=1,stderr='test failure',stdout=''),SimpleNamespace(returncode=0,stderr='',stdout='not-json'),SimpleNamespace(returncode=0,stderr='',stdout='{}'),SimpleNamespace(returncode=0,stderr='',stdout='[]')]:
 with patch.object(v,'run',return_value=result): assert v._ocr_pass(frames,'0,0,1,1') is None
assert [v.ocr_status(x) for x in [None,[],[(0,'')],[(0,'字')],[(0,'这是字幕')]]]==['failed','empty','empty','too_thin','recognized']
for rows,status in [(None,'failed'),([], 'empty'),([(0,'字')],'too_thin'),([(0,'这是字幕')],'recognized')]:
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);out=root/'item'
  for name in ['frames','subs','notes']:(out/name).mkdir(parents=True)
  (out/'frames/t000000_fixed.jpg').touch()
  for name in ['transcript.srt','transcript_ocr.srt']:(out/'subs'/name).write_text('old content')
  meta={'text':{},'capture':{},'notes':''}
  args=SimpleNamespace(force=False,no_frames=False,interval=15,ocr_roi=None)
  with patch.object(v,'ocr_frames',return_value=rows),patch.object(v,'append_index'):
   assert v.finish_visual_pipeline(meta,out,Path('/tmp/video.mp4'),args,root,'no audio')=='ok'
  assert meta['text']['ocr_status']==status
  assert (out/'subs/transcript_ocr.srt').exists()==(status=='recognized')
  if status!='recognized':assert len(list((out/'notes/_superseded').rglob('*.srt')))==2
print('PASS OCR errors differ from empty/thin; visual branch suppresses invalid SRT; prior files recoverable')

for rows,status in [(None,'failed'),([], 'empty'),([(0,'字')],'too_thin'),([(0,'这是字幕')],'recognized')]:
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);out=root/'item'
  for name in ['frames','subs','notes']:(out/name).mkdir(parents=True)
  video=out/'video.mp4';video.touch()
  (out/'frames/t000000_fixed.jpg').touch()
  (out/'subs/transcript.srt').write_text('1\n00:00:00,000 --> 00:00:01,000\n这是字幕\n')
  (out/'subs/transcript_ocr.srt').write_text('old OCR')
  (out/'notes/dual_check.md').write_text('old success')
  meta={'text':{'primary':'ocr'},'capture':{},'notes':'','duration_sec':1}
  args=SimpleNamespace(force=False,no_frames=False,interval=15,ocr_roi=None,lang='zh',force_asr=False,dual=True)
  with patch.object(v,'ocr_frames',return_value=rows),patch.object(v,'append_index'):
   assert v.finish_pipeline('local',meta,out,video,args,root)=='ok'
  assert meta['text']['ocr_status']==status
  assert meta['text']['dual_check']==(status=='recognized')
  if status!='recognized':
   assert not (out/'subs/transcript_ocr.srt').exists()
   assert '未完成' in (out/'notes/dual_check.md').read_text()
   assert 'primary' not in meta['text']
print('PASS dual OCR failure/empty/thin cannot retain success report or stale primary')
