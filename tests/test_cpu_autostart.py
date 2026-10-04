"""Real shell and startup-process regression tests; no models or cloud calls."""
import ast
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.request

SOURCE = Path(os.environ.get('HUIZUO_BOOT_TEST_SOURCE', '/tmp/huizuo-boot-source'))


class CpuAutostart(unittest.TestCase):
    def test_no_gpu_shell_still_invokes_start_script(self):
        tree = ast.parse((SOURCE / 'install_autostart.py').read_text())
        wrapper = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'wrapper' for t in node.targets))
        with tempfile.TemporaryDirectory(prefix='huizuo-shell-') as folder:
            root = Path(folder)
            marker = root / 'started'
            (root / 'start.sh').write_text(f'#!/bin/bash\nprintf started > {marker}\n')
            bin_dir = root / 'bin'; bin_dir.mkdir()
            no_gpu = bin_dir / 'nvidia-smi'; no_gpu.write_text('#!/bin/bash\nexit 1\n'); no_gpu.chmod(0o755)
            script = root / 'autostart.sh'; script.write_text(wrapper.replace('/root/HuizuoStudio', str(root)))
            env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'])
            subprocess.run(['/bin/bash', str(script)], env=env, check=True, capture_output=True, timeout=5)
            self.assertTrue(marker.exists(), 'No-GPU boot must launch the interface, not exit.')

    def test_startup_page_precedes_download_and_cpu_prepares_models_before_launch(self):
        with tempfile.TemporaryDirectory(prefix='huizuo-cpu-boot-') as folder:
            root = Path(folder); scripts = root / 'scripts'; scripts.mkdir()
            comfy = root / 'ComfyUI'; comfy.mkdir()
            marker = comfy / 'main-arguments.json'; imported = root / 'model-library-imported'
            shutil.copy2(SOURCE / 'bootstrap_runtime.py', scripts / 'bootstrap_runtime.py')
            (root / 'models-manifest.json').write_text(json.dumps({'models':[]}))
            (root / 'deploy').mkdir()
            (root / 'deploy/autodl-public-models.json').write_text(json.dumps({'models':{}}))
            (scripts / 'torch.py').write_text('import time\ntime.sleep(1)\nclass cuda:\n @staticmethod\n def is_available(): return False\n')
            (scripts / 'model_startup.py').write_text(
                f'from pathlib import Path\nimport json\nROOT=Path({str(root)!r})\nPath({str(imported)!r}).write_text("imported")\n'
                'def write_json(p,v):\n p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v))\n'
                'def ensure_models(*a,**k):\n import time\n k["progress"]({"phase":"downloading","model":"fixture","bytes_done":1,"bytes_total":2})\n time.sleep(1)\n return [{"model":"fixture","source":"download"}]\n'
                'def read_public_catalog(*a,**k): return {}\n')
            (comfy / 'main.py').write_text(f'import sys,json\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(json.dumps(sys.argv))\n')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            process = subprocess.Popen(['python', str(scripts / 'bootstrap_runtime.py'), '--comfy-root', str(comfy),
                '--purpose', 'research', '--port', str(port), '--prompt-enhancer','off','--apply'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                page_seen = False
                for _ in range(60):
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=.2) as response:
                            self.assertEqual(response.status, 200); page_seen = True; break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(.02)
                self.assertTrue(page_seen, 'Startup page must already be available during heavy import.')
                self.assertFalse(marker.exists(), 'This observation must precede native core launch.')
                for _ in range(100):
                    if marker.exists(): break
                    time.sleep(.03)
                self.assertTrue(marker.exists(), 'CPU boot must automatically exec native ComfyUI.')
                self.assertIn('--cpu', json.loads(marker.read_text()))
                self.assertTrue(imported.exists(), 'CPU startup must prepare required models by default.')
                ready=json.loads((comfy / '.huizuo-runtime/models-ready.json').read_text())
                self.assertEqual(ready['models'][0]['source'],'download')
                process.wait(timeout=3)
                self.assertEqual(process.returncode, 0)
            finally:
                if process.poll() is None: process.terminate(); process.wait(timeout=3)
                process.stdout.close()


if __name__ == '__main__': unittest.main()
