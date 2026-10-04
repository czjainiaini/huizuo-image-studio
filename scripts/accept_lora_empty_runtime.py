"""Run installed manager's empty-list path with an inert model; no weights/queue."""
import importlib
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch

comfy_root=Path('/opt/ComfyUI');sys.path.insert(0,str(comfy_root));sys.argv=['accept','--cpu']
import comfy.options
comfy.options.enable_args_parsing()
plugin=comfy_root/'custom_nodes/ComfyUI-Lora-Manager'
# Import the installed, unmodified backend modules without starting a second HTTP server.
namespace=types.ModuleType('huizuo_lm_acceptance');namespace.__path__=[str(plugin)];sys.modules[namespace.__name__]=namespace
loader=importlib.import_module('huizuo_lm_acceptance.py.nodes.lora_loader').LoraLoaderLM()
model=object()
with patch('comfy.utils.load_torch_file',side_effect=AssertionError('Empty list must not read weights')),patch('comfy.sd.load_lora_for_models',side_effect=AssertionError('Empty list must not patch model')):
    result=loader.load_loras(model,'',loras=[])
    assert result[0] is model and result[1] is None and result[2:]==('','')
    wrapped=loader.load_loras(model,'',loras={'__value__':[]})
    assert wrapped[0] is model and wrapped[1] is None and wrapped[2:]==('','')
    inactive=loader.load_loras(model,'',loras=[{'name':'nonexistent-unused','strength':.5,'active':False}])
    assert inactive[0] is model and inactive[2:]==('','')
toggle=importlib.import_module('huizuo_lm_acceptance.py.nodes.trigger_word_toggle').TriggerWordToggleLM()
filtered=toggle.process_trigger_words('test',True,True,orinalMessage='style-a, style-b',trigger_words='style-a, style-b',
    toggle_trigger_words=[{'text':'style-a','active':True},{'text':'style-b','active':False}])
assert filtered==('style-a',)
record={'registry_version':'1.2.1','empty_list_identity':True,'wrapped_empty_list_identity':True,
        'inactive_entry_no_weight_read':True,'trigger_filter':'style-a','clip_none':True,
        'model_weight_read':False,'queue_submitted':False,'gpu_inference':False}
print('HUIZUO_LORA_ACCEPTANCE='+json.dumps(record),flush=True)
