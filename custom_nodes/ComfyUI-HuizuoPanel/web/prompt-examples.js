import { role, settings, readPrompt, writePrompt } from "./controller.js?v=0.4.4";

// Chinese user examples. Prior English benchmark prompts stay in test evidence.
export const PROMPT_TIPS = {
  t2i: "写清主体、动作或位置、场景、构图、光线、风格；画面文字加引号逐字说明。比例用生成设置选择。",
  edit: "先说修改区域和目标，再说保留内容。不要把整张图重新描述一遍；保留要求应与修改目标一致。",
  multi: "图1作为主图；逐一说明图2–4只提供什么。写清放在哪里、比例与光影，以及哪些参考内容不要带入。",
};
export const PROMPT_EXAMPLES = [
  { id:"t2i-cup", task:"t2i", refs:0, title:"杯子产品摄影",
    materials:"无需参考图；先用默认1:1画幅。",
    prompt:'一只白色陶瓷咖啡杯的产品摄影，杯子有红色把手，杯身正面用深灰色清晰写出“COFFEE”。背景为纯净的暖米色，光线柔和，投影自然。杯子居中，以略带侧面的正面视角拍摄，画面中不出现其他物体。',
    tip:"明确主体、把手颜色、准确文字和背景；画面文字可按需求替换。" },
  { id:"t2i-poster", task:"t2i", refs:0, title:"中文活动海报", materials:"无需参考图；可在生成设置选3:4。",
    prompt:'竖版城市读书活动海报，奶油白纸张质感，中央是一叠书和一盏小台灯，柔和暖光，墨绿与橙色点缀，平面插画风格。顶部大标题准确写“周末读书会”，下方小字准确写“把时间留给一本书”。文字排列整齐、对比清晰，四周留白，不添加其他文字或标志。',
    tip:"明确每段文字、位置和层级；文字较多时分几次尝试，不保证一次完全准确。" },
  { id:"t2i-portrait", task:"t2i", refs:0, title:"自然人像", materials:"无需参考图；此例是成年人物。",
    prompt:"一位成年女性坐在咖啡馆窗边，穿浅蓝色衬衫，双手自然放在桌面上，轻微微笑，视线朝镜头。半身构图，窗外阴天的柔和光线照亮面部，背景轻度虚化，真实皮肤纹理，自然人像摄影，画面不出现文字。",
    tip:"主体、动作和取景范围比堆叠画质词更方便调整。" },
  { id:"t2i-room", task:"t2i", refs:0, title:"等距场景插画", materials:"无需参考图；先用1:1画幅。",
    prompt:"一个小型家庭阅读角的等距插画：木质书架靠后墙，绿色单人沙发位于右侧，圆形地毯上有小茶几，左侧窗台摆一盆绿植。下午柔和阳光从左侧照入，米色与浅木色为主，轮廓简洁，物体之间层次清晰，背景留白，无人物、无文字。",
    tip:"用左右位置和前后关系约束构图。" },
  { id:"edit-cup", task:"edit", refs:1, title:"仅改变背景", materials:"图1：白杯、红把手、COFFEE文字的产品照片。",
    prompt:'仅将当前图片中的米色背景改为柔和的薄荷绿色。保留白色陶瓷杯、红色把手和杯身“COFFEE”文字，尽量保持原有拍摄角度、杯子大小和柔和光线，不添加其他物体。',
    tip:"改动和保留要求分开说明；实际仍可能有构图、光照微小变化。" },
  { id:"edit-clothing", task:"edit", refs:1, title:"替换一件服装", materials:"图1：成年人物的上半身照片。",
    prompt:"仅将当前图片中成年人物的外套改成深蓝色牛仔夹克，保留原有内搭。尽量保持面部特征、发型、姿态、背景及原画幅，衣物褶皱和光照与原图一致，不添加帽子、首饰或其他人物。",
    tip:"明确要换哪件衣物，避免同时要求保留其原颜色和材质。" },
  { id:"edit-sign", task:"edit", refs:1, title:"替换招牌文字", materials:"图1：有清晰招牌的店面照片。",
    prompt:'仅将当前图片店铺招牌中央的店名替换为“青禾书屋”，准确保留这四个汉字，不添加英文。沿用原招牌的字色、排列方向、材质和透视；保留招牌外框、建筑、门窗及其余画面内容。',
    tip:"说清替换区域及原文字要被移除；短文字更容易核对。" },
  { id:"edit-remove", task:"edit", refs:1, title:"移除干扰物", materials:"图1：桌面上有杯子和一根电线的照片。",
    prompt:"移除当前图片桌面左下角的黑色电线，用周围桌面纹理自然补全该区域。保留杯子、桌面边缘、背景和整体光照，补全处不要出现新的物体或明显接缝，沿用原图画幅。",
    tip:"用位置和物体特征定位，不要只写‘移除多余东西’。" },
  { id:"multi-checker", task:"multi", refs:2, title:"迁移商品图案", materials:"图1：白杯、红把手和COFFEE产品照片；图2：蓝白格纹样本。",
    prompt:'以 <image1> 的杯子产品照片为主画面，仅将 <image2> 的蓝色与奶油白格纹应用到陶瓷杯身。保留红色把手和清晰可辨的“COFFEE”文字，保持图1的米色背景、拍摄角度和杯子形状，不带入图2背景或其他内容。',
    tip:"图2只提供图案，图1保留主体与场景；指定文字需逐字核对。" },
  { id:"multi-product", task:"multi", refs:2, title:"商品放入场景", materials:"图1：有空位的桌面场景；图2：一瓶香水的清晰产品照片。",
    prompt:"以 <image1> 为主画面，在桌面中央空位放入 <image2> 的香水瓶。图2只提供瓶子的外形、材质和瓶身文字，不带入图2背景。瓶子大小与桌面比例协调，匹配图1的拍摄角度、光照和接触阴影；保留图1其他物体及背景，不复制出第二个瓶子。",
    tip:"明确位置、数量和不要带入的参考背景。" },
  { id:"multi-style", task:"multi", refs:2, title:"只参考配色风格", materials:"图1：需要编辑的街景；图2：喜欢的水彩风格参考。",
    prompt:"以 <image1> 街景为主画面，仅参考 <image2> 的柔和水彩笔触、低饱和配色和纸张质感。保留图1建筑、街道与物体的位置关系，不把图2中的人物、建筑或文字加入画面。图1原有招牌文字保持可辨，沿用图1画幅。",
    tip:"风格参考与内容参考要分开说明。" },
  { id:"multi-people", task:"multi", refs:2, title:"两人自然合照", materials:"图1、图2：各一位成年人物；图1场景作为背景。",
    prompt:"以 <image1> 的场景为合照背景，将 <image2> 中的成年人物安排在图1人物右侧，两人并肩站立，朝镜头自然微笑。分别参考各自原图的面部特征、发型与服装，统一人物大小、透视和环境光，画面只出现这两个人，不带入图2背景。",
    tip:"身份保持是目标，结果仍需人工核对；不要把两人的身份描述混在一起。" },
  { id:"multi-outfit-pose", task:"multi", refs:3, title:"服装与姿态分工", materials:"图1：成年人物主图；图2：目标外套；图3：成年人物的站姿参考。",
    prompt:"以 <image1> 为主图，保持人物面部特征、发型和背景。将人物外套换成 <image2> 的外套款式、颜色与材质，图2只提供外套；将人物站姿调整为 <image3> 的站姿，图3只提供姿态，不替换面部或服装。匹配图1光照，不加入图2和图3的背景，沿用图1画幅。",
    tip:"姿态是本次要改变的内容，因此保留要求里不要再写‘保持原姿态’。" },
  { id:"multi-pattern-color", task:"multi", refs:3, title:"图案与配色分工", materials:"图1：素色帆布袋；图2：叶片图案样本；图3：绿、米色配色样本。",
    prompt:"以 <image1> 的帆布袋产品照片为主图，仅在袋身正面添加 <image2> 的叶片图案，图案配色参考 <image3> 的深绿和米白。图2只提供叶片形状与排列，图3只提供配色，不带入两张参考的物体和背景。图案随袋身褶皱自然变形，保留提手、袋子轮廓、背景和光照。",
    tip:"同一区域的多图参考要说明谁负责形状、谁负责颜色。" },
  { id:"multi-four", task:"multi", refs:4, title:"四图产品布景", materials:"图1：空桌面主场景；图2：香水产品；图3：一束花；图4：柔和配色参考。",
    prompt:"以 <image1> 为主场景，在桌面中央放入 <image2> 的一瓶香水，在香水左后方摆放 <image3> 的一束花，花不要挡住瓶身文字。图2只提供商品外形、材质与文字，图3只提供花束，<image4> 仅提供柔和暖色配色，不引入图4的物体或构图。保持图1桌面、镜头视角与画幅，统一物体比例、光照和接触阴影。",
    tip:"四图先明确四份职责；参考越多不代表效果一定越好。" },
];

export function examplesForTask(task, refs) {
  return PROMPT_EXAMPLES.filter(example => example.task === task && example.refs === refs);
}
export function applyPromptExample(graph, id, confirm = () => false) {
  const example = PROMPT_EXAMPLES.find(item => item.id === id);
  const cfg = settings(graph);
  const refs = cfg.task === "t2i" ? 0 : cfg.task === "edit" ? 1 : cfg.refCount;
  if (!example || example.task !== cfg.task || example.refs !== refs) throw new Error("示例与当前任务／参考图数量不匹配，请先选择对应任务和图数。");
  const encoder = role(graph, "encode");
  const before = readPrompt(graph) ?? "";
  if (before.trim() && before !== example.prompt && !confirm("采用示例会替换当前提示词，素材、助手字段和PE开关保持原设置。继续吗？")) return null;
  writePrompt(graph,example.prompt);
  graph.change?.();
  return { before, applied: example.prompt, task: cfg.task, refs };
}
export function undoPromptExample(graph, snapshot, confirm = () => false) {
  if (!snapshot) throw new Error("没有可撤销的示例采用操作。");
  const cfg = settings(graph);
  const refs = cfg.task === "t2i" ? 0 : cfg.task === "edit" ? 1 : cfg.refCount;
  if (cfg.task !== snapshot.task || refs !== snapshot.refs) throw new Error("请回到采用示例时的任务与图数，再撤销。");
  const encoder = role(graph, "encode");
  if (readPrompt(graph) !== snapshot.applied && !confirm("提示词在采用示例后又修改过，撤销会替换这些修改。继续吗？")) return false;
  writePrompt(graph,snapshot.before);
  graph.change?.();
  return true;
}
