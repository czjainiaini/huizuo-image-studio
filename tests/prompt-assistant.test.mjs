import test from "node:test";
import assert from "node:assert/strict";
import { buildPromptDraft, buildEnhancerRequest, parseEnhancedPrompt } from "../custom_nodes/ComfyUI-HuizuoPanel/web/prompt-assistant.js";

test("multi-image draft spells out each ordered source without claiming to have seen it", () => {
  const value = buildPromptDraft({ task:"multi", count:4, goal:"把商品自然放在桌上", preserve:"主图背景与视角", exactText:"夏日特惠",
    roles:[{role:"product"},{role:"style",detail:"蓝白配色"},{role:"pose",detail:"商品摆放位置"}] });
  for (let index=1;index<=4;index++) assert.ok(value.includes(`<image${index}>`));
  assert.ok(value.includes('"夏日特惠"')); assert.ok(value.includes("主图背景与视角"));
  assert.ok(value.includes("蓝白配色")); assert.ok(!value.includes("我看到"));
});
test("single edits use natural image reference and preserve explicit literals", () => {
  const value=buildPromptDraft({task:"edit",count:1,goal:"给 <image1> 换背景",exactText:"COFFEE"});
  assert.ok(!value.includes("<image1>")); assert.ok(value.includes('"COFFEE"'));
  assert.throws(()=>buildPromptDraft({task:"t2i",goal:"修改 <image1>"}),/没有参考图/);
  assert.throws(()=>buildPromptDraft({task:"multi",count:2,goal:"使用 <image3>",roles:[{role:"style"}]}),/未提供/);
});
test("PE parser rejects truncated JSON, reasoning and conflicting ratios", () => {
  assert.throws(()=>parseEnhancedPrompt('{"rewritten_prompt":',{task:"t2i"}),/完整JSON/);
  assert.throws(()=>parseEnhancedPrompt('{"rewritten_prompt":"<think>hi</think>"}',{task:"t2i"}),/缺少/);
  assert.throws(()=>parseEnhancedPrompt(JSON.stringify({rewritten_prompt:"修改背景",wh_ratio:"1:1",ratio_follow:"<image1>"}),{task:"edit",count:1}),/冲突/);
  assert.throws(()=>parseEnhancedPrompt(JSON.stringify({rewritten_prompt:"用 <image3>",wh_ratio:"",ratio_follow:"<image1>"}),{task:"multi",count:2}),/未上传/);
});
test("PE parser keeps prompt and ratio metadata separate", () => {
  assert.deepEqual(parseEnhancedPrompt(JSON.stringify({rewritten_prompt:"将 <image2> 的商品放进 <image1>，保持品牌字样。",wh_ratio:"",ratio_follow:"<image1>"}),{task:"multi",count:2}),
    {prompt:"将 <image2> 的商品放进 <image1>，保持品牌字样。",ratio:"",follow:"<image1>"});
  assert.equal(parseEnhancedPrompt('{"rewritten_prompt":"a ceramic mug","wh_ratio":"1:1"}',{task:"t2i"}).ratio,"1:1");
});
test("PE request includes selected image roles without adopting a structure draft",()=>{
  const input={task:"multi",count:3,goal:"让参考内容与主图协调",roles:[{role:"product"},{role:"style",detail:"只参考米色配色"}]};
  const first=buildEnhancerRequest(input);assert.match(first,/<image2>.*商品/);assert.match(first,/<image3>.*米色配色/);
  input.roles[1]={role:"pose",detail:"只参考站姿"};const changed=buildEnhancerRequest(input);
  assert.match(changed,/<image3>.*站姿/);assert.ok(!changed.includes("米色配色"));
  assert.throws(()=>buildEnhancerRequest({...input,roles:[{role:"custom",detail:"使用 <image4>"},{role:"style"}]}),/未提供/);
});
test("exact text preserves deliberate whitespace while blank text adds no literal",()=>{
  const value=buildEnhancerRequest({task:"t2i",goal:"排版海报",exactText:"  COFFEE · 读书  "});
  assert.ok(value.includes(JSON.stringify("  COFFEE · 读书  ")));
  assert.ok(!buildEnhancerRequest({task:"t2i",goal:"画一朵花",exactText:"  "}).includes("指定文字"));
  assert.ok(buildEnhancerRequest({task:"t2i",goal:"排版说明牌",exactText:"<image9>"}).includes('"<image9>"'));
  const multi=buildEnhancerRequest({task:"multi",count:2,goal:"使用 <image2> 的格纹",roles:[{role:"instruction"}]});
  assert.ok(!multi.includes("商品或物品"));
});
