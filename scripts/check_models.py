"""Check real model files without loading or downloading them."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect_models(model_root, manifest, verify_hash=False):
    results = []
    model_root = model_root.resolve()
    for model in manifest["models"]:
        path = model_root / model["path"]
        # Model folders may intentionally be mounts/symlinks to an official library.
        record = {"name": model["path"], "exists": path.is_file(), "valid": False}
        if path.is_file():
            record["bytes"] = path.stat().st_size
            record["valid"] = record["bytes"] == model["bytes"]
            if record["valid"] and verify_hash:
                h = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                        h.update(chunk)
                record["sha256"] = h.hexdigest()
                record["valid"] = record["sha256"] == model["sha256"]
        results.append(record)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--hash", action="store_true", help="Read all ~17.3GB and verify SHA-256")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "models-manifest.json").read_text(encoding="utf-8"))
    results = inspect_models(args.model_root or args.comfy_root / "models", manifest, args.hash)
    report = {"models": results, "verification": "sha256" if args.hash else "file_size", "ready": all(r["valid"] for r in results)}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ready"]:
        parser.exit(1, "模型缺失或大小/哈希不符；请按 models-manifest.json 安装或挂载官方权重。没有下载或运行推理。\n")


if __name__ == "__main__":
    main()
