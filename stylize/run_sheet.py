"""把 8 张测试照片都套上某种风格，拼成对照图（每张：上原图、下结果），并记录耗时。

用法: python3 run_sheet.py ink [--size 1024] [--tag v1]
"""
import argparse
import glob
import os
import sys
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import stylize  # noqa: E402
from evaluate import chrome_render  # noqa: E402
import numpy as np  # noqa: E402

FONT = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 18)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    outdir = os.path.join(HERE, "out", a.style, a.tag)
    os.makedirs(outdir, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="chrome-profile-")
    tiles, times = [], []
    for p in sorted(glob.glob(os.path.join(HERE, "photos", "*.jpg"))):
        name = os.path.splitext(os.path.basename(p))[0]
        src = Image.open(p).convert("RGB")
        t0 = time.time()
        res = stylize.stylize(src, a.style, size=a.size)
        times.append(time.time() - t0)
        if isinstance(res, str):
            sp = os.path.join(outdir, name + ".svg")
            open(sp, "w").write(res)
            w, h = [int(float(v)) for v in res.split('width="')[1].split('"')[0:1] + res.split('height="')[1].split('"')[0:1]]
            arr = chrome_render(sp, w, h, os.path.join(outdir, name + ".png"), profile)
            res = Image.fromarray((arr * 255).astype(np.uint8))
        else:
            res.save(os.path.join(outdir, name + ".png"))
        k = a.size / max(src.size)
        if k < 1:
            src = src.resize((round(src.width * k), round(src.height * k)), Image.LANCZOS)
        tiles.append((name, src, res))
    # 对照图：4 列，每格上原图下结果，高度统一 300
    H = 300
    cells = []
    for name, src, res in tiles:
        a1 = src.resize((int(src.width * H / src.height), H))
        b1 = res.resize((int(res.width * H / res.height), H))
        cell = Image.new("RGB", (max(a1.width, b1.width), 2 * H + 36), "white")
        ImageDraw.Draw(cell).text((4, 2), name, fill="black", font=FONT)
        cell.paste(a1, (0, 28))
        cell.paste(b1, (0, 32 + H))
        cells.append(cell)
    rows = [cells[i:i + 4] for i in range(0, len(cells), 4)]
    Wd = max(sum(c.width for c in r) + 12 * (len(r) + 1) for r in rows)
    sheet = Image.new("RGB", (Wd, len(rows) * (2 * H + 48) + 12), "white")
    y = 12
    for r in rows:
        x = 12
        for c in r:
            sheet.paste(c, (x, y))
            x += c.width + 12
        y += 2 * H + 48
    path = os.path.join(outdir, "sheet.png")
    sheet.save(path)
    print(f"{a.style} {a.tag}: 每张平均 {np.mean(times):.2f}s（最慢 {max(times):.2f}s），对照图 {path}")


if __name__ == "__main__":
    main()
