import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_workflows.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CanvasWorkflowContract(unittest.TestCase):
    def test_optional_ai_is_visible_and_wired_without_a_required_pe_loader(self):
        graph=module.Graph('multi').build()
        optimizer=next(n for n in graph['nodes'] if n['type']=='HuizuoCanvasPromptOptimize')
        self.assertFalse(optimizer['widgets_values_named']['enabled'])
        encoder=next(n for n in graph['nodes'] if n['type']=='TextEncodeQwenImage21')
        prompt_port=next(p for p in encoder['inputs'] if p['name']=='prompt')
        wire=next(w for w in graph['links'] if w[0]==prompt_port['link'])
        self.assertEqual(wire[1],optimizer['id'])
        self.assertEqual(wire[2],0)
        loaders=[n for n in graph['nodes'] if n['type']=='CLIPLoader']
        self.assertEqual(len(loaders),1)
        self.assertNotIn('_pe_',loaders[0]['widgets_values'][0])
        self.assertTrue(any(n['type']=='HuizuoEphemeralPreview' for n in graph['nodes']))

if __name__=='__main__':unittest.main()
