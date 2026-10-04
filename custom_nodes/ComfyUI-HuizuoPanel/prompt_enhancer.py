"""Thin optional PE adapter over ComfyUI's existing CLIP generate API.

Keeps differently sized image references separate and ordered; no downloads,
remote APIs or diffusion jobs. Official prompts are inert bundled text.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

class HuizuoQwenPromptEnhance:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{
            'enabled':('BOOLEAN',{'default':False}),
            'task':(['t2i','edit'],),
            'prompt':('STRING',{'multiline':True,'default':''}),
            'max_length':('INT',{'default':4096,'min':512,'max':32768}),
        },'optional':{'clip':('CLIP',{'lazy':True}),
                     **{f'image_{index}':('IMAGE',{'lazy':True}) for index in range(1,5)}}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('enhanced_json',)
    FUNCTION='enhance'
    CATEGORY='绘作台/可选提示词优化'
    DESCRIPTION='默认关闭。开启后使用官方任务专用PE权重，返回可预览的JSON；不生成图片。'
    @staticmethod
    def require_gpu():
        import comfy.model_management as management
        if management.get_torch_device().type!='cuda':raise ValueError('无卡模式只下载PE权重；提示词优化需要GPU。')

    def check_lazy_status(self,enabled,task,prompt,max_length,clip=None,**images):
        if not enabled:return []
        self.require_gpu()
        pending=[]
        if clip is None:pending.append('clip')
        if task=='edit':pending += [key for key,value in images.items() if key.startswith('image_') and value is None]
        return pending

    def enhance(self,enabled,task,prompt,max_length,clip=None,**images):
        if not enabled:
            return (json.dumps({'rewritten_prompt':prompt,'wh_ratio':'','ratio_follow':'<image1>' if task=='edit' else ''},ensure_ascii=False),)
        if not prompt.strip():raise ValueError('先填写需要优化的要求。')
        self.require_gpu()
        if clip is None:raise ValueError('官方PE优化需要单独的PE CLIP模型。普通跑图可以关闭此节点。')
        if task not in {'t2i','edit'}:raise ValueError('未知PE任务。')
        ordered=[];gap=False
        for index in range(1,5):
            image=images.get(f'image_{index}')
            if image is None:gap=True;continue
            if gap:raise ValueError('参考图必须从图1开始连续连接，不能跳号。')
            if image.shape[0]!=1:raise ValueError('每个参考端口只接受一张图，请不要连接图像批次。')
            image=image[...,:3]
            height,width=image.shape[1:3]
            if height*width>1024*1024:
                import torch.nn.functional as functional
                scale=math.sqrt((1024*1024)/(height*width))
                image=functional.interpolate(image.movedim(-1,1),size=(max(1,int(height*scale)),max(1,int(width*scale))),mode='bilinear',align_corners=False).movedim(1,-1)
            ordered.append(image)
        if task=='t2i' and ordered:raise ValueError('文生图PE不接受图片；请改用编辑PE。')
        if task=='edit' and not ordered:raise ValueError('编辑PE必须实际读取至少一张参考图。')
        system=(Path(__file__).parent/'web/pe'/f'{task}-system.txt').read_text(encoding='utf-8')
        vision='<|vision_start|><|image_pad|><|vision_end|>'*len(ordered)
        chat='<|im_start|>system\n'+system+'<|im_end|>\n<|im_start|>user\n'+vision+prompt+'<|im_end|>\n<|im_start|>assistant\n<think>\n'
        tokens=clip.tokenize(chat,images=ordered,thinking=True,min_length=1)
        generated=clip.generate(tokens,do_sample=True,max_length=max_length,temperature=1.0,top_k=20,top_p=.95,
                                min_p=0,repetition_penalty=1.0,presence_penalty=1.5 if task=='t2i' else 0,seed=42,mtp=False)
        text=clip.decode(generated)
        if '</think>' not in text:raise ValueError('PE思考未结束，输出长度不足；原提示词保留。请增加PE输出长度后再试。')
        answer=text.split('</think>',1)[1].strip()
        if not answer:raise ValueError('PE未返回增强指令，原提示词保留。')
        return (answer,)


class HuizuoCanvasPromptOptimize:
    """Optional canvas text edge; no PE loader dependency exists when disabled."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'enabled': ('BOOLEAN', {'default': False}),
            'task': (['文生图', '图像编辑'],),
            'prompt': ('STRING', {'multiline': True, 'default': ''}),
            'max_length': ('INT', {'default': 8192, 'min': 512, 'max': 32768}),
        }, 'optional': {'clip': ('CLIP', {'lazy': True}),
            **{f'image_{i}': ('IMAGE', {'lazy': True}) for i in range(1, 5)}}}

    RETURN_TYPES = ('STRING', 'STRING')
    RETURN_NAMES = ('prompt', 'details_json')
    FUNCTION = 'optimize'
    CATEGORY = '绘作台/提示词'
    DESCRIPTION = '第一项为AI优化开关，默认关闭。关闭原文透传；开启按任务读取本地官方PE权重，不自动下载。只回填优化文字，不自动改变画幅。'

    def check_lazy_status(self, enabled, **inputs):
        if not enabled:
            return []
        return [key for key, value in inputs.items()
                if (key == 'clip' or key.startswith('image_')) and value is None]

    def optimize(self, enabled, task, prompt, max_length, clip=None, **images):
        if not enabled:
            return prompt, json.dumps({'enabled': False, 'rewritten_prompt': prompt}, ensure_ascii=False)
        profile = {'文生图': 't2i', '图像编辑': 'edit'}.get(task)
        if profile is None:
            raise ValueError('请选择文生图或图像编辑优化任务。')
        adapter = HuizuoQwenPromptEnhance()
        adapter.require_gpu()
        if clip is None:
            clip = load_canvas_pe_clip(profile)
        answer = adapter.enhance(True, profile, prompt, max_length, clip=clip, **images)[0]
        rewritten = parse_canvas_rewrite(answer, profile, sum(value is not None for value in images.values()))
        return rewritten, answer


def parse_canvas_rewrite(answer, profile, count):
    raw = answer.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1].removesuffix('```').strip()
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError('AI优化结果不是完整JSON；原始要求仍保留，可以关闭优化继续出图。') from error
    if not isinstance(result, dict):
        raise ValueError('AI优化结果必须是JSON对象。')
    text = result.get('rewritten_prompt')
    if not isinstance(text, str) or not text.strip() or '<think>' in text or '</think>' in text:
        raise ValueError('AI优化没有返回可用提示词；原始要求仍保留。')
    import re
    refs = [int(value) for value in re.findall(r'<image(\d+)>', text)]
    if (profile == 't2i' and refs) or any(value < 1 or value > count for value in refs):
        raise ValueError('AI优化引用了未提供的图片；原始要求仍保留。')
    return text.strip()


def load_canvas_pe_clip(profile):
    import folder_paths
    filename = 'qwen3.5_9b_qwen_image_2.1_pe_' + ('t2i' if profile == 't2i' else 'i2i') + '.int8_convrot.safetensors'
    path = folder_paths.get_full_path('text_encoders', filename)
    if not path or not Path(path).is_file():
        raise ValueError('没有准备对应的官方PE模型。关闭画布AI优化即可普通出图；需要时先在无卡模式准备PE权重。')
    stat = Path(path).stat()
    return _load_canvas_pe_clip(str(Path(path).resolve()), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=1)
def _load_canvas_pe_clip(path, size, mtime_ns):
    import comfy.sd
    import folder_paths
    return comfy.sd.load_clip(ckpt_paths=[path], embedding_directory=folder_paths.get_folder_paths('embeddings'),
                              clip_type=comfy.sd.CLIPType.QWEN_IMAGE, model_options={})
