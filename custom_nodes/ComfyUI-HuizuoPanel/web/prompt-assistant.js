export const IMAGE_ROLES = {
  instruction: ["按主提示词要求", ""],
  identity: ["人物身份", "人物身份与外观"],
  product: ["商品／物品", "指定的商品或物品"],
  style: ["画风／配色", "画风、配色和材质风格"],
  pose: ["姿态／布局", "姿态、相对位置和布局"],
  background: ["背景／场景", "背景场景"],
  custom: ["自定义用途", ""],
};

export function buildPromptDraft({ task, goal, preserve = "", exactText = "", roles = [], count = 0 }) {
  const clean = value => String(value ?? "").trim();
  goal = clean(goal); preserve = clean(preserve); exactText = String(exactText ?? "");
  if (!goal) throw new Error("先填写你想生成或修改什么。");
  if (!["t2i", "edit", "multi"].includes(task)) throw new Error("未知任务。");
  const tags = [...goal.matchAll(/<image(\d+)>/g)].map(match => Number(match[1]));
  if (task === "t2i" && tags.length) throw new Error("文生图没有参考图，请移除图像编号。");
  if (task !== "t2i" && tags.some(index => index < 1 || index > count)) throw new Error("要求引用了未提供的图片编号。");
  const lines = [];
  if (task === "multi") {
    if (!Number.isInteger(count) || count < 2 || count > 4) throw new Error("多图助手支持2–4张图。");
    lines.push("以 <image1> 为编辑主画面，沿用其画面比例和原有构图。");
    for (let index = 2; index <= count; index++) {
      const source = roles[index - 2] ?? {};
      const info = IMAGE_ROLES[source.role];
      if (!info) throw new Error(`请选择图${index}的用途。`);
      const detail = clean(source.detail);
      if (source.role === "instruction" && !detail) continue;
      if (source.role === "custom" && !detail) throw new Error(`请写明图${index}提供什么。`);
      lines.push(`从 <image${index}> 取用${detail || info[1]}，只使用上述指定内容。`);
    }
  }
  lines.push(task === "edit" ? goal.replaceAll("<image1>", "当前图片") : goal);
  if (preserve) lines.push(`保持不变：${preserve}。`);
  if (exactText.trim()) lines.push(`画面中的指定文字必须逐字写为${JSON.stringify(exactText)}，不翻译、不增删字符。`);
  if (task !== "t2i") lines.push("只执行明确要求的改动，其余未指定内容保持不变。");
  const result=lines.join("\n");
  const referenceText=lines.filter(line=>!line.startsWith("画面中的指定文字必须逐字写为")).join("\n");
  if ([...referenceText.matchAll(/<image(\d+)>/g)].some(match => Number(match[1]) < 1 || Number(match[1]) > count)) throw new Error("助手字段引用了未提供的图片编号。");
  return result;
}

// The same structured request is sent to PE; role fields do not need a prior adopt.
export const buildEnhancerRequest = options => buildPromptDraft(options);

// PE must return a complete parsed answer. Never feed its reasoning or raw JSON
// into the image model; a failed/truncated rewrite leaves the original intact.
export function parseEnhancedPrompt(text, { task, count = 0 }) {
  const raw = String(text ?? "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  let answer;
  try { answer = JSON.parse(raw); } catch { throw new Error("增强器没有返回完整JSON；保留原提示词，请增加输出长度后再试。"); }
  if (!answer || typeof answer !== "object" || Array.isArray(answer)) throw new Error("增强器结果不是JSON对象。");
  const prompt = answer.rewritten_prompt;
  if (typeof prompt !== "string" || !prompt.trim() || /<think>|<\/think>/i.test(prompt)) throw new Error("增强结果缺少可用提示词。");
  const ratio = answer.wh_ratio ?? "";
  const follow = answer.ratio_follow ?? "";
  if (typeof ratio !== "string" || typeof follow !== "string" || (ratio && follow)) throw new Error("增强结果的比例字段冲突。");
  if (ratio && !/^\d{1,3}:\d{1,3}$/.test(ratio)) throw new Error("增强结果比例格式无效。");
  if(ratio && ratio.split(':').some(value=>Number(value)<=0))throw new Error("增强结果比例必须为正数。");
  if (task === "t2i" && (follow || /<image\d+>/.test(prompt))) throw new Error("文生图增强结果错误地引用图片。");
  if (task !== "t2i") {
    if(!Number.isInteger(count)||count<1||count>4)throw new Error('编辑PE需要1–4张实际参考图。');
    if (!ratio && !follow) throw new Error("编辑增强结果没有输出比例依据。");
    if (follow && !new RegExp(`^<image[1-${count}]>$`).test(follow)) throw new Error("增强结果引用了不存在的主图。");
    if ([...prompt.matchAll(/<image(\d+)>/g)].some(match => Number(match[1]) < 1 || Number(match[1]) > count)) throw new Error("增强提示词引用了未上传图片。");
  }
  return { prompt: prompt.trim(), ratio, follow };
}
