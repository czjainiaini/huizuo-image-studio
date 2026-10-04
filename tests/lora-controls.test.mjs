import test from "node:test";
import assert from "node:assert/strict";
import { LORA_LOADER, setLoraEnabled, loraEnabled, loraSelection, validateLoraSelection } from "../custom_nodes/ComfyUI-HuizuoPanel/web/lora-controls.js";
import { makeGraph } from "./graph_fixture.mjs";
import { role, readWidget, setTask } from "../custom_nodes/ComfyUI-HuizuoPanel/web/controller.js";

function fixture(){
  const graph=makeGraph();graph.extra.huizuoLoraManager={enabled:false};
  graph._nodes.push({id:30,type:LORA_LOADER,mode:4,properties:{huizuoRole:"lora"},widgets:[{name:"text",value:""},{name:"loras",value:[]}]});
  for(const [id,key] of [[31,"loraTriggers"],[32,"loraPreview"],[33,"loraLoaded"]])graph._nodes.push({id,mode:2,properties:{huizuoRole:key}});
  return graph;
}
test("LoRA manager defaults off and empty; toggle never changes prompt, CLIP or PE",()=>{
  const graph=fixture(),links=JSON.stringify(graph.links),prompt=readWidget(role(graph,"encode"),"prompt");
  assert.equal(loraEnabled(graph),false);assert.deepEqual(loraSelection(graph),{selected:0,active:0});
  setLoraEnabled(graph,true);assert.equal(loraEnabled(graph),true);assert.equal(role(graph,"loraPreview").mode,0);
  assert.equal(readWidget(role(graph,"encode"),"prompt"),prompt);assert.equal(JSON.stringify(graph.links),links);
  setLoraEnabled(graph,false);assert.equal(role(graph,"lora").mode,4);assert.equal(role(graph,"loraPreview").mode,2);
  assert.deepEqual(validateLoraSelection(graph),[]);
});
test("disabled LoRA preserves selections; enabled rejects malformed active settings",()=>{
  const graph=fixture(),rows=role(graph,"lora").widgets.find(item=>item.name==="loras");
  rows.value=[{name:"my-qwen21-lora",strength:.6,clipStrength:0,active:true},{name:"inactive",strength:NaN,active:false}];
  setLoraEnabled(graph,true);assert.deepEqual(loraSelection(graph),{selected:2,active:1});assert.deepEqual(validateLoraSelection(graph),[]);
  rows.value[0].strength=Infinity;assert.ok(validateLoraSelection(graph).some(error=>error.includes("有限")));
  setLoraEnabled(graph,false);assert.deepEqual(validateLoraSelection(graph),[]);assert.equal(rows.value[0].name,"my-qwen21-lora");
});
test("task switching preserves LoRA toggles and list; ordinary workflow has no manager",()=>{
  const graph=fixture();setLoraEnabled(graph,true);
  const before=JSON.stringify(role(graph,"lora"));
  for(const task of ["edit","multi","t2i"]){setTask(graph,task);assert.equal(JSON.stringify(role(graph,"lora")),before);}
  assert.throws(()=>setLoraEnabled(makeGraph(),true),/管理版/);
});
