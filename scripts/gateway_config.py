"""Generate an owned Nginx front door; native ComfyUI stays on loopback."""
import hashlib
import json
from pathlib import Path
import re

WAIT_PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>绘作台 · 正在启动</title>
<style>body{margin:0;background:#101719;color:#edf3ef;font:16px system-ui;min-height:100vh;display:grid;place-items:center}main{width:min(520px,84vw);padding:30px}small{color:#96c9b6}h1{font-size:28px}p{line-height:1.7;color:#bccbc3}.track{height:7px;border-radius:8px;background:#294138;overflow:hidden}.bar{height:100%;width:35%;background:#86dcb6;animation:move 1.6s ease-in-out infinite}@keyframes move{50%{transform:translateX(180%)}}#detail{font-size:13px;overflow-wrap:anywhere}#error{color:#f3b1a5}</style>
<main><small>绘作台 · Qwen Image 2.1</small><h1 id="title">正在启动 ComfyUI</h1><p id="message">实例已开机，正在准备界面。准备好后会自动进入，无需反复开关机。</p><div class="track"><div class="bar"></div></div><p id="detail"></p><p id="error"></p><p>无卡模式仅浏览和编辑工作流；有卡模式准备模型后可生成图片。</p></main>
<script>async function poll(){try{const r=await fetch('/system_stats',{cache:'no-store'});if(r.ok){const s=await r.json();if(s.system?.comfyui_version){location.replace('/');return}}}catch(e){}
try{const r=await fetch('/huizuo-startup-status',{cache:'no-store'});if(r.ok){const s=await r.json();document.querySelector('#message').textContent=s.message||'正在准备环境，完成后自动进入。';document.querySelector('#detail').textContent=s.model||'';document.querySelector('#error').textContent=s.error||'';}}catch(e){}
try{const r=await fetch('/_huizuo-entry-state.json',{cache:'no-store'});const s=await r.json();if(s.phase==='failed'){document.querySelector('#title').textContent='启动遇到问题';document.querySelector('#error').textContent=s.message;}}catch(e){}setTimeout(poll,800)}poll();</script></html>'''


def configure(app_root, public_port=6006, backend_port=6007, public_dir=None):
    app = Path(app_root).resolve()
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(app)):
        raise ValueError('Application path contains unsupported configuration characters')
    if not 1 <= public_port <= 65535 or not 1 <= backend_port <= 65535 or public_port == backend_port:
        raise ValueError('Invalid public/backend port')
    folder = app / 'gateway'; folder.mkdir(parents=True, exist_ok=True)
    public = Path(public_dir).resolve() if public_dir else Path('/var/lib/huizuo-startup') / hashlib.sha256(str(app).encode()).hexdigest()[:12]
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(public)):
        raise ValueError('Invalid public status directory')
    public.mkdir(parents=True, exist_ok=True); public.chmod(0o755)
    for name, data in [('index.html', WAIT_PAGE), ('state.json', json.dumps({'phase':'starting'}))]:
        path=public/name;path.write_text(data,encoding='utf-8');path.chmod(0o644)
    common = f'''proxy_pass http://127.0.0.1:{backend_port};
            proxy_http_version 1.1;
            proxy_set_header Host $http_host;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $huizuo_connection;
            proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 3600s;
'''
    config = f'''worker_processes 1;
user www-data;
pid "{folder}/nginx.pid";
error_log "{folder}/error.log" warn;
events {{ worker_connections 512; }}
http {{
    access_log off;
    map $http_upgrade $huizuo_connection {{ default upgrade; '' close; }}
    server {{
        listen {public_port};
        client_max_body_size 100m;
        location = / {{
            {common}
            proxy_intercept_errors on;
            error_page 502 504 =200 @huizuo_wait;
        }}
        location / {{ {common} proxy_intercept_errors off; }}
        location = /_huizuo-entry-state.json {{
            alias "{public}/state.json";
            default_type application/json;
            add_header Cache-Control "no-store" always;
        }}
        location @huizuo_wait {{
            root "{public}";
            default_type text/html;
            add_header Cache-Control "no-store" always;
            try_files /index.html =503;
        }}
    }}
}}
'''
    path=folder/'nginx.conf';path.write_text(config,encoding='utf-8')
    return {'nginx_config':str(path),'public_dir':str(public),'public_port':public_port,'backend_port':backend_port}
