export const PE_MODELS = {
  t2i: "qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors",
  edit: "qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors",
};

export function buildEnhancementGraph({ task, prompt, images, systemPrompt, maxLength = 4096 }) {
  const profile = task === "t2i" ? "t2i" : "edit";
  if (!["t2i", "edit", "multi"].includes(task)) throw new Error("未知优化任务。");
  if (!prompt.trim()) throw new Error("提示词不能为空。");
  if (task === "t2i" && images.length) throw new Error("文生图优化不能忽略已上传参考图。");
  if ((task === "edit" && images.length !== 1) || (task === "multi" && (images.length < 2 || images.length > 4))) throw new Error("参考图数量与优化任务不一致。");
  const graph = {
    "1": { class_type:"CLIPLoader", inputs:{ clip_name:PE_MODELS[profile], type:"qwen_image", device:"default" } },
    "2": { class_type:"HuizuoQwenPromptEnhance", inputs:{ clip:["1",0], enabled:true,task:profile,prompt,max_length:maxLength } },
    "3": { class_type:"PreviewAny", inputs:{ source:["2",0] } },
  };
  for (let index=0;index<images.length;index++) {
    const id=String(10+index);
    graph[id]={class_type:"HuizuoEphemeralLoadImage",inputs:{image:images[index]}};
    graph["2"].inputs[`image_${index+1}`]=[id,0];
  }
  return graph;
}

export async function enhanceLocally(api, request) {
  const profile=request.task === "t2i" ? "t2i" : "edit";
  const responses=await Promise.all([api.fetchApi('/system_stats'),api.fetchApi('/object_info')]);
  if(responses.some(response=>!response.ok))throw new Error("无法读取本地ComfyUI环境。");
  const [stats,registry]=await Promise.all(responses.map(response=>response.json()));
  if(!stats.devices?.some(device=>device.type==='cuda'))throw new Error("无卡模式可下载模型；官方PE看图优化需要GPU，请普通开机后再试。");
  const names=registry.CLIPLoader?.input?.required?.clip_name?.[0] ?? [];
  if(!names.includes(PE_MODELS[profile]))throw new Error(`未安装${profile === 't2i'?'文生图':'编辑'}增强模型；普通跑图不受影响。请在无卡启动配置中将prompt_enhancer设为${profile}或both后准备模型。`);
  for(const node of ['HuizuoQwenPromptEnhance','PreviewAny'])if(!registry[node])throw new Error(`当前环境缺少${node}，请安装完整0.4扩展并重启ComfyUI。`);
  const queueResponse=await api.fetchApi('/queue');
  if(!queueResponse.ok)throw new Error("无法读取当前队列。");
  const queue=await queueResponse.json();
  if(queue.queue_running?.length||queue.queue_pending?.length)throw new Error("当前已有任务，请等待完成后优化，避免模型同时占用显存。");
  const graph=buildEnhancementGraph(request);
  const response=await api.fetchApi('/prompt',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({prompt:graph,client_id:api.clientId ?? 'huizuo-prompt-enhancer'})});
  if(!response.ok)throw new Error(`优化任务未入队：HTTP ${response.status}`);
  const queued=await response.json();
  if(!queued.prompt_id||Object.keys(queued.node_errors ?? {}).length)throw new Error("优化节点校验失败；原提示词保留。");
  const deadline=Date.now()+10*60*1000;
  while(Date.now()<deadline){
    await new Promise(resolve=>setTimeout(resolve,1000));
    const res=await api.fetchApi(`/history/${encodeURIComponent(queued.prompt_id)}`);
    if(!res.ok)throw new Error("连接中断；任务可能仍在运行，请检查队列后再操作。");
    const item=(await res.json())[queued.prompt_id];
    if(!item)continue;
    if(item.status?.status_str==='error')throw new Error("官方PE执行失败，请查看ComfyUI任务错误，原提示词保留。");
    if(item.status?.completed){
      const value=item.outputs?.["3"]?.text;
      const text=Array.isArray(value)?value.join('\n'):value;
      if(typeof text !== 'string'||!text.trim())throw new Error("优化任务没有返回可用文本。");
      return text;
    }
  }
  throw new Error("优化等待超时，未取消后台任务；请先检查队列，避免重复提交。");
}
