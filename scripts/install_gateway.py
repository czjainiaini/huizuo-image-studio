"""Install the owned persistent 6006 front door without starting or stopping services."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from gateway_config import configure


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root',type=Path,default=Path('/root/HuizuoStudio'))
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();app=args.app_root.resolve()
    if app!=Path('/root/HuizuoStudio'):parser.error('This installer is scoped to the existing AutoDL app root.')
    required=[app/'start.sh',app/'startup-config.json',app/'ComfyUI/main.py',app/'package/scripts/run_gateway.py']
    if not all(path.is_file() for path in required):parser.error('Existing owned app files are required.')
    nginx=shutil.which('nginx')
    if not nginx:parser.error('Install nginx from the official OS package repository first.')
    marker=app/'gateway-install.json'
    if marker.exists():
        record=json.loads(marker.read_text())
        for name,digest in record['files'].items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:parser.error('Owned gateway file was modified; preserved.')
        print(json.dumps({'already_applied':True}));return
    original=(app/'start.sh').read_text()
    if 'package/scripts/bootstrap_runtime.py' not in original or 'startup-config.json' not in original:
        parser.error('Startup entry differs from the reviewed app; preserved.')
    if (app/'backend-start.sh').exists():parser.error('Existing backend-start.sh preserved.')
    if not args.apply:
        print(json.dumps({'plan':'Nginx 6006; loopback ComfyUI 6007; fallback page','applied':False}));return
    backup=app/('gateway-backup-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir()
    for name in ['start.sh','startup-config.json']:shutil.copy2(app/name,backup/name)
    settings=configure(app,6006,6007)
    settings.update(app_root=str(app),backend_command=['/bin/bash',str(app/'backend-start.sh')])
    subprocess.run([nginx,'-t','-c',settings['nginx_config']],check=True)
    (app/'backend-start.sh').write_text(original);(app/'backend-start.sh').chmod(0o755)
    config=json.loads((app/'startup-config.json').read_text())
    config.update(port=6007,listen='127.0.0.1',device='auto')
    (app/'startup-config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2))
    gateway_config=app/'gateway/runtime.json';gateway_config.write_text(json.dumps(settings,indent=2))
    startup='''#!/bin/bash
set -euo pipefail
APP_ROOT=/root/HuizuoStudio
exec "$APP_ROOT/ComfyUI/.venv/bin/python" "$APP_ROOT/package/scripts/run_gateway.py" --config "$APP_ROOT/gateway/runtime.json"
'''
    temporary=app/'start.sh.gateway-new';temporary.write_text(startup);temporary.chmod(0o755);temporary.replace(app/'start.sh')
    tracked=[app/'start.sh',app/'backend-start.sh',app/'startup-config.json',gateway_config,Path(settings['nginx_config'])]
    record={'public_port':6006,'backend_port':6007,'backend_listen':'127.0.0.1','backup':str(backup),
            'files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}}
    marker.write_text(json.dumps(record,indent=2))
    print(json.dumps({'installed':True,'backup':str(backup),'services_started':False}))


if __name__=='__main__':main()
