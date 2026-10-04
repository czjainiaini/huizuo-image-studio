"""Show startup progress, prepare pinned models, then exec native ComfyUI."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    # Startup must bind its HTTP page before importing model/download libraries.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.boot-tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)

PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>绘作台 · 启动中</title>
<style>body{margin:0;background:#101719;color:#e9eeec;font:16px system-ui;display:grid;min-height:100vh;place-items:center}main{width:min(520px,85vw);padding:32px}small{color:#9cc9ba}h1{font-size:28px}p{line-height:1.7;color:#becdc7}.track{height:8px;background:#263b33;border-radius:8px;overflow:hidden}.bar{height:100%;width:0;background:#82d4b6;transition:width .3s}#file{font-size:13px;overflow-wrap:anywhere;color:#8faaa0}#error{color:#f5b3a4}a{color:#b5ecd9}</style>
<main><small>绘作台 · Qwen Image 2.1</small><h1 id="title">正在准备创作环境</h1><p id="message">检查模型，准备好后自动进入 ComfyUI。</p><div class="track"><div class="bar" id="bar"></div></div><p id="file"></p><p id="error"></p><p>优先复用已校验模型和平台公共模型。需要下载时会显示进度；初次准备可能需要数分钟。</p></main>
<script>const labels={checking:'正在校验模型',reusing:'复用已有模型',linking:'连接平台公共模型',downloading:'正在下载模型',models_ready:'模型已准备好',starting:'正在启动 ComfyUI',failed:'启动遇到问题',gpu_check:'正在检查运行环境'};
async function poll(){try{const r=await fetch('/huizuo-startup-status',{cache:'no-store'});if(!r.ok)throw Error();const s=await r.json();document.querySelector('#title').textContent=labels[s.phase]||'正在准备创作环境';document.querySelector('#message').textContent=s.message||'准备好后将自动进入 ComfyUI。';document.querySelector('#file').textContent=s.model||'';document.querySelector('#bar').style.width=(s.bytes_total?Math.min(100,100*s.bytes_done/s.bytes_total):s.phase==='starting'?100:0)+'%';document.querySelector('#error').textContent=s.error||'';}catch(e){try{const r=await fetch('/system_stats',{cache:'no-store'});if(r.ok){location.replace('/');return;}}catch(e){}}setTimeout(poll,1000)}poll();</script></html>'''


def status_server(host, port, status, lock):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split('?', 1)[0] == '/system_stats':
                self.send_response(503); self.end_headers(); return
            if self.path.split('?', 1)[0] == '/huizuo-startup-status':
                with lock:
                    body = json.dumps(status, ensure_ascii=False).encode()
                content = 'application/json; charset=utf-8'
            else:
                body = PAGE.encode(); content = 'text/html; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path)
    p.add_argument('--comfy-root', type=Path)
    p.add_argument('--model-source', choices=['auto','public','download','existing'])
    p.add_argument('--purpose', choices=['research','commercial'])
    p.add_argument('--commercial-license-record', type=Path)
    p.add_argument('--port', type=int)
    p.add_argument('--device', choices=['auto', 'cuda', 'cpu'])
    p.add_argument('--listen')
    p.add_argument('--ui-only', action='store_true', help='CPU UI QA only: explicitly skip model preparation')
    p.add_argument('--prompt-enhancer',choices=['off','t2i','edit','both'])
    p.add_argument('--apply', action='store_true', help='Prepare models and launch; otherwise print the plan only')
    p.add_argument('comfy_args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    config = json.loads(a.config.read_text(encoding='utf-8')) if a.config else {}
    comfy = (a.comfy_root or Path(config.get('comfy_root','/opt/ComfyUI'))).resolve()
    source = a.model_source or config.get('model_source','auto')
    purpose = a.purpose or config.get('purpose')
    record = a.commercial_license_record or (Path(config['commercial_license_record']) if config.get('commercial_license_record') else None)
    port = a.port or config.get('port',6006)
    device = a.device or config.get('device', 'auto')
    listen = a.listen or config.get('listen', '0.0.0.0')
    if listen not in {'0.0.0.0','127.0.0.1'}:
        p.error('监听地址仅支持公开入口或本机后端')
    if not 1 <= port <= 65535 or source not in {'auto','public','download','existing'}:
        p.error('启动策略或端口无效')
    if purpose not in {'research','commercial'}:
        p.error('启动模型准备需要明确用途')
    if purpose == 'commercial' and not (record and record.is_file()):
        p.error('请提供已有商业授权记录；本程序不能授予或核实许可。')
    ui_only = a.ui_only or config.get('ui_only',False)
    enhancer = a.prompt_enhancer or config.get('prompt_enhancer','off')
    if enhancer not in {'off','t2i','edit','both'}:p.error('提示词增强模型选项无效')
    if not isinstance(ui_only,bool):p.error('ui_only必须为布尔值')
    if ui_only and device == 'cuda':p.error('GPU运行不能跳过模型准备')
    plan = {'comfy_root':str(comfy),'model_source':source,'purpose':purpose,'port':port,'device':device,'ui_only':ui_only,'prompt_enhancer':enhancer,'apply':a.apply}
    print(json.dumps(plan,ensure_ascii=False),flush=True)
    if not a.apply:
        return
    if not (comfy/'main.py').is_file():
        p.error('需要已有 ComfyUI 环境')
    if not (comfy/'.huizuo-runtime').resolve().is_relative_to(comfy):
        p.error('启动状态目录越出 ComfyUI；保留原文件。')
    status = {'phase':'gpu_check','message':'检查运行环境，随后准备模型。'}
    lock = threading.Lock()
    server = status_server(listen,port,status,lock)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    state_file = comfy/'.huizuo-runtime/startup-status.json'

    def progress(value):
        with lock:
            status.clear(); status.update(value)
        write_json(state_file,{**value,'updated_at_unix':time.time()})
        print(json.dumps(value,ensure_ascii=False),flush=True)

    try:
        # Model preparation does not load tensor weights and needs no GPU.
        # Download before importing torch to reduce memory use on 2GB CPU mode.
        if not ui_only:
            from model_startup import ensure_models, read_public_catalog
            manifest = json.loads((ROOT/'models-manifest.json').read_text(encoding='utf-8'))
            catalog = read_public_catalog(ROOT/'deploy/autodl-public-models.json')
            results = ensure_models(comfy,manifest,catalog,source,progress=progress)
            write_json(comfy/'.huizuo-runtime/models-ready.json',{'models':results,'purpose':purpose,'prepared_at_unix':time.time()})
            if enhancer != 'off':
                extra_manifest=json.loads((ROOT/'prompt-enhancer-models-manifest.json').read_text(encoding='utf-8'))
                if (extra_manifest['repository'],extra_manifest['revision']) != (manifest['repository'],manifest['revision']):
                    raise ValueError('增强模型与核心模型清单版本不一致。')
                extra_manifest['models']=[model for model in extra_manifest['models'] if enhancer == 'both' or model['profile'] == enhancer]
                try:
                    extra_results=ensure_models(comfy,extra_manifest,{},source,progress=progress)
                    write_json(comfy/'.huizuo-runtime/prompt-enhancer-status.json',{'state':'ready','profile':enhancer,'models':extra_results})
                except Exception as pe_error:
                    warning=re.sub(r'https?://\S+','[下载地址]',str(pe_error))[:500]
                    write_json(comfy/'.huizuo-runtime/prompt-enhancer-status.json',{'state':'unavailable','profile':enhancer,'error':warning,'base_models_ready':True})
                    print('可选PE准备未完成，继续启动普通跑图环境：'+warning,flush=True)
        import torch
        cuda_available = torch.cuda.is_available()
        use_cpu = device == 'cpu' or (device == 'auto' and not cuda_available)
        if device == 'cuda' and not cuda_available:
            raise ValueError('未检测到 CUDA 显卡，无法开始模型出图。')
        if ui_only and not use_cpu:raise ValueError('仅界面验收模式不允许在GPU上跳过模型准备。')
        if use_cpu:
            progress({'phase':'starting','device':'cpu','message':'无卡模式：'+('仅验收界面，已明确跳过模型准备。' if ui_only else '所需模型已准备好，正在打开界面；开GPU后即可出图。')})
        else:
            progress({'phase':'starting','device':'cuda','message':'模型已准备好，正在进入 ComfyUI。'})
        server.shutdown(); thread.join(timeout=5); server.server_close()
        os.chdir(comfy)
        extra = a.comfy_args[1:] if a.comfy_args[:1] == ['--'] else a.comfy_args
        mode_args = ['--cpu'] if use_cpu else ['--lowvram']
        os.execv(sys.executable,[sys.executable,str(comfy/'main.py'),'--listen',listen,'--port',str(port),*mode_args,*extra])
    except Exception as error:
        message = re.sub(r'https?://\S+','[下载地址]',str(error))[:500]
        if 'Hub' in message and ('connection' in message or 'cache' in message):
            print('模型仓库网络连接失败：'+message,flush=True)
            message='无法连接模型仓库。请检查平台网络，或使用可用的公共模型后重启。详细原因已保存到启动日志。'
        progress({'phase':'failed','message':'模型准备未完成，尚未开始出图。','error':message or '请查看 JupyterLab 启动日志。'})
        # Keep an informative page available. /system_stats remains 503, so
        # readiness checks cannot mistake this page for a working ComfyUI.
        print('模型准备失败；实例计费仍由平台控制，请处理问题或关闭实例。',flush=True)
        try:
            thread.join()
        except KeyboardInterrupt:
            server.shutdown(); server.server_close()
            raise SystemExit(1)


if __name__ == '__main__':
    main()
