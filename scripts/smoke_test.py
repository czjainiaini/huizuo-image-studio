"""Opt-in real GPU smoke test. Without --run: no network calls or inference."""
import argparse
import datetime
import io
import json
import math
from pathlib import Path
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r: return json.load(r)


def upload(server, path):
    boundary = "huizuo" + uuid.uuid4().hex
    extension = path.suffix.lower()
    if extension not in [".png", ".jpg", ".jpeg", ".webp"]: raise ValueError("PNG/JPEG/WebP input required")
    filename = "huizuo_test_" + uuid.uuid4().hex + extension
    mime = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp"}[extension]
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n').encode() + path.read_bytes() + (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n').encode()
    req = urllib.request.Request(server + "/upload/image", data=body, headers={"Content-Type":f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as response: info = json.load(response)
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server", default="http://127.0.0.1:6006")
    p.add_argument("--task", choices=["t2i","edit","multi"], default="t2i")
    p.add_argument("--image", type=Path, action="append", default=[])
    p.add_argument("--prompt")
    p.add_argument("--steps", type=int, help="Optional diagnostic override, 1–100")
    p.add_argument("--cache-device", choices=["auto", "gpu", "cpu", "off"], help="Optional diagnostic override")
    p.add_argument("--edit-resolution", type=int, help="Optional reference pixel budget, multiple of 32")
    p.add_argument("--run", action="store_true")
    p.add_argument("--purpose", choices=["research","commercial"])
    p.add_argument("--commercial-license-record", type=Path)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--evidence", type=Path, default=ROOT / "evidence" / "gpu-smoke.json")
    a = p.parse_args()
    if a.steps is not None and not 1 <= a.steps <= 100:
        p.error("--steps must be between 1 and 100")
    if a.edit_resolution is not None and (not 32 <= a.edit_resolution <= 4096 or a.edit_resolution % 32):
        p.error("--edit-resolution must be a multiple of 32 between 32 and 4096")
    graph = json.loads((ROOT / "api" / f"{a.task}.json").read_text(encoding="utf-8"))
    if a.steps is not None:
        next(n for n in graph.values() if n["class_type"] == "KSampler")["inputs"]["steps"] = a.steps
    if a.cache_device is not None:
        next(n for n in graph.values() if n["class_type"] == "QwenImage21Cache")["inputs"]["device"] = a.cache_device
    if a.edit_resolution is not None:
        next(n for n in graph.values() if n["class_type"] == "TextEncodeQwenImage21")["inputs"]["resolution"] = a.edit_resolution
    if not a.run:
        print("Dry run. No network, upload, queue, or GPU work performed.")
        print("This test submits ONE job only after --run and --purpose are specified.")
        print(json.dumps({"task":a.task,"server":a.server,"image_paths":[str(x) for x in a.image]}, ensure_ascii=False)); return
    if not a.purpose: p.error("Specify model-use purpose explicitly.")
    if a.purpose == "commercial" and not (a.commercial_license_record and a.commercial_license_record.is_file()):
        p.error("Supply a commercial-license record. This script cannot verify its scope.")
    expected_count = {"t2i":0,"edit":1,"multi":2}[a.task]
    if len(a.image) != expected_count: p.error(f"This API smoke template needs exactly {expected_count} image(s). Panel supports 2–4 references separately.")
    for path in a.image:
        if not path.is_file(): p.error(f"Input image missing: {path}")
    from PIL import Image, ImageOps
    server = a.server.rstrip("/")
    refs = []
    for path in a.image: refs.append(upload(server,path))
    loaders = [n for n in graph.values() if n["class_type"] in {"LoadImage", "HuizuoEphemeralLoadImage"}]
    for node, name in zip(loaders,refs): node["inputs"]["image"] = name
    if a.prompt:
        next(n for n in graph.values() if n["class_type"] == "TextEncodeQwenImage21")["inputs"]["prompt"] = a.prompt
    if a.task == "t2i": expected_size = (1024,1024)
    else:
        with Image.open(a.image[0]) as im: w,h = ImageOps.exif_transpose(im).size
        ratio = w / h
        budget = next(n for n in graph.values() if n["class_type"] == "TextEncodeQwenImage21")["inputs"]["resolution"]
        expected_size = (max(32,round(math.sqrt(budget**2*ratio)/32)*32), max(32,round(math.sqrt(budget**2/ratio)/32)*32))
    started = time.monotonic()
    ui_name = {"t2i":"01-文生图.json", "edit":"02-单图编辑.json", "multi":"03-多图融合.json"}[a.task]
    ui = json.loads((ROOT / "workflows" / ui_name).read_text(encoding="utf-8"))
    for node in ui["nodes"]:
        api_node = graph.get(str(node["id"]))
        if not api_node: continue
        named = node.get("widgets_values_named", {})
        for name in list(named):
            if name in api_node["inputs"]: named[name] = api_node["inputs"][name]
        if "control_after_generate" in named: named["control_after_generate"] = "fixed"
        if named: node["widgets_values"] = list(named.values())
    data = json.dumps({"prompt":graph,"client_id":"huizuo-smoke-"+uuid.uuid4().hex,
                       "extra_data":{"extra_pnginfo":{"workflow":ui}}}).encode()
    with urllib.request.urlopen(urllib.request.Request(server+"/prompt",data=data,headers={"Content-Type":"application/json"}), timeout=60) as response: queued=json.load(response)
    pid = queued["prompt_id"]; print("Queued one job:",pid)
    history = None
    while time.monotonic()-started < a.timeout:
        item = get_json(server+"/history/"+pid).get(pid)
        if item:
            status = item.get("status",{})
            if status.get("status_str") == "error": raise RuntimeError(json.dumps(status,ensure_ascii=False))
            if status.get("completed"):
                history=item; break
        time.sleep(2)
    if history is None: raise TimeoutError("Job was NOT cancelled. Inspect the existing ComfyUI queue/history before rerunning.")
    outputs = [im for out in history.get("outputs",{}).values() for im in out.get("images",[]) if im.get("type") in {"output", "temp"}]
    if not outputs: raise RuntimeError("No generated preview or output image returned")
    from urllib.parse import urlencode
    with urllib.request.urlopen(server+"/view?"+urlencode(outputs[0]), timeout=60) as response: png=response.read()
    with Image.open(io.BytesIO(png)) as im: actual_size=im.size
    if actual_size != expected_size: raise AssertionError(f"Wrong output size {actual_size}; expected {expected_size}. Check core latent compatibility.")
    a.evidence.parent.mkdir(parents=True,exist_ok=True)
    image_path=a.evidence.with_suffix(".png");image_path.write_bytes(png)
    report={"time":datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),"task":a.task,"prompt_id":pid,
            "seconds":round(time.monotonic()-started,2),"size":actual_size,"expected_size":expected_size,
            "core_execution":"passed","visual_quality":"requires_human_review","output":str(image_path),"history":history}
    a.evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Execution and size checks passed. Review image quality separately:",image_path)


if __name__ == "__main__": main()
