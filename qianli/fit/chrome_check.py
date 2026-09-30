"""用 Chrome（headless，独立临时配置目录）把 SVG 按 1:1 渲染成 PNG，再和目标图打分。
这样分数就是"浏览器打开这份代码看到的图"的分数，而不是拟合程序内部的估计。

用法: python3 chrome_check.py target.png a.svg [b.svg ...]
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

from evaluate import chrome_render, psnr, ssim

def main():
    target = Image.open(sys.argv[1]).convert("RGB")
    T = np.asarray(target, dtype=np.float64) / 255
    H, W = T.shape[:2]
    profile = tempfile.mkdtemp(prefix="chrome-profile-")
    for svg in sys.argv[2:]:
        out = svg[:-4] + "_chrome.png"
        R = chrome_render(svg, W, H, out, profile)
        if R.shape != T.shape:
            print(svg, "size mismatch", R.shape)
            continue
        print(f"{os.path.basename(svg)}: SSIM={ssim(R, T):.4f} PSNR={psnr(R, T):.2f}", flush=True)


if __name__ == "__main__":
    main()
