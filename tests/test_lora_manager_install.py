"""Safety checks for the optional installer; no network or plugin execution."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
import zipfile
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('lora_install',Path(__file__).resolve().parents[1]/'scripts/install_lora_manager.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class InstallChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.comfy=self.root/'ComfyUI';self.comfy.mkdir()
        for name in ['main.py','nodes.py']:(self.comfy/name).write_text('')
        (self.root/'deploy').mkdir()
        self.zip=io.BytesIO()
        with zipfile.ZipFile(self.zip,'w') as archive:archive.writestr('requirements.txt',b'expected')
        self.data=self.zip.getvalue()
        manifest={'repository':'https://github.com/willmiao/ComfyUI-Lora-Manager','version':'1.2.1','license':'GPL-3.0',
                  'download_url':'https://cdn.comfy.org/willmiao/comfyui-lora-manager/1.2.1/node.zip',
                  'archive_bytes':len(self.data),'archive_sha256':hashlib.sha256(self.data).hexdigest(),
                  'files_sha256':{'requirements.txt':hashlib.sha256(b'expected').hexdigest()}}
        (self.root/'deploy/lora-manager-plugin.json').write_text(json.dumps(manifest))
    def call(self,*flags):
        with patch.object(module,'ROOT',self.root),patch('sys.argv',['install','--comfy-root',str(self.comfy),*flags]),contextlib.redirect_stdout(io.StringIO()):
            module.main()
    def test_default_plan_does_not_install_or_download(self):
        with patch.object(module,'run') as run,patch.object(module.subprocess,'run') as sub:
            self.call();run.assert_not_called();sub.assert_not_called()
        self.assertFalse((self.comfy/'custom_nodes').exists())
    def test_existing_plugin_preserved_without_commands(self):
        target=self.comfy/'custom_nodes/ComfyUI-Lora-Manager';target.mkdir(parents=True)
        (target/'user-settings.json').write_text('private fixture')
        with patch.object(module,'run') as run:
            with self.assertRaises(SystemExit):self.call('--apply')
            run.assert_not_called()
        self.assertEqual((target/'user-settings.json').read_text(),'private fixture')
    def test_bad_source_digest_never_runs_dependency_install(self):
        metadata={'status':'NodeVersionStatusActive','downloadUrl':'https://cdn.comfy.org/willmiao/comfyui-lora-manager/1.2.1/node.zip'}
        with patch.object(module.subprocess,'run') as sub,patch.object(module.urllib.request,'urlopen',side_effect=[io.BytesIO(json.dumps(metadata).encode()),io.BytesIO(b'wrong')]),patch.object(module,'run') as run:
            sub.return_value.returncode=0
            with self.assertRaisesRegex(ValueError,'校验失败'):self.call('--apply')
            run.assert_not_called()
        self.assertFalse((self.comfy/'.huizuo-runtime/lora-manager-install.json').exists())
        self.assertFalse((self.comfy/'custom_nodes/ComfyUI-Lora-Manager').exists())
    def test_flagged_version_stops_before_archive_download(self):
        with patch.object(module.subprocess,'run') as sub,patch.object(module.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps({'status':'NodeVersionStatusFlagged'}).encode())) as fetch,patch.object(module,'run') as run:
            sub.return_value.returncode=0
            with self.assertRaises(SystemExit):self.call('--apply')
            self.assertEqual(fetch.call_count,1);run.assert_not_called()
    def test_zip_path_traversal_is_rejected(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:archive.writestr('../outside',b'data')
        data.seek(0)
        with zipfile.ZipFile(data) as archive:
            with self.assertRaisesRegex(ValueError,'不安全'):module.validate_archive(archive,self.comfy/'plugin')
    def test_virtualenv_python_symlink_identity_is_preserved(self):
        link=self.root/'runtime/.venv/bin/python';link.parent.mkdir(parents=True)
        try:link.symlink_to(Path(sys.executable))
        except OSError as error:self.skipTest(f'Host does not permit symlinks: {error}')
        for explicit in [False,True]:
            output=io.StringIO()
            argv=['install','--comfy-root',str(self.comfy)]+(['--python',str(link)] if explicit else [])
            with patch.object(module,'ROOT',self.root),patch('sys.argv',argv),patch('sys.executable',str(link)),contextlib.redirect_stdout(output):module.main()
            self.assertEqual(json.loads(output.getvalue())['python'],str(link.absolute()),'Resolving the venv symlink installs into the wrong interpreter environment')
    def test_repair_reinstalls_dependencies_without_overwriting_plugin_settings(self):
        target=self.comfy/'custom_nodes/ComfyUI-Lora-Manager';target.mkdir(parents=True)
        (target/'requirements.txt').write_bytes(b'expected');(target/'settings.json').write_text('private fixture')
        metadata={'status':'NodeVersionStatusActive','downloadUrl':'https://cdn.comfy.org/willmiao/comfyui-lora-manager/1.2.1/node.zip'}
        with patch.object(module.subprocess,'run') as sub,patch.object(module.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(metadata).encode())) as fetch,patch.object(module,'run') as run:
            sub.return_value.returncode=0;self.call('--apply','--repair-dependencies')
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(run.call_args_list[0].args[0][1:4],['-m','pip','install'])
        self.assertEqual((target/'settings.json').read_text(),'private fixture');self.assertEqual((target/'requirements.txt').read_bytes(),b'expected')
    def test_repair_refuses_modified_plugin_before_network_or_pip(self):
        target=self.comfy/'custom_nodes/ComfyUI-Lora-Manager';target.mkdir(parents=True);(target/'requirements.txt').write_bytes(b'changed')
        with patch.object(module.urllib.request,'urlopen') as fetch,patch.object(module,'run') as run:
            with self.assertRaises(SystemExit):self.call('--apply','--repair-dependencies')
            fetch.assert_not_called();run.assert_not_called()
        self.assertEqual((target/'requirements.txt').read_bytes(),b'changed')

if __name__=='__main__':unittest.main()
