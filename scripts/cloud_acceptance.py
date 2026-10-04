"""Run the three explicitly authorized research checks in an existing service.

Never provisions, publishes, downloads weights, or changes platform billing.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    p.add_argument("--purpose", choices=["research"], required=True)
    p.add_argument("--server", default="http://127.0.0.1:6006")
    p.add_argument("--output", type=Path, default=Path("/root/huizuo-cloud-evidence"))
    a = p.parse_args()
    if not a.run:
        print("Read-only plan: text-to-image, edit background, transfer a reference pattern. No jobs submitted.")
        return
    if a.output.exists():
        p.error("Evidence directory exists. Inspect the existing queue and results before another run.")
    a.output.mkdir(parents=True)
    runtime = Path(__file__).resolve().parents[2]
    for source in [runtime / "build-record.json", runtime / "runtime.freeze.txt", Path("/root/public-models-sha256.txt")]:
        if source.is_file():
            shutil.copy2(source, a.output / source.name)
    from PIL import Image, ImageDraw
    ref = Image.new("RGB", (768, 768), "#f8f5e9")
    draw = ImageDraw.Draw(ref)
    for y in range(0, 768, 96):
        for x in range(0, 768, 96):
            if (x // 96 + y // 96) % 2 == 0:
                draw.rectangle((x, y, x + 95, y + 95), fill="#1765b1")
    reference = a.output / "original-checker-reference.png"
    ref.save(reference)
    with urllib.request.urlopen(a.server.rstrip("/") + "/system_stats", timeout=30) as r:
        stats = json.load(r)
    (a.output / "cloud-system-stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    done = threading.Event()
    samples = []

    def monitor():
        with (a.output / "gpu-samples.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["utc", "gpu_used_MiB", "gpu_total_MiB", "utilization_percent"])
            while not done.is_set():
                result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        values = [int(x.strip()) for x in line.split(",")]
                        samples.append(values)
                        writer.writerow([datetime.datetime.now(datetime.timezone.utc).isoformat(), *values])
                    f.flush()
                done.wait(1)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    smoke = Path(__file__).with_name("smoke_test.py")
    tasks = [
        ("t2i", "Studio product photograph of one white ceramic coffee mug with a red handle, the word COFFEE printed clearly in dark charcoal on the front. Plain warm beige background, soft shadow, centered front three-quarter view, no other objects.", []),
        ("edit", "Change only the beige background to a soft mint green background. Preserve the white ceramic mug, red handle, COFFEE text, angle, size and soft lighting.", [a.output / "cloud-t2i.png"]),
        ("multi", "Use image 1 as the product photograph. Apply the blue and cream checkerboard pattern from image 2 to the ceramic body of the mug. Keep the red handle and the COFFEE label clearly readable, preserve the beige background, camera angle and product shape from image 1.", [a.output / "cloud-t2i.png", reference]),
    ]
    outcomes = []
    try:
        for task, prompt, images in tasks:
            args = [sys.executable, "-u", str(smoke), "--server", a.server, "--task", task, "--prompt", prompt, "--run", "--purpose", "research", "--timeout", "1200", "--evidence", str(a.output / f"cloud-{task}.json")]
            for image in images:
                args += ["--image", str(image)]
            print(f"Starting authorized research test: {task}", flush=True)
            started = time.monotonic()
            with (a.output / f"cloud-{task}.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT)
            outcome = {"task": task, "exit_code": result.returncode, "seconds": round(time.monotonic() - started, 2), "prompt": prompt}
            outcomes.append(outcome)
            print(json.dumps(outcome, ensure_ascii=False), flush=True)
            if result.returncode:
                print((a.output / f"cloud-{task}.log").read_text(encoding="utf-8"), flush=True)
                break
    finally:
        done.set()
        thread.join(timeout=5)
        summary = {"purpose": "research", "tasks": outcomes, "all_three_execution_checks_passed": len(outcomes) == 3 and all(x["exit_code"] == 0 for x in outcomes), "sampled_peak_gpu_memory_MiB": max((x[0] for x in samples), default=None), "visual_quality": "requires review", "reference_origin": "original deterministic checkerboard drawn by this script"}
        (a.output / "cloud-acceptance-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = a.output.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for file in sorted(a.output.iterdir()):
                if file.is_file():
                    z.write(file, file.name)
        print("Evidence archive:", archive, flush=True)
    if not summary["all_three_execution_checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
