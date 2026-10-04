"""Prepare a new native ComfyUI environment inside an existing Linux instance.

Default is a read-only plan. --apply installs files/packages but never rents,
queues inference, changes platform settings, saves an image, or publishes.
"""
import argparse
import json
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
COMFY_COMMIT = "651ca296a73cd21c12a57eb8741d52e40dc6528f"


def command(args, cwd=None):
    print("执行：", " ".join(str(value) for value in args), flush=True)
    subprocess.run([str(value) for value in args], cwd=cwd, check=True)


def write_startup(target, device, source, purpose=None, license_record=None, enhancer='off'):
    target = Path(target).resolve()
    startup = '''#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMFY_ROOT="$APP_ROOT/ComfyUI"
cd -- "$COMFY_ROOT"
export HUIZUO_HUB_ENDPOINT="${HUIZUO_HUB_ENDPOINT:-https://hf-mirror.com}"
'''
    config = {"comfy_root": str(target / "ComfyUI"), "model_source": source,
              "purpose": purpose or "research", "port": 6006, "device": "auto",
              "commercial_license_record": str(Path(license_record).resolve()) if license_record else None,
              "prompt_enhancer":enhancer}
    (target / "startup-config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    startup += 'exec "$COMFY_ROOT/.venv/bin/python" "$APP_ROOT/package/scripts/bootstrap_runtime.py" --config "$APP_ROOT/startup-config.json" --apply\n'
    (target / "start.sh").write_text(startup, encoding="utf-8")
    (target / "start.sh").chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/root/HuizuoStudio"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--prompt-enhancer",choices=['off','t2i','edit','both'],default='off')
    parser.add_argument('--with-lora-manager',action='store_true',help='Install the optional fixed LoRA Manager plugin; no LoRA weights')
    parser.add_argument("--model-source", choices=["auto", "download", "public", "existing"], default="auto")
    parser.add_argument("--purpose", choices=["research", "commercial"])
    parser.add_argument("--commercial-license-record", type=Path)
    args = parser.parse_args()
    target = args.root.resolve()
    if target.exists():
        parser.error("目标已存在；为保护用户数据，准备脚本只接受新的空路径。已有环境请使用 install.py。")
    if target.is_relative_to(ROOT):
        parser.error("安装目标不能位于交付包内，避免递归复制；请选择独立系统盘目录。")
    if target == Path("/") or target == Path("/root") or target.is_relative_to(Path("/root/autodl-tmp")) or target.is_relative_to(Path("/root/autodl-fs")):
        parser.error("应用运行时需保存在系统盘的新目录；不接受根目录或 AutoDL 临时/公共数据目录。")
    if args.model_source in ("auto", "download", "public") or args.device == "cuda":
        if not args.purpose:
            parser.error("准备模型需要明确 --purpose research 或 commercial")
        if args.purpose == "commercial" and not (args.commercial_license_record and args.commercial_license_record.is_file()):
            parser.error("请提供已有商业授权记录；本脚本不能授予或核实许可范围。")
    plan = {"root": str(target), "comfyui_commit": COMFY_COMMIT,
            "torch": "2.11.0", "torchvision": "0.26.0",
            "torch_channel": "cu128" if args.device == "cuda" else "cpu",
            "model_source": args.model_source, "device": args.device,
            "models_included": args.model_source == "download",
            "startup_command": f"bash {shlex.quote(str(target / 'start.sh'))}",
            "port": 6006, "inference": "not_run", "platform_image": "not_saved",
            "optional_lora_manager_install":args.with_lora_manager,"lora_weights_included":False}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not args.apply:
        print("只读计划：没有安装、下载、创建实例或运行推理。加 --apply 才在已有实例内安装。")
        return
    if platform.system() != "Linux":
        parser.error("--apply 只适用于现有 Linux 实例；本机 Windows 可用 Docker 进行真实界面验收。")
    if sys.version_info < (3, 10):
        parser.error("Python >= 3.10 required")
    for binary in ["git", "bash"]:
        if not shutil.which(binary):
            parser.error(f"基础环境缺少 {binary}，请使用官方 Python/PyTorch 基础镜像")
    if not shutil.which('nginx'):
        policy=Path('/usr/sbin/policy-rc.d')
        if not policy.is_file() or 'exit 101' not in policy.read_text():
            parser.error('请先由系统软件源安装nginx，并禁止包安装时默认服务自启；本脚本不会创建额外公开端口。')
        command(['apt-get','update','-qq'])
        command(['apt-get','install','-y','--no-install-recommends','nginx'])
    ancestor = target.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    # Allow space for Python/PyTorch, dependencies, official source, and weights.
    minimum = 35 * 1024**3 if args.model_source == "download" else (15 if args.device == "cuda" else 4) * 1024**3
    if shutil.disk_usage(ancestor).free < minimum:
        parser.error(f"空间不足：该方案要求安装前至少 {minimum / 1024**3:.0f} GiB 空闲；不会自动扩容或收费。")
    target.mkdir(parents=True)
    package = target / "package"
    package.mkdir()
    for name in ["scripts", "deploy", "workflows", "api", "custom_nodes", "third_party"]:
        shutil.copytree(ROOT / name, package / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ["models-manifest.json", "prompt-enhancer-models-manifest.json", "README.md", "使用指南.md", "提示词示例.md", "LoRA使用说明.md", "NOTICE.md"]:
        shutil.copy2(ROOT / name, package / name)
    comfy = target / "ComfyUI"
    command(["git", "init", comfy])
    command(["git", "-C", comfy, "remote", "add", "origin", "https://github.com/Comfy-Org/ComfyUI.git"])
    command(["git", "-C", comfy, "fetch", "--depth", "1", "origin", COMFY_COMMIT])
    command(["git", "-C", comfy, "checkout", "--detach", "FETCH_HEAD"])
    command([sys.executable, "-m", "venv", comfy / ".venv"])
    python = comfy / ".venv" / "bin" / "python"
    command([python, "-m", "pip", "install", "--no-cache-dir", "torch==2.11.0", "torchvision==0.26.0", "--index-url", f"https://download.pytorch.org/whl/{plan['torch_channel']}"])
    command([python, "-m", "pip", "install", "--no-cache-dir", "--index-url", "https://pypi.org/simple", "-r", comfy / "requirements.txt", "-c", package / "deploy" / "torch-constraints.txt"])
    command([python, "-m", "pip", "check"])
    command([python, package / "scripts" / "fix_root_navigation.py", "--comfy-root", comfy, "--apply"])
    installer = [python, package / "scripts" / "install.py", "--comfy-root", comfy]
    if args.model_source == "download":
        installer += ["--download-models", "--purpose", args.purpose]
        if args.commercial_license_record:
            installer += ["--commercial-license-record", args.commercial_license_record.resolve()]
    command(installer)
    if args.with_lora_manager:
        command([python,package/'scripts/install_lora_manager.py','--comfy-root',comfy,'--python',python,'--apply'])
    if args.model_source == "public":
        command([python, package / "scripts/link_public_models.py", "--comfy-root", comfy, "--apply"])
    write_startup(target, args.device, args.model_source, args.purpose, args.commercial_license_record,args.prompt_enhancer)
    if target==Path('/root/HuizuoStudio'):
        command([python,package/'scripts/install_gateway.py','--app-root',target,'--apply'])
        plan['persistent_front_door']=True
    else:
        plan['persistent_front_door']=False
    boot_source = Path('/proc/1/fd/255')
    plan['native_boot_hook_installed'] = False
    if (target == Path('/root/HuizuoStudio') and boot_source.exists()
            and re.search(r'^\s*source /etc/profile\b', boot_source.read_text(errors='replace'), re.M)):
        command([python, package / 'scripts/install_autostart.py', '--app-root', target, '--apply'])
        plan['native_boot_hook_installed'] = True
    plan['navigation_fix'] = json.loads((comfy / '.huizuo-runtime/navigation-fix.json').read_text())
    freeze = subprocess.check_output([python, "-m", "pip", "freeze"], text=True)
    (target / "runtime.freeze.txt").write_text(freeze, encoding="utf-8")
    (target / "build-record.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print("安装完成。未启动当前服务、跑图、保存镜像或发布。原生开机钩子：", plan['native_boot_hook_installed'])
    if args.model_source == "existing" and args.device == "cuda":
        print("请将官方权重按 manifest 放入 ComfyUI/models 的三个对应子目录；缺少模型时启动脚本会明确报错。")
    print("平台开机命令：", plan["startup_command"])
    if plan['native_boot_hook_installed']:
        print('此平台已安装PID1开机钩子；若另设镜像开机命令，请用 bash /root/HuizuoStudio/autostart.sh 共用进程锁。')


if __name__ == "__main__":
    main()
