import test from "node:test";
import assert from "node:assert/strict";
import { PROMPT_EXAMPLES, examplesForTask, applyPromptExample, undoPromptExample } from "../custom_nodes/ComfyUI-HuizuoPanel/web/prompt-examples.js";
import { role, readWidget, writeWidget, setTask, settings, readPrompt, writePrompt } from "../custom_nodes/ComfyUI-HuizuoPanel/web/controller.js";
import { makeGraph } from "./graph_fixture.mjs";

test("example previews offer only the current task and exact reference count",()=>{
  assert.equal(PROMPT_EXAMPLES.length,15);
  assert.equal(new Set(PROMPT_EXAMPLES.map(item=>item.id)).size,15);
  for(const [task,refs] of [["t2i",0],["edit",1],["multi",2],["multi",3],["multi",4]]){
    const examples=examplesForTask(task,refs);assert.ok(examples.length);
    for(const item of examples){
      assert.ok(item.materials&&item.tip&&item.prompt);
      assert.ok([...item.prompt.matchAll(/<image(\d)>/g)].every(match=>Number(match[1])<=refs));
    }
  }
  assert.deepEqual(examplesForTask("multi",1),[]);
});
test("preview and declined adoption preserve custom prompts and optional PE settings",()=>{
  const graph=makeGraph();const cfg=settings(graph);cfg.promptAssistant={t2i:{peEnabled:false,preserve:"保留我的要求"}};
  writePrompt(graph,"我的原提示词");const before=JSON.stringify(cfg);
  examplesForTask("t2i",0);
  assert.equal(readPrompt(graph),"我的原提示词");
  assert.equal(applyPromptExample(graph,"t2i-cup",()=>false),null);
  assert.equal(readPrompt(graph),"我的原提示词");assert.equal(JSON.stringify(cfg),before);
  assert.throws(()=>applyPromptExample(graph,"multi-four",()=>true),/不匹配/);
});
test("adoption changes only the prompt; undo protects edits made after adoption",()=>{
  const graph=makeGraph();const cfg=settings(graph);cfg.promptAssistant={t2i:{peEnabled:true}};
  const nodesBefore=graph._nodes.map(node=>[node.id,node.mode]);
  const old=readPrompt(graph);
  const snapshot=applyPromptExample(graph,"t2i-poster",()=>true);
  assert.equal(cfg.promptAssistant.t2i.peEnabled,true);assert.deepEqual(graph._nodes.map(node=>[node.id,node.mode]),nodesBefore);
  writePrompt(graph,"采用后继续写的内容");
  assert.equal(undoPromptExample(graph,snapshot,()=>false),false);
  assert.equal(readPrompt(graph),"采用后继续写的内容");
  assert.equal(undoPromptExample(graph,snapshot,()=>true),true);assert.equal(readPrompt(graph),old);
});
test("multi-image adoption never rewires images; mismatched undo is refused",()=>{
  const graph=makeGraph();setTask(graph,"multi",3);const links=JSON.stringify(graph.links);
  const snapshot=applyPromptExample(graph,"multi-outfit-pose",()=>true);
  assert.equal(JSON.stringify(graph.links),links);assert.equal(settings(graph).refCount,3);
  setTask(graph,"edit");const editPrompt=readPrompt(graph);
  assert.throws(()=>undoPromptExample(graph,snapshot,()=>true),/回到/);
  assert.equal(readPrompt(graph),editPrompt);
});
