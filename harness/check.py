#!/usr/bin/env python3
"""检查和汇总 runs/ 下的运行结果。

用法：
  python3 harness/check.py                 # 汇总成 Markdown 表（打印出来）
  python3 harness/check.py --regen         # 先对还没检查过的运行做复现检查，再汇总
  python3 harness/check.py --sheet out.jpg # 另外把所有成图拼成一张总览图

复现检查：把交上来的 src/ 和 run.sh 拷到干净目录，在断网的新容器里执行 run.sh，
和交上来的 out/final.png 比：逐像素相同记"一致"，否则记 PSNR。结果写回 result.json 的 regen 字段。
src/ 里只拷文本文件：图片、.blend 这类中间产物必须由 run.sh 重新生成，跳过的文件记在 regen.skipped。
run.sh 要在该档的时间上限内跑完。
"""
import argparse
import json
import math
import pathlib
import shutil
import subprocess
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
RUNS = REPO / "runs"
IMAGE = "code2pixel/env:0.1"


def psnr(a, b):
    import numpy as np
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    mse = ((a - b) ** 2).mean()
    return math.inf if mse == 0 else 10 * math.log10(255 ** 2 / mse)


def regen(run, minutes):
    from PIL import Image
    ws = run / "workspace"
    final = ws / "out" / "final.png"
    if not final.exists() or not (ws / "run.sh").exists():
        return {"status": "no_output"}
    tmp = RUNS / "_regen" / run.name
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "out").mkdir(parents=True)
    skipped = []

    def code_only(d, names):   # 跳过 __pycache__ 和不是文本的文件
        skip = []
        for n in names:
            p = pathlib.Path(d) / n
            if n == "__pycache__":
                skip.append(n)
            elif p.is_file():
                try:
                    p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, ValueError):
                    skip.append(n)
                    skipped.append(str(p.relative_to(ws)))
        return skip

    shutil.copytree(ws / "src", tmp / "src", ignore=code_only)
    shutil.copy(ws / "run.sh", tmp / "run.sh")
    subprocess.run(["chmod", "-R", "a+rwX", str(tmp)], check=True)
    name = f"c2p-regen-{run.name}".replace("_", "-").lower()[:60]
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    start = time.time()
    proc = subprocess.Popen(["docker", "run", "--name", name, "--network", "none", "--cpus", "4", "--memory", "6g",
                             "-v", f"{tmp}:/workspace", "-w", "/workspace", IMAGE, "bash", "run.sh"],
                            stdout=subprocess.DEVNULL, stderr=open(tmp / "regen_stderr.log", "w"))
    timed_out = False
    try:
        proc.wait(timeout=minutes * 60)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["docker", "kill", name], capture_output=True)
        proc.wait()
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    secs = round(time.time() - start)
    out = tmp / "out" / "final.png"
    if timed_out or not out.exists():
        return {"status": "timeout" if timed_out else "failed", "exit_code": proc.returncode, "seconds": secs,
                "skipped": skipped}
    a, b = Image.open(final).convert("RGB"), Image.open(out).convert("RGB")
    if a.size != b.size:
        return {"status": "size_mismatch", "seconds": secs, "skipped": skipped}
    p = psnr(a, b)
    return {"status": "identical" if p == math.inf else "differs", "psnr": None if p == math.inf else round(p, 2),
            "seconds": secs, "skipped": skipped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true")
    ap.add_argument("--sheet", default=None)
    a = ap.parse_args()
    runs = sorted(p for p in RUNS.glob("pilot-*") if (p / "result.json").exists())
    rows = []
    for run in runs:
        r = json.loads((run / "result.json").read_text())
        if a.regen and "regen" not in r and r["status"] == "completed":
            print("regen", run.name, flush=True)
            r["regen"] = regen(run, r["limits"]["minutes"])
            (run / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
        rows.append((run, r))

    print("| 题目 | agent | 档位 | 状态 | 用时（分钟） | token | 看图 | 复现 |")
    print("|---|---|---|---|---|---|---|---|")
    for run, r in sorted(rows, key=lambda x: (x[1]["task_id"], x[1]["agent"], x[1]["tier"])):
        g = r.get("regen") or {}
        rg = {"identical": "逐像素一致", "differs": f"不一致（PSNR {g.get('psnr')} dB）"}.get(g.get("status"), g.get("status", "未检查"))
        print(f"| {r['task_id']} | {r['agent']} | {r['tier']} | {r['status']} | {r['minutes']} | "
              f"{r['budget_tokens']:,} | {r['image_views']} | {rg} |")

    if a.sheet:
        from PIL import Image, ImageDraw
        done = [(run, r) for run, r in rows if (run / "workspace" / "out" / "final.png").exists()]
        cols, w, h = 3, 512, 360
        sheet = Image.new("RGB", (cols * w, ((len(done) + cols - 1) // cols) * (h + 24)), "white")
        d = ImageDraw.Draw(sheet)
        for i, (run, r) in enumerate(sorted(done, key=lambda x: (x[1]["task_id"], x[1]["agent"], x[1]["tier"]))):
            im = Image.open(run / "workspace" / "out" / "final.png").convert("RGB")
            im.thumbnail((w - 8, h - 8))
            x, y = (i % cols) * w, (i // cols) * (h + 24)
            sheet.paste(im, (x + 4, y + 24))
            d.text((x + 4, y + 6), f"{r['task_id']} {r['agent']} {r['tier']}", fill="black")
        sheet.save(a.sheet, quality=85)
        print("sheet:", a.sheet)


if __name__ == "__main__":
    main()
