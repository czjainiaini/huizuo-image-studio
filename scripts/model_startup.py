"""Prepare pinned weights at startup using verified files, AutoDL, or HF Hub.

Downloading is an explicit runtime policy. No package installation, inference,
instance creation, commercial-license grant, or publication is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Comfy-Org/Qwen-Image-2.1"


def validate_manifest(manifest):
    if manifest.get("repository") != REPOSITORY or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", "")):
        raise ValueError("模型仓库或固定修订无效。")
    seen = set()
    for model in manifest["models"]:
        path = PurePosixPath(model["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in model["path"] or len(path.parts) != 2 or path.parts[0] not in {"diffusion_models", "text_encoders", "vae"} or path.suffix != ".safetensors" or model["path"] in seen:
            raise ValueError("模型路径无效或重复。")
        seen.add(model["path"])
        if not isinstance(model["bytes"], int) or model["bytes"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", model["sha256"]):
            raise ValueError("模型大小或 SHA-256 无效。")
    if not seen:
        raise ValueError("模型清单为空。")


def fingerprint(path):
    stat = path.stat()
    return {"real_path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "ctime_ns": stat.st_ctime_ns, "device": stat.st_dev, "inode": stat.st_ino}


def digest(path, progress=lambda _: None, model=None):
    result = hashlib.sha256()
    total = path.stat().st_size
    checked = 0
    last = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
            checked += len(block)
            now = time.monotonic()
            if now - last >= .5 or checked == total:
                progress({"phase": "checking", "model": model or path.name, "bytes_done": checked, "bytes_total": total})
                last = now
    return result.hexdigest()


def write_json(path, data):
    if path.is_symlink():
        raise ValueError("状态文件存在外部软链接；保留原文件。")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".huizuo-", suffix=".json", delete=False, encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        temp = Path(stream.name)
    os.replace(temp, path)


def worker_environment(endpoint):
    environment = dict(os.environ)
    if endpoint == "https://hf-mirror.com":
        for key in list(environment):
            if key.lower() in {"http_proxy", "https_proxy", "all_proxy"}:
                environment.pop(key)
    environment.update({"NO_PROXY":"127.0.0.1,localhost,::1","no_proxy":"127.0.0.1,localhost,::1",
                        "HF_HUB_DISABLE_TELEMETRY":"1","HF_HUB_DOWNLOAD_TIMEOUT":"30",
                        "HF_HUB_DISABLE_XET":"1","HF_HUB_DISABLE_IMPLICIT_TOKEN":"1"})
    return environment


def download_official(manifest, model, staging, progress):
    endpoint = os.environ.get("HUIZUO_HUB_ENDPOINT") or ("https://hf-mirror.com" if Path("/.autodl").is_dir() else "https://huggingface.co")
    if endpoint not in {"https://huggingface.co", "https://hf-mirror.com"}:
        raise ValueError("模型下载端点不在经过确认的列表中。")
    if endpoint == "https://huggingface.co":
        return hub_download(manifest, model, staging, progress, endpoint)
    progress({"phase":"downloading","model":Path(model["path"]).name,"message":"正在通过平台文档推荐镜像下载，完成后核对官方 SHA-256。","bytes_done":0,"bytes_total":model["bytes"]})
    worker = Path(__file__).with_name("hub_download_worker.py")
    process = subprocess.Popen([sys.executable,str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,text=True,env=worker_environment(endpoint))
    process.stdin.write(json.dumps({"manifest":manifest,"model":model,"staging":str(staging),"endpoint":endpoint}));process.stdin.close()
    result = None
    failure = None
    for line in process.stdout:
        value = json.loads(line)
        if value.get("event") == "progress":
            progress(value["data"])
        elif value.get("event") == "result":
            result = Path(value["path"])
        elif value.get("event") == "error":
            failure = value["message"]
    if process.wait() or result is None:
        raise RuntimeError(failure or "模型下载失败，请检查平台网络连接。")
    return result


def hub_download(manifest, model, staging, progress, endpoint="https://huggingface.co"):
    # Already supplied by official ComfyUI requirements. Hub owns retries,
    # incomplete files, cache metadata and resumable transfer.
    from huggingface_hub import hf_hub_download
    from tqdm.auto import tqdm

    class StartupProgress(tqdm):
        def update(self, amount=1):
            result = super().update(amount)
            now = time.monotonic()
            if self.total and (now-getattr(self,'_huizuo_report_at',0)>=.5 or self.n>=self.total):
                progress({"phase": "downloading", "model": Path(model["path"]).name,
                          "bytes_done": int(self.n), "bytes_total": int(self.total)})
                self._huizuo_report_at=now
            return result

    return Path(hf_hub_download(repo_id=manifest["repository"], filename=model["path"],
                               revision=manifest["revision"], local_dir=staging,
                               endpoint=endpoint, token=False, etag_timeout=30,
                               library_name="huizuo-studio", library_version="0.3",
                               tqdm_class=StartupProgress))


def ensure_models(comfy, manifest, public_sources=None, source="auto", progress=lambda _: None,
                  downloader=download_official, reserve_bytes=2 * 1024**3):
    from filelock import FileLock
    comfy = Path(comfy).resolve()
    if not (comfy / "main.py").is_file():
        raise ValueError("需要已有 ComfyUI 环境。")
    if source not in {"auto", "public", "download", "existing"}:
        raise ValueError("模型准备策略无效。")
    validate_manifest(manifest)
    state_dir = comfy / ".huizuo-runtime"
    if not state_dir.resolve().is_relative_to(comfy):
        raise ValueError("状态目录越出 ComfyUI；保留原文件。")
    state_dir.mkdir(exist_ok=True)
    if (state_dir / "model-preparation.lock").is_symlink():
        raise ValueError("模型锁存在外部软链接；保留原文件。")
    with FileLock(str(state_dir / "model-preparation.lock"), timeout=1):
        cache_file = state_dir / "model-verification.json"
        if cache_file.is_symlink():
            raise ValueError("验证记录存在外部软链接；保留原文件。")
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {}
        results = []
        plans = []

        def verified(path, model):
            if not path.is_file() or path.stat().st_size != model["bytes"]:
                return False
            identity = fingerprint(path)
            # Some filesystems expose coarse timestamps. Always verify content;
            # metadata alone can miss a same-size rewrite within one clock tick.
            if digest(path, progress, path.name) != model["sha256"]:
                return False
            if fingerprint(path) != identity:
                raise ValueError("模型在校验期间发生变化，请重试。")
            cache[model["path"]] = {"sha256": model["sha256"], "fingerprint": identity}
            progress({"phase": "reusing", "model": path.name})
            return True

        for model in manifest["models"]:
            target = comfy / "models" / model["path"]
            if not target.parent.resolve().is_relative_to(comfy):
                raise ValueError("模型目标目录越出 ComfyUI；保留原文件。")
            if target.exists():
                if not verified(target, model):
                    raise ValueError(f"已有模型内容不符，已保留：{target.name}。请更换该文件后重新启动。")
                results.append({"model": model["path"], "source": "existing"})
                continue
            if target.is_symlink():
                # Keep a broken link for restoration; never erase a user's file.
                backup = target.with_name(target.name + ".huizuo-broken-link")
                if backup.exists() or backup.is_symlink():
                    raise ValueError("旧软链接备份已存在，请先检查。")
                target.rename(backup)
            public = Path((public_sources or {}).get(model["path"], ""))
            if source in {"auto", "public"} and public.is_file() and verified(public, model):
                plans.append((model, target, public))
            elif source in {"auto", "download"}:
                plans.append((model, target, None))
            else:
                raise ValueError(f"缺少可用模型：{target.name}。当前策略不允许自动下载。")

        staging = comfy / ".huizuo-downloads"
        if not staging.resolve().is_relative_to(comfy):
            raise ValueError("下载暂存目录越出 ComfyUI；保留原文件。")
        needed = sum(model["bytes"] for model, _, public in plans if public is None)
        # Conservative free-space gate; no paid expansion or deletion of caches.
        if needed and shutil.disk_usage(comfy).free < needed + reserve_bytes:
            raise ValueError(f"下载空间不足：需要至少 {(needed+reserve_bytes)/1024**3:.1f} GiB 空闲；不会自动扩容。")
        for model, target, public in plans:
            target.parent.mkdir(parents=True, exist_ok=True)
            if public is not None:
                progress({"phase": "linking", "model": target.name})
                if target.exists() or target.is_symlink():
                    raise ValueError("模型目标在准备期间出现；已保留。")
                target.symlink_to(public.resolve())
                results.append({"model": model["path"], "source": "public"})
            else:
                progress({"phase": "downloading", "model": target.name, "bytes_done": 0, "bytes_total": model["bytes"]})
                staging.mkdir(exist_ok=True)
                if not (staging / model["path"]).parent.resolve().is_relative_to(staging.resolve()) or not (staging / '.cache').resolve().is_relative_to(staging.resolve()):
                    raise ValueError("下载暂存路径存在外部软链接；保留原文件。")
                downloaded = Path(downloader(manifest, model, staging, progress))
                if not downloaded.resolve().is_relative_to(staging.resolve()) or downloaded.is_symlink():
                    raise ValueError("下载返回了暂存目录之外的文件；已保留。")
                if not verified(downloaded, model):
                    raise ValueError(f"下载内容校验失败：{target.name}。暂存文件已保留，未启用该模型。")
                if target.exists() or target.is_symlink():
                    raise ValueError("模型目标在下载期间出现；已保留。")
                os.replace(downloaded, target)
                results.append({"model": model["path"], "source": "download"})
            cache[model["path"]] = {"sha256": model["sha256"], "fingerprint": fingerprint(target)}
            write_json(cache_file, cache)
        write_json(cache_file, cache)
        progress({"phase": "models_ready", "models": results})
        return results


def read_public_catalog(path):
    sources = json.loads(Path(path).read_text(encoding="utf-8"))["models"]
    for value in sources.values():
        source = Path(value)
        if not source.is_absolute() or not source.is_relative_to(Path("/.autodl")) or ".." in source.parts:
            raise ValueError("公共模型源必须是已记录的 /.autodl 路径。")
    return sources


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comfy-root", type=Path, required=True)
    p.add_argument("--source", choices=["auto", "public", "download", "existing"], default="auto")
    p.add_argument("--purpose", choices=["research", "commercial"], required=True)
    p.add_argument("--commercial-license-record", type=Path)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    if a.purpose == "commercial" and not (a.commercial_license_record and a.commercial_license_record.is_file()):
        p.error("商业用途需要已有授权记录；本程序不能授予或核实许可。")
    if not a.apply:
        print(json.dumps({"source": a.source, "purpose": a.purpose, "root": str(a.comfy_root), "writes": False, "downloads": False}, ensure_ascii=False))
        return
    manifest = json.loads((ROOT / "models-manifest.json").read_text(encoding="utf-8"))
    catalog = read_public_catalog(ROOT / "deploy/autodl-public-models.json")
    results = ensure_models(a.comfy_root, manifest, catalog, a.source,
                            progress=lambda value: print(json.dumps(value, ensure_ascii=False), flush=True))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
