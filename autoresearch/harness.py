"""autoresearch 的固定评分脚本。实验期间不改这个文件。

用法: python3 harness.py "这次改了什么" [--seed 0] [--target ../target.png] [--no-decide]

流程：存快照 → 限时运行 solver.py → 检查字节预算和 SVG 合规 → Chrome 渲染打分
     → 和当前最好版本比较，决定保留或回退 → 追加一行到 results.tsv。
"""
import argparse
import csv
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from evaluate import chrome_render, psnr, ssim  # noqa: E402

TIME_LIMIT = 60
BUDGETS = [16000, 160000]
THRESH = 0.002           # 保留阈值（平均 SSIM）。baseline 三个种子在 0.757–0.764 之间，所以每次跑两个种子取平均
SEEDS = [0, 1]
SPEEDUP = 0.75           # 分数持平（不低于最好版本 0.001 以内）且用时不超过最好版本的 75%，也算进步
PSNR_GUARD = 0.3         # 平均 PSNR 最多允许比最好版本低这么多
FORBIDDEN = [r"<image", r"data:", r"<script", r"foreignObject", r"href\s*=\s*[\"'](?!#)", r"@import", r"url\((?!#)"]
FIELDS = ["id", "time", "score", "ssim_16k", "ssim_160k", "psnr_16k", "psnr_160k", "fit_s", "shapes", "status",
          "desc"]


def run_once(solver, target, seed, out):
    """限时跑一次 solver，返回 (状态, 用时, solver 报告)。"""
    t0 = time.time()
    status, info = "ok", {}
    try:
        p = subprocess.run([sys.executable, solver, target, out, "--time", str(TIME_LIMIT),
                            "--budgets", ",".join(map(str, BUDGETS)), "--seed", str(seed)],
                           capture_output=True, text=True, timeout=TIME_LIMIT + 30, cwd=HERE)
        fit_s = time.time() - t0
        open(os.path.join(out, "solver.log"), "w").write(p.stdout + "\n" + p.stderr)
        if p.returncode != 0:
            status = "crash"
            print(p.stderr[-3000:])
        elif fit_s > TIME_LIMIT + 10:
            status = "overtime"
        for line in p.stdout.splitlines():
            if line.startswith("RESULT "):
                info = json.loads(line[7:])
    except subprocess.TimeoutExpired:
        fit_s, status = time.time() - t0, "overtime"
    return status, fit_s, info


def score_once(out, T, profile):
    """检查字节预算和合规，Chrome 渲染打分。返回 (状态, {预算: (ssim, psnr, gz)})。"""
    H, W = T.shape[:2]
    scores = {}
    for b in BUDGETS:
        path = os.path.join(out, f"b{b}.svg")
        if not os.path.exists(path):
            return f"missing b{b}", scores
        raw = open(path, "rb").read()
        gz = len(gzip.compress(raw, 9))
        text = raw.decode("utf-8", "replace")
        bad = [f for f in FORBIDDEN if re.search(f, text)]
        if gz > b or bad:
            return f"invalid b{b} gz={gz} bad={bad}", scores
        R = chrome_render(path, W, H, os.path.join(out, f"b{b}.png"), profile)
        if R.shape != T.shape:
            return f"render size {R.shape}", scores
        scores[b] = (ssim(R, T), psnr(R, T), gz)
    return "ok", scores


def rows():
    path = os.path.join(HERE, "results.tsv")
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path), delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("desc")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--target", default=os.path.join(os.path.dirname(HERE), "target.png"))
    ap.add_argument("--no-decide", action="store_true", help="只打分，不参与保留/回退（用于测噪声、测泛化）")
    ap.add_argument("--one-seed", action="store_true", help="只跑一个种子（测泛化、测时间曲线时用）")
    a = ap.parse_args()

    prev = rows()
    exp_id = f"{len(prev):03d}"
    solver = os.path.join(HERE, "solver.py")
    shutil.copy(solver, os.path.join(HERE, "snapshots", f"{exp_id}.py"))
    core = os.path.join(HERE, "core.c")
    shutil.copy(core, os.path.join(HERE, "snapshots", f"{exp_id}_core.c"))
    out = tempfile.mkdtemp(prefix=f"exp{exp_id}-")

    T = np.asarray(Image.open(a.target).convert("RGB"), dtype=np.float64) / 255
    profile = tempfile.mkdtemp(prefix="chrome-profile-")
    seeds = [a.seed] if a.one_seed else [a.seed + k for k in SEEDS]
    status, runs = "ok", []
    for sd in seeds:
        o = out if sd == seeds[0] else tempfile.mkdtemp(prefix=f"exp{exp_id}-s{sd}-")
        st, fit_s, info = run_once(solver, a.target, sd, o)
        if st == "ok":
            st, sc = score_once(o, T, profile)
        if st != "ok":
            status = st
            break
        runs.append((fit_s, info, sc))
    if status == "ok":
        scores = {b: tuple(float(np.mean([r[2][b][k] for r in runs])) for k in range(3)) for b in BUDGETS}
        fit_s = float(np.mean([r[0] for r in runs]))
        info = {"shapes": {str(b): [r[1].get("shapes", {}).get(str(b)) for r in runs] for b in BUDGETS}}
        score = float(np.mean([scores[b][0] for b in BUDGETS]))
        mean_psnr = float(np.mean([scores[b][1] for b in BUDGETS]))
    else:
        scores, fit_s, info, score, mean_psnr = {}, 0.0, {}, 0.0, 0.0

    kept = [r for r in prev if r["status"] == "keep"]
    best = max(kept, key=lambda r: float(r["score"])) if kept else None  # 历史最高分
    ref = kept[-1] if kept else None                                       # 当前在用的版本（最近一次保留）
    if a.no_decide:
        decision = "measure"
    elif status != "ok":
        decision = status
    elif best is None:
        decision = "keep"
    else:
        ref_psnr = (float(ref["psnr_16k"]) + float(ref["psnr_160k"])) / 2
        better = score > float(best["score"]) + THRESH and mean_psnr >= ref_psnr - PSNR_GUARD
        faster = (score >= float(best["score"]) - 0.001 and mean_psnr >= ref_psnr - 0.1
                  and fit_s <= SPEEDUP * float(ref["fit_s"]))
        decision = "keep" if (better or faster) else "discard"

    if decision == "keep":
        shutil.copy(solver, os.path.join(HERE, "best_solver.py"))
        shutil.copy(core, os.path.join(HERE, "best_core.c"))
        shutil.copytree(out, os.path.join(HERE, "best_out"), dirs_exist_ok=True)
    elif decision != "measure" and os.path.exists(os.path.join(HERE, "best_solver.py")):
        shutil.copy(os.path.join(HERE, "best_solver.py"), solver)  # 回退
        if os.path.exists(os.path.join(HERE, "best_core.c")):
            shutil.copy(os.path.join(HERE, "best_core.c"), core)

    row = {"id": exp_id, "time": time.strftime("%H:%M:%S"), "score": f"{score:.4f}",
           "ssim_16k": f"{scores[16000][0]:.4f}" if 16000 in scores else "",
           "ssim_160k": f"{scores[160000][0]:.4f}" if 160000 in scores else "",
           "psnr_16k": f"{scores[16000][1]:.2f}" if 16000 in scores else "",
           "psnr_160k": f"{scores[160000][1]:.2f}" if 160000 in scores else "",
           "fit_s": f"{fit_s:.1f}", "shapes": json.dumps(info.get("shapes", {})), "status": decision,
           "desc": a.desc}
    path = os.path.join(HERE, "results.tsv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter="\t")
        if new:
            w.writeheader()
        w.writerow(row)
    best_score = float(best["score"]) if best else float("nan")
    print(f"[{exp_id}] {decision}  score={score:.4f} (best {best_score:.4f})  "
          f"16k: SSIM {row['ssim_16k']} PSNR {row['psnr_16k']} | 160k: SSIM {row['ssim_160k']} PSNR {row['psnr_160k']} "
          f"| {fit_s:.0f}s | shapes {row['shapes']} | out {out}")


if __name__ == "__main__":
    main()
