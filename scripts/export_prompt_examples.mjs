// Build the user-readable examples from the same catalog used by the sidebar.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PROMPT_EXAMPLES, PROMPT_TIPS } from "../custom_nodes/ComfyUI-HuizuoPanel/web/prompt-examples.js";
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const sections=["# 绘作台 · 中文提示词示例与画布AI优化", "适用于0.4.4。15个用户模板均使用中文描述，由本项目编写，借鉴参考工作流的教学方式与官方输入规则。0.4.4私人镜像已保存；15个中文模板已实际GPU执行并查看原图。执行成功不代表所有编辑要求都满足：额外小字、姿势保持、参考图背景混入等限制及复测结果见[补漏验收记录](evidence/v044-complete-validation.md)。旧镜像不会随本机文档自动更新。",
"## 从哪里打开", "左侧调色盘 → 绘作台 → 画面／编辑要求下的提示词示例。选择后只预览，采用才替换原始要求，可撤销。采用不改变素材、图数或AI开关。多图模板随当前2／3／4图数量显示；换模板后核对结构助手中以前填写的保留要求。",
"## 主画布中的可选AI节点", "00／01／02／03／20生成画布的最左侧就是中文要求与AI优化节点。第一项启用AI优化默认关闭，也可用侧栏的出图前使用画布AI优化勾选框切换。关闭时原文直接送入绘图编码器，无需额外PE权重；开启时按任务加载本地官方PE，先优化再出图。编辑参考图同时接入优化节点image_1…image_4与绘图编码器，顺序一致。",
"节点类型HuizuoCanvasPromptOptimize，分类绘作台/提示词。第一路输出为可用提示词，连接绘图编码器的prompt和文字预览；第二路仅为结构详情。不会把整段JSON或思考内容送入编码器，也不自动修改画幅。主画布输入是中文；官方文生图PE可能返回英文视觉描述，准确画面文字仍按用户要求保留；编辑PE按官方输入规则处理。",
"开启需先按使用指南准备对应PE-T2I或PE-I2I权重，并使用GPU。关闭开关即可普通生成；优化出错时原始要求仍保留，关闭后重试。运行开始后关闭开关不会取消已提交的任务。10／11是同一开关节点的独立文字预览流程，不生成图片，也无需预先验证PE文件才能关闭运行。",
"侧栏提示词助手继续提供免费结构草稿和独立PE预览／采用／撤销。独立采用后关闭主画布自动优化，避免同一要求被连续优化两次。安装、启动、下载和关机清图说明见[使用指南](使用指南.md)。"];
for(const [task,title] of [["t2i","文生图"],["edit","单图编辑"],["multi","多图融合"]]){
  sections.push(`## ${title}`,PROMPT_TIPS[task]);
  for(const item of PROMPT_EXAMPLES.filter(example=>example.task===task)){
    sections.push(`### ${item.title}${item.refs>1?`（${item.refs}图）`:''}`,item.materials,
      "验证状态：中文原模板已GPU执行并查看原图；具体质量限制见上方补漏验收记录，不保证任意素材都能完全满足要求。",
      "```text\n"+item.prompt+"\n```",item.tip);
  }
}
sections.push("## 参考依据与边界", "官方PE按输入顺序引用图像，并区分优化文本与画布字段：[官方PE说明](https://github.com/QwenLM/Qwen-Image-2.1/blob/6627d87c6433151463ec4b48b8945a24fcf16a35/prompt_rewrite/README.md)。官方系统提示对明确要求与未指定内容的处理见[T2I系统提示](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I/blob/f3ed7985c788ad75b3ab7223e0c4c51e2a43545b/system_prompt.txt)、[编辑系统提示](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I/blob/72927bc08afc99b7888ceb7d7d51a12db3700bbd/system_prompt.txt)。本项目把这些规则组织成可填写的示例与素材说明；分类、示例文本和图1固定为主图是本项目的产品设计。",
"以下功能没有在当前工作流开放：透明RGBA输出、掩码局部编辑、10图输入。不要仅通过提示词或照搬官方其他后端示例，声称本包已支持这些功能。当前文生图／单图／2–4图路径及其验收边界见[evidence/v04-validation.md](evidence/v04-validation.md)。");
fs.writeFileSync(path.join(root,"提示词示例.md"),sections.join("\n\n")+"\n");
console.log(`Exported ${PROMPT_EXAMPLES.length} original prompt examples.`);
