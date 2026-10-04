import test from 'node:test';
import assert from 'node:assert/strict';
import {makeGraph} from './graph_fixture.mjs';
import {role,readPrompt,writePrompt,readWidget,setTask,canvasOptimizationEnabled,setCanvasOptimization} from '../custom_nodes/ComfyUI-HuizuoPanel/web/controller.js';

test('raw requirements and the visible AI switch remain independent across tasks',()=>{
  const graph=makeGraph();assert.equal(canvasOptimizationEnabled(graph),false);
  writePrompt(graph,'保留“COFFEE”，仅修改背景。');
  assert.equal(readWidget(role(graph,'pe'),'prompt'),'保留“COFFEE”，仅修改背景。');
  setCanvasOptimization(graph,true);setTask(graph,'multi',3);
  assert.equal(canvasOptimizationEnabled(graph),true);
  assert.equal(readWidget(role(graph,'pe'),'task'),'图像编辑');
  for(let i=1;i<=3;i++)assert.equal(graph.links[role(graph,'pe').inputs.find(p=>p.name===`image_${i}`).link].origin_id,role(graph,`image${i}`).id);
  setTask(graph,'t2i');setCanvasOptimization(graph,false);
  assert.equal(readPrompt(graph),'保留“COFFEE”，仅修改背景。');
  for(const p of role(graph,'pe').inputs.filter(p=>p.name.startsWith('image_')))assert.equal(p.link,null);
});

test('all user examples use Chinese descriptions and do not borrow English test status',async()=>{
  const {PROMPT_EXAMPLES}=await import('../custom_nodes/ComfyUI-HuizuoPanel/web/prompt-examples.js');
  for(const sample of PROMPT_EXAMPLES){assert.match(sample.prompt,/[\u4e00-\u9fff]/);assert.doesNotMatch(sample.prompt,/Studio product photograph|Change only the beige|Use image 1 as the product/);}
  for(const id of ['t2i-cup','edit-cup','multi-checker'])assert.notEqual(PROMPT_EXAMPLES.find(p=>p.id===id).tested,true);
});
