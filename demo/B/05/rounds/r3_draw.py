#!/usr/bin/env python3
"""B05 窗台上晒太阳的橘猫：一张橘白长毛猫在窗台上晒太阳的照片做底，
用代码补画窗台、去掉窗边杂物，再加暖阳调色、从窗外斜射进来的光束、空气里的浮尘和高光泛光。

只读 refs/ 里的照片，不联网。用法：python3 draw.py [--out final.png]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
from stylize import fbm, smoothstep  # noqa: E402  程序化噪声（只 import，不改）

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 5
W = 1600
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def ref(name):
    return os.path.join(HERE, "refs", name)


def to_lin(x):
    return np.power(np.clip(x, 0, 1), 2.2)


def to_srgb(x):
    return np.power(np.clip(x, 0, 1), 1 / 2.2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "final.png"))
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)

    # ---------- 裁切：去掉左边窗帘和下方前景的深色杂物（原图 4030x2267） ----------
    src = Image.open(ref("Basking_in_the_spring_sun_(54428014640).jpg")).convert("RGB")
    X0, X1, Y0, Y1 = 130, 4030, 10, 1960                 # 原图坐标，2:1
    crop = src.crop((X0, Y0, X1, Y1))
    H = round(W * (Y1 - Y0) / (X1 - X0))
    S = W / (X1 - X0)
    img = np.asarray(crop.resize((W, H), Image.LANCZOS), np.float32) / 255
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    lum = img @ LUMA

    # ---------- 补画窗台：底部那条深色前景换成向前延伸的白色窗台 ----------
    # 每列从 y≈1650（原图）往下找第一处变暗的位置，当作深色前景的上沿
    ys = int((1745 - Y0) * S)                            # 猫身最低处在这之上（左前爪除外，那里前景更低）
    dark = (lum < 0.3) & (yy >= ys)
    run = ndi.minimum_filter1d(dark.astype(np.uint8), 9, axis=0, origin=-4).astype(bool)   # 往下连续 9 行都暗才算
    edge = np.where(run.any(0), run.argmax(0), H).astype(np.float32)
    edge = ndi.median_filter(edge, 31)
    edge = ndi.gaussian_filter1d(edge, 6)
    band = 18                                           # 取上沿以上这段窗台的颜色往下延伸
    ref_rows = np.clip((edge[None, :] - 6 - np.arange(band)[:, None]).astype(int), 0, H - 1)
    sill_col = np.stack([img[ref_rows, np.arange(W)[None, :], c].mean(0) for c in range(3)], -1)   # (W, 3)
    sill_col = ndi.gaussian_filter1d(sill_col, 25, axis=0)
    depth = np.clip(yy - edge[None, :], 0, None)          # 往前延伸的距离（像素）
    shade = 1 - 0.10 * smoothstep(0, H - edge.min(), depth)   # 越靠前越略暗（离窗远）
    grain = (fbm(H, W, 3, 2, SEED + 1) - 0.5) * 0.02
    fill = sill_col[None, :, :] * shade[..., None] + grain[..., None]
    m = smoothstep(-4, 3, yy - edge[None, :])
    img = img * (1 - m[..., None]) + fill * m[..., None]

    # 窗台前沿：最底下一道窄的阴影线，像窗台的外沿
    lip = smoothstep(H - 26, H - 12, yy)
    img = img * (1 - 0.35 * lip[..., None])

    # ---------- 去掉猫脸左边窗框上的小温度计（用上下的窗框颜色补上） ----------
    tx0, tx1, ty0, ty1 = [int(v) for v in ((80 - X0) * S, (215 - X0) * S, (1040 - Y0) * S, (1165 - Y0) * S)]
    tx0 = max(tx0, 0)
    top = img[ty0 - 6:ty0 - 1, tx0:tx1].mean(0)
    bot = img[ty1 + 1:ty1 + 6, tx0:tx1].mean(0)
    t = np.linspace(0, 1, ty1 - ty0)[:, None, None]
    patch = top[None] * (1 - t) + bot[None] * t
    pm = np.zeros((H, W), np.float32)
    pm[ty0:ty1, tx0:tx1] = 1
    pm = ndi.gaussian_filter(pm, 1.5)
    full = img.copy()
    full[ty0:ty1, tx0:tx1] = patch
    img = img * (1 - pm[..., None]) + full * pm[..., None]

    # ---------- 暖阳调色：高光偏金，暗部略冷；橘色毛再饱和一点 ----------
    lin = to_lin(img)
    L = lin @ LUMA
    warm = np.array([1.10, 1.00, 0.84], np.float32)
    cool = np.array([0.96, 0.99, 1.06], np.float32)
    k = smoothstep(0.05, 0.6, L)[..., None]
    lin = lin * (cool * (1 - k) + warm * k)
    # 窗外（玻璃里的雪景）保持偏冷：窗框内侧、猫身上方的蓝白区域
    srgb = to_srgb(lin)
    hsv_s = srgb.max(-1) - srgb.min(-1)
    orange = (srgb[..., 0] > srgb[..., 2] + 0.12) & (srgb[..., 0] >= srgb[..., 1])
    orange = ndi.gaussian_filter(orange.astype(np.float32), 1.0)
    Yv = srgb @ LUMA
    srgb = srgb + (srgb - Yv[..., None]) * (0.18 * orange)[..., None]
    lin = to_lin(srgb)

    # ---------- 光束：窗外的太阳在画面上方偏右，光从玻璃透进来往下铺 ----------
    lum2 = to_srgb(lin) @ LUMA
    glass = ((xx > (430 - X0) * S) & (xx < (3370 - X0) * S) & (yy < (1000 - Y0) * S)).astype(np.float32)
    src_light = glass * smoothstep(0.62, 0.9, lum2)          # 玻璃里的亮处才透光（猫身挡住的地方不透）
    lx, ly = 0.62 * W, -0.9 * H                             # 光源位置（画面外上方）
    n_s, decay = 64, 0.985
    acc = np.zeros((H, W), np.float32)
    wgt = 1.0
    dx, dy = (lx - xx) / n_s * 0.55, (ly - yy) / n_s * 0.55
    for i in range(n_s):
        acc += wgt * ndi.map_coordinates(src_light, [yy + dy * i, xx + dx * i], order=1, mode="constant")
        wgt *= decay
    rays = acc / n_s
    stripes = fbm(1, W, 40, 3, SEED + 2)[0]                 # 窗外树影把光切成一条条
    rays = rays * (0.55 + 0.9 * stripes[None, :] ** 1.5)
    beam_col = np.array([1.0, 0.82, 0.55], np.float32)
    lin = lin + 0.28 * rays[..., None] * beam_col

    # ---------- 浮尘：光束里亮一点的小颗粒，少数大而虚（离镜头近、失焦） ----------
    dust = np.zeros((H, W), np.float32)
    n = 230
    px = rng.uniform(0, W, n)
    py = rng.uniform(0, H * 0.85, n)
    big = rng.random(n) < 0.18
    rad = np.where(big, rng.uniform(5, 11, n), rng.uniform(0.8, 2.0, n))
    amp = np.where(big, rng.uniform(0.12, 0.3, n), rng.uniform(0.6, 1.4, n))
    for x0, y0, r, a_ in zip(px, py, rad, amp):
        s = int(3 * r + 3)
        xa, xb, ya, yb = max(0, int(x0) - s), min(W, int(x0) + s), max(0, int(y0) - s), min(H, int(y0) + s)
        d2 = (xx[ya:yb, xa:xb] - x0) ** 2 + (yy[ya:yb, xa:xb] - y0) ** 2
        if r > 4:   # 失焦的光斑：边缘稍亮的圆盘
            disc = smoothstep(r + 1, r - 1, np.sqrt(d2)) * (0.7 + 0.3 * smoothstep(r - 3, r, np.sqrt(d2)))
        else:
            disc = np.exp(-d2 / (2 * r * r))
        dust[ya:yb, xa:xb] += a_ * disc
    dust *= smoothstep(0.03, 0.2, rays) * 1.4
    lin = lin + 0.35 * dust[..., None] * beam_col

    # ---------- 泛光：高光（窗外雪地、逆光的毛尖）向外晕开 ----------
    Lb = lin @ LUMA
    hi = np.clip(Lb - 0.55, 0, None)[..., None] * lin / np.maximum(Lb, 1e-4)[..., None]
    bloom = ndi.gaussian_filter(hi, (22, 22, 0)) * 0.35 + ndi.gaussian_filter(hi, (70, 70, 0)) * 0.12
    lin = lin + bloom * np.array([1.0, 0.9, 0.75], np.float32)

    # ---------- 收尾：柔和的暗角 + 细颗粒 ----------
    out = to_srgb(lin / (1 + 0.25 * lin))  # 轻微压高光，避免泛光后发白
    out = out / out.max() * 0.985 if out.max() > 0.985 else out
    r2 = ((xx - W * 0.5) / (W * 0.62)) ** 2 + ((yy - H * 0.45) / (H * 0.75)) ** 2
    out = out * (1 - 0.22 * np.clip(r2 - 0.3, 0, None))[..., None]
    out = out + rng.normal(0, 0.005, out.shape).astype(np.float32)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(a.out)
    print("saved", a.out, out.shape)


if __name__ == "__main__":
    main()
