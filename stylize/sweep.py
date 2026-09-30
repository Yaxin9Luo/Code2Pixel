"""风格参数扫描：一次加载 CLIP，给多个参数变体打分（评测专用，在装了 torch/open_clip/scipy 的环境里跑）。

用法: python sweep.py ink variants.json [--size 768]
variants.json: {"变体名": {"params": {...}, "kw": {...}}, ...}
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stylize  # noqa: E402
from eval_style import Scorer  # noqa: E402
sys.path.insert(0, os.path.dirname(HERE))
from evaluate import chrome_render, ssim  # noqa: E402
import tempfile  # noqa: E402

_PROFILE = tempfile.mkdtemp(prefix="chrome-profile-")


def as_image(out):
    """风格函数可能返回 SVG 文本：用 Chrome 渲染成图。"""
    if not isinstance(out, str):
        return out
    w = int(float(out.split('width="')[1].split('"')[0]))
    h = int(float(out.split('height="')[1].split('"')[0]))
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "x.svg")
        open(sp, "w").write(out)
        arr = chrome_render(sp, w, h, os.path.join(td, "x.png"), _PROFILE)
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("variants")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--save", default="")
    ap.add_argument("--seeds", default="0", help="逗号分隔；多个种子时取平均")
    a = ap.parse_args()
    V = json.load(open(a.variants))
    sc = Scorer()
    photos = sorted(glob.glob(os.path.join(HERE, "photos", "*.jpg")))
    srcs = [(os.path.splitext(os.path.basename(p))[0], Image.open(p).convert("RGB")) for p in photos]
    print(f"{'variant':28s} style  content  aes   ssim   time   per-photo style")
    seeds = [int(x) for x in a.seeds.split(",")]
    for name, v in V.items():
        st, ct, ae, tt, per, ss = [], [], [], [], [], []
        for pn, src in srcs:
            ps = []
            for sd in seeds:
                kw = dict(v.get("kw", {}))
                kw.setdefault("seed", sd)
                t0 = time.time()
                out = stylize.STYLES[a.style](src, size=a.size, params=v.get("params"), **kw)
                tt.append(time.time() - t0)
                out = as_image(out)
                if a.save and sd == seeds[0]:
                    d = os.path.join(HERE, "out", a.style, a.save, name)
                    os.makedirs(d, exist_ok=True)
                    out.save(os.path.join(d, pn + ".png"))
                ref = src.resize(out.size, Image.LANCZOS)
                ss.append(ssim(np.asarray(out.convert("RGB"), np.float32) / 255, np.asarray(ref, np.float32) / 255))
                r = sc.score(out, a.style, src)
                st.append(r["style"]); ct.append(r["content"]); ae.append(r["aes"]); ps.append(r["style"])
            per.append(np.mean(ps))
        print(f"{name:28s} {np.mean(st):.3f}  {np.mean(ct):.3f}   {np.mean(ae):.2f}  {np.mean(ss):.3f}  {np.mean(tt):.2f}s  "
              + " ".join(f"{x:.2f}" for x in per), flush=True)


if __name__ == "__main__":
    main()
