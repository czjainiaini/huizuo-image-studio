"""Structural checks plus optional read-only comparison to a live ComfyUI server."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CORE = {"UNETLoader", "CLIPLoader", "VAELoader", "QwenImage21Cache", "TextEncodeQwenImage21", "LoadImage", "HuizuoEphemeralLoadImage", "EmptyLatentImage", "ComfySwitchNode", "KSampler", "VAEDecode", "HuizuoEphemeralPreview", "HuizuoCanvasPromptOptimize", "PreviewAny", "MarkdownNote"}
OPTIONAL_PE = {"HuizuoQwenPromptEnhance", "PreviewAny"}
OPTIONAL_LORA = {"Lora Loader (LoraManager)","TriggerWord Toggle (LoraManager)","PreviewAny"}


def validate(graph):
    optional = graph.get('extra',{}).get('huizuoPromptEnhancer',{}).get('optional') is True
    lora_optional=graph.get('extra',{}).get('huizuoLoraManager',{}).get('optional') is True
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert len(nodes) == len(graph["nodes"]), "duplicate node id"
    links = {l[0]: l for l in graph["links"]}
    assert len(links) == len(graph["links"]), "duplicate link id"
    for n in nodes.values():
        assert n["type"] in (CORE | OPTIONAL_PE if optional else CORE | OPTIONAL_LORA if lora_optional else CORE), f"unexpected third-party node: {n['type']}"
        for i, p in enumerate(n["inputs"]):
            if p["link"] is not None:
                l = links[p["link"]]
                assert l[3:5] == [n["id"], i], "input backlink mismatch"
        for i, p in enumerate(n["outputs"]):
            for li in p["links"]:
                assert links[li][1:3] == [n["id"], i], "output backlink mismatch"
    for li, sid, so, tid, ti, kind in links.values():
        assert nodes[tid]["inputs"][ti]["link"] == li
        assert li in nodes[sid]["outputs"][so]["links"]
        assert nodes[sid]["outputs"][so]["type"] == kind and nodes[tid]["inputs"][ti]["type"] in {kind,'*'}, "port type mismatch"
        if lora_optional:
            assert nodes[sid]['mode'] in {0,2,4}
            assert nodes[sid]['mode']!=2 or nodes[tid]['mode']==2,'Muted LoRA preview connected into active generation'
        else: assert nodes[sid]["mode"] == 0, "muted upstream linked into executable graph"
    pending = set(nodes)
    visited = set()
    while pending:
        ready = {nid for nid in pending if all(l[1] in visited for l in links.values() if l[3] == nid)}
        assert ready, "cycle detected"
        visited.update(ready); pending.difference_update(ready)
    if optional:
        assert not any(node['type'] in {'UNETLoader','KSampler','VAEDecode'} for node in nodes.values()),'Optional PE must not include image generation'
        pe=next(node for node in nodes.values() if node['type']=='HuizuoCanvasPromptOptimize')
        assert pe['widgets_values'][0] is False,'PE must default to off'
        assert not any(node['type']=='CLIPLoader' for node in nodes.values()),'Disabled PE must not validate extra model weights'
        return
    roles = {n["properties"]["huizuoRole"]: n for n in nodes.values()}
    cfg = graph["extra"]["huizuo"]
    assert roles['pe']['widgets_values'][0] is False,'Canvas PE must default off'
    prompt_input=next(port for port in roles['encode']['inputs'] if port['name']=='prompt')
    assert links[prompt_input['link']][1:3]==[roles['pe']['id'],0],'Draw encoder must use only plaintext PE output'
    assert roles['save']['type']=='HuizuoEphemeralPreview','Default results must use process-owned memory'
    if lora_optional:
        loader=roles['lora']; assert loader['mode']==4,'LoRA must default to bypass'
        assert loader['widgets_values'][-1]==[] and loader['widgets_values'][-2]=='','Default LoRA list must be empty'
        assert loader['inputs'][1]['link'] is None,'Qwen model-only LoRA must not patch CLIP'
        assert not loader['outputs'][1]['links'],'LoRA CLIP output must not enter encoding or PE'
        assert all(roles[key]['mode']==2 for key in ['loraTriggers','loraPreview','loraLoaded'])
        for key in ['loraTriggers','loraPreview','loraLoaded']:
            for output in roles[key]['outputs']:
                assert all(links[index][3] in {roles[k]['id'] for k in ['loraTriggers','loraPreview','loraLoaded']} for index in output['links']), 'Trigger preview must not overwrite generation prompt'
        assert links[roles['cache']['inputs'][0]['link']][1:3]==[loader['id'],0]
    refs = [p for p in roles["encode"]["inputs"] if p["name"].startswith("images.") and p["link"] is not None]
    expected = {"t2i": 0, "edit": 1, "multi": cfg["refCount"]}[cfg["task"]]
    assert len(refs) == expected, "wrong active reference count"
    assert roles["latentSwitch"]["widgets_values"][0] == (cfg["task"] != "t2i")
    latent_link = links[roles["latentSwitch"]["inputs"][1]["link"]]
    assert latent_link[1:3] == [roles["encode"]["id"], 2], "edit must use native 64-channel encoder latent"
    sampler = roles["sampler"]["widgets_values_named"]
    assert sampler["cfg"] == 1 and sampler["denoise"] == 1
    assert sampler["sampler_name"] == "euler" and sampler["scheduler"] == "simple"
    assert roles["clip"]["widgets_values_named"]["type"] == "qwen_image"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", help="Existing ComfyUI origin; read-only, never queues inference")
    p.add_argument("--allow-missing-models", action="store_true", help="Frontend-only acceptance: checks registry/schema, never certifies inference readiness")
    p.add_argument("--report")
    args = p.parse_args()
    checks = []
    for path in sorted((ROOT / "workflows").glob("*.json")):
        graph = json.loads(path.read_text(encoding="utf-8")); validate(graph)
        checks.append({"file": path.name, "structural": "passed", "nodes": len(graph["nodes"]), "links": len(graph["links"])})
    runtime = "not_tested"
    if args.server:
        with urllib.request.urlopen(args.server.rstrip("/") + "/object_info", timeout=30) as response:
            definitions = json.load(response)
        needed = CORE - {"MarkdownNote"}
        missing = needed - definitions.keys()
        assert not missing, f"Missing core nodes: {sorted(missing)}"
        absent_models = []
        for node_name, param, expected in [("UNETLoader", "unet_name", "qwen_image_2.1_int8_convrot.safetensors"),
                                          ("CLIPLoader", "clip_name", "qwen3vl_8b_int8_convrot.safetensors"),
                                          ("VAELoader", "vae_name", "qwen_image_2.1_vae_bf16.safetensors")]:
            available = definitions[node_name]["input"]["required"][param][0]
            if expected not in available:
                absent_models.append(expected)
        if not args.allow_missing_models:
            assert not absent_models, f"Models not found by server: {absent_models}"
        for branch in ["t2i", "edit", "multi"]:
            api_graph = json.loads((ROOT / "api" / (branch + ".json")).read_text(encoding="utf-8"))
            for node in api_graph.values():
                schema = definitions[node["class_type"]]["input"]
                valid = set(schema.get("required", {})) | set(schema.get("optional", {}))
                for name in node["inputs"]:
                    assert name in valid or ("." in name and name.split(".",1)[0] in valid), f"Input schema mismatch: {node['class_type']}.{name}"
        runtime = "node_registry_and_schema_passed; models_missing; inference_not_run" if absent_models else "node_registry_and_model_list_passed; inference_not_run"
    report = {"workflows": checks, "server_preflight": runtime, "gpu_inference": "not_tested", "comfyui_frontend_import": "not_checked_by_this_script; see native-frontend-validation.json"}
    if args.report:
        path = Path(args.report); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
