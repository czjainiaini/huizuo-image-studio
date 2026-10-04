"""Create an original optional manager layout over the unchanged base graph."""
import copy
import json
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]

def build(base,plugin):
    graph=copy.deepcopy(base)
    graph['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'huizuo-v0.4.2-lora-manager'))
    roles={node['properties'].get('huizuoRole'):node for node in graph['nodes']}
    for node in graph['nodes']:
        if node['pos'][1]>=1100: node['pos'][1]+=700
    for group in graph['groups']:
        if group['title'].startswith('模型与解码'):group['bounding'][1]+=700
    def node(number,kind,title,pos,size,widgets,inputs,outputs,key,extra=None):
        value={'id':number,'type':kind,'title':title,'pos':pos,'size':size,'flags':{},'order':len(graph['nodes']),
               'mode':4 if key=='lora' else 2,'inputs':inputs,'outputs':outputs,
               'properties':{'Node name for S&R':kind,'huizuoRole':key,**(extra or {})},'widgets_values':widgets}
        graph['nodes'].append(value);return value
    def port(name,kind,optional=False):return {'name':name,'type':kind,'link':None,**({'shape':7} if optional else {})}
    def out(name,kind):return {'name':name,'type':kind,'links':[]}
    metadata={'cnr_id':'comfyui-lora-manager','aux_id':'willmiao/ComfyUI-Lora-Manager','ver':plugin['version']}
    first_id=max(node['id'] for node in graph['nodes'])+1
    loader=node(first_id,'Lora Loader (LoraManager)','LoRA管理器 · 默认关闭／空列表',[40,1530],[700,500],
                [{'version':1,'textWidgetName':'text'},'',[]],
                [port('model','MODEL'),port('clip','CLIP',True),port('lora_stack','LORA_STACK',True)],
                [out('MODEL','MODEL'),out('CLIP','CLIP'),out('trigger_words','STRING'),out('loaded_loras','STRING')],
                'lora',metadata|{'__lm_widget_ids':['__lm_autocomplete_meta_text','text','loras']})
    trigger=node(first_id+1,'TriggerWord Toggle (LoraManager)','触发词选择 · 不自动写入提示词',[800,1530],[400,320],
                 [True,True,False,[], ''],[port('trigger_words','STRING',True)],[out('filtered_trigger_words','STRING')],
                 'loraTriggers',metadata)
    preview=node(first_id+2,'PreviewAny','触发词预览 · 核对后手动加入',[1240,1530],[380,260],[],[port('source','*')],[out('STRING','STRING')],'loraPreview')
    loaded=node(first_id+3,'PreviewAny','已加载LoRA · 核对条目与强度',[1650,1530],[380,260],[],[port('source','*')],[out('STRING','STRING')],'loraLoaded')
    old_link=roles['cache']['inputs'][0]['link']
    graph['links']=[link for link in graph['links'] if link[0]!=old_link]
    roles['model']['outputs'][0]['links'].remove(old_link)
    roles['cache']['inputs'][0]['link']=None
    def connect(source,source_slot,target,target_slot,kind):
        index=max([graph['last_link_id'],*[link[0] for link in graph['links']]])+1
        graph['last_link_id']=index
        graph['links'].append([index,source['id'],source_slot,target['id'],target_slot,kind])
        source['outputs'][source_slot]['links'].append(index);target['inputs'][target_slot]['link']=index
    connect(roles['model'],0,loader,0,'MODEL');connect(loader,0,roles['cache'],0,'MODEL')
    connect(loader,2,trigger,0,'STRING');connect(trigger,0,preview,0,'STRING');connect(loader,3,loaded,0,'STRING')
    graph['last_node_id']=first_id+3
    graph['groups'].append({'id':max(group['id'] for group in graph['groups'])+1,'title':'可选LoRA · 列表管理与触发词预览','bounding':[15,1470,2055,605],
                            'color':'#605e86','font_size':24,'flags':{}})
    graph['extra']['huizuoLoraManager']={'optional':True,'enabled':False,'model_only':True,'trigger_words_auto_apply':False,
                                      'plugin_id':'comfyui-lora-manager','registry_version':plugin['version'],'archive_sha256':plugin['archive_sha256']}
    guide=roles['guide'];guide['widgets_values'][0]+='\n\n**可选LoRA管理版：** 与Aaalice相同的LoRA Manager，列表为空、总开关关闭。模型链为UNET→LoRA→Cache→采样。只接MODEL，不接CLIP／PE。侧栏「LoRA管理」切总开关；原生节点选择条目和强度，触发词仅预览，不自动改提示词。仅选择Qwen Image2.1基座的合法权重，不沿用Anima／Flux／SDXL LoRA。安装与边界见LoRA使用说明.md。缺插件时用普通流程。'
    guide['widgets_values_named']['text']=guide['widgets_values'][0]
    return graph

def main():
    base=json.loads((ROOT/'workflows/00-绘作台-整合版.json').read_text(encoding='utf-8'))
    plugin=json.loads((ROOT/'deploy/lora-manager-plugin.json').read_text(encoding='utf-8'))
    result=build(base,plugin)
    path=ROOT/'workflows/20-绘作台-LoRA管理版.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path.name)

if __name__=='__main__':main()
