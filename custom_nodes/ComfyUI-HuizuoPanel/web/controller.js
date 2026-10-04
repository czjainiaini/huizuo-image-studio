export const TASKS = {
  t2i: { label: "文生图", hint: "描述你想看见的画面，无需上传图片。" },
  edit: { label: "单图编辑", hint: "上传主图，说清要改哪里、哪些内容需要保留。" },
  multi: { label: "多图融合", hint: "图1作为主画面，图2–4提供人物、商品或风格参考。" },
};
export const PRESETS = {
  t2i: [
    ["中文海报", '一张精致的咖啡店海报，暖色自然光，木质桌面上一杯拿铁，背景简洁。海报标题准确写出“今天也要好好生活”，文字清晰，构图留白。'],
    ["产品摄影", "一瓶磨砂玻璃香水置于米色石台上，柔和侧光，瓶身材质细腻，自然接触阴影，简洁高级的产品摄影。"],
    ["人像写真", "一位成年女性站在窗边，白色衬衫，自然微笑，柔和窗光，皮肤纹理真实，背景干净，电影人像摄影。"],
  ],
  edit: [
    ["换背景", "将当前图片的背景改为傍晚的海边，保留主体的身份、服装、姿态和构图，让光线和阴影自然协调。"],
    ["换服装", "将当前图片中人物的外套改为深蓝色牛仔夹克，保留面部身份、发型、姿态和背景，衣物纹理与光影自然。"],
    ["改文字", '将当前图片中招牌上的文字改为“欢迎光临”，保留招牌的材质、透视和其他画面内容，文字准确清晰。'],
  ],
  multi: [
    ["商品入景", "以 <image1> 为主画面，将 <image2> 中的物品自然放入主画面。保持原有构图，匹配物品透视、比例、材质、光线和接触阴影。"],
    ["人物合照", "将 <image1> 与 <image2> 中的成年人物放入同一张自然合照，分别保留两人的面部身份和服装，以图1的场景为背景，统一光线和透视。"],
    ["风格参考", "保持 <image1> 的主体、身份和构图，参考 <image2> 的配色、材质和光照风格，形成统一自然的画面。"],
  ],
};
export const RATIOS = ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"];
export const QUALITIES = { quick: 20, standard: 25, fine: 40 };
export const DEFAULT_EDIT_RESOLUTION = 992;

export function role(graph, key) {
  return graph?._nodes?.find(n => n.properties?.huizuoRole === key);
}
export function readWidget(node, name) {
  return node?.widgets?.find(w => w.name === name)?.value;
}
export function writeWidget(node, name, value) {
  const w = node?.widgets?.find(w => w.name === name);
  if (!w) throw new Error(`找不到参数 ${name}，请导入本包工作流并更新 ComfyUI。`);
  if (name === "image" && Array.isArray(w.options?.values) && !w.options.values.includes(value)) w.options.values.push(value);
  w.value = value;
  w.callback?.(value);
  node.setDirtyCanvas?.(true, true);
}
export function promptNode(graph) { return role(graph,"pe") ?? role(graph,"encode"); }
export function readPrompt(graph) { return readWidget(promptNode(graph),"prompt"); }
export function writePrompt(graph,value) { writeWidget(promptNode(graph),"prompt",value); }
export function canvasOptimizationEnabled(graph) { return Boolean(readWidget(role(graph,"pe"),"enabled")); }
export function setCanvasOptimization(graph,enabled) {
  const node=role(graph,"pe");
  if(!node)throw new Error("此旧工作流没有画布AI优化节点，请载入新版内置工作流。");
  writeWidget(node,"enabled",Boolean(enabled));graph.change?.();
}
export function settings(graph) {
  graph.extra ??= {};
  graph.extra.huizuo ??= { version: 1, task: "t2i", refCount: 2, ratio: "1:1", pixelBudget: 1, quality: "standard" };
  return graph.extra.huizuo;
}
export function dimensions(ratio, budget) {
  if (!RATIOS.includes(ratio) || ![1, 2, 4].includes(Number(budget))) throw new Error("不支持的画幅或像素预算");
  const [w, h] = ratio.split(":").map(Number);
  const scale = Math.sqrt(Number(budget) * 1024 * 1024 / (w * h));
  return [Math.round(w * scale / 32) * 32, Math.round(h * scale / 32) * 32];
}
export function setSize(graph, ratio, budget) {
  const [w, h] = dimensions(ratio, budget);
  writeWidget(role(graph, "latent"), "width", w);
  writeWidget(role(graph, "latent"), "height", h);
  Object.assign(settings(graph), { ratio, pixelBudget: Number(budget) });
  graph.setDirtyCanvas?.(true, true);
  return [w, h];
}
export function setTask(graph, task, refCount = settings(graph).refCount) {
  if (!TASKS[task] || ![2, 3, 4].includes(Number(refCount))) throw new Error("不支持的任务或参考图数量");
  const enc = role(graph, "encode");
  if (!enc || !role(graph, "latentSwitch")) throw new Error("请先导入绘作台工作流");
  const cfg = settings(graph);
  // Per-task drafts live inside the workflow, not in browser-wide storage.
  cfg.drafts ??= {};
  cfg.drafts[cfg.task] = readPrompt(graph) ?? "";
  const count = task === "t2i" ? 0 : task === "edit" ? 1 : Number(refCount);
  // The pinned Qwen 2.1 edit path is noisy at budget 1024 (ComfyUI #16435).
  // Migrate legacy workflows on mode change; text-to-image uses its own latent.
  if (count && Number(readWidget(enc, "resolution")) === 1024) writeWidget(enc, "resolution", DEFAULT_EDIT_RESOLUTION);
  // Disconnect from the tail: core autogrow compacts its ports on the next frame.
  for (let i = 4; i > count; i--) {
    const image = role(graph, `image${i}`);
    const slot = enc.inputs.findIndex(p => p.name === `images.image_${i}`);
    if (!image) throw new Error(`缺少参考图 ${i} 节点，请重新导入完整工作流。`);
    if (slot >= 0 && enc.inputs[slot].link != null) enc.disconnectInput(slot);
    const optimizer=role(graph,"pe");
    const peSlot=optimizer?.inputs.findIndex(p=>p.name===`image_${i}`);
    if(optimizer && peSlot>=0 && optimizer.inputs[peSlot].link!=null)optimizer.disconnectInput(peSlot);
    image.mode = 2;
  }
  // Connecting the spare slot makes core grow the next slot synchronously.
  for (let i = 1; i <= count; i++) {
    const image = role(graph, `image${i}`);
    const slot = enc.inputs.findIndex(p => p.name === `images.image_${i}`);
    if (!image || slot < 0) throw new Error(`缺少参考图 ${i} 接口，请更新 ComfyUI 后重新导入。`);
    const current = enc.inputs[slot].link;
    const linked = current != null ? graph.links[current] : null;
    image.mode = 0;
    if (!linked || linked.origin_id !== image.id) image.connect(0, enc, slot);
    const optimizer=role(graph,"pe");
    const peSlot=optimizer?.inputs.findIndex(p=>p.name===`image_${i}`);
    if(optimizer && peSlot>=0){
      const peLink=optimizer.inputs[peSlot].link;
      if(peLink==null || graph.links[peLink]?.origin_id!==image.id)image.connect(0,optimizer,peSlot);
    }
  }
  writeWidget(role(graph, "latentSwitch"), "switch", task !== "t2i");
  const output = role(graph, "save");
  if (output?.type === "SaveImage") writeWidget(output, "filename_prefix", `Huizuo/${task}/image`);
  Object.assign(cfg, { task, refCount: Number(refCount) });
  if(role(graph,"pe"))writeWidget(role(graph,"pe"),"task",task==="t2i"?"文生图":"图像编辑");
  writePrompt(graph, cfg.drafts[task] ?? PRESETS[task][0][1]);
  graph.change?.();
  graph.setDirtyCanvas?.(true, true);
}
export function validate(graph) {
  const cfg = settings(graph);
  const errors = [];
  for (const name of ["encode", "sampler", "latentSwitch", "save", "model", "clip", "vae"]) {
    if (!role(graph, name)) errors.push("请先导入绘作台工作流。");
  }
  if (errors.length) return [...new Set(errors)];
  if (!readPrompt(graph)?.trim()) errors.push("请先填写画面或编辑要求。");
  const count = cfg.task === "t2i" ? 0 : cfg.task === "edit" ? 1 : cfg.refCount;
  if (count && Number(readWidget(role(graph, "encode"), "resolution")) === 1024) errors.push("编辑预算1024可能产生颗粒，请改为992或1056。");
  for (let i = 1; i <= count; i++) {
    if (!readWidget(role(graph, `image${i}`), "image")) errors.push(`请上传图 ${i}。`);
  }
  const steps = Number(readWidget(role(graph, "sampler"), "steps"));
  if (!Number.isInteger(steps) || steps < 1 || steps > 100) errors.push("步数需要在1–100之间。");
  const seed = Number(readWidget(role(graph, "sampler"), "seed"));
  if (!Number.isSafeInteger(seed) || seed < 0) errors.push("种子需要是非负安全整数。");
  return errors;
}
