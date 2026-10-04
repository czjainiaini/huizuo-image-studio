import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { buildEnhancementGraph, enhanceLocally, PE_MODELS } from "../custom_nodes/ComfyUI-HuizuoPanel/web/pe-client.js";

test("PE only graph uses the right checkpoint, official sampling, ordered references and no diffusion", () => {
  const graph=buildEnhancementGraph({task:"multi",prompt:"把商品放入主画面",images:["main.png","product.png","style.png"],systemPrompt:"official fixture"});
  assert.equal(graph["1"].inputs.clip_name,PE_MODELS.edit);
  assert.equal(graph["2"].class_type,'HuizuoQwenPromptEnhance');
  assert.equal(graph["2"].inputs.enabled,true);
  for(let index=1;index<=3;index++)assert.deepEqual(graph["2"].inputs[`image_${index}`],[String(9+index),0]);
  assert.ok(!graph['20'],'different aspect ratios must never be cropped into a tensor batch');
  assert.ok(!Object.values(graph).some(node=>["UNETLoader","KSampler","VAEDecode"].includes(node.class_type)));
  const t2i=buildEnhancementGraph({task:"t2i",prompt:"a mug",images:[],systemPrompt:"official fixture"});
  assert.equal(t2i["1"].inputs.clip_name,PE_MODELS.t2i);
  assert.equal(t2i["2"].inputs.task,'t2i');
  assert.ok(!t2i["2"].inputs.image_1);
});
test("base API templates never require optional PE weights", () => {
  for(const task of ["t2i","edit","multi"]){
    const graph=JSON.parse(fs.readFileSync(new URL(`../api/${task}.json`,import.meta.url),"utf8"));
    assert.ok(!Object.values(graph).some(node=>node.class_type==="TextGenerate"));
    assert.ok(!JSON.stringify(graph).includes("_pe_"));
  }
});
test("CPU or missing PE stops before any queue POST and leaves base generation available", async () => {
  for(const cuda of [false,true]){
    const calls=[];
    const api={async fetchApi(path,options){calls.push({path,options});return {ok:true,async json(){return path==='/system_stats'?{devices:[{type:cuda?'cuda':'cpu'}]}:{CLIPLoader:{input:{required:{clip_name:[[]]}}}};}};}};
    await assert.rejects(enhanceLocally(api,{task:"multi",prompt:"edit",images:["a.png","b.png"]},()=>"system"),cuda?/未安装/:/需要GPU/);
    assert.ok(!calls.some(call=>call.options?.method==='POST'));
  }
});
