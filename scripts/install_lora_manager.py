"""Install a fixed optional registry plugin; default prints a plan only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
import stat

ROOT=Path(__file__).resolve().parents[1]

def run(args):
    subprocess.run([str(arg) for arg in args],check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfy-root',type=Path,required=True)
    parser.add_argument('--python',type=Path,help='Existing ComfyUI interpreter; default current interpreter')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--repair-dependencies',action='store_true',help='Reinstall dependencies for an intact fixed plugin without overwriting its source or settings')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'deploy/lora-manager-plugin.json').read_text(encoding='utf-8'))
    assert manifest['repository']=='https://github.com/willmiao/ComfyUI-Lora-Manager'
    assert manifest['download_url']=='https://cdn.comfy.org/willmiao/comfyui-lora-manager/1.2.1/node.zip'
    comfy=args.comfy_root.resolve();target=comfy/'custom_nodes/ComfyUI-Lora-Manager'
    # A venv executable is often a symlink: resolving it switches pip to the base
    # environment. Preserve the invocation path for both explicit/default Python.
    python=(args.python if args.python else Path(sys.executable)).absolute()
    if not (comfy/'main.py').is_file() or not (comfy/'nodes.py').is_file():parser.error('需要现有ComfyUI目录。')
    if not target.resolve().is_relative_to(comfy):parser.error('插件路径必须位于当前ComfyUI目录内。')
    plan={'repository':manifest['repository'],'registry_version':manifest['version'],'archive_sha256':manifest['archive_sha256'],'target':str(target),'python':str(python),
          'apply':args.apply,'repair_dependencies':args.repair_dependencies,'lora_weights_downloaded':False,'inference':False,'restart_service':False,
          'external_ai_credentials_configured':False,'license':manifest['license']}
    print(json.dumps(plan,ensure_ascii=False,indent=2),flush=True)
    if not args.apply:return
    if target.exists() and not args.repair_dependencies:parser.error('插件目录已存在，保留现有内容；不会覆盖或自动升级。')
    if args.repair_dependencies:
        if not target.is_dir() or target.is_symlink():parser.error('修复依赖需要已安装的固定插件目录。')
        for name,expected in manifest['files_sha256'].items():
            file=target/name
            if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(target.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
                parser.error('现有插件源码不匹配固定版本；保留内容，不执行依赖修复。')
    if not python.is_file():parser.error('ComfyUI解释器不存在。')
    if subprocess.run([str(python),'-m','pip','check'],capture_output=True).returncode:parser.error('原环境依赖检查失败，请先处理；不继续安装。')
    with urllib.request.urlopen('https://api.comfy.org/nodes/comfyui-lora-manager/versions/1.2.1',timeout=30) as response:
        metadata=json.load(response)
    if metadata.get('status')!='NodeVersionStatusActive' or metadata.get('downloadUrl')!=manifest['download_url']:
        parser.error('固定Registry版本状态或地址已改变，停止安装；请重新评估。')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not args.repair_dependencies:
      with tempfile.TemporaryDirectory(prefix='huizuo-lm-') as temp:
        archive_path=Path(temp)/'node.zip'
        digest=hashlib.sha256();size=0
        with urllib.request.urlopen(manifest['download_url'],timeout=60) as response,archive_path.open('wb') as output:
            while block:=response.read(1024*1024):
                size+=len(block)
                if size>manifest['archive_bytes']:raise ValueError('插件包超过固定大小，停止安装。')
                digest.update(block);output.write(block)
        if size!=manifest['archive_bytes'] or digest.hexdigest()!=manifest['archive_sha256']:
            raise ValueError('固定插件包校验失败；不会执行安装。')
        with zipfile.ZipFile(archive_path) as archive:
            validate_archive(archive,target)
            for name,expected in manifest['files_sha256'].items():
                if hashlib.sha256(archive.read(name)).hexdigest()!=expected:raise ValueError(f'固定插件文件校验失败：{name}')
            archive.extractall(target)
    requirements=target/'requirements.txt'
    run([python,'-m','pip','install','--no-cache-dir','--index-url','https://pypi.org/simple','-r',requirements,
         '-c',ROOT/'deploy/torch-constraints.txt'])
    run([python,'-m','pip','check'])
    record=comfy/'.huizuo-runtime/lora-manager-install.json';record.parent.mkdir(exist_ok=True)
    record.write_text(json.dumps(plan|{'installed':True,'archive_verified':True},ensure_ascii=False,indent=2),encoding='utf-8')
    print('可选LoRA管理器已安装；在队列空闲时重启ComfyUI。未下载LoRA、配置外部API或运行推理。')

def validate_archive(archive,target):
    if archive.testzip() is not None:raise ValueError('插件ZIP内容损坏。')
    if sum(item.file_size for item in archive.infolist())>200*1024*1024:raise ValueError('插件解压大小超出预期。')
    for item in archive.infolist():
        path=Path(item.filename)
        if path.is_absolute() or '..' in path.parts or '\\' in item.filename or not (target/path).resolve().is_relative_to(target.resolve()) or stat.S_ISLNK(item.external_attr>>16):
            raise ValueError('插件ZIP包含不安全路径或符号链接。')

if __name__=='__main__':main()
