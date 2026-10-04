"""Package original deliverables and verified notes, excluding raw reference files."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name',default='绘作台-QwenImage2.1-v0.4.4.zip')
    args=parser.parse_args()
    if Path(args.output_name).name!=args.output_name or not args.output_name.endswith('.zip') or '/' in args.output_name or '\\' in args.output_name:
        parser.error('输出名称只能是ZIP文件名，不能包含目录。')
    files = []
    for folder in ["workflows","api","custom_nodes","scripts","tests","third_party","evidence","deploy","research"]:
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and "mirror-restored-cloud" not in p.parts and "v04-cloud" not in p.parts and "v043-cloud" not in p.parts and "v044-cloud" not in p.parts and p.suffix != ".pyc" and not p.name.startswith(("autodl-", "private-", "reference-")) and p.name != "test_mirror_cleanup_guards.py" and "upstream" not in p.parts)
    files += [ROOT / name for name in ["README.md","使用指南.md","提示词示例.md","LoRA使用说明.md","NOTICE.md","package.json","models-manifest.json","prompt-enhancer-models-manifest.json",".dockerignore"]]
    files = sorted(set(files))
    # Paid-session plans and progress contain account-specific operational notes.
    files = [p for p in files if p.name not in {
        'complete-acceptance-plan.md', 'complete-acceptance-progress.md',
        'complete-acceptance-round2-result.md'}]
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    target = dist / args.output_name
    with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as archive:
        for p in files: archive.write(p,"huizuo-studio/"+p.relative_to(ROOT).as_posix())
        archive.writestr("huizuo-studio/PACKAGE-SHA256.json",json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(manifest) + 1
        assert not any("reference-" in name or "/upstream/" in name for name in archive.namelist())
        assert not any("/v04-cloud/" in name or "/v043-cloud/" in name or "/v044-cloud/" in name or Path(name).name.startswith(("autodl-", "private-")) or Path(name).name == "test_mirror_cleanup_guards.py" for name in archive.namelist())
    checksum=hashlib.sha256(target.read_bytes()).hexdigest()
    (dist / "SHA256SUMS.txt").write_text(f"{checksum}  {target.name}\n",encoding="utf-8")
    print(json.dumps({"zip":str(target),"files":len(files),"bytes":target.stat().st_size,"sha256":checksum},ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
