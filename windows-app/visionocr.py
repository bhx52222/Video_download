"""RapidOCR adapter matching the existing Vision JSON contract and bottom-left ROI."""
import argparse,json
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--roi',default='0,0,1,1');p.add_argument('files',nargs='+');a=p.parse_args()
x,y,w,h=map(float,a.roi.split(','))
if min(x,y,w,h)<0 or x+w>1.0001 or y+h>1.0001:raise ValueError('ROI outside image')
engine=RapidOCR();out=[]
for name in a.files:
    im=Image.open(name).convert('RGB');W,H=im.size
    crop=im.crop((int(x*W),int((1-y-h)*H),int((x+w)*W),int((1-y)*H)))
    result,_=engine(np.asarray(crop))
    out.append({'file':name,'lines':[{'text':r[1],'conf':float(r[2])} for r in result or []]})
print(json.dumps(out,ensure_ascii=False))
