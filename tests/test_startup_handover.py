"""Continuously probe the public page through an intentionally slow core handover."""
import json
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request

SOURCE = Path(os.environ.get('HUIZUO_BOOT_TEST_SOURCE', '/tmp/huizuo-boot-source'))


class Handover(unittest.TestCase):
    def test_public_page_never_disappears_during_core_import(self):
        with tempfile.TemporaryDirectory(prefix='huizuo-handover-') as folder:
            root = Path(folder); scripts = root / 'scripts'; scripts.mkdir()
            root.chmod(0o755)
            comfy = root / 'ComfyUI'; comfy.mkdir()
            shutil.copy2(SOURCE / 'bootstrap_runtime.py', scripts / 'bootstrap_runtime.py')
            (scripts / 'torch.py').write_text('import time\ntime.sleep(.7)\nclass cuda:\n @staticmethod\n def is_available():return False\n')
            (comfy / 'main.py').write_text('''import time,sys,json
from http.server import BaseHTTPRequestHandler,HTTPServer
time.sleep(1.5)
port=int(sys.argv[sys.argv.index('--port')+1])
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({'system':{'comfyui_version':'fixture'}}).encode() if self.path=='/system_stats' else b'fixture-core-ready'
  self.send_response(200);self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',port),Handler).serve_forever()
''')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            front=None;backend_port=port
            if os.environ.get('HUIZUO_USE_PERSISTENT_GATEWAY')=='1':
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',0));backend_port=sock.getsockname()[1]
                spec=importlib.util.spec_from_file_location('gateway_config','/tmp/gateway_config.py')
                gateway=importlib.util.module_from_spec(spec);spec.loader.exec_module(gateway)
                settings=gateway.configure(root,port,backend_port,root/'public')
                front=subprocess.Popen(['nginx','-c',settings['nginx_config'],'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            process = subprocess.Popen(['python',str(scripts/'bootstrap_runtime.py'),'--comfy-root',str(comfy),
                '--purpose','research','--port',str(backend_port),'--ui-only','--apply'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            responses=[]; started=False; ready=False
            try:
                until=time.monotonic()+6
                while time.monotonic()<until:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/',timeout=.15) as r:
                            body=r.read();started=True;responses.append(r.status)
                            if b'fixture-core-ready' in body:ready=True;break
                    except Exception:
                        if started:responses.append('unreachable')
                    time.sleep(.03)
                self.assertTrue(ready,'Core fixture must become ready.')
                self.assertNotIn('unreachable',responses,'Public entry disappears while native core imports.')
            finally:
                process.terminate();process.wait(timeout=3)
                if front is not None:front.terminate();front.wait(timeout=3)


if __name__=='__main__':unittest.main()
