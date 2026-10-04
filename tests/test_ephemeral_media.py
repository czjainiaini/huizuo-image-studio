"""Images remain readable while the owner lives, then release without disk payloads."""
import importlib.util
import os
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ephemeral_media',ROOT/'custom_nodes/ComfyUI-HuizuoPanel/ephemeral_media.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@unittest.skipUnless(sys.platform=='linux','Linux cloud storage contract')
class MediaLifecycleContract(unittest.TestCase):
    def test_conda_without_python_memfd_binding_uses_host_libc_without_disk_fallback(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(module.os,'memfd_create',None,create=True):
            root=Path(temporary);store=module.MemoryMediaStore(root/'input',root/'temp')
            info=store.put('input',b'conda-compatible memory image')
            self.assertEqual(store.read(info['name'],'input',module.SUBFOLDER),b'conda-compatible memory image')
            self.assertTrue((root/'input'/module.SUBFOLDER/info['name']).is_symlink())
            store.close()
    def test_preview_survives_core_clearing_empty_temp_at_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);store=module.MemoryMediaStore(root/'input',root/'temp')
            (root/'temp'/module.SUBFOLDER).rmdir();(root/'temp').rmdir()
            info=store.put('temp',b'preview')
            self.assertEqual(store.read(info['name'],'temp',module.SUBFOLDER),b'preview')
            store.close()

    def test_input_and_preview_bytes_are_readable_then_gone_when_owner_closes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);store=module.MemoryMediaStore(root/'input',root/'temp')
            data=b'private image payload'
            inputs=store.put('input',data,'.png');preview=store.put('temp',data,'.png')
            links=[root/info['type']/info['subfolder']/info['name'] for info in [inputs,preview]]
            for link in links:
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.read_bytes(),data)
            self.assertFalse(any(p.is_file() and not p.is_symlink() for p in root.rglob('*')))
            store.close()
            for link in links:self.assertFalse(link.exists())

    def test_process_termination_releases_bytes_without_a_shutdown_cleanup_hook(self):
        with tempfile.TemporaryDirectory() as temporary:
            code="import importlib.util,json,sys,time;from pathlib import Path;s=importlib.util.spec_from_file_location('m',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);r=Path(sys.argv[2]);store=m.MemoryMediaStore(r/'input',r/'temp');i=store.put('input',b'private input');o=store.put('temp',b'private output');print(json.dumps([str(r/x['type']/x['subfolder']/x['name']) for x in [i,o]]),flush=True);time.sleep(60)"
            child=subprocess.Popen([sys.executable,'-u','-c',code,str(ROOT/'custom_nodes/ComfyUI-HuizuoPanel/ephemeral_media.py'),temporary],stdout=subprocess.PIPE,text=True)
            try:
                links=[Path(p) for p in json.loads(child.stdout.readline())]
                self.assertEqual([p.read_bytes() for p in links],[b'private input',b'private output'])
                child.terminate();child.wait(timeout=5)
                for p in links:self.assertFalse(p.is_file())
                next_boot=module.MemoryMediaStore(Path(temporary)/'input',Path(temporary)/'temp')
                for p in links:self.assertFalse(p.is_symlink())
                next_boot.close()
            finally:
                if child.poll() is None:child.kill();child.wait()
                child.stdout.close()

    def test_reclaiming_old_previews_preserves_live_reference_and_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);store=module.MemoryMediaStore(root/'input',root/'temp',max_bytes=10)
            regular=root/'input'/'ordinary.png';regular.write_bytes(b'keep')
            ref=store.put('input',b'abcdef');old=store.put('temp',b'1234');new=store.put('temp',b'5678')
            self.assertEqual((root/'input'/ref['subfolder']/ref['name']).read_bytes(),b'abcdef')
            self.assertFalse((root/'temp'/old['subfolder']/old['name']).exists())
            self.assertEqual((root/'temp'/new['subfolder']/new['name']).read_bytes(),b'5678')
            store.close();self.assertEqual(regular.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
