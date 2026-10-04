"""Opt-in download of official PE files. No inference or platform operations."""
import argparse
import json
from pathlib import Path
from model_startup import ensure_models

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy-root',type=Path,required=True)
    parser.add_argument('--profile',choices=['t2i','edit','both'],required=True)
    parser.add_argument('--purpose',choices=['research','commercial'],required=True)
    parser.add_argument('--commercial-license-record',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.purpose=='commercial' and not (args.commercial_license_record and args.commercial_license_record.is_file()):
        parser.error('商业用途需要已有授权记录；本程序不授予模型许可。')
    manifest=json.loads((ROOT/'prompt-enhancer-models-manifest.json').read_text(encoding='utf-8'))
    manifest['models']=[model for model in manifest['models'] if args.profile=='both' or model['profile']==args.profile]
    plan={'profile':args.profile,'bytes':sum(model['bytes'] for model in manifest['models']),
          'apply':args.apply,'inference':False,'cpu_download_supported':True}
    print(json.dumps(plan,ensure_ascii=False),flush=True)
    if args.apply:
        ensure_models(args.comfy_root,manifest,{},'auto',progress=lambda value:print(json.dumps(value,ensure_ascii=False),flush=True))
if __name__=='__main__':main()
