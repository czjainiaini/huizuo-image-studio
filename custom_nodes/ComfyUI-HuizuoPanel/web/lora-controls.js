import { role, readWidget } from "./controller.js?v=0.4.4";

export const LORA_LOADER = "Lora Loader (LoraManager)";
export const LORA_TRIGGER = "TriggerWord Toggle (LoraManager)";
export function loraEnabled(graph) { return role(graph,"lora")?.mode === 0; }
export function setLoraEnabled(graph, enabled) {
  const loader=role(graph,"lora");
  if(!loader || loader.type!==LORA_LOADER) throw new Error("请先载入LoRA管理版工作流。");
  loader.mode=enabled?0:4; // Native bypass routes the original MODEL to cache.
  for(const key of ["loraTriggers","loraPreview","loraLoaded"]){
    const node=role(graph,key);if(node)node.mode=enabled?0:2;
  }
  if(graph.extra?.huizuoLoraManager)graph.extra.huizuoLoraManager.enabled=Boolean(enabled);
  graph.change?.();graph.setDirtyCanvas?.(true,true);
}
export function loraSelection(graph) {
  const loader=role(graph,"lora");if(!loader)return {selected:0,active:0};
  const rows=readWidget(loader,"loras") ?? [];
  if(!Array.isArray(rows))throw new Error("LoRA列表格式不正确，请在管理器节点重新选择。");
  return {selected:rows.length,active:rows.filter(item=>item?.active===true).length};
}
export function validateLoraSelection(graph) {
  if(!loraEnabled(graph))return [];
  const rows=readWidget(role(graph,"lora"),"loras") ?? [];
  if(!Array.isArray(rows))return ["LoRA列表格式不正确，请在管理器节点重新选择。"];
  const errors=[];
  for(const row of rows){
    if(row?.active!==true)continue;
    if(!row || typeof row.name!=="string" || !row.name.trim())errors.push("启用的LoRA缺少名称，请重新选择。");
    if(typeof row?.strength!=="number" || !Number.isFinite(row.strength))errors.push("LoRA模型强度必须是有限数值。");
  }
  return [...new Set(errors)];
}
