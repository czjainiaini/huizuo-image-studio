"""Install an owned boot hook only on the verified AutoDL bash/profile boot path."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import shutil
import datetime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, default=Path('/root/HuizuoStudio'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--update', action='store_true', help='Replace only files matching the previous owned install marker')
    args = parser.parse_args()
    app = args.app_root.resolve()
    if app != Path('/root/HuizuoStudio') or not (app / 'start.sh').is_file():
        parser.error('Expected existing /root/HuizuoStudio/start.sh; no arbitrary shell paths accepted.')
    source = Path('/proc/1/fd/255')
    if not source.exists() or not re.search(r'^\s*source /etc/profile\b', source.read_text(errors='replace'), re.M):
        parser.error('This platform boot path is not verified to source /etc/profile; no files changed.')
    wrapper = '''#!/bin/bash
set -euo pipefail
APP_ROOT=/root/HuizuoStudio
printf 'HUizuo boot attempt: %s\\n' "$(date -Is)"
exec /usr/bin/flock -n "$APP_ROOT/.autostart.lock" /bin/bash "$APP_ROOT/start.sh"
'''
    hook = '''# Huizuo owned AutoDL boot hook v1; only the platform PID 1 sources this at boot.
if [ "${BASHPID:-$$}" = "1" ] && [ -r /root/HuizuoStudio/autostart.sh ]; then
  /usr/bin/nohup /bin/bash /root/HuizuoStudio/autostart.sh >>/root/HuizuoStudio/autostart.log 2>&1 </dev/null &
fi
'''
    jobs = [(app / 'autostart.sh', wrapper), (Path('/etc/profile.d/90-huizuo-autostart.sh'), hook)]
    marker_path = app / 'autostart-install.json'
    previous = json.loads(marker_path.read_text()) if marker_path.exists() else {'files': {}}
    for target, content in jobs:
        checked = subprocess.run(['/bin/bash', '-n'], input=content, text=True, capture_output=True)
        if checked.returncode:
            parser.error(checked.stderr)
        if target.exists() and target.read_text() != content:
            if not args.update or previous['files'].get(str(target)) != hashlib.sha256(target.read_bytes()).hexdigest():
                parser.error(f'Existing modified file preserved: {target}')
    if args.apply:
        backup = app / ('autostart-backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        for target, content in jobs:
            if target.exists() and target.read_text() != content:
                backup.mkdir(exist_ok=True)
                shutil.copy2(target, backup / target.name)
            target.write_text(content)
            target.chmod(0o644)
        marker = {'boot_path': '/init/bin/init_boot.sh sources /etc/profile',
                  'scope': 'PID 1 only; CPU auto-opens interface, CUDA prepares models; no new terminals start jobs',
                  'files': {str(target): hashlib.sha256(content.encode()).hexdigest() for target, content in jobs}}
        (app / 'autostart-install.json').write_text(json.dumps(marker, indent=2))
    print(json.dumps({'applied': args.apply, 'files': [str(target) for target, _ in jobs], 'cold_boot_verified': False}))


if __name__ == '__main__':
    main()
