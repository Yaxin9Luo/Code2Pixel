"""出图：相似度-字节数曲线、整卷对比、局部对比。

用法: python3 plot.py   （需先跑完 fit.py、evaluate.py，并用 chrome_check.py 渲染过手写 SVG）
"""
import gzip
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.ticker import FixedLocator, NullLocator
from PIL import Image, ImageDraw, ImageFont

from evaluate import psnr, ssim

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()

SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
C_TRI, C_JPEG, C_WEBP, C_HAND = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"

T = np.asarray(Image.open("target.png").convert("RGB"), dtype=np.float64) / 255
R = json.load(open("eval/results.json"))["rows"]

hand = []
for v in [1, 2]:
    svg = open(f"b2_handwritten_v{v}.svg", "rb").read()
    img = np.asarray(Image.open(f"b2_handwritten_v{v}_chrome.png").convert("RGB"), dtype=np.float64) / 255
    hand.append({"v": v, "svg_bytes": len(svg), "svgz_bytes": len(gzip.compress(svg, 9)),
                 "ssim": ssim(img, T), "psnr": psnr(img, T)})
json.dump(hand, open("b2_results.json", "w"), indent=1)


def codec_points(key):
    pts = {}
    for r in R:
        c = r.get(key)
        if c:
            pts[c["bytes"]] = c
    return [pts[b] for b in sorted(pts)]


def human(b):
    return f"{b / 1e6:.0f}MB" if b >= 1e6 else (f"{b / 1e3:.0f}KB" if b >= 1e3 else f"{b:.0f}B")


# ---------- 曲线图：两张小图，同一横轴，不用双纵轴 ----------
fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), dpi=160, facecolor=SURFACE)
for ax, metric, title, ylim in [(axes[0], "ssim", "SSIM（越高越像原图）", (0.64, 1.0)),
                                (axes[1], "psnr", "PSNR（dB，越高越像原图）", (17, 40))]:
    ax.set_facecolor(SURFACE)
    series = [("三角形 SVG（优化器拟合）", C_TRI, [r["svgz_bytes"] for r in R], [r[metric] for r in R]),
              ("JPEG", C_JPEG, [c["bytes"] for c in codec_points("jpeg")], [c[metric] for c in codec_points("jpeg")]),
              ("WebP", C_WEBP, [c["bytes"] for c in codec_points("webp")], [c[metric] for c in codec_points("webp")])]
    for name, col, xs, ys in series:
        ax.plot(xs, ys, color=col, lw=2, solid_capstyle="round", solid_joinstyle="round", label=name, zorder=3)
        ax.plot(xs, ys, "o", ms=6.5, color=col, mec=SURFACE, mew=1.5, zorder=4)
    hx, hy = [h["svgz_bytes"] for h in hand], [h[metric] for h in hand]
    ax.plot(hx, hy, color=C_HAND, lw=2, zorder=3)
    ax.plot(hx, hy, "D", ms=7, color=C_HAND, mec=SURFACE, mew=1.5, zorder=4, label="手写 SVG（模型看图目测）")
    for h in hand:
        ax.annotate(f"手写 v{h['v']}", (h["svgz_bytes"], h[metric]), xytext=(8, -4 if h["v"] == 1 else 4),
                    textcoords="offset points", fontsize=9, color=INK2, va="center")
    ax.set_xscale("log")
    ax.xaxis.set_major_locator(FixedLocator([300, 1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([human(v) for v in [300, 1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6]])
    ax.set_xlim(250, 1.2e6)
    ax.set_ylim(*ylim)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)
    ax.set_xlabel("文件大小（gzip 压缩后，对数刻度）", fontsize=9.5, color=INK2)
    # 端点直接标注，补充图例
    last = R[-1]
    ax.annotate(f"{last['n']:,} 个三角形", (last["svgz_bytes"], last[metric]),
                xytext=(3.3e5, 0.925) if metric == "ssim" else (5.2e5, 31.6), textcoords="data", fontsize=9,
                color=INK2, ha="center", va="center",
                arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8, "shrinkA": 4, "shrinkB": 5})
    ax.annotate("JPEG/WebP 到 q95 封顶", (codec_points("jpeg")[-1]["bytes"], codec_points("jpeg")[-1][metric]),
                xytext=(-8, 10), textcoords="offset points", fontsize=9, color=INK2, ha="right")
axes[0].legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK2)
fig.suptitle("同样的字节数，谁更像原画？（目标：《千里江山图》画心缩到 5612×240）", x=0.01, ha="left", fontsize=13,
             color=INK)
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig("chart.png", facecolor=SURFACE)

# ---------- 整卷对比 ----------
lab_font = ImageFont.truetype(FONT, 22)
rows = [("原图（Wikimedia Commons 扫描，画心部分）", "target.png")]
for n in [1000, 10000, R[-1]["n"]]:
    r = next(x for x in R if x["n"] == n)
    rows.append((f"{n:,} 个三角形 · SVG {human(r['svg_bytes'])} · SSIM {r['ssim']:.3f} · PSNR {r['psnr']:.1f}",
                 f"eval/tri_{n}_chrome.png"))
h2 = hand[-1]
rows.append((f"手写 SVG 第 2 版（目测） · {human(h2['svg_bytes'])} · SSIM {h2['ssim']:.3f} · PSNR {h2['psnr']:.1f}",
             "b2_handwritten_v2_chrome.png"))
Wd = 2806
strip_h = 120
out = Image.new("RGB", (Wd + 40, len(rows) * (strip_h + 44) + 20), SURFACE)
d = ImageDraw.Draw(out)
for i, (lab, p) in enumerate(rows):
    y = 20 + i * (strip_h + 44)
    d.text((20, y), lab, fill=INK, font=lab_font)
    out.paste(Image.open(p).convert("RGB").resize((Wd, strip_h), Image.LANCZOS), (20, y + 32))
out.save("overview.png")

# ---------- 局部对比（桥附近，放大 2 倍） ----------
x0, x1 = 3650, 4250
r1k = next(x for x in R if x["n"] == 1000)
panels = [("原图", "target.png"),
          (f"手写 v2 · {human(h2['svg_bytes'])}", "b2_handwritten_v2_chrome.png"),
          (f"1,000 个三角形 · {human(r1k['svg_bytes'])}", "eval/tri_1000_chrome.png"),
          (f"JPEG · {human(r1k['jpeg']['bytes'])}（与 1,000 个三角形 gzip 后同大小）", "eval/jpeg_at_1000.png"),
          ("10,000 个三角形", "eval/tri_10000_chrome.png"),
          (f"{R[-1]['n']:,} 个三角形", f"eval/tri_{R[-1]['n']}_chrome.png")]
S = 2
w, h = (x1 - x0) * S, 240 * S
out = Image.new("RGB", (w * 2 + 30, (h + 44) * 3 + 10), SURFACE)
d = ImageDraw.Draw(out)
for k, (lab, p) in enumerate(panels):
    im = Image.open(p).convert("RGB").crop((x0, 0, x1, 240)).resize((w, h), Image.LANCZOS)
    cx, cy = 10 + (k % 2) * (w + 10), 10 + (k // 2) * (h + 44)
    d.text((cx, cy), lab, fill=INK, font=lab_font)
    out.paste(im, (cx, cy + 34))
out.save("detail.png")
print(json.dumps(hand, ensure_ascii=False))
