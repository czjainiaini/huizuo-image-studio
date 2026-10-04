import fs from "node:fs";
import { role } from "../custom_nodes/ComfyUI-HuizuoPanel/web/controller.js";
export function makeGraph(filename = "00-绘作台-整合版.json", compact = false) {
  const raw = JSON.parse(fs.readFileSync(new URL(`../workflows/${filename}`, import.meta.url), "utf8"));
  const graph = { extra: raw.extra, _nodes: raw.nodes, links: {}, _frames: [],
    change(){}, setDirtyCanvas(){}, flushFrames(){const jobs=this._frames.splice(0); for(const job of jobs)job();} };
  let next = raw.last_link_id;
  for (const [id, origin_id, origin_slot, target_id, target_slot, type] of raw.links) {
    graph.links[id] = {id, origin_id, origin_slot, target_id, target_slot, type};
  }
  for (const node of graph._nodes) {
    node.graph = graph;
    node.widgets = Object.entries(node.widgets_values_named ?? {}).map(([name, value]) => ({name,value}));
    node.setDirtyCanvas = () => {};
    node.disconnectInput = slot => {
      const input = node.inputs[slot]; if(input.link == null)return;
      const link = graph.links[input.link]; const source=graph._nodes.find(n=>n.id===link.origin_id);
      source.outputs[link.origin_slot].links=source.outputs[link.origin_slot].links.filter(id=>id!==link.id);
      delete graph.links[input.link]; input.link=null;
      if (compact && input.name.startsWith("images.")) graph._frames.push(()=> {
        const current = node.inputs.find(p=>p.name===input.name); if(current?.link != null)return;
        const refs=node.inputs.filter(p=>p.name.startsWith("images."));
        const linked=refs.filter(p=>p.link != null);
        node.inputs=node.inputs.filter(p=>!p.name.startsWith("images."));
        for(let i=0;i<linked.length;i++){linked[i].name=`images.image_${i+1}`;node.inputs.push(linked[i]);}
        node.inputs.push({name:`images.image_${linked.length+1}`,type:"IMAGE",shape:7,link:null});
        node.inputs.forEach((p,i)=>{if(p.link != null)graph.links[p.link].target_slot=i;});
      });
    };
    node.connect = (slot,target,ti) => {
      if(target.inputs[ti].link != null)target.disconnectInput(ti);
      const id=++next; target.inputs[ti].link=id;
      graph.links[id]={id,origin_id:node.id,origin_slot:slot,target_id:target.id,target_slot:ti,type:node.outputs[slot].type};
      node.outputs[slot].links.push(id);
      if(compact && target.inputs[ti].name.startsWith("images.")) {
        const num=Number(target.inputs[ti].name.split("_").at(-1));
        if(!target.inputs.some(p=>p.name===`images.image_${num+1}`))target.inputs.push({name:`images.image_${num+1}`,type:"IMAGE",shape:7,link:null});
      }
      return graph.links[id];
    };
  }
  if(compact){const enc=role(graph,"encode");enc.inputs=enc.inputs.filter(p=>!p.name.startsWith("images.")||p.name==="images.image_1");}
  return graph;
}
