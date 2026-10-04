"""Container entrypoint for the persistent public listener and native backend."""
import json
import os
from pathlib import Path
import sys
from gateway_config import configure

app=Path('/opt/huizuo');comfy=Path(os.environ.get('COMFY_ROOT','/opt/ComfyUI')).resolve()
public_port=int(os.environ.get('HUIZUO_PORT','6006'))
backend_port=int(os.environ.get('HUIZUO_BACKEND_PORT','6007'))
device=os.environ.get('HUIZUO_DEVICE','cuda')
if device not in {'cuda','cpu'}:raise SystemExit('HUIZUO_DEVICE must be cuda or cpu')
settings=configure(app,public_port,backend_port)
config={'comfy_root':str(comfy),'port':backend_port,'listen':'127.0.0.1',
        'device':'cpu' if device=='cpu' else 'auto','model_source':os.environ.get('HUIZUO_MODEL_SOURCE','auto'),
        'purpose':os.environ.get('HUIZUO_MODEL_PURPOSE','research'),
        'commercial_license_record':os.environ.get('HUIZUO_COMMERCIAL_LICENSE_RECORD')}
config['ui_only']=os.environ.get('HUIZUO_UI_ONLY','0')=='1'
config['prompt_enhancer']=os.environ.get('HUIZUO_PROMPT_ENHANCER','off')
backend_config=app/'gateway/backend.json';backend_config.write_text(json.dumps(config))
settings.update(app_root=str(app),backend_command=[sys.executable,str(app/'scripts/bootstrap_runtime.py'),
                '--config',str(backend_config),'--apply','--',*sys.argv[1:]])
runtime=app/'gateway/runtime.json';runtime.write_text(json.dumps(settings))
os.execv(sys.executable,[sys.executable,str(app/'scripts/run_gateway.py'),'--config',str(runtime)])
