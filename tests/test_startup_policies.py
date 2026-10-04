"""Subprocess checks of CPU download policy, opt-in PE and failure readiness."""
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

SOURCE=Path(os.environ.get('HUIZUO_BOOT_TEST_SOURCE','/tmp/huizuo-boot-source'))
class StartupPolicies(unittest.TestCase):
    def run_fixture(self,extra=(),fail=False,pe_fail=False):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        root=Path(folder.name);scripts=root/'scripts';scripts.mkdir();comfy=root/'ComfyUI';comfy.mkdir()
        shutil.copy2(SOURCE/'bootstrap_runtime.py',scripts/'bootstrap_runtime.py')
        (root/'deploy').mkdir();(root/'deploy/autodl-public-models.json').write_text('{"models":{}}')
        base={'repository':'Comfy-Org/Qwen-Image-2.1','revision':'a'*40,'models':[{'path':'vae/core.safetensors'}]}
        pe={**base,'models':[{'profile':'edit','path':'text_encoders/edit-pe.safetensors'},{'profile':'t2i','path':'text_encoders/t2i-pe.safetensors'}]}
        (root/'models-manifest.json').write_text(json.dumps(base));(root/'prompt-enhancer-models-manifest.json').write_text(json.dumps(pe))
        (scripts/'torch.py').write_text('class cuda:\n @staticmethod\n def is_available():return False\n')
        marker=root/'models-requested.json'
        (scripts/'model_startup.py').write_text(
            'import json\nfrom pathlib import Path\n'
            'def read_public_catalog(path):return {}\n'
            'def ensure_models(comfy,manifest,catalog,source,progress):\n'
            f' p=Path({str(marker)!r}); old=json.loads(p.read_text()) if p.exists() else [];p.write_text(json.dumps(old+manifest["models"]))\n'
            ' progress({"phase":"downloading","bytes_done":1,"bytes_total":2})\n'
            +( ' if any("pe.safetensors" in m["path"] for m in manifest["models"]): raise RuntimeError("optional PE unavailable fixture")\n' if pe_fail else '')
            +(' raise RuntimeError("network unavailable fixture")\n' if fail else ' return [{"model":m["path"],"source":"download"} for m in manifest["models"]]\n'))
        main=root/'main-started';(comfy/'main.py').write_text(f'from pathlib import Path\nPath({str(main)!r}).write_text("started")\n')
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        process=subprocess.Popen(['python',str(scripts/'bootstrap_runtime.py'),'--comfy-root',str(comfy),
           '--purpose','research','--device','cpu','--port',str(port),'--apply',*extra],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def stop():
            if process.poll() is None:process.terminate()
            process.wait(timeout=4)
        self.addCleanup(stop)
        state=comfy/'.huizuo-runtime/startup-status.json';until=time.monotonic()+4
        while time.monotonic()<until:
            if main.exists() or (state.exists() and json.loads(state.read_text()).get('phase')=='failed'):break
            time.sleep(.03)
        return marker,main,state,port,comfy
    def test_cpu_default_downloads_core_but_not_optional_pe(self):
        marker,main,state,port,comfy=self.run_fixture()
        self.assertTrue(main.exists())
        self.assertEqual([model['path'] for model in json.loads(marker.read_text())],['vae/core.safetensors'])
        self.assertTrue((comfy/'.huizuo-runtime/models-ready.json').exists())
    def test_explicit_edit_pe_prepares_only_selected_additional_model(self):
        marker,main,*_=self.run_fixture(['--prompt-enhancer','edit'])
        self.assertTrue(main.exists())
        self.assertEqual([model['path'] for model in json.loads(marker.read_text())],['vae/core.safetensors','text_encoders/edit-pe.safetensors'])
    def test_ui_only_is_explicit_and_never_calls_download(self):
        marker,main,*_=self.run_fixture(['--ui-only'])
        self.assertTrue(main.exists());self.assertFalse(marker.exists())
    def test_cpu_download_failure_shows_error_without_false_ready_or_core_launch(self):
        marker,main,state,port,comfy=self.run_fixture(fail=True)
        self.assertFalse(main.exists());self.assertEqual(json.loads(state.read_text())['phase'],'failed')
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/huizuo-startup-status',timeout=1) as response:
            self.assertEqual(json.load(response)['phase'],'failed')
        with self.assertRaises(urllib.error.HTTPError) as context:urllib.request.urlopen(f'http://127.0.0.1:{port}/system_stats',timeout=1)
        self.assertEqual(context.exception.code,503)
        self.assertFalse((comfy/'.huizuo-runtime/models-ready.json').exists())
    def test_selected_pe_download_failure_does_not_block_ready_core(self):
        marker,main,state,port,comfy=self.run_fixture(['--prompt-enhancer','edit'],pe_fail=True)
        self.assertTrue(main.exists(),'Optional PE failure must not block native UI/base generation')
        ready=json.loads((comfy/'.huizuo-runtime/models-ready.json').read_text())
        self.assertEqual(ready['models'],[{'model':'vae/core.safetensors','source':'download'}])
        pe_status=json.loads((comfy/'.huizuo-runtime/prompt-enhancer-status.json').read_text())
        self.assertEqual(pe_status['state'],'unavailable');self.assertTrue(pe_status['base_models_ready'])
if __name__=='__main__':unittest.main(verbosity=2)
