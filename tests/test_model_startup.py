import hashlib
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import model_startup as models
from bootstrap_runtime import status_server


class ModelStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.comfy=self.root/'ComfyUI';self.comfy.mkdir()
        (self.comfy/'main.py').write_text('# fixture')
        self.payload=b'original-test-model-payload'*100
        self.model={'path':'vae/test.safetensors','bytes':len(self.payload),'sha256':hashlib.sha256(self.payload).hexdigest()}
        self.manifest={'repository':models.REPOSITORY,'revision':'a'*40,'models':[self.model]}
        self.calls=[]

    def tearDown(self):
        self.temp.cleanup()

    def fetch(self,manifest,model,staging,progress):
        self.calls.append(model['path'])
        target=staging/model['path'];target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(self.payload)
        progress({'phase':'downloading','model':target.name,'bytes_done':len(self.payload),'bytes_total':len(self.payload)})
        return target

    def target(self):
        return self.comfy/'models'/self.model['path']

    def prepare(self,**kwargs):
        return models.ensure_models(self.comfy,self.manifest,downloader=self.fetch,reserve_bytes=0,**kwargs)

    def test_missing_public_model_downloads_and_next_boot_reuses_verified_file(self):
        phases=[]
        result=self.prepare(progress=lambda value:phases.append(value['phase']))
        self.assertEqual(result[0]['source'],'download')
        self.assertEqual(self.target().read_bytes(),self.payload)
        self.assertIn('downloading',phases)
        self.assertIn('checking',phases)
        self.assertEqual(self.prepare()[0]['source'],'existing')
        self.assertEqual(len(self.calls),1)

    def test_matching_public_file_links_without_downloading(self):
        public=self.root/'public.safetensors';public.write_bytes(self.payload)
        self.assertEqual(self.prepare(public_sources={self.model['path']:str(public)})[0]['source'],'public')
        self.assertTrue(self.target().samefile(public))
        self.assertEqual(self.calls,[])

    def test_restored_broken_public_link_downloads_and_survives_next_boot(self):
        self.target().parent.mkdir(parents=True)
        missing=self.root/'unavailable-public-model.safetensors'
        self.target().symlink_to(missing)
        result=self.prepare(public_sources={self.model['path']:str(missing)})
        self.assertEqual(result[0]['source'],'download')
        backup=self.target().with_name(self.target().name+'.huizuo-broken-link')
        self.assertTrue(backup.is_symlink())
        self.assertEqual(backup.readlink(),missing)
        self.assertFalse(self.target().is_symlink())
        self.assertEqual(self.prepare()[0]['source'],'existing')
        self.assertEqual(len(self.calls),1)

    def test_download_retry_after_restored_broken_link_preserves_backup(self):
        self.target().parent.mkdir(parents=True)
        missing=self.root/'unavailable-public-model.safetensors'
        self.target().symlink_to(missing)
        with self.assertRaisesRegex(RuntimeError,'network unavailable'):
            models.ensure_models(self.comfy,self.manifest,reserve_bytes=0,
                                 downloader=mock.Mock(side_effect=RuntimeError('network unavailable')))
        self.assertFalse(self.target().exists())
        result=self.prepare()
        self.assertEqual(result[0]['source'],'download')
        self.assertEqual(self.target().read_bytes(),self.payload)
        backup=self.target().with_name(self.target().name+'.huizuo-broken-link')
        self.assertTrue(backup.is_symlink())

    def test_wrong_public_hash_falls_back_to_download(self):
        public=self.root/'public.safetensors';public.write_bytes(b'x'*len(self.payload))
        self.assertEqual(self.prepare(public_sources={self.model['path']:str(public)})[0]['source'],'download')
        self.assertEqual(public.read_bytes(),b'x'*len(self.payload))

    def test_existing_wrong_file_is_preserved_and_never_overwritten(self):
        self.target().parent.mkdir(parents=True);self.target().write_bytes(b'user-file')
        with self.assertRaisesRegex(ValueError,'已有模型内容不符'):
            self.prepare()
        self.assertEqual(self.target().read_bytes(),b'user-file');self.assertEqual(self.calls,[])

    def test_changed_file_invalidates_verification_cache(self):
        self.prepare();self.target().write_bytes(b'x'*len(self.payload))
        with self.assertRaisesRegex(ValueError,'已有模型内容不符'):
            self.prepare()

    def test_corrupt_download_is_not_promoted(self):
        def corrupt(manifest,model,staging,progress):
            target=staging/model['path'];target.parent.mkdir(parents=True);target.write_bytes(b'x'*len(self.payload));return target
        with self.assertRaisesRegex(ValueError,'下载内容校验失败'):
            models.ensure_models(self.comfy,self.manifest,downloader=corrupt,reserve_bytes=0)
        self.assertFalse(self.target().exists())
        self.assertTrue((self.comfy/'.huizuo-downloads'/self.model['path']).exists())

    def test_low_disk_space_stops_before_download(self):
        with mock.patch.object(models.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaisesRegex(ValueError,'下载空间不足'):
                self.prepare()
        self.assertEqual(self.calls,[]);self.assertFalse(self.target().exists())

    def test_existing_only_policy_never_downloads(self):
        with self.assertRaisesRegex(ValueError,'不允许自动下载'):
            self.prepare(source='existing')
        self.assertEqual(self.calls,[])

    def test_manifest_escape_is_rejected_before_mutation(self):
        self.model['path']='../outside.safetensors'
        with self.assertRaisesRegex(ValueError,'模型路径无效'):
            self.prepare()
        self.assertFalse((self.comfy/'.huizuo-runtime').exists())

    def test_official_hub_uses_fixed_revision_without_ambient_credentials(self):
        staging=self.comfy/'.huizuo-downloads'
        result=staging/self.model['path']
        with mock.patch('huggingface_hub.hf_hub_download',return_value=str(result)) as download:
            self.assertEqual(models.download_official(self.manifest,self.model,staging,lambda _:None),result)
        self.assertEqual(download.call_args.kwargs['revision'],'a'*40)
        self.assertIs(download.call_args.kwargs['token'],False)
        self.assertEqual(download.call_args.kwargs['endpoint'],'https://huggingface.co')

    def test_progress_page_is_not_a_false_ready_service(self):
        status={'phase':'downloading','bytes_done':20,'bytes_total':100}
        server=status_server('127.0.0.1',0,status,threading.Lock())
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base+'/huizuo-startup-status') as r:
                self.assertEqual(json.load(r)['phase'],'downloading')
            with urllib.request.urlopen(base+'/') as r:
                self.assertIn('绘作台',r.read().decode())
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base+'/system_stats')
            self.assertEqual(error.exception.code,503)
        finally:
            server.shutdown();thread.join();server.server_close()

    def test_mirror_worker_does_not_forward_platform_proxy_credentials(self):
        with mock.patch.dict(models.os.environ,{'https_proxy':'http://user:secret@proxy.invalid','HTTP_PROXY':'http://user:secret@proxy.invalid'}):
            environment=models.worker_environment('https://hf-mirror.com')
        self.assertFalse(any(key.lower() in {'http_proxy','https_proxy','all_proxy'} for key in environment))
        self.assertEqual(environment['HF_HUB_DISABLE_IMPLICIT_TOKEN'],'1')
        self.assertEqual(environment['HF_HUB_DISABLE_XET'],'1')


if __name__=='__main__':
    unittest.main(verbosity=2)
