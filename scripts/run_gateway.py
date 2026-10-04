"""Keep the public front door alive while ComfyUI prepares, imports, or stops."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    settings=json.loads(args.config.read_text())
    app=Path(settings['app_root']).resolve()
    nginx=shutil.which('nginx')
    if not nginx:parser.error('Nginx is required from the official OS package repository.')
    subprocess.run([nginx,'-t','-c',settings['nginx_config']],check=True)
    state_path=Path(settings['public_dir'])/'state.json'
    def state(phase,message):
        temporary=state_path.with_suffix('.new')
        temporary.write_text(json.dumps({'phase':phase,'message':message,'updated_at':time.time()},ensure_ascii=False),encoding='utf-8')
        temporary.chmod(0o644);os.replace(temporary,state_path)
    front=subprocess.Popen([nginx,'-c',settings['nginx_config'],'-g','daemon off;'])
    native=None;stopping=False
    def stop(*unused):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        for _ in range(50):
            if front.poll() is not None:raise RuntimeError('Front door exited; inspect gateway/error.log')
            if Path(settings['nginx_config']).with_name('nginx.pid').exists():break
            time.sleep(.04)
        state('starting','正在准备 ComfyUI，完成后自动进入。')
        command=settings.get('backend_command') or [str(app/'ComfyUI/.venv/bin/python'),str(app/'package/scripts/bootstrap_runtime.py'),
                                 '--config',str(app/'startup-config.json'),'--apply']
        native=subprocess.Popen(command,cwd=app)
        reported=False
        while not stopping:
            if front.poll() is not None:raise RuntimeError('Front door stopped unexpectedly')
            if native.poll() is not None and not reported:
                state('failed','ComfyUI 已停止。请检查启动日志或重启实例；当前没有运行图片生成。')
                reported=True
            time.sleep(.3)
    finally:
        for process in [native,front]:
            if process is not None and process.poll() is None:process.terminate()
        for process in [native,front]:
            if process is not None:
                try:process.wait(timeout=8)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
