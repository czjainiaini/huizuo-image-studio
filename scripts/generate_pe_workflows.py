"""Generate optional text-only preview workflows using the same canvas switch."""
import json
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]
def build(task):
    nodes=[];links=[]
    def node(number,kind,title,pos,widgets,inputs,outputs):
        value={'id':number,'type':kind,'title':title,'pos':pos,'size':[360,250],'flags':{},'order':len(nodes),'mode':0,
               'inputs':inputs,'outputs':outputs,'properties':{'Node name for S&R':kind},'widgets_values':widgets}
        nodes.append(value);return value
    def port(name,kind,link=None):return {'name':name,'type':kind,'link':link}
    def output(name,kind):return {'name':name,'type':kind,'links':[]}
    def connect(source,slot,target,target_slot,kind):
        number=len(links)+1;links.append([number,source['id'],slot,target['id'],target_slot,kind])
        source['outputs'][slot]['links'].append(number);target['inputs'][target_slot]['link']=number
    optimizer=node(2,'HuizuoCanvasPromptOptimize','中文要求 / AI优化开关 · 默认关闭',[490,310],[False,'文生图' if task=='t2i' else '图像编辑','白色陶瓷杯，红色把手，杯身准确写“COFFEE”，米色背景，柔和产品摄影光线。' if task=='t2i' else '以 <image1> 杯子产品照为主图，仅将 <image2> 的蓝白格纹应用到杯身；保留红把手、“COFFEE”文字和米色背景，不带入图2背景。',8192],
                   [port('clip','CLIP'),*[port(f'image_{index}','IMAGE') for index in range(1,5)]],[output('prompt','STRING'),output('details_json','STRING')])
    optimizer['size']=[400,450]
    preview=node(3,'PreviewAny','可用提示词 · 只复制这里的文字',[930,310],[],[port('source','*')],[output('STRING','STRING')])
    detail=node(5,'PreviewAny','结构详情 · 不送入绘图编码器',[930,630],[],[port('source','*')],[output('STRING','STRING')])
    connect(optimizer,0,preview,0,'STRING');connect(optimizer,1,detail,0,'STRING')
    if task=='edit':
        for index in range(1,3):
            image=node(10+index,'HuizuoEphemeralLoadImage',f'图{index} · '+('编辑主图' if index==1 else '参考图'),[40,630+(index-1)*330],['','image'],[],[output('IMAGE','IMAGE'),output('MASK','MASK')])
            connect(image,0,optimizer,index,'IMAGE')
    note='普通出图请打开00／01／02／03／20工作流：AI优化开关已经在主画布，开启后自动先优化再出图。本文件仅用于独立预览文字，不生成图片。默认关闭，原文透传且无需PE权重；开启后按任务加载已准备的本地官方PE模型，需要GPU。\n无卡模式可下载模型，不执行PE。图1为主图，图2–4按顺序提供参考。默认8192输出长度含思考，截断时增加长度或关闭优化。官方T2I参考16256、编辑24000，长度越大耗时越长。\n只采用左侧可用提示词文字；结构详情不送入绘图模型。画幅建议需核对，主生成流程仍按主图与尺寸设置决定画幅。'
    note+='\n示例素材：文生图无需图片；编辑示例图1为白杯红把手产品照，图2为蓝白格纹。按任务对应填写，未逐条验证任意示例效果。\n侧栏提示词示例可预览／采用／撤销，更多2–4图分工见包内提示词示例.md。原生节点在「绘作台/可选提示词优化」分类；本工作流只预览，不自动回填另一个生成画布。'
    node(4,'MarkdownNote','使用说明',[40,30],[note],[],[])['size']=[1220,210]
    return {'id':str(uuid.uuid4()),'revision':0,'last_node_id':max(node['id'] for node in nodes),'last_link_id':len(links),
            'nodes':nodes,'links':links,'groups':[],'config':{},'extra':{'ds':{'scale':.7,'offset':[20,20]},'huizuoPromptEnhancer':{'task':task,'optional':True}},'version':.4}
def main():
    for task,name in [('t2i','10-可选提示词优化-文生图.json'),('edit','11-可选提示词优化-编辑.json')]:
        path=ROOT/'workflows'/name;path.write_text(json.dumps(build(task),ensure_ascii=False,indent=2),encoding='utf-8')
        print(path.name)

if __name__ == '__main__': main()
