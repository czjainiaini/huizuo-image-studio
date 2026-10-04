"""Install onto an existing ComfyUI. Never provisions, publishes, or starts a server."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b""): h.update(b)
    return h.hexdigest()


def contained(root, path):
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Target escapes ComfyUI: {resolved}")
    return resolved


def download_models(comfy, manifest):
    for m in manifest["models"]:
        path = contained(comfy, comfy / "models" / m["path"])
        if path.exists():
            if path.stat().st_size != m["bytes"] or digest(path) != m["sha256"]:
                raise ValueError(f"Existing model has wrong content; preserved: {path}")
            print("Verified existing model:", path.name); continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = contained(comfy, path.with_name(path.name + ".huizuo-partial"))
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "HuizuoInstaller/0.1"}
        if 0 < offset < m["bytes"]: headers["Range"] = f"bytes={offset}-"
        if offset != m["bytes"]:
            with urllib.request.urlopen(urllib.request.Request(m["url"], headers=headers), timeout=60) as response:
                resume = offset > 0 and response.status == 206
                if resume:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise ValueError("Download server returned unexpected byte range")
                print(f"Downloading {path.name}; total {m['bytes'] / 1e9:.2f} GB")
                with partial.open("ab" if resume else "wb") as out:
                    shutil.copyfileobj(response, out, length=8 * 1024 * 1024)
        if partial.stat().st_size != m["bytes"] or digest(partial) != m["sha256"]:
            raise ValueError(f"Model size/checksum mismatch; original untouched: {partial}")
        if path.exists(): raise ValueError(f"Target appeared during download; preserved: {path}")
        partial.rename(path)
        print("Model checksum passed:", path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--update", action="store_true", help="Update only files from an intact earlier Huizuo install")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--download-models", action="store_true", help="Downloads about 17.3GB; never implicit")
    parser.add_argument("--purpose", choices=["research", "commercial"])
    parser.add_argument("--commercial-license-record", type=Path)
    args = parser.parse_args()
    comfy = args.comfy_root.resolve()
    if not (comfy / "main.py").is_file() or not (comfy / "nodes.py").is_file():
        parser.error("--comfy-root must point to an existing ComfyUI directory")
    if args.download_models:
        if not args.purpose: parser.error("Model use requires --purpose research or commercial")
        if args.purpose == "commercial" and not (args.commercial_license_record and args.commercial_license_record.is_file()):
            parser.error("Provide your commercial-license record. This script does not judge coverage or grant a license.")
    jobs = []
    for source in (ROOT / "custom_nodes" / "ComfyUI-HuizuoPanel").rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts:
            jobs.append((source, comfy / "custom_nodes" / "ComfyUI-HuizuoPanel" / source.relative_to(ROOT / "custom_nodes" / "ComfyUI-HuizuoPanel")))
    for source in (ROOT / "workflows").glob("*.json"):
        jobs.append((source, comfy / "user" / "default" / "workflows" / "Huizuo" / source.name))
        jobs.append((source, comfy / "custom_nodes" / "ComfyUI-HuizuoPanel" / "web" / "workflows" / source.name))
    for source in (ROOT / "third_party").glob("*"):
        if source.is_file(): jobs.append((source, comfy / "custom_nodes" / "ComfyUI-HuizuoPanel" / "third_party" / source.name))
    marker = contained(comfy, comfy / "custom_nodes" / "ComfyUI-HuizuoPanel" / ".huizuo-package.json")
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {"files": {}}
    records = {}
    for source, target in jobs:
        target = contained(comfy, target)
        key = target.relative_to(comfy).as_posix()
        if target.exists():
            if not args.update or previous.get("files", {}).get(key) != digest(target):
                parser.error(f"Refusing to overwrite an existing/modified file: {target}")
        records[key] = digest(source)
        print(f"{'Would copy' if args.dry_run else 'Copy'}: {source.name} -> {key}")
    if args.dry_run:
        print("Dry run: no files written, no models downloaded."); return
    if args.download_models:
        manifest = json.loads((ROOT / "models-manifest.json").read_text(encoding="utf-8"))
        download_models(comfy, manifest)
    for source, target in jobs:
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"version": "0.4.4", "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "files": records}, indent=2), encoding="utf-8")
    print("Installed. Restart ComfyUI and use the 绘作台 sidebar's built-in workflow buttons, or native workflow menu.")
    print("No inference, provisioning, commercial authorization, or marketplace publication was performed.")


if __name__ == "__main__":
    main()
