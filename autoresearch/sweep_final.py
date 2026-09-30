"""最终版 solver 的用时-质量曲线，以及在未参与调参的图上的表现。结果写到 sweep_final.tsv。"""
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

RUNS = [("target.png", e) for e in [0.125, 0.25, 0.5, 1, 1.5]] + [("holdout.png", 1)]
with open(os.path.join(HERE, "sweep_final.tsv"), "w", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["image", "effort", "seed", "seconds", "ssim_16k", "psnr_16k", "ssim_160k", "psnr_160k"])
    for img, e in RUNS:
        target = os.path.join(os.path.dirname(HERE), img)
        T = np.asarray(Image.open(target).convert("RGB"), dtype=np.float64) / 255
        for seed in [0, 1]:
            out = tempfile.mkdtemp(prefix="final-")
            t0 = time.time()
            subprocess.run([sys.executable, os.path.join(HERE, "best_solver.py"), target, out, "--time", "60",
                            "--budgets", ",".join(map(str, BUDGETS)), "--seed", str(seed), "--effort", str(e)],
                           check=True, capture_output=True, cwd=HERE)
            secs = time.time() - t0
            st, sc = score_once(out, T, tempfile.mkdtemp(prefix="chrome-profile-"))
            row = [img, e, seed, f"{secs:.1f}"] + [f"{sc[b][k]:.4f}" if k == 0 else f"{sc[b][k]:.2f}"
                                                  for b in BUDGETS for k in (0, 1)]
            w.writerow(row)
            f.flush()
            print("\t".join(map(str, row)), flush=True)
