"""Public canvas node contract: an optional optimizer cannot require PE when off."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import json

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('canvas_optimizer',ROOT/'custom_nodes/ComfyUI-HuizuoPanel/prompt_enhancer.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CanvasPromptContract(unittest.TestCase):
    def test_disabled_canvas_node_preserves_raw_chinese_without_runtime_or_weights(self):
        raw='仅将背景改为薄荷绿，保留“COFFEE”和红色把手。'
        with patch.dict(sys.modules,{'comfy':None,'comfy.model_management':None,'folder_paths':None}):
            node=module.HuizuoCanvasPromptOptimize()
            result=node.optimize(False,'图像编辑',raw,8192)
        self.assertEqual(result[0],raw)
        self.assertFalse(node.INPUT_TYPES()['required']['enabled'][1]['default'])

    def test_enabled_node_sends_only_rewritten_text_to_draw_encoder(self):
        class Clip:
            def tokenize(self, text, **kwargs):return text
            def generate(self, tokens, **kwargs):return tokens
            def decode(self, tokens):return 'reasoning</think>```json\n'+json.dumps({'rewritten_prompt':'一只红色陶瓷杯，柔和光线。','wh_ratio':'1:1'})+'\n```'
        with patch.object(module.HuizuoQwenPromptEnhance,'require_gpu'):
            result=module.HuizuoCanvasPromptOptimize().optimize(True,'文生图','红杯',8192,clip=Clip())
        self.assertEqual(result[0],'一只红色陶瓷杯，柔和光线。')
        self.assertNotIn('reasoning',result[0])

    def test_invalid_ai_output_stops_before_drawing_and_raw_input_is_untouched(self):
        node=module.HuizuoCanvasPromptOptimize();raw='保留图1的红色把手。'
        for answer in ['{"rewritten_prompt":', '{"rewritten_prompt":"使用 <image2>"}', '{"rewritten_prompt":"<think>秘密"}']:
            with self.subTest(answer=answer),patch.object(module.HuizuoQwenPromptEnhance,'require_gpu'),patch.object(module.HuizuoQwenPromptEnhance,'enhance',return_value=(answer,)):
                with self.assertRaises(ValueError):node.optimize(True,'图像编辑',raw,8192,clip=object(),image_1=object())
            self.assertEqual(node.optimize(False,'图像编辑',raw,8192)[0],raw)

if __name__=='__main__':unittest.main()
