import test from "node:test";
import assert from "node:assert/strict";
import { role, readWidget, writeWidget, setTask, setSize, settings, validate, dimensions, readPrompt, writePrompt } from "../custom_nodes/ComfyUI-HuizuoPanel/web/controller.js";
import { makeGraph } from "./graph_fixture.mjs";

function linkedImages(graph) {return role(graph,"encode").inputs.filter(p=>p.name.startsWith("images.") && p.link != null).map(p=>graph.links[p.link].origin_id);}
test("mode transitions isolate references and restore prompt drafts", () => {
  const g=makeGraph(); const original=readPrompt(g);
  setTask(g,"multi",4); assert.equal(linkedImages(g).length,4); assert.equal(readWidget(role(g,"latentSwitch"),"switch"),true);
  writePrompt(g,"我的融合草稿");
  setTask(g,"edit"); assert.deepEqual(linkedImages(g),[role(g,"image1").id]);
  setTask(g,"t2i"); assert.equal(linkedImages(g).length,0); assert.equal(readPrompt(g),original);
  assert.equal(readWidget(role(g,"latentSwitch"),"switch"),false);
  for(let i=1;i<=4;i++)assert.equal(role(g,`image${i}`).mode,2);
  setTask(g,"multi"); assert.equal(readPrompt(g),"我的融合草稿");
});
test("core autogrow can shrink to one spare port and grow back to four", () => {
  const g=makeGraph(undefined,true);
  for(const [task,count] of [["multi",4],["edit",2],["multi",3],["t2i",2],["multi",4],["t2i",4]]) {
    setTask(g,task,count);g.flushFrames();
    const expected=task==="t2i"?0:task==="edit"?1:count;
    assert.equal(linkedImages(g).length,expected);
    for(let i=1;i<=expected;i++)assert.equal(g.links[role(g,"encode").inputs.find(p=>p.name===`images.image_${i}`).link].origin_id,role(g,`image${i}`).id);
  }
});
test("missing uploads block edit/multi but never text-to-image", () => {
  const g=makeGraph();assert.deepEqual(validate(g),[]);
  setTask(g,"multi",3);assert.equal(validate(g).filter(x=>x.includes("上传")).length,3);
  for(let i=1;i<=3;i++)writeWidget(role(g,`image${i}`),"image",`user-${i}.png`);
  assert.deepEqual(validate(g),[]);writePrompt(g,"  ");assert.match(validate(g)[0],/填写/);
});
test("size presets align to 32, keep pixel budgets and reject malformed values", () => {
  const g=makeGraph();const [w,h]=setSize(g,"9:16",2);
  assert.equal(w%32,0);assert.equal(h%32,0);assert.ok(Math.abs((w*h)/(2*1024**2)-1)<.04);
  assert.equal(settings(g).ratio,"9:16");assert.equal(readWidget(role(g,"latent"),"width"),w);
  assert.deepEqual(dimensions("1:1",4),[2048,2048]);assert.throws(()=>dimensions("garbage",4));assert.throws(()=>setTask(g,"multi",10));
});
test("invalid step count and unsafe seeds block queue", () => {
  const g=makeGraph();writeWidget(role(g,"sampler"),"steps",0);writeWidget(role(g,"sampler"),"seed",Number.MAX_SAFE_INTEGER+1);
  assert.equal(validate(g).length,2);
});
test("known noisy edit budget is blocked without restricting text-to-image size", () => {
  const g=makeGraph();
  setTask(g,"edit");writeWidget(role(g,"image1"),"image","fixture.png");
  writeWidget(role(g,"encode"),"resolution",1024);
  assert.ok(validate(g).some(error=>error.includes("1024")));
  writeWidget(role(g,"encode"),"resolution",992);
  assert.deepEqual(validate(g),[]);
  setTask(g,"t2i");writeWidget(role(g,"encode"),"resolution",1024);
  assert.deepEqual(validate(g),[]);
  assert.equal(readWidget(role(g,"latent"),"width"),1024);
});
