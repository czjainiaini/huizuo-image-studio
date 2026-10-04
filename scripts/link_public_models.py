"""Verify all official model hashes before linking observed AutoDL public files.

Read-only plan by default. Never downloads, overwrites, queues, or publishes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "deploy/autodl-public-models.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    comfy = args.comfy_root.resolve()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))["models"]
    models = json.loads((ROOT / "models-manifest.json").read_text(encoding="utf-8"))["models"]
    planned = []
    for model in models:
        relative = Path(model["path"])
        if relative.is_absolute() or ".." in relative.parts:
            parser.error("Invalid model manifest path")
        source = Path(catalog[model["path"]])
        if not source.is_absolute() or not source.is_relative_to(Path("/.autodl")) or ".." in source.parts:
            parser.error("Public sources must use an absolute /.autodl path")
        target = comfy / "models" / relative
        if not target.parent.resolve().is_relative_to(comfy):
            parser.error(f"Target parent escapes ComfyUI; preserved: {target}")
        planned.append((model, source, target))
    print(json.dumps({"apply": args.apply, "links": [{"source": str(s), "target": str(t)} for _, s, t in planned]}, ensure_ascii=False, indent=2))
    if not args.apply:
        print("只读计划。公共库条目不代表商用许可；实机必须校验与官方 manifest 一致。")
        return
    if platform.system() != "Linux" or not (comfy / "main.py").is_file():
        parser.error("--apply requires an existing Linux ComfyUI environment")
    # Verify every file and destination before making the first link.
    for model, source, target in planned:
        if not source.is_file() or source.stat().st_size != model["bytes"]:
            parser.error(f"Public model missing or wrong size; no links created: {source}")
        print(f"校验 SHA-256：{model['path']}", flush=True)
        if digest(source) != model["sha256"]:
            parser.error(f"Public model differs from pinned official weights; no links created: {source}")
        if target.exists() or target.is_symlink():
            if not target.is_file() or not target.samefile(source):
                parser.error(f"Existing target preserved; no links created: {target}")
    for _, source, target in planned:
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
    print("三份权重已校验并挂载。没有复制权重、下载、推理或发布。")


if __name__ == "__main__":
    main()
