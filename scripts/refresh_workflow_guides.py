"""Refresh teaching text only; keep existing graph identities and generation settings."""
import copy
import json
from pathlib import Path
from build_workflows import Graph
from generate_pe_workflows import build

root=Path(__file__).resolve().parents[1]
for path in (root/'workflows').glob('*.json'):
    graph=json.loads(path.read_text(encoding='utf-8'))
    if graph.get('extra',{}).get('huizuoLoraManager'):
        continue # Optional manager layout has its own generator and teaching text.
    before=copy.deepcopy(graph)
    optional=graph.get('extra',{}).get('huizuoPromptEnhancer',{})
    task=optional.get('task') if optional else graph['extra']['huizuo']['task']
    generated=build(task) if optional else Graph(task).build()
    note=next(node for node in generated['nodes'] if node['type']=='MarkdownNote')
    target=next(node for node in graph['nodes'] if node['type']=='MarkdownNote')
    target['widgets_values']=copy.deepcopy(note['widgets_values'])
    if 'widgets_values_named' in target: target['widgets_values_named']['text']=target['widgets_values'][0]
    if optional:
        example=next(node for node in generated['nodes'] if node['type']=='HuizuoCanvasPromptOptimize')
        actual=next(node for node in graph['nodes'] if node['type']=='HuizuoCanvasPromptOptimize')
        actual['widgets_values'][2]=example['widgets_values'][2]
    assert graph['links']==before['links'] and graph['extra']==before['extra'] and graph['id']==before['id']
    for old,new in zip(before['nodes'],graph['nodes']):
        if new['type'] not in {'MarkdownNote','HuizuoCanvasPromptOptimize'}: assert old==new
    path.write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path.name)
