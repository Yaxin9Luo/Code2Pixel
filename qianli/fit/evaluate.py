"""评测拟合结果：取前 N 个形状渲染、打分（SSIM / PSNR），写出 SVG，
并和同样字节数的 JPEG / WebP 比较。

用法: python3 evaluate.py target.png shapes.json outdir
"""
import argparse
import gzip
import io
import json
import os
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from fit import A, raster

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def chrome_render(svg_path, W, H, out_png, profile):
    # macOS 上 headless Chrome 截完图有时不退出：等截图文件写完就结束进程
    if os.path.exists(out_png):
        os.remove(out_png)
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                          f"--user-data-dir={profile}", f"--window-size={W},{H}", f"--screenshot={out_png}",
                          "file://" + os.path.abspath(svg_path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last, t0 = -1, time.time()
    while time.time() - t0 < 300:
        time.sleep(1)
        size = os.path.getsize(out_png) if os.path.exists(out_png) else -1
        if size > 0 and size == last:
            break
        last = size
    p.terminate()
    p.wait(timeout=30)
    return np.asarray(Image.open(out_png).convert("RGB"), dtype=np.float64) / 255


LUMA = np.array([0.299, 0.587, 0.114])


def ssim(a, b):
    """Wang et al. 2004 的 SSIM，在亮度通道上算，高斯窗 σ=1.5。输入 [0,1] 的 RGB。"""
    ya, yb = a @ LUMA * 255, b @ LUMA * 255
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2

    def g(z):
        return gaussian_filter(z, 1.5, truncate=3.5)

    m1, m2 = g(ya), g(yb)
    s11, s22, s12 = g(ya * ya) - m1 ** 2, g(yb * yb) - m2 ** 2, g(ya * yb) - m1 * m2
    return float((((2 * m1 * m2 + c1) * (2 * s12 + c2)) / ((m1 ** 2 + m2 ** 2 + c1) * (s11 + s22 + c2))).mean())


def psnr(a, b):
    return float(10 * np.log10(1 / ((a - b) ** 2).mean()))


def sequence(J):
    return [(s[0], s[1]) for s in J["stage1"]] + [(s[0], s[1]) for s in J["stage2"]]


def render(J, Ns):
    """按顺序画形状，在每个 N 处存一张快照。和拟合时用的是同一个光栅化函数。"""
    W, H = J["W"], J["H"]
    C = np.empty((H, W, 3))
    C[:] = np.array(J["bg"]) / 255
    want, out = set(Ns), {}
    if 0 in want:
        out[0] = C.copy()
    for i, (tri, col) in enumerate(sequence(J), 1):
        r = raster(np.array(tri, np.float64), 0, W, H)
        if r is not None:
            i0, i1, j0, j1, m = r
            sub = C[i0:i1, j0:j1]
            sub[m] = (1 - A) * sub[m] + A * np.array(col) / 255
        if i in want:
            out[i] = C.copy()
    return out


def to_svg(J, n):
    W, H = J["W"], J["H"]
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
             f'<rect width="{W}" height="{H}" fill="#%02x%02x%02x"/>' % tuple(J["bg"]),
             f'<g fill-opacity="{A:g}">']
    for tri, col in sequence(J)[:n]:
        lines.append('<path fill="#%02x%02x%02x" d="M%d %d %d %d %d %dz"/>' % (*col, *tri))
    lines.append("</g></svg>")
    return "\n".join(lines) + "\n"


def codec_best(T, img, budget, fmt):
    """在字节预算内，试不同缩放比例和质量，取 SSIM 最高的一档。"""
    W, H = img.size
    best = None
    for sc in [1, 0.7, 0.5, 0.35, 0.25, 0.18, 0.125, 0.09, 0.0625, 0.045, 0.03]:
        small = img if sc == 1 else img.resize((max(8, round(W * sc)), max(2, round(H * sc))), Image.LANCZOS)
        lo, hi, got = 1, 95, None
        while lo <= hi:
            q = (lo + hi) // 2
            buf = io.BytesIO()
            if fmt == "JPEG":
                small.save(buf, "JPEG", quality=q, optimize=True)
            else:
                small.save(buf, "WEBP", quality=q, method=6)
            if buf.tell() <= budget:
                got, lo = (q, buf.getvalue()), q + 1
            else:
                hi = q - 1
        if got is None:
            continue
        dec = Image.open(io.BytesIO(got[1])).convert("RGB").resize((W, H), Image.BICUBIC)
        arr = np.asarray(dec, dtype=np.float64) / 255
        s = ssim(arr, T)
        if best is None or s > best["ssim"]:
            best = {"scale": sc, "quality": got[0], "bytes": len(got[1]), "ssim": s, "psnr": psnr(arr, T),
                    "img": dec}
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("shapes")
    ap.add_argument("outdir")
    ap.add_argument("--ns", default="10,30,100,300,1000,3000,10000,20000")
    ap.add_argument("--magick", default="", help="逗号分隔的 N：用 ImageMagick 渲染对应 SVG 复核分数")
    ap.add_argument("--no-chrome", action="store_true", help="不用 Chrome 渲染（正式分数默认来自 Chrome）")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    img = Image.open(a.target).convert("RGB")
    T = np.asarray(img, dtype=np.float64) / 255
    J = json.load(open(a.shapes))
    total = len(J["stage1"]) + len(J["stage2"])
    Ns = sorted({min(int(n), total) for n in a.ns.split(",")})
    snaps = render(J, Ns)
    profile = tempfile.mkdtemp(prefix="chrome-profile-")

    rows = []
    for n in Ns:
        svg = to_svg(J, n)
        raw = svg.encode()
        gz = gzip.compress(raw, 9)
        path = os.path.join(a.outdir, f"tri_{n}.svg")
        open(path, "wb").write(raw)
        Image.fromarray(np.round(snaps[n] * 255).astype(np.uint8)).save(os.path.join(a.outdir, f"tri_{n}.png"))
        row = {"n": n, "svg_bytes": len(raw), "svgz_bytes": len(gz),
               "ssim_internal": ssim(snaps[n], T), "psnr_internal": psnr(snaps[n], T)}
        if not a.no_chrome:
            R = chrome_render(path, J["W"], J["H"], path[:-4] + "_chrome.png", profile)
            row["ssim"], row["psnr"] = ssim(R, T), psnr(R, T)
        for fmt in ["JPEG", "WEBP"]:
            b = codec_best(T, img, len(gz), fmt)
            if b:
                b["img"].save(os.path.join(a.outdir, f"{fmt.lower()}_at_{n}.png"))
                row[fmt.lower()] = {k: v for k, v in b.items() if k != "img"}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    for n in [int(x) for x in a.magick.split(",") if x]:
        n = min(n, total)
        src = os.path.join(a.outdir, f"tri_{n}.svg")
        dst = os.path.join(a.outdir, f"tri_{n}_magick.png")
        subprocess.run(["magick", "-background", "none", src, "-alpha", "remove", dst], check=True)
        R = np.asarray(Image.open(dst).convert("RGB").resize(img.size), dtype=np.float64) / 255
        for row in rows:
            if row["n"] == n:
                row["magick"] = {"ssim": ssim(R, T), "psnr": psnr(R, T)}
                print("magick check", n, row["magick"], flush=True)

    json.dump({"target": a.target, "W": J["W"], "H": J["H"], "fit_seconds": J["seconds"], "rows": rows},
              open(os.path.join(a.outdir, "results.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
