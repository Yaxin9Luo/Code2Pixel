"""出 autoresearch 的总结图：实验进展、用时-质量曲线、新旧对比图。

用法: python3 report.py   （需要 results.tsv、sweep.tsv）
"""
import csv
import glob
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
C_NEW, C_OLD, C_DIS = "#2a78d6", "#eb6834", "#c3c2b7"


def style(ax, title):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10)


rows = list(csv.DictReader(open(os.path.join(HERE, "results.tsv")), delimiter="\t"))
rows = [r for r in rows if r["status"] in ("keep", "discard")]
ids = np.array([int(r["id"]) for r in rows])
score = np.array([float(r["score"]) for r in rows])
secs = np.array([float(r["fit_s"]) for r in rows])
keep = np.array([r["status"] == "keep" for r in rows])
best = np.maximum.accumulate(np.where(keep, score, 0))

# ---------- 图 1：实验进展（两张小图，不用双纵轴） ----------
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), dpi=160, facecolor=SURFACE)
ax = axes[0]
style(ax, "每次实验的分数（两档预算 SSIM 平均）")
ax.plot(ids[~keep], score[~keep], "o", ms=6, color=C_DIS, mec=SURFACE, mew=1.5, label="不保留（自动回退）", zorder=3)
ax.plot(ids[keep], score[keep], "o", ms=7, color=C_NEW, mec=SURFACE, mew=1.5, label="保留", zorder=4)
ax.step(ids, best, where="post", color=C_NEW, lw=2, zorder=2, label="当前最好")
notes = {2: ("加大搜索", (8, -4)), 7: ("相对坐标编码", (-8, 14)), 10: ("颜色量化", (-6, 12)),
         15: ("亮度加权", (8, -4)), 17: ("几何回拟合", (8, -14)), 35: ("覆盖率渲染模型", (-8, 10)),
         40: ("组合小改进", (-8, 12)), 44: ("删减再补", (6, 14))}
for i, (t, off) in notes.items():
    k = np.where(ids == i)[0]
    if len(k):
        ax.annotate(t, (i, score[k[0]]), xytext=off, textcoords="offset points", fontsize=9, color=INK2,
                    ha="right" if off[0] < 0 else "left", va="center")
ax.set_xlabel("实验编号", fontsize=9.5, color=INK2)
ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK2)
ax = axes[1]
style(ax, "每次实验的用时（秒，限时 60）")
ax.plot(ids[~keep], secs[~keep], "o", ms=6, color=C_DIS, mec=SURFACE, mew=1.5, zorder=3)
ax.plot(ids[keep], secs[keep], "o", ms=7, color=C_NEW, mec=SURFACE, mew=1.5, zorder=4)
ax.annotate("C 内核", (1, secs[ids == 1][0]), xytext=(6, 4), textcoords="offset points", fontsize=9, color=INK2)
ax.annotate("行前缀和", (33, secs[ids == 33][0]), xytext=(6, -10), textcoords="offset points", fontsize=9, color=INK2)
ax.set_ylim(0, 62)
ax.set_xlabel("实验编号", fontsize=9.5, color=INK2)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "progress.png"), facecolor=SURFACE)

# ---------- 图 2：用时-质量曲线 ----------
sw = list(csv.DictReader(open(os.path.join(HERE, "sweep.tsv")), delimiter="\t"))


def agg(algo, img):
    pts = {}
    for r in sw:
        if r["algo"] == algo and r["image"] == img:
            pts.setdefault(r["setting"], []).append(r)
    out = []
    for k, rs in pts.items():
        if k == "effort=0.125":  # 力度这么低时用时基本是固定开销，受计时波动影响大，图里不画（数据保留在 sweep.tsv）
            continue
        s = np.mean([(float(r["ssim_16k"]) + float(r["ssim_160k"])) / 2 for r in rs])
        t = np.mean([float(r["seconds"]) for r in rs])
        out.append((t, s, k))
    return sorted(out, key=lambda z: float(z[2].split("=")[1]))  # 按力度/限时排序，不按实测用时


fin = list(csv.DictReader(open(os.path.join(HERE, "sweep_final.tsv")), delimiter="\t"))


def agg_final(img):
    pts = {}
    for r in fin:
        if r["image"] == img:
            pts.setdefault(float(r["effort"]), []).append(r)
    return sorted((np.mean([float(r["seconds"]) for r in rs]),
                   np.mean([(float(r["ssim_16k"]) + float(r["ssim_160k"])) / 2 for r in rs]), f"力度 {e:g}")
                  for e, rs in pts.items())


C_MID = "#1baf7a"
fig, ax = plt.subplots(figsize=(8, 5), dpi=160, facecolor=SURFACE)
style(ax, "用时 vs 质量（《千里江山图》，两个种子取平均）")
series = [("最终版", C_NEW, agg_final("target.png")),
          ("第一轮结束时的版本", C_MID, [p for p in agg("新算法", "target.png")]),
          ("旧算法（fit.py 移植）", C_OLD, agg("旧算法", "target.png"))]
for name, col, pts in series:
    ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=col, lw=2, ms=7, mec=SURFACE, mew=1.5, label=name)
for t, sv, k in series[0][2]:
    ax.annotate(k, (t, sv), xytext=(0, 10), textcoords="offset points", fontsize=8.5, color=INK2, ha="center")
for t, sv, k in series[2][2]:
    ax.annotate(k.replace("time=", "限时 ") + " 秒", (t, sv), xytext=(0, -14), textcoords="offset points", fontsize=8.5,
                color=INK2, ha="center")
ax.set_xscale("log")
from matplotlib.ticker import FixedLocator, NullLocator  # noqa: E402
ax.xaxis.set_major_locator(FixedLocator([8, 10, 15, 20, 30, 45, 60]))
ax.xaxis.set_minor_locator(NullLocator())
ax.set_xticklabels(["8", "10", "15", "20", "30", "45", "60"])
ax.set_xlim(7, 75)
ax.set_xlabel("单次用时（秒，对数刻度）", fontsize=9.5, color=INK2)
ax.set_ylabel("SSIM（两档预算平均）", fontsize=9.5, color=INK2)
ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK2)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "speed_quality.png"), facecolor=SURFACE)

# ---------- 图 3：新旧对比（桥附近，160KB 与 16KB） ----------
lab = ImageFont.truetype(FONT, 20)
base_dir = sorted(glob.glob("/var/folders/*/*/T/exp000-63fylg_z"))
panels = [("原图", os.path.join(os.path.dirname(HERE), "target.png"))]
if base_dir:
    panels += [("旧算法 · 160KB", os.path.join(base_dir[0], "b160000.png"))]
panels += [("新算法 · 160KB", os.path.join(HERE, "best_out", "b160000.png"))]
if base_dir:
    panels += [("旧算法 · 16KB", os.path.join(base_dir[0], "b16000.png"))]
panels += [("新算法 · 16KB", os.path.join(HERE, "best_out", "b16000.png"))]
x0, x1, S = 3650, 4250, 2
w, h = (x1 - x0) * S, 240 * S
cols = 2
nrow = (len(panels) + 1) // cols
out = Image.new("RGB", (w * cols + 30, (h + 34) * nrow + 10), SURFACE)
d = ImageDraw.Draw(out)
order = [0, None, 1, 2, 3, 4] if len(panels) == 5 else list(range(len(panels)))
for slot, k in enumerate(order):
    if k is None or k >= len(panels):
        continue
    t, p = panels[k]
    im = Image.open(p).convert("RGB").crop((x0, 0, x1, 240)).resize((w, h), Image.LANCZOS)
    cx, cy = 10 + (slot % cols) * (w + 10), 10 + (slot // cols) * (h + 34)
    d.text((cx, cy), t, fill=INK, font=lab)
    out.paste(im, (cx, cy + 30))
out.save(os.path.join(HERE, "before_after.png"))
print("saved progress.png speed_quality.png before_after.png")
