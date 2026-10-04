"""Exercise owned local ComfyUI media APIs without model weights or GPU jobs.

Run before, restart the owned QA container, then run after. Only this script's
new fixtures are used; no existing uploads, settings or weights are removed.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

def request(origin, path, data=None, content_type='application/json'):
    req=urllib.request.Request(origin+path,data=data,headers={'Content-Type':content_type})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:
            return response.status,response.read(),dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code,error.read(),dict(error.headers)

def queue(origin, graph):
    status,data,_=request(origin,'/prompt',json.dumps({'prompt':graph,'client_id':'huizuo-v044-local-qa'}).encode())
    assert status==200,(status,data)
    job=json.loads(data)['prompt_id']
    for _ in range(100):
        _,data,_=request(origin,'/history/'+job)
        history=json.loads(data).get(job)
        if history and history.get('status',{}).get('status_str')=='error':raise AssertionError(history)
        if history and history.get('status',{}).get('completed'):
            assert history['status']['status_str']=='success',history
            return history
        time.sleep(.1)
    raise AssertionError('Local fixture execution did not complete')

def view(origin, info):
    return request(origin,'/view?'+urllib.parse.urlencode({key:info[key] for key in ['filename','subfolder','type']}))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',default='http://127.0.0.1:6006')
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('phase',choices=['before','after'])
    args=parser.parse_args();origin=args.origin
    if args.phase=='after':
        report=json.loads(args.report.read_text())
        for info in report['media']:
            status,_,headers=view(origin,info)
            assert status==404,(info,status)
            assert headers.get('Cache-Control')=='no-store'
            path=Path('/opt/ComfyUI')/('input' if info['type']=='input' else 'temp')/info['subfolder']/info['filename']
            assert not path.exists() and not path.is_symlink(),path
        report['after_restart']='all fixture uploads and previews return 404; managed links removed'
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(report['after_restart']);return
    from PIL import Image
    payload=io.BytesIO();Image.new('RGB',(64,48),'#f0ccaa').save(payload,format='PNG');raw=payload.getvalue()
    boundary='hzqa'+uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="qa-reference.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode())
    status,data,_=request(origin,'/upload/image',body,'multipart/form-data; boundary='+boundary)
    assert status==200,(status,data)
    uploaded=json.loads(data);uploaded['filename']=uploaded['name']
    history=queue(origin,{'1':{'class_type':'HuizuoEphemeralLoadImage','inputs':{'image':uploaded['subfolder']+'/'+uploaded['name']}},'2':{'class_type':'HuizuoEphemeralPreview','inputs':{'images':['1',0]}}})
    preview=history['outputs']['2']['images'][0]
    text='以 <image1> 为主图，仅修改背景为薄荷绿，保留红色把手。'
    pe=queue(origin,{'1':{'class_type':'HuizuoCanvasPromptOptimize','inputs':{'enabled':False,'task':'图像编辑','prompt':text,'max_length':8192}},'2':{'class_type':'PreviewAny','inputs':{'source':['1',0]}}})
    assert text in str(pe['outputs']),pe['outputs']
    media=[uploaded,preview]
    for info in media:
        status,data,headers=view(origin,info);assert status==200 and data.startswith(b'\x89PNG')
        assert headers.get('Cache-Control')=='no-store'
        path=Path('/opt/ComfyUI')/('input' if info['type']=='input' else 'temp')/info['subfolder']/info['filename']
        assert path.is_symlink() and path.read_bytes()==data
        info['sha256']=hashlib.sha256(data).hexdigest()
    report={'scope':'Local CPU ComfyUI API; no diffusion or real PE inference','upload':'passed','memory_reference_loader':'passed','native_preview':'passed','PE_off_without_weights':'passed','media':media}
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
