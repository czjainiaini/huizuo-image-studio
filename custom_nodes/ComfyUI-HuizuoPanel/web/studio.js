import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { createPanel } from "./panel.js?v=0.4.4";
import { enhanceLocally } from "./pe-client.js?v=0.4.4";
import { role, readWidget } from "./controller.js?v=0.4.4";

let panel, panelContainer;
const css = document.createElement("link");
css.rel = "stylesheet";
css.href = new URL("./studio.css?v=0.4.4", import.meta.url).href;
document.head.append(css);
const viewUrl = ({ filename, subfolder = "", type = "output" }) => {
  const parts = filename.replaceAll("\\", "/").split("/");
  const basename = parts.pop();
  const folder = [subfolder, ...parts].filter(Boolean).join("/");
  return api.apiURL(`/view?${new URLSearchParams({ filename: basename, subfolder: folder, type })}`);
};

app.registerExtension({
  name: "Huizuo.StudioPanel",
  async setup() {
    if (!app.extensionManager?.registerSidebarTab) {
      console.warn("绘作台面板需要新版 ComfyUI 前端；工作流仍可使用原生节点运行。");
      return;
    }
    app.extensionManager.registerSidebarTab({
      id: "huizuo-studio", title: "绘作台", icon: "pi pi-palette", type: "custom",
      tooltip: "文生图 · 单图编辑 · 多图融合",
      render(container) {
        // ComfyUI's reactive slot calls render again when widget values change.
        // Keep the editing DOM mounted so caret, IME and scrolling stay intact.
        if (panel && panelContainer === container) {
          panel.syncFromGraph();
          return;
        }
        panel?.destroy();
        panelContainer = container;
        panel = createPanel(container, {
          getGraph: () => app.graph,
          confirm: message => window.confirm(message),
          viewUrl,
          loraManagerUrl: "/loras",
          async checkRuntime() {
            const responses = await Promise.all([api.fetchApi("/object_info"), api.fetchApi("/system_stats")]);
            if (responses.some(res => !res.ok)) throw new Error("无法读取 ComfyUI 运行环境，请检查服务连接。");
            const [registry, stats] = await Promise.all(responses.map(res => res.json()));
            const missing = [];
            for (const [key, param] of [["model", "unet_name"], ["clip", "clip_name"], ["vae", "vae_name"]]) {
              const node = role(app.graph, key);
              const selected = readWidget(node, param);
              const available = registry[node?.type]?.input?.required?.[param]?.[0];
              if (!selected || !Array.isArray(available) || !available.includes(selected)) missing.push(key);
            }
            const errors = [];
            if(role(app.graph,"lora")){
              for(const name of ["Lora Loader (LoraManager)","TriggerWord Toggle (LoraManager)"]){
                if(!registry[name])errors.push("LoRA管理版缺少ComfyUI-LoRA-Manager插件，请安装后重启，或使用普通工作流。");
              }
            }
            if (missing.length) errors.push(`缺少${missing.map(key => ({ model: "绘图模型", clip: "文本编码器", vae: "VAE" })[key]).join("、")}，请先按部署说明安装。`);
            if (!stats.devices?.some(device => device.type === "cuda")) errors.push("当前未检测到 CUDA GPU，仅可验收界面和工作流。");
            return errors;
          },
          async openWorkflow(task, options = {}) {
            const files = { t2i: "01-文生图.json", edit: "02-单图编辑.json", multi: "03-多图融合.json", "pe-t2i":"10-可选提示词优化-文生图.json", "pe-edit":"11-可选提示词优化-编辑.json", lora:"20-绘作台-LoRA管理版.json" };
            const file = files[task];
            if (!file) throw new Error("未知的工作流任务");
            if (app.graph?._nodes?.length && !options.confirmed && !window.confirm("将载入内置工作流并切换当前画布，请先保存修改。继续载入吗？")) return;
            const res = await fetch(new URL(`./workflows/${encodeURIComponent(file)}?v=0.4.4`, import.meta.url));
            if (!res.ok) throw new Error(`内置工作流载入失败：HTTP ${res.status}，请更新安装包。`);
            await app.loadGraphData(await res.json(), true, true, file);
          },
          async upload(file) {
            const body = new FormData(); body.append("image", file); body.append("type", "input");
            // Core LoadImage lists top-level input files in its model registry.
            body.append("overwrite", "false");
            const res = await api.fetchApi("/upload/image", { method: "POST", body });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
          },
          queue: () => app.queuePrompt(0, 1),
          enhancePrompt: request => enhanceLocally(api,request),
        });
      },
      destroy() { panel?.destroy(); panel = undefined; panelContainer = undefined; },
    });
    api.addEventListener("executed", event => {
      if (String(event.detail?.node) !== String(role(app.graph,"save")?.id)) return;
      const info = event.detail?.output?.images?.[0]; if (info) panel?.showResult(info);
    });
    api.addEventListener("execution_error", event => {
      if (role(app.graph,"encode")) panel?.showError(`生成失败：${event.detail?.exception_message ?? "请查看 ComfyUI 错误提示"}`);
    });
  },
  afterConfigureGraph() { panel?.refresh(); },
  async beforeRegisterNodeDef(nodeType,nodeData) {
    if(nodeData.name!=="HuizuoCanvasPromptOptimize")return;
    const original=nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated=function(...args){
      const value=original?.apply(this,args);
      for(const widget of this.widgets ?? [])widget.label=({enabled:"启用AI优化（默认关闭）",task:"优化任务",prompt:"原始要求",max_length:"输出长度上限（含思考）"})[widget.name] ?? widget.label;
      return value;
    };
  },
});
