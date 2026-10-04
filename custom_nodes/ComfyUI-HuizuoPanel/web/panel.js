import { TASKS, PRESETS, RATIOS, QUALITIES, role, settings, readWidget, writeWidget, setTask, setSize, validate, readPrompt, writePrompt, canvasOptimizationEnabled, setCanvasOptimization } from "./controller.js?v=0.4.4";
import { IMAGE_ROLES, buildPromptDraft, buildEnhancerRequest, parseEnhancedPrompt } from "./prompt-assistant.js?v=0.4.4";
import { PROMPT_TIPS, examplesForTask, applyPromptExample, undoPromptExample } from "./prompt-examples.js?v=0.4.4";
import { loraEnabled, setLoraEnabled, loraSelection, validateLoraSelection } from "./lora-controls.js?v=0.4.4";

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function field(text, input) {
  const label = el("label", "hz-field");
  input.setAttribute("aria-label", text);
  label.append(el("span", "hz-label", text), input);
  return label;
}
function select(options, value, onChange) {
  const s = el("select", "hz-input");
  for (const [id, text] of options) {
    const o = el("option", "", text); o.value = id; s.append(o);
  }
  s.value = String(value);
  s.addEventListener("change", () => onChange(s.value));
  return s;
}

export function createPanel(container, host) {
  let graph, cfg, running = false, uploads = 0, destroyed = false, renderEpoch = 0, enhancing = false;
  let runtimeErrors = [], checkingRuntime = false;
  let statusNode, queueButton, outputNode;
  let viewEncoder, viewTask, viewRefCount;
  let bindings = [];
  const root = el("section", "hz-panel");
  container.classList.add("hz-panel-host");
  root.setAttribute("aria-label", "绘作台操作面板");
  container.append(root);
  const status = (text, error = false) => {
    if (!statusNode) return;
    statusNode.textContent = text;
    statusNode.classList.toggle("hz-error", error);
  };
  const attempt = action => {
    try { return action(); } catch (error) { status(error.message, true); }
  };
  const updateQueue = () => {
    if (queueButton) queueButton.disabled = running || enhancing || uploads > 0 || checkingRuntime || runtimeErrors.length > 0;
  };
  const bind = (control, read) => {
    bindings.push(() => {
      if (document.activeElement === control) return;
      const value = String(read() ?? "");
      if (control.value !== value) control.value = value;
    });
    return control;
  };

  function syncFromGraph() {
    if (destroyed) return;
    const current = host.getGraph();
    const encoder = role(current, "encode");
    if (current !== graph || encoder !== viewEncoder) { render(); return; }
    if (!encoder) return;
    const next = settings(current);
    if (next.task !== viewTask || next.refCount !== viewRefCount) { render(); return; }
    for (const update of bindings) update();
  }

  function render() {
    if (destroyed) return;
    const epoch = ++renderEpoch;
    graph = host.getGraph();
    viewEncoder = role(graph, "encode");
    bindings = [];
    root.replaceChildren();
    const header = el("header", "hz-header");
    const brand = el("div", "hz-brand");
    brand.append(el("span", "hz-mark", "绘"), el("h2", "", "绘作台"));
    header.append(brand, el("span", "hz-version", "IMAGE STUDIO"));
    root.append(header, el("p", "hz-subtitle", "Qwen Image 2.1 · 从一句话到一张图"));
    statusNode = el("p", "hz-status");
    statusNode.setAttribute("role", "status");
    if (!role(graph, "encode")) {
      root.append(el("div", "hz-empty", host.openWorkflow ? "选择一条内置工作流，直接在 ComfyUI 画布中打开。模型配置在下方，日常操作集中在上方。" : "将本包任意工作流 JSON 拖入 ComfyUI 画布，再打开这个面板。"));
      if (host.openWorkflow) {
        const entries = el("div", "hz-workflow-list");
        for (const [task, info] of Object.entries(TASKS)) {
          const button = el("button", "hz-workflow-entry", `载入${info.label}工作流`);
          button.type = "button";
          button.addEventListener("click", async () => {
            button.disabled = true;
            try { await host.openWorkflow(task); render(); }
            catch (error) { status(error.message, true); }
            finally { button.disabled = false; }
          });
          entries.append(button);
        }
        root.append(entries);
        const extras=el("div","hz-chips");
        for(const [task,title] of [["pe-t2i","载入可选PE文生图节点"],["pe-edit","载入可选PE编辑节点"]]){
          const button=el("button","hz-chip",title);button.type="button";
          button.addEventListener("click",async()=>{try{await host.openWorkflow(task);render();}catch(error){status(error.message,true);}});
          extras.append(button);
        }
        root.append(extras,el("p","hz-small","PE独立工作流默认关闭，只预览优化文本；普通三类生成不需要载入PE工作流。"));
      }
      root.append(statusNode);
      return;
    }
    cfg = settings(graph);
    viewTask = cfg.task; viewRefCount = cfg.refCount;
    const tabs = el("div", "hz-tasks"); tabs.setAttribute("role", "group"); tabs.setAttribute("aria-label", "创作任务");
    for (const [id, task] of Object.entries(TASKS)) {
      const b = el("button", `hz-task ${cfg.task === id ? "is-active" : ""}`, task.label);
      b.type = "button"; b.setAttribute("aria-pressed", String(cfg.task === id));
      b.addEventListener("click", () => attempt(() => { setTask(graph, id); render(); }));
      tabs.append(b);
    }
    root.append(tabs, el("p", "hz-hint", TASKS[cfg.task]?.hint));

    if (cfg.task !== "t2i") {
      const uploadsBox = el("div", "hz-section");
      uploadsBox.append(el("h3", "hz-section-title", "01 / 参考素材"));
      if (cfg.task === "multi") uploadsBox.append(field("参考图数量", select([[2,"2张"],[3,"3张"],[4,"4张"]], cfg.refCount,
        value => attempt(() => { setTask(graph, "multi", Number(value)); render(); }))));
      const grid = el("div", "hz-upload-grid");
      const count = cfg.task === "edit" ? 1 : cfg.refCount;
      for (let i = 1; i <= count; i++) {
        const image = role(graph, `image${i}`);
        const card = el("label", "hz-upload");
        card.append(el("span", "hz-upload-title", `图 ${i} · ${i === 1 ? "主图" : "参考"}`));
        const filename = readWidget(image, "image");
        const preview = el("img", "hz-upload-preview");
        preview.alt = `图${i}预览`; preview.hidden = !filename;
        if (filename) preview.src = host.viewUrl({ filename, type: "input" });
        const caption = el("span", "hz-upload-caption", filename ? "点击更换图片" : "+ 上传图片");
        card.append(preview, caption);
        bindings.push(() => {
          const name = readWidget(image, "image");
          const src = name ? host.viewUrl({ filename: name, type: "input" }) : null;
          if (preview.getAttribute("src") !== src) {
            if (src) preview.setAttribute("src", src); else preview.removeAttribute("src");
          }
          preview.hidden = !name;
          caption.textContent = name ? "点击更换图片" : "+ 上传图片";
        });
        const fileInput = el("input", "hz-file"); fileInput.type = "file";
        fileInput.accept = "image/png,image/jpeg,image/webp"; fileInput.setAttribute("aria-label", `上传图 ${i}`);
        fileInput.addEventListener("change", async () => {
          const file = fileInput.files?.[0]; if (!file) return;
          const uploadGraph = graph; const uploadImage = image;
          let uploaded = false;
          uploads++; queueButton.disabled = true; status(`正在上传图 ${i}…`);
          try {
            const info = await host.upload(file);
            const name = info.subfolder ? `${info.subfolder}/${info.name}` : info.name;
            writeWidget(uploadImage, "image", name);
            uploaded = true;
            uploadGraph.change?.();
            if (host.getGraph() === uploadGraph) syncFromGraph();
          } catch (error) { status(`上传失败：${error.message}`, true); }
          finally {
            uploads--; updateQueue();
            if (uploaded && host.getGraph() === uploadGraph) status(uploads ? "正在上传素材…" : "素材上传完成");
          }
        });
        card.append(fileInput); grid.append(card);
      }
      uploadsBox.append(grid, el("p", "hz-small", "图1决定输出比例；在要求中使用 <image1>、<image2> 指定每张图的用途。"));
      root.append(uploadsBox);
    }

    const promptBox = el("div", "hz-section");
    promptBox.append(el("h3", "hz-section-title", cfg.task === "t2i" ? "01 / 画面描述" : "02 / 编辑要求"));
    const chips = el("div", "hz-chips");
    const prompt = el("textarea", "hz-prompt"); prompt.rows = 6;
    prompt.setAttribute("aria-label", "画面或编辑要求"); prompt.value = readPrompt(graph) ?? "";
    bind(prompt, () => readPrompt(graph));
    prompt.addEventListener("input", () => attempt(() => { writePrompt(graph, prompt.value); graph.change?.(); }));
    for (const [label, text] of PRESETS[cfg.task]) {
      const b = el("button", "hz-chip", label); b.type = "button";
      b.addEventListener("click", () => attempt(() => {
        if (prompt.value.trim() && !PRESETS[cfg.task].some(([,p]) => p === prompt.value) && !host.confirm("套用预设会替换当前要求，继续吗？")) return;
        prompt.value = text; writePrompt(graph, text); graph.change?.();
      })); chips.append(b);
    }
    promptBox.append(chips, prompt,el("p","hz-small",PROMPT_TIPS[cfg.task]));
    if(role(graph,"pe")){
      const canvasAI=el("input");canvasAI.type="checkbox";canvasAI.checked=canvasOptimizationEnabled(graph);
      canvasAI.addEventListener("change",()=>attempt(()=>setCanvasOptimization(graph,canvasAI.checked)));
      bindings.push(()=>{if(document.activeElement!==canvasAI)canvasAI.checked=canvasOptimizationEnabled(graph);});
      const toggle=field("出图前使用画布AI优化（可选，默认关闭）",canvasAI);toggle.classList.add("hz-toggle");
      promptBox.append(toggle,
        el("p","hz-small","开关与画布最左侧AI节点同步。关闭直接用原文；开启后先本地优化再出图，需要对应PE权重。优化只改文字，不自动改画幅。"));
    }
    const exampleCount=cfg.task==="t2i"?0:cfg.task==="edit"?1:cfg.refCount;
    const examples=examplesForTask(cfg.task,exampleCount);
    cfg.promptExamples ??= {};
    const exampleState=cfg.promptExamples[cfg.task] ??= {};
    const exampleBox=el("details","hz-advanced hz-examples");
    exampleBox.append(el("summary","",`提示词示例 · ${examples.length}个${exampleCount>1?` · ${exampleCount}图`:''}`));
    const examplePreview=el("textarea","hz-prompt");examplePreview.rows=5;examplePreview.readOnly=true;
    examplePreview.setAttribute("aria-label","示例提示词预览");
    const exampleMaterials=el("p","hz-small"),exampleTip=el("p","hz-small");
    let selected=examples.find(item=>item.id===exampleState.selected)??examples[0];
    const showExample=()=>{exampleState.selected=selected.id;examplePreview.value=selected.prompt;
      exampleMaterials.textContent=selected.materials;
      exampleTip.textContent=(selected.tested?"基础出图已验收 · ":"可改写模板，未逐条出图验证 · ")+selected.tip;};
    showExample();
    exampleBox.append(field("选择提示词示例",select(examples.map(item=>[item.id,item.title]),selected.id,id=>{clearExampleConfirmation();selected=examples.find(item=>item.id===id);showExample();})),exampleMaterials,examplePreview,exampleTip);
    const exampleActions=el("div","hz-chips");
    const useExample=el("button","hz-chip","采用示例"),undoExample=el("button","hz-chip","撤销示例");
    useExample.type=undoExample.type="button";
    const exampleConfirmation=el("div");exampleConfirmation.hidden=true;
    const confirmationText=el("p","hz-small");confirmationText.setAttribute("role","status");
    const confirmReplacement=el("button","hz-chip","确认替换提示词"),cancelReplacement=el("button","hz-chip","取消替换");
    confirmReplacement.type=cancelReplacement.type="button";
    let pendingExampleAction, exampleUndo;
    const clearExampleConfirmation=()=>{pendingExampleAction=null;exampleConfirmation.hidden=true;};
    const confirmInPanel=action=>action(message=>{
      confirmationText.textContent=message;exampleConfirmation.hidden=false;pendingExampleAction=()=>action(()=>true);return false;
    });
    confirmReplacement.addEventListener("click",()=>attempt(()=>{const action=pendingExampleAction;clearExampleConfirmation();action?.();}));
    cancelReplacement.addEventListener("click",clearExampleConfirmation);
    exampleConfirmation.append(confirmationText,confirmReplacement,cancelReplacement);
    const adoptExample=(id,confirm)=>{
      const snapshot=applyPromptExample(graph,id,confirm);
      if(!snapshot)return;exampleUndo=snapshot;syncFromGraph();
      status("已采用示例；请核对素材与助手中的保留要求。没有提交生成或PE任务。");
    };
    useExample.addEventListener("click",()=>attempt(()=>{const id=selected.id;clearExampleConfirmation();confirmInPanel(confirm=>adoptExample(id,confirm));}));
    undoExample.addEventListener("click",()=>attempt(()=>{const snapshot=exampleUndo;clearExampleConfirmation();confirmInPanel(confirm=>{
      if(undoPromptExample(graph,snapshot,confirm)){exampleUndo=null;syncFromGraph();status("已恢复采用示例前的提示词。");}
    });}));
    exampleActions.append(useExample,undoExample);exampleBox.append(exampleActions,exampleConfirmation,
      el("p","hz-small","预览不改原提示词；采用只替换主提示词。多图示例按当前参考图数量显示，切换为3／4图可查看更多分工示例。"));
    promptBox.append(exampleBox);root.append(promptBox);

    cfg.promptAssistant ??= {};
    const draftState = cfg.promptAssistant[cfg.task] ??= { preserve:"", exactText:"", roles:[] };
    const helper = el("details", "hz-advanced hz-assistant");
    helper.append(el("summary", "", "提示词助手 · 图像分工与保留要求"),
      el("p", "hz-small", "结构助手不读取图片、不增加模型。以当前要求为基础生成草稿，确认后再采用。图1始终作为编辑主图。"));
    const keep = el("textarea", "hz-input"); keep.rows = 2; keep.value = draftState.preserve;
    keep.addEventListener("input", () => { draftState.preserve=keep.value; });
    const literal = el("input", "hz-input"); literal.value = draftState.exactText;
    literal.addEventListener("input", () => { draftState.exactText=literal.value; });
    helper.append(field("保持不变的内容", keep),field("画面中必须准确出现的文字（可留空）",literal));
    const refCount = cfg.task === "t2i" ? 0 : cfg.task === "edit" ? 1 : cfg.refCount;
    for (let index=2;index<=refCount;index++) {
      const item = draftState.roles[index-2] ??= { role:"instruction", detail:"" };
      helper.append(field(`图${index}提供什么`,select(Object.entries(IMAGE_ROLES).map(([key,[title]])=>[key,title]),item.role,value=>{item.role=value;})));
      const detail=el("input","hz-input");detail.value=item.detail;
      detail.addEventListener("input",()=>{item.detail=detail.value;});
      helper.append(field(`图${index}的具体用途（可留空）`,detail));
    }
    const preview=el("textarea","hz-prompt");preview.rows=6;preview.readOnly=true;
    preview.setAttribute("aria-label","提示词草稿预览");preview.value=draftState.preview ?? "";
    const notice=el("p","hz-small");
    const build=el("button","hz-chip","生成结构草稿");build.type="button";
    build.addEventListener("click",()=>attempt(()=>{
      preview.value=buildPromptDraft({task:cfg.task,count:refCount,goal:prompt.value,preserve:keep.value,exactText:literal.value,roles:draftState.roles});
      draftState.preview=preview.value;draftState.peCanvasAnswer=null;notice.textContent="结构草稿已生成，尚未替换当前要求。";
    }));
    const apply=el("button","hz-chip","采用草稿");apply.type="button";
    const undo=el("button","hz-chip","撤销采用");undo.type="button";
    let previous;
    apply.addEventListener("click",()=>attempt(()=>{
      if (!preview.value.trim()) throw new Error("先生成或优化草稿。");
      const canvas=draftState.peCanvasAnswer;
      if(canvas && ((canvas.follow&&canvas.follow!=="<image1>") || (canvas.ratio&&cfg.task!=="t2i"))) {
        if(!host.confirm(`PE建议画布${canvas.follow||canvas.ratio}，当前编辑流程仍沿用图1。是否只采用文字并保留图1画幅？取消后可调整图1再优化。`))return;
      }
      previous=prompt.value;prompt.value=preview.value;
      writePrompt(graph,preview.value);graph.change?.();
      if(canvas && role(graph,"pe"))setCanvasOptimization(graph,false);
      if(canvas?.ratio && cfg.task==='t2i'){
        if(RATIOS.includes(canvas.ratio))setSize(graph,canvas.ratio,cfg.pixelBudget);
        else if(!host.confirm(`PE建议比例${canvas.ratio}，当前快捷画幅不支持。是否保持当前画幅并只采用文字？`)){
          prompt.value=previous;writePrompt(graph,previous);graph.change?.();return;
        }
      }
      notice.textContent="已采用，可继续修改或撤销。";
    }));
    undo.addEventListener("click",()=>attempt(()=>{
      if (previous===undefined) throw new Error("没有可撤销的采用操作。");
      prompt.value=previous;writePrompt(graph,previous);graph.change?.();previous=undefined;
      notice.textContent="已恢复采用前的提示词。";
    }));
    const helperActions=el("div","hz-chips");helperActions.append(build,apply,undo);
    const pe=el("button","hz-chip","官方PE看图优化");pe.type="button";
    if(cfg.task==="t2i")pe.textContent="官方PE文生图优化";
    const enabled=el("input");enabled.type="checkbox";enabled.checked=Boolean(draftState.peEnabled);
    pe.disabled=!enabled.checked;
    enabled.addEventListener("change",()=>{
      draftState.peEnabled=enabled.checked;pe.disabled=!enabled.checked||enhancing;
      if(!enabled.checked&&enhancing)notice.textContent="已关闭后续优化；当前已入队任务继续，请在ComfyUI队列中查看。";
    });
    helper.append(field("启用官方PE优化（可选，默认关闭）",enabled));
    const peLength=el("input","hz-input");peLength.type="number";peLength.min="512";peLength.max="32768";peLength.step="512";
    peLength.value=String(draftState.maxLength ?? 4096);
    peLength.addEventListener("change",()=>{draftState.maxLength=Number(peLength.value);});
    helper.append(field("PE输出长度上限（含思考）",peLength));
    pe.addEventListener("click",async()=>{
      if(!enabled.checked)return;
      if(enhancing||running||uploads) {status("请等待当前任务或上传结束。",true);return;}
      const requestGraph=graph,requestTask=cfg.task,requestCount=refCount;
      let currentPrompt;
      try{currentPrompt=buildEnhancerRequest({task:requestTask,count:requestCount,goal:prompt.value,preserve:keep.value,exactText:literal.value,roles:draftState.roles});}
      catch(error){status(error.message,true);return;}
      const maxLength=Number(peLength.value);
      if(!Number.isInteger(maxLength)||maxLength<512||maxLength>32768){status("PE输出长度应在512–32768之间。",true);return;}
      if(!currentPrompt.trim()){status("先填写画面或编辑要求。",true);return;}
      if(!host.enhancePrompt){status("当前前端没有提示词优化接口，请更新完整包。",true);return;}
      const images=[];
      for(let index=1;index<=refCount;index++){
        const name=readWidget(role(graph,`image${index}`),"image");
        if(!name){status(`先上传图${index}，PE需要实际看图。`,true);return;}images.push(name);
      }
      enhancing=true;pe.disabled=true;updateQueue();status("正在用官方PE优化，不运行图片生成…");
      try{
        const raw=await host.enhancePrompt({task:requestTask,prompt:currentPrompt,images,maxLength});
        if(destroyed||host.getGraph()!==requestGraph||settings(requestGraph).task!==requestTask||!preview.isConnected) return;
        const answer=parseEnhancedPrompt(raw,{task:requestTask,count:requestCount});
        preview.value=answer.prompt;draftState.preview=answer.prompt;draftState.peCanvasAnswer={ratio:answer.ratio,follow:answer.follow};
        const ratioNote=answer.follow&&answer.follow!=="<image1>"?`PE建议以${answer.follow}为画布；当前工作流仍以图1为主图，请调整素材顺序后重新优化。`:
          answer.ratio?`PE建议比例${answer.ratio}；当前画幅没有自动改变，请核对生成设置。`:"沿用图1比例。";
        notice.textContent=ratioNote+" 优化结果仅进入预览，确认后采用。";
        status("提示词优化完成，尚未生成图片。");
      }catch(error){status(`优化未完成：${error.message}`,true);}
      finally{enhancing=false;pe.disabled=!enabled.checked;updateQueue();}
    });
    helperActions.append(pe);helper.append(helperActions,preview,notice,
      el("p","hz-small","官方PE需要独立的本地增强模型和GPU，会增加耗时。无卡模式只下载权重；单独预览不会出图，也不发送图片给外部API。画布AI开关开启时，开始生成会先优化要求。"));
    if(host.openWorkflow){
      const peWorkflow=el("button","hz-chip","查看独立PE优化节点工作流");peWorkflow.type="button";
      peWorkflow.addEventListener("click",async()=>{try{await host.openWorkflow(cfg.task==="t2i"?"pe-t2i":"pe-edit");}catch(error){status(error.message,true);}});
      helper.append(peWorkflow,el("p","hz-small","会切换画布，请先保存。节点在「绘作台／可选提示词优化」分类，默认enabled=false。"));
    }
    root.append(helper);

    const loraBox=el("details","hz-advanced");
    loraBox.append(el("summary","","LoRA管理 · 可选"));
    const loraNode=role(graph,"lora");
    if(loraNode){
      const on=el("input");on.type="checkbox";on.checked=loraEnabled(graph);
      on.addEventListener("change",()=>attempt(()=>{setLoraEnabled(graph,on.checked);status(on.checked?"已启用LoRA管理器；在画布节点里选择文件与强度。":"已关闭LoRA，使用原始绘图模型；列表和强度保留。");}));
      loraBox.append(field("启用LoRA（默认关闭）",on));
      const selected=el("p","hz-small");
      const syncLoras=()=>{
        on.checked=loraEnabled(graph);
        try{const counts=loraSelection(graph);selected.textContent=`列表${counts.selected}个／条目开关开启${counts.active}个。${on.checked?'总开关已开启；空列表仍使用原模型。':'总开关关闭，不加载列表中的权重。'}`;}
        catch(error){selected.textContent=error.message;}
      };
      syncLoras();bindings.push(syncLoras);loraBox.append(selected,
        el("p","hz-small","在画布的「LoRA管理器」节点搜索、添加LoRA，逐条开关并调整模型强度。这里只修改绘图模型，文本编码器和PE保持原样。触发词在右侧节点预览，核对后再手动加入主提示词。"));
      if(host.loraManagerUrl){const library=el("a","hz-button","打开LoRA模型库");library.href=host.loraManagerUrl;library.target="_blank";library.rel="noopener noreferrer";loraBox.append(library);}
    }else if(host.openWorkflow){
      const loadLoras=el("button","hz-chip","载入LoRA管理版工作流");loadLoras.type="button";
      const confirmation=el("div");confirmation.hidden=true;
      const proceed=el("button","hz-chip","确认载入LoRA管理版"),cancel=el("button","hz-chip","取消载入");proceed.type=cancel.type="button";
      confirmation.append(el("p","hz-small","将切换当前画布，请先保存修改。LoRA列表为空、总开关默认关闭。"),proceed,cancel);
      loadLoras.addEventListener("click",()=>{confirmation.hidden=false;});cancel.addEventListener("click",()=>{confirmation.hidden=true;});
      proceed.addEventListener("click",async()=>{proceed.disabled=true;try{await host.openWorkflow("lora",{confirmed:true});}catch(error){status(error.message,true);}finally{proceed.disabled=false;}});
      loraBox.append(loadLoras,confirmation,el("p","hz-small","该可选工作流需要预装与Aaalice相同的ComfyUI-LoRA-Manager插件。普通三类流程无需此插件。"));
    }
    loraBox.append(el("p","hz-small","只选择训练基座明确匹配Qwen Image 2.1的LoRA。原参考中的Anima LoRA不能直接沿用；没有兼容权重时关闭总开关即可正常生成。"));
    root.append(loraBox);

    const options = el("div", "hz-section");
    options.append(el("h3", "hz-section-title", cfg.task === "t2i" ? "02 / 生成设置" : "03 / 生成设置"));
    const row = el("div", "hz-row");
    if (cfg.task === "t2i") {
      const ratio = bind(select(RATIOS.map(x => [x,x]), cfg.ratio, value => attempt(() => { setSize(graph, value, cfg.pixelBudget); render(); })), () => cfg.ratio);
      const pixels = bind(select([[1,"标准 · 约1MP"],[2,"细节 · 约2MP"],[4,"大图 · 约4MP"]], cfg.pixelBudget, value => attempt(() => { setSize(graph, cfg.ratio, Number(value)); render(); })), () => cfg.pixelBudget);
      row.append(field("画面比例", ratio), field("画面精度", pixels));
      options.append(row, el("p", "hz-small", `${readWidget(role(graph,"latent"),"width")} × ${readWidget(role(graph,"latent"),"height")} px`));
    } else {
      options.append(field("编辑像素预算", bind(select([[768,"轻量 · 768²"],[992,"标准 · 约1MP"],[1536,"精细 · 1536²"],[2048,"大图 · 2048²"]], readWidget(role(graph,"encode"),"resolution"),
        value => attempt(() => { writeWidget(role(graph,"encode"),"resolution",Number(value)); graph.change?.(); })), () => readWidget(role(graph,"encode"),"resolution"))),
        el("p", "hz-small", "按主图比例处理，所有参考图使用相同像素预算。大图与更多参考图会增加耗时和显存。"));
    }
    const currentSteps = Number(readWidget(role(graph,"sampler"),"steps"));
    cfg.quality = Object.keys(QUALITIES).find(key => QUALITIES[key] === currentSteps) ?? "custom";
    const qualityOptions = [["quick","快速 · 20步"],["standard","标准 · 25步"],["fine","精细 · 40步"]];
    if (cfg.quality === "custom") qualityOptions.push(["custom",`自定义 · ${currentSteps}步`]);
    const qualitySelect = select(qualityOptions, cfg.quality, value => attempt(() => {
      if (value === "custom") return;
      cfg.quality = value; writeWidget(role(graph,"sampler"),"steps",QUALITIES[value]); graph.change?.(); render();
    }));
    bind(qualitySelect, () => {
      const count = Number(readWidget(role(graph,"sampler"),"steps"));
      const quality = Object.keys(QUALITIES).find(key => QUALITIES[key] === count) ?? "custom";
      if (quality === "custom") {
        let custom = [...qualitySelect.options].find(option => option.value === "custom");
        if (!custom) { custom = el("option"); custom.value = "custom"; qualitySelect.append(custom); }
        custom.textContent = `自定义 · ${count}步`;
      }
      return quality;
    });
    options.append(field("生成档位", qualitySelect));
    const advanced = el("details", "hz-advanced");
    advanced.append(el("summary", "", "高级设置"));
    const seed = el("input", "hz-input"); seed.type = "number"; seed.min = "0"; seed.max = String(Number.MAX_SAFE_INTEGER); seed.step = "1";
    seed.value = readWidget(role(graph,"sampler"),"seed");
    bind(seed, () => readWidget(role(graph,"sampler"),"seed"));
    seed.addEventListener("change", () => attempt(() => { writeWidget(role(graph,"sampler"),"seed",Number(seed.value)); graph.change?.(); }));
    const seedMode = select([["randomize","每次随机"],["fixed","固定种子"]], readWidget(role(graph,"sampler"),"control_after_generate"),
      value => attempt(() => { writeWidget(role(graph,"sampler"),"control_after_generate",value); graph.change?.(); }));
    bind(seedMode, () => readWidget(role(graph,"sampler"),"control_after_generate"));
    const steps = el("input", "hz-input"); steps.type = "number"; steps.min = "1"; steps.max = "100"; steps.step = "1";
    steps.value = readWidget(role(graph,"sampler"),"steps");
    bind(steps, () => readWidget(role(graph,"sampler"),"steps"));
    steps.addEventListener("change", () => attempt(() => {
      const value = Number(steps.value); writeWidget(role(graph,"sampler"),"steps",value);
      cfg.quality = Object.keys(QUALITIES).find(key => QUALITIES[key] === value) ?? "custom";
      if (cfg.quality === "custom") {
        let custom = [...qualitySelect.options].find(o => o.value === "custom");
        if (!custom) { custom = el("option"); custom.value = "custom"; qualitySelect.append(custom); }
        custom.textContent = `自定义 · ${value}步`;
      }
      qualitySelect.value = cfg.quality; graph.change?.();
    }));
    advanced.append(field("种子策略",seedMode),field("随机种子",seed),field("采样步数",steps),
      field("参考图缓存", bind(select([["auto","自动"],["cpu","系统内存"],["gpu","显存"],["off","关闭"]], readWidget(role(graph,"cache"),"device"),
        value => attempt(() => { writeWidget(role(graph,"cache"),"device",value); graph.change?.(); })), () => readWidget(role(graph,"cache"),"device"))),
      el("p", "hz-small", "推荐 CFG 1、euler / simple。固定种子适合比较提示词的改动。"));
    options.append(advanced); root.append(options);

    queueButton = el("button", "hz-generate", "开始生成"); queueButton.type = "button";
    runtimeErrors = []; checkingRuntime = Boolean(host.checkRuntime);
    updateQueue();
    queueButton.addEventListener("click", async () => {
        const errors = [...validate(graph),...validateLoraSelection(graph)];
      if (errors.length) { status(errors.join(" "), true); return; }
      running = true; queueButton.disabled = true; status("正在提交任务…");
      try {
        runtimeErrors = host.checkRuntime ? await host.checkRuntime() : [];
        if (runtimeErrors.length) throw new Error(runtimeErrors.join(" "));
        const accepted = await host.queue();
        if (accepted === false) throw new Error("任务未成功入队，请检查 ComfyUI 的错误提示或队列状态。");
        status("已提交队列，生成完成后会显示结果。");
      } catch (error) { status(`提交失败：${error.message}`, true); }
      finally { running = false; updateQueue(); }
    });
    const scroll = el("div", "hz-scroll");
    // Keep the brand and primary action visible while long forms scroll.
    while (root.children.length > 1) scroll.append(root.children[1]);
    const runtimeNote = el("p", "hz-runtime hz-error"); runtimeNote.hidden = true;
    scroll.prepend(runtimeNote);
    outputNode = el("div", "hz-output"); scroll.append(outputNode);
    const actions = el("div", "hz-actions");
    actions.append(queueButton,statusNode,el("footer", "hz-footer", role(graph,"save")?.type==="HuizuoEphemeralPreview" ? "内存图片 · 关机清除 · 需要时下载本机" : role(graph,"save")?.type==="PreviewImage" ? "旧版磁盘临时预览 · 更新工作流才支持关机清图" : "当前工作流会保存到服务器输出目录"));
    root.append(scroll,actions);
    status(uploads ? "正在上传素材…" : checkingRuntime ? "正在检查运行环境…" : "准备就绪");
    if (host.checkRuntime) {
      Promise.resolve().then(() => host.checkRuntime()).catch(error => [error.message]).then(errors => {
        if (destroyed || epoch !== renderEpoch) return;
        runtimeErrors = errors; checkingRuntime = false; updateQueue();
        runtimeNote.textContent = errors.join(" "); runtimeNote.hidden = !errors.length;
        status(uploads ? "正在上传素材…" : errors.length ? "运行环境尚未就绪" : "准备就绪", errors.length > 0);
      });
    }
  }
  render();
  return {
    refresh: render,
    syncFromGraph,
    showResult(info) {
      if (destroyed || !outputNode) return;
      const a = el("a", "hz-result"); a.href = host.viewUrl(info); a.target = "_blank"; a.rel = "noopener";
      const img = el("img", ""); img.src = a.href; img.alt = "本次生成结果，点击打开原图";
      const download = el("a", "hz-button", "下载 PNG 到本机");
      download.href = a.href; download.download = info.filename;
      a.append(img); outputNode.replaceChildren(el("h3","hz-section-title","最新作品"), a, download);
      status(info.filename?.startsWith("hz_mem_temp_") ? "生成完成，图片在服务内存中；关机前请下载。" : info.type==="temp" ? "生成完成，图片在服务器临时目录。" : "生成完成，已保存到输出目录。");
    },
    showError(message) { status(message, true); },
    destroy() { destroyed = true; root.remove(); container.classList.remove("hz-panel-host"); },
  };
}
