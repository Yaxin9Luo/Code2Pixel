"""收尾实验：新旧 solver 在不同用时/力度下的质量，以及在未参与调参的图上的表现。

用法: python3 sweep.py  （结果写到 sweep.tsv）
"""
import csv
import os
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from harness import BUDGETS, score_once  # noqa: E402

RUNS = []
for img in ["target.png"]:
    for e in [0.125, 0.25, 0.5, 1, 2]:
        RUNS.append(("新算法", img, "best_solver.py", ["--effort", str(e)], f"effort={e}"))
    for t in [15, 30, 60]:
        RUNS.append(("旧算法", img, "snapshots/000.py", [], f"time={t}"))
for img in ["holdout.png"]:
    RUNS.append(("新算法", img, "best_solver.py", ["--effort", "1"], "effort=1"))
    RUNS.append(("旧算法", img, "snapshots/000.py", [], "time=60"))

out_path = os.path.join(HERE, "sweep.tsv")
with open(out_path, "w", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["algo", "image", "setting", "seed", "seconds", "ssim_16k", "psnr_16k", "ssim_160k", "psnr_160k"])
    for algo, img, solver, extra, setting in RUNS:
        tl = int(setting.split("=")[1]) if setting.startswith("time=") else 60
        target = os.path.join(os.path.dirname(HERE), img)
        T = np.asarray(Image.open(target).convert("RGB"), dtype=np.float64) / 255
        for seed in [0, 1]:
            out = tempfile.mkdtemp(prefix="sweep-")
            t0 = time.time()
            subprocess.run([sys.executable, os.path.join(HERE, solver), target, out, "--time", str(tl),
                            "--budgets", ",".join(map(str, BUDGETS)), "--seed", str(seed)] + extra,
                           check=True, capture_output=True, cwd=HERE)
            secs = time.time() - t0
            st, sc = score_once(out, T, tempfile.mkdtemp(prefix="chrome-profile-"))
            row = [algo, img, setting, seed, f"{secs:.1f}"] + [f"{sc[b][k]:.4f}" if k == 0 else f"{sc[b][k]:.2f}"
                                                               for b in BUDGETS for k in (0, 1)]
            w.writerow(row)
            f.flush()
            print("\t".join(map(str, row)), flush=True)
