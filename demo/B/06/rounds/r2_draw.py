#!/usr/bin/env python3
"""B06 窗边看书的老人。

素材：一张授权照片（Shixart1985 拍的老人在窗前沙发上叼着烟斗看书，CC BY 2.0），存在 refs/。
画法（自己写的水彩渲染，只借用 stylize 里的 L0 平滑、分形噪声、纸纹、XDoG 这些底层函数）：
  1. 窗帘后面的窗子"找"出来：窗帘区域亮部色阶拉开，两扇窗格留纸白，窗框和窗下墙面成淡灰紫；
  2. 概括：L0 平滑成平涂色块，画面中心（脸、烟斗、书、手）概括得轻，四周（花靠垫、毯子、椅子）概括得重；
  3. 水彩颜料模型（Bousseau 2006）：色块边界积色、大尺度浓淡不匀、颜料颗粒；边界随噪声扭动；
  4. 透明罩染：颜色换成吸光度叠在纸上，最亮处就是纸白；
  5. 中心区域加淡淡的铅笔底稿线，四周不规则留白。
用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys
import time

sys.dont_write_bytecode = True                      # 不在 stylize/ 下写 __pycache__
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
from scipy import ndimage as ndi                    # noqa: E402
import stylize as S                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "refs", "elderly_man_reading_pipe_window_shixart1985.jpg")
W = 1500
SEED = 3
PAPER = np.array([0.975, 0.962, 0.930], np.float32)


def load():
    im = Image.open(REF).convert("RGB")
    im = im.resize((W, round(W * im.height / im.width)), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def background_mask(rgb):
    """窗帘（窗子）区域：上半部分、很亮、和画面上边连通的一片。"""
    h, w = rgb.shape[:2]
    yy = np.mgrid[0:h, 0:w][0]
    Ls = ndi.gaussian_filter(rgb @ S.LUMA, 2)
    cand = (Ls > 0.82) & (yy < 540)
    lbl, _ = ndi.label(cand)
    keep = [k for k in np.unique(lbl[0]) if k != 0]
    bg = np.isin(lbl, keep)
    bg = ndi.binary_opening(ndi.binary_closing(bg, iterations=2), iterations=1)
    return ndi.gaussian_filter(bg.astype(np.float32), 1.5)


def window_structure(rgb, bg):
    """窗帘区域亮部色阶拉开：窗格仍是最亮（留白），窗框、窗下墙面露出淡灰；暗处偏冷、亮处略暖。"""
    L = rgb @ S.LUMA
    st = np.clip((L - 0.80) / 0.20, 0, 1)
    Ln = 0.66 + 0.34 * st ** 0.9
    out = np.clip(rgb * (Ln / np.maximum(L, 1e-3))[..., None], 0, 1)
    cool = np.array([0.93, 0.95, 1.04], np.float32)            # 窗框、窗下墙面：灰紫偏冷
    warm = np.array([1.02, 1.0, 0.95], np.float32)             # 窗格：一点暖的阳光
    t = st[..., None]
    out = np.clip(out * (cool * (1 - t) + warm * t), 0, 1)
    return rgb * (1 - bg[..., None]) + out * bg[..., None]


def focus_map(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    f = np.exp(-(((xx - 790) / 400) ** 2 + ((yy - 450) / 360) ** 2))
    return np.clip(1.5 * f, 0, 1)


def abstract(rgb, focus, bg):
    """L0 概括：中心轻、四周重；窗帘区域用中等强度（保留窗框和一点花边）。"""
    fine = S.l0_smooth(rgb, 0.006)
    coarse = S.l0_smooth(rgb, 0.04)
    k = np.clip(np.maximum(focus, 0.6 * bg), 0, 1)[..., None]
    return np.clip(fine * k + coarse * (1 - k), 0, 1)


def watercolor(A, rgb, focus, bg, seed):
    h, w = A.shape[:2]
    # 边界扭动：用低频噪声位移场重采样（窗帘区域扭得少，窗框保持直）
    amp = 2.2 * (1 - 0.7 * bg)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dy = (S.fbm(h, w, 24, 3, seed) - 0.5) * 2 * amp
    dx = (S.fbm(h, w, 24, 3, seed + 1) - 0.5) * 2 * amp
    A = np.stack([ndi.map_coordinates(A[..., c], [yy + dy, xx + dx], order=1, mode="reflect") for c in range(3)], -1)
    # 透明颜料：颜色 → 相对纸的吸光度；水彩比照片浅
    a = -np.log(np.clip(A / PAPER, 0.03, 1.0))
    a *= 0.78
    # 颜料密度：色块边界积色 + 大尺度浓淡 + 颗粒
    Lg = A @ S.LUMA
    g = ndi.gaussian_gradient_magnitude(Lg, 1.2)
    edge = np.clip(g / 0.06, 0, 1)
    d = 1 + 0.55 * edge
    d *= 1 + 0.28 * (S.fbm(h, w, 70, 4, seed + 2) - 0.5) * 2
    d *= 1 + 0.22 * (S.fbm(h, w, 2.5, 2, seed + 3) - 0.5) * 2
    a *= d[..., None]
    # 纸白：窗格最亮的地方干脆不上色
    a *= S.smoothstep(0.985, 0.94, Lg)[..., None] * 0.9 + 0.1
    # 四周不规则留白
    r = np.maximum(np.abs(xx - w / 2) / (w / 2), np.abs(yy - h / 2) / (h / 2))
    r = r + 0.22 * (S.fbm(h, w, 90, 4, seed + 12) - 0.5)
    a *= (1 - S.smoothstep(0.80, 1.0, r))[..., None]
    paper = S.paper_texture(h, w, 1.0, seed + 10, PAPER, fiber=0.25)
    out = paper * np.exp(-a)
    # 铅笔底稿：只在中心区域、不在窗帘上
    E = S.xdog(ndi.gaussian_filter(rgb @ S.LUMA, 0.6), 1.1, p=22, eps=0.55, phi=12)
    pen = (1 - E) * np.clip(focus * 1.2, 0, 1) * (1 - 0.8 * bg)
    pen = ndi.gaussian_filter(pen, 0.5)
    graphite = np.array([0.30, 0.27, 0.25], np.float32)
    out = out * (1 - 0.45 * pen[..., None]) + graphite * 0.45 * pen[..., None] * 0.3
    return np.clip(out, 0, 1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    t0 = time.time()
    rgb = load()
    h, w = rgb.shape[:2]
    bg = background_mask(rgb)
    rgb = window_structure(rgb, bg)
    focus = focus_map(h, w)
    A = abstract(rgb, focus, bg)
    out = watercolor(A, rgb, focus, bg, SEED)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(out_path)
    print(out_path, (w, h), "bg frac = %.3f" % float(bg.mean()), "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
