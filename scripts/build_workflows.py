"""Build original ComfyUI graphs with optional PE and memory-media nodes; references are not copied."""
import copy
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen_image_2.1_int8_convrot.safetensors"
CLIP = "qwen3vl_8b_int8_convrot.safetensors"
VAE = "qwen_image_2.1_vae_bf16.safetensors"
PROMPTS = {
    "t2i": '一张精致的咖啡店海报，暖色自然光，木质桌面上一杯拿铁，背景简洁。海报标题准确写出“今天也要好好生活”，文字清晰，构图留白，竖版商业摄影风格。',
    "edit": '将 <image1> 的背景改为傍晚的海边，保留主体的身份、服装、姿态和构图，让光线和阴影自然协调。',
    "multi": '以 <image1> 为主画面，将 <image2> 中的物品自然放入主画面。保持主图主体身份和原有构图，匹配物品的透视、比例、材质、光线和接触阴影。',
}
PROMPT_GUIDANCE = "\n\n**中文示例：** 侧栏提示词示例先预览再采用，可撤销；多图明确图1主图、图2–4各自提供什么，3／4图先选择对应图数。完整15个中文模板见提示词示例.md。免费结构助手按填写的分工整理草稿，不读取图片。"



def port(name, kind, **kwargs):
    return {"name": name, "type": kind, **kwargs}


class Graph:
    def __init__(self, task):
        self.task, self.nodes, self.links, self.groups = task, [], [], []

    def node(self, role, kind, title, pos, size, ins=(), outs=(), widgets=None, names=None, **props):
        n = {"id": len(self.nodes) + 1, "type": kind, "title": title, "pos": pos,
             "size": size, "flags": {}, "order": len(self.nodes), "mode": 0,
             "inputs": [port(a, b, link=None, **c) for a, b, c in ins],
             "outputs": [port(a, b, links=[]) for a, b in outs],
             "properties": {"Node name for S&R": kind, "huizuoRole": role, **props}}
        if widgets is not None:
            n["widgets_values"] = widgets
        if names is not None:
            n["widgets_values_named"] = dict(zip(names, widgets))
        self.nodes.append(n)
        return n

    def connect(self, source, slot, target, name):
        ti = next(i for i, p in enumerate(target["inputs"]) if p["name"] == name)
        li = len(self.links) + 1
        self.links.append([li, source["id"], slot, target["id"], ti, source["outputs"][slot]["type"]])
        source["outputs"][slot]["links"].append(li)
        target["inputs"][ti]["link"] = li

    def group(self, title, bounds, color):
        self.groups.append({"id": len(self.groups) + 1, "title": title, "bounding": bounds,
                            "color": color, "font_size": 24, "flags": {}})

    def build(self):
        task = self.task
        models_url = "https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/cb504a4090723e43f17ad01cec0359490e2de613/"
        model = self.node("model", "UNETLoader", "扩散模型 · INT8", [40, 1180], [400, 90],
                          outs=[("MODEL", "MODEL")], widgets=[MODEL, "default"], names=["unet_name", "weight_dtype"],
                          models=[{"name": MODEL, "url": models_url + "diffusion_models/" + MODEL, "directory": "diffusion_models"}])
        clip = self.node("clip", "CLIPLoader", "文本编码器 · Qwen3-VL", [470, 1180], [400, 120],
                         outs=[("CLIP", "CLIP")], widgets=[CLIP, "qwen_image", "default"], names=["clip_name", "type", "device"],
                         models=[{"name": CLIP, "url": models_url + "text_encoders/" + CLIP, "directory": "text_encoders"}])
        vae = self.node("vae", "VAELoader", "图像编解码器 · 2.1 专用 VAE", [900, 1180], [400, 70],
                        outs=[("VAE", "VAE")], widgets=[VAE], names=["vae_name"],
                        models=[{"name": VAE, "url": models_url + "vae/" + VAE, "directory": "vae"}])
        cache = self.node("cache", "QwenImage21Cache", "参考图缓存 · 自动", [1330, 1180], [280, 90],
                          ins=[("model", "MODEL", {})], outs=[("MODEL", "MODEL")],
                          widgets=["auto", "default"], names=["device", "dtype"])
        # Five autogrow slots: four reference slots and one spare, as core's editor expects.
        enc = self.node("encode", "TextEncodeQwenImage21", "绘图编码 · 接收上方提示词", [40, 1070], [440, 230],
                        ins=[("clip", "CLIP", {})] + [(f"images.image_{i}", "IMAGE", {"shape": 7, "label": f"参考图 {i}"}) for i in range(1, 6)] + [("vae", "VAE", {"shape": 7})],
                        outs=[("positive", "CONDITIONING"), ("negative", "CONDITIONING"), ("latent", "LATENT")],
                        widgets=[PROMPTS[task], "", 992], names=["prompt", "negative_prompt", "resolution"])
        images = []
        for i in range(1, 5):
            image = self.node(f"image{i}", "HuizuoEphemeralLoadImage", f"图 {i} · {'主图 / 构图基准' if i == 1 else '参考素材'}",
                              [530 + ((i-1) % 2) * 335, 310 + ((i-1)//2)*345], [310, 285],
                              outs=[("IMAGE", "IMAGE"), ("MASK", "MASK")], widgets=["", "image"], names=["image", "upload"])
            image["mode"] = 2
            images.append(image)
        latent = self.node("latent", "EmptyLatentImage", "文生图尺寸 · 编辑模式沿用主图", [1220, 700], [280, 130],
                           outs=[("LATENT", "LATENT")], widgets=[1024, 1024, 1], names=["width", "height", "batch_size"])
        switch = self.node("latentSwitch", "ComfySwitchNode", "尺寸来源 · 开=主图 / 关=文生图", [1220, 910], [280, 90],
                           ins=[("on_false", "LATENT", {"shape": 7}), ("on_true", "LATENT", {"shape": 7})],
                           outs=[("output", "LATENT")], widgets=[task != "t2i"], names=["switch"])
        sampler = self.node("sampler", "KSampler", "02 · 出图参数", [1220, 310], [280, 290],
                            ins=[("model", "MODEL", {}), ("positive", "CONDITIONING", {}), ("negative", "CONDITIONING", {}), ("latent_image", "LATENT", {})],
                            outs=[("LATENT", "LATENT")], widgets=[42, "randomize", 25, 1, "euler", "simple", 1],
                            names=["seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"])
        decode = self.node("decode", "VAEDecode", "解码", [1580, 1190], [220, 70],
                           ins=[("samples", "LATENT", {}), ("vae", "VAE", {})], outs=[("IMAGE", "IMAGE")])
        save = self.node("save", "HuizuoEphemeralPreview", "03 · 内存预览 · 关机清除", [1580, 310], [470, 690],
                         ins=[("images", "IMAGE", {})])
        self.node("guide", "MarkdownNote", "绘作台 · Qwen Image 2.1 创作工作流", [40, 30], [2010, 185],
                  widgets=["# 绘作台 · Qwen Image 2.1\n**三步操作：** ①选择对应工作流，填写画面或编辑要求 → ②编辑时上传素材，调整尺寸/步数 → ③点击 ComfyUI「运行」。\n\n**文生图：** 不上传图片。**单图编辑：** 上传图1。**多图融合：** 上传图1和图2，用 `<image1>`、`<image2>` 说明用途。图1决定编辑输出比例。\n\n左侧「绘作台」为可选的快捷操作：整合版可切换三个任务，使用2–4张参考图。模型在下方设置一次，日常主要操作上方区域。\n\n文生图默认1024²；编辑默认约1MP（992预算）。25步起步，40步用于细节对比。编辑预算请避开1024，以免当前版本出现颗粒。PNG保留工作流，用户修改后请另存自己的副本。授权与环境说明见 README。"], names=["text"])
        pe = self.node("pe", "HuizuoCanvasPromptOptimize", "01 · 中文要求 / AI优化开关（默认关闭）", [40,310], [440,450],
                       ins=[("clip","CLIP",{"shape":7})]+[(f"image_{i}","IMAGE",{"shape":7}) for i in range(1,5)],
                       outs=[("prompt","STRING"),("details_json","STRING")],
                       widgets=[False,'文生图' if task=='t2i' else '图像编辑',PROMPTS[task],8192],
                       names=['enabled','task','prompt','max_length'])
        pe_preview = self.node("pePreview","PreviewAny","实际送入绘图的提示词",[40,800],[440,220],
                               ins=[('source','*',{})],outs=[('STRING','STRING')])
        enc['inputs'].append(port('prompt','STRING',link=None,widget={'name':'prompt'}))
        self.connect(pe,0,enc,'prompt');self.connect(pe,0,pe_preview,'source')
        for a, o, b, name in [(model,0,cache,"model"),(clip,0,enc,"clip"),(vae,0,enc,"vae"),
                              (cache,0,sampler,"model"),(enc,0,sampler,"positive"),(enc,1,sampler,"negative"),
                              (latent,0,switch,"on_false"),(enc,2,switch,"on_true"),(switch,0,sampler,"latent_image"),
                              (sampler,0,decode,"samples"),(vae,0,decode,"vae"),(decode,0,save,"images")]:
            self.connect(a,o,b,name)
        guide = next(node for node in self.nodes if node["properties"].get("huizuoRole") == "guide")
        guide["widgets_values"][0] += PROMPT_GUIDANCE
        guide["widgets_values_named"]["text"] = guide["widgets_values"][0]
        count = {"t2i": 0, "edit": 1, "multi": 2}[task]
        for i, image in enumerate(images[:count], 1):
            image["mode"] = 0
            self.connect(image,0,enc,f"images.image_{i}")
            self.connect(image,0,pe,f"image_{i}")
        for node in [model,clip,vae,cache,decode]:
            node['pos'][1]+=380
        guide['widgets_values'][0] += '\n\n**画布AI优化：** 最左侧节点第一项“启用AI优化”为开关，默认关闭。关闭直接使用原始中文要求；开启后本地官方PE先优化文字，再送入绘图编码器。无需更换画布或手动复制JSON。PE权重按需准备，未准备时关闭可正常出图；画幅仍由原图与生成设置决定。\n**图片保留：** 本流程生成图及上传参考图在当前服务内存中使用，实例完整关机后释放；模型与设置保留。需要图片请关机前下载到本机。'
        guide['widgets_values_named']['text']=guide['widgets_values'][0]
        self.group("01 中文要求 · 可选AI优化", [15,255,490,1080], "#346c68")
        self.group("参考素材 · 图1为主图", [510, 255, 690, 825], "#5b658c")
        self.group("02  生成设置", [1205, 255, 335, 825], "#826748")
        self.group("03  作品输出", [1560, 255, 520, 825], "#665384")
        self.group("模型与解码 · 部署时设置一次", [15,1495,2065,240], "#414654")
        return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"huizuo-v0.1-{task}")), "revision": 0,
                "last_node_id": len(self.nodes), "last_link_id": len(self.links), "nodes": self.nodes,
                "links": self.links, "groups": self.groups, "config": {}, "version": 0.4,
                "extra": {"ds": {"scale": 0.65, "offset": [30, 30]},
                          "huizuo": {"version": 1, "task": task, "refCount": max(2, count),
                                     "ratio": "1:1", "quality": "standard", "pixelBudget": 1}}}


WIDGET_NAMES = {
    "UNETLoader": ["unet_name", "weight_dtype"], "CLIPLoader": ["clip_name", "type", "device"],
    "VAELoader": ["vae_name"], "QwenImage21Cache": ["device", "dtype"],
    "TextEncodeQwenImage21": ["prompt", "negative_prompt", "resolution"],
    "HuizuoEphemeralLoadImage": ["image", "upload"], "EmptyLatentImage": ["width", "height", "batch_size"],
    "ComfySwitchNode": ["switch"], "KSampler": ["seed", "control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "PreviewImage": [], "MarkdownNote": ["text"],
    "HuizuoEphemeralPreview": [],
}


def to_api(graph):
    links = {l[0]: l for l in graph["links"]}
    result = {}
    for n in graph["nodes"]:
        if n["mode"] == 2 or n["type"] == "MarkdownNote" or n['properties'].get('huizuoRole') in {'pe','pePreview'}:
            continue
        values = dict(zip(WIDGET_NAMES.get(n["type"], []), n.get("widgets_values", [])))
        values.pop("upload", None)
        values.pop("control_after_generate", None)
        for p in n["inputs"]:
            if p["link"] is not None:
                link = links[p["link"]]
                source=next(node for node in graph['nodes'] if node['id']==link[1])
                if p['name']=='prompt' and source['properties'].get('huizuoRole')=='pe':
                    # Packaged base API templates stay PE-free. Native canvas
                    # export retains the visible optional optimization branch.
                    values['prompt']=source['widgets_values_named']['prompt']
                else:values[p["name"]] = [str(link[1]), link[2]]
        result[str(n["id"])] = {"class_type": n["type"], "inputs": values, "_meta": {"title": n["title"]}}
    return result


def main():
    (ROOT / "workflows").mkdir(exist_ok=True)
    (ROOT / "api").mkdir(exist_ok=True)
    for task, filename in [("t2i", "01-文生图.json"), ("edit", "02-单图编辑.json"), ("multi", "03-多图融合.json")]:
        g = Graph(task).build()
        (ROOT / "workflows" / filename).write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding="utf-8")
        (ROOT / "api" / f"{task}.json").write_text(json.dumps(to_api(g), ensure_ascii=False, indent=2), encoding="utf-8")
    integrated = Graph("t2i").build()
    integrated["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "huizuo-v0.1-studio"))
    (ROOT / "workflows" / "00-绘作台-整合版.json").write_text(json.dumps(integrated, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Built 4 original UI workflows and 3 API templates.")


if __name__ == "__main__":
    main()
