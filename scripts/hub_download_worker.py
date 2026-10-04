"""Private, opt-in download worker with a scoped platform proxy environment."""
import json
from pathlib import Path
import re
import sys
from model_startup import hub_download, validate_manifest


def main():
    request=json.load(sys.stdin)
    validate_manifest(request['manifest'])
    if request['model'] not in request['manifest']['models']:
        raise ValueError('Download worker accepts only a model from the pinned manifest.')
    endpoint=request.get('endpoint','https://huggingface.co')
    if endpoint not in {'https://huggingface.co','https://hf-mirror.com'}:
        raise ValueError('Unrecognized model download endpoint.')
    def progress(value):
        print(json.dumps({'event':'progress','data':value},ensure_ascii=False),flush=True)
    try:
        result=hub_download(request['manifest'],request['model'],Path(request['staging']),progress,endpoint)
        print(json.dumps({'event':'result','path':str(result)}),flush=True)
    except Exception as error:
        message=re.sub(r'https?://\S+','[下载地址]',str(error))[:500]
        print(json.dumps({'event':'error','message':message},ensure_ascii=False),flush=True)
        raise SystemExit(1)


if __name__=='__main__':
    main()
