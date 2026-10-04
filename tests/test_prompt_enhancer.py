import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hz_pe',ROOT/'custom_nodes/ComfyUI-HuizuoPanel/prompt_enhancer.py')
pe=importlib.util.module_from_spec(spec);spec.loader.exec_module(pe)

class ImageFixture:
    def __init__(self,height,width):self.shape=(1,height,width,3)
    def __getitem__(self,key):return self
class ClipFixture:
    def tokenize(self,chat,**kwargs):self.chat=chat;self.tokenizer_args=kwargs;return {'fixture':[]}
    def generate(self,tokens,**kwargs):self.generation=kwargs;return [1]
    def decode(self,tokens):return 'reasoning</think>'+json.dumps({'rewritten_prompt':'将 <image2> 商品放入 <image1>。','wh_ratio':'','ratio_follow':'<image1>'},ensure_ascii=False)

class PromptEnhancerTests(unittest.TestCase):
    def test_large_reference_is_scaled_proportionally_without_cropping(self):
        try:import torch
        except ImportError:self.skipTest('Torch is tested in the Linux ComfyUI fixture')
        node=pe.HuizuoQwenPromptEnhance();clip=ClipFixture();image=torch.zeros((1,1100,2100,3))
        with patch.object(node,'require_gpu'):node.enhance(True,'edit','修改背景',4096,clip=clip,image_1=image)
        resized=clip.tokenizer_args['images'][0];height,width=resized.shape[1:3]
        self.assertLessEqual(height*width,1024*1024)
        self.assertLess(abs(width/height-2100/1100),.01)
        self.assertEqual(resized.shape[0],1)
    def test_default_disabled_is_lazy_and_never_touches_clip_or_gpu(self):
        node=pe.HuizuoQwenPromptEnhance()
        with patch.object(node,'require_gpu',side_effect=AssertionError('GPU must not be inspected')):
            self.assertEqual(node.check_lazy_status(False,'t2i','原词',4096),[])
            answer=json.loads(node.enhance(False,'t2i','原词',4096)[0])
        self.assertEqual(answer['rewritten_prompt'],'原词')
        self.assertFalse(node.INPUT_TYPES()['required']['enabled'][1]['default'])
    def test_different_image_shapes_stay_separate_ordered_and_keep_official_settings(self):
        node=pe.HuizuoQwenPromptEnhance();clip=ClipFixture();a=ImageFixture(400,800);b=ImageFixture(800,400)
        with patch.object(node,'require_gpu'):
            answer=node.enhance(True,'edit','放入商品',4096,clip=clip,image_1=a,image_2=b)[0]
        self.assertEqual(clip.tokenizer_args['images'],[a,b])
        self.assertEqual(clip.chat.count('<|image_pad|>'),2)
        self.assertTrue(clip.chat.endswith('<think>\n'))
        self.assertEqual(clip.generation['presence_penalty'],0)
        self.assertEqual(clip.generation['min_p'],0)
        self.assertEqual(json.loads(answer)['ratio_follow'],'<image1>')
    def test_missing_images_and_truncated_reasoning_fail_without_usable_prompt(self):
        node=pe.HuizuoQwenPromptEnhance();clip=ClipFixture()
        with patch.object(node,'require_gpu'):
            with self.assertRaisesRegex(ValueError,'至少一张'):node.enhance(True,'edit','修改',4096,clip=clip)
            with self.assertRaisesRegex(ValueError,'跳号'):node.enhance(True,'edit','修改',4096,clip=clip,image_2=ImageFixture(10,10))
            clip.decode=lambda _: 'still thinking'
            with self.assertRaisesRegex(ValueError,'思考未结束'):node.enhance(True,'t2i','杯子',4096,clip=clip)
    def test_enabled_node_requests_clip_and_t2i_rejects_reference_images(self):
        node=pe.HuizuoQwenPromptEnhance()
        with patch.object(node,'require_gpu'):
            self.assertEqual(node.check_lazy_status(True,'t2i','杯子',4096),['clip'])
            with self.assertRaisesRegex(ValueError,'不接受图片'):node.enhance(True,'t2i','杯子',4096,clip=ClipFixture(),image_1=ImageFixture(10,10))

if __name__=='__main__':unittest.main(verbosity=2)
