"""B04 雪地里一只回头看的红狐。
素材：refs/ 里的一张公有领域照片（NPS / Neal Herbert，雪地里回头看的赤狐）。
代码做的事：调色（Lab 里色度 +15%、色相往红偏；整体偏冷压暗一点，像阴天下雪）、暗角；
程序化生成三层飘雪（远处细而虚、中景清楚、较近的大而虚且拖影长，带运动模糊）；
狐狸背上和头顶落的小雪团（按照片局部清晰度虚化，跟景深一致）；细颗粒。
不联网，只读 refs/ 里的照片；随机数固定种子。
用法: python3 draw.py [--out final.png]
"""
import argparse
import os

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.signal import fftconvolve

import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402  只用它的 rgb2lab / lab2rgb

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "refs", "Hunting_fox_Hayden_Valley_28415856272_.jpg")
W, H = 1536, 1024
SEED = 4


def srgb_to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def load_photo():
    im = Image.open(REF).convert("RGB")
    # 原图 4540x3027（3:2），整幅缩到 1536x1024
    im = im.resize((W, H), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def grade(rgb):
    """整体一次调色（不分割，避免狐狸白色胸毛和雪地之间出现色差接缝）：
    Lab 里色度 +15%、色相往红偏 6°（中性的雪不受影响，狐狸更像"红"狐）；
    再在线性空间里曝光略降、偏冷（阴天下的雪）。"""
    lab = stylize.rgb2lab(rgb.astype(np.float64))
    a, b = lab[..., 1], lab[..., 2]
    th = np.deg2rad(-6.0)
    a2, b2 = a * np.cos(th) - b * np.sin(th), a * np.sin(th) + b * np.cos(th)
    lab[..., 1], lab[..., 2] = 1.15 * a2, 1.15 * b2
    rgb = stylize.lab2rgb(lab).astype(np.float32)
    lin = srgb_to_lin(rgb)
    lin = lin * np.array([0.86, 0.89, 0.93], np.float32)
    # 竖直方向：上面远处的雪地稍暗一点（纵深）
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    return lin * (0.94 + 0.06 * np.clip(yy * 1.4, 0, 1))


def fox_mask(rgb):
    """狐狸的橙色毛（Lab 色度高的地方），开运算去噪、补洞、略模糊。"""
    lab = stylize.rgb2lab(rgb.astype(np.float64))
    C = np.hypot(lab[..., 1], lab[..., 2])
    m = C > 12
    m = ndi.binary_opening(m, iterations=2)
    lbl, n = ndi.label(m)
    if n:
        sizes = ndi.sum(m, lbl, range(1, n + 1))
        m = lbl == (1 + int(np.argmax(sizes)))
    m = ndi.binary_fill_holes(ndi.binary_closing(m, iterations=6))
    return m


def snow_dust(rng, m):
    """落在狐狸背上、头顶的雪：少量不规则的小雪团，越靠近上沿越多（按每列从上往下进入狐狸的深度衰减）。
    每团由 2–4 个错开的小圆拼成，下沿略暗（有一点体积感）。返回 (alpha, 明暗) 两张图。"""
    depth = np.cumsum(m, axis=0).astype(np.float32)                  # 从上沿往下数进入了多少像素
    wgt = np.exp(-depth / 14.0) * m + 0.04 * m
    wgt = ndi.gaussian_filter(wgt, 1.0)
    p = wgt.ravel() / wgt.sum()
    A = np.zeros((H, W), np.float32)
    S = np.ones((H, W), np.float32)
    n = 260
    idx = rng.choice(H * W, size=n, replace=False, p=p)
    for cy, cx in zip(idx // W, idx % W):
        size = rng.choice([0.7, 1.0, 1.4, 2.0], p=[0.4, 0.3, 0.2, 0.1])
        for _ in range(rng.integers(2, 5)):
            ox, oy = rng.normal(0, 0.9 * size, 2)
            r = size * rng.uniform(0.6, 1.1)
            x, y = cx + ox, cy + oy * 0.6                              # 扁一点（压在毛上）
            R = int(r + 3)
            x0, x1 = max(0, int(x) - R), min(W, int(x) + R + 1)
            y0, y1 = max(0, int(y) - R), min(H, int(y) + R + 1)
            if x0 >= x1 or y0 >= y1:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            d = np.hypot(xx - x, (yy - y) / 0.75)
            a = np.clip(r + 0.5 - d, 0, 1) * rng.uniform(0.75, 0.95)
            A[y0:y1, x0:x1] = np.maximum(A[y0:y1, x0:x1], a)
            shade = 1 - 0.18 * np.clip((yy - y) / (r + 0.5), 0, 1)     # 下半边略暗
            S[y0:y1, x0:x1] = np.where(a > 0, np.minimum(S[y0:y1, x0:x1], shade), S[y0:y1, x0:x1])
    return ndi.gaussian_filter(A, 0.4), S


def vignette(lin):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx - W * 0.55) / (W * 0.62), (yy - H * 0.52) / (H * 0.70))
    v = 1 - 0.30 * np.clip(r - 0.55, 0, None) ** 1.6
    return lin * v[..., None]


def disc_kernel(radius, blur):
    R = int(np.ceil(radius + 3 * blur + 1))
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1].astype(np.float32)
    d = np.hypot(xx, yy)
    k = np.clip(radius + 0.5 - d, 0, 1)
    if blur > 0:
        k = ndi.gaussian_filter(k, blur)
    return k / k.max()


def streak(kernel, length, angle):
    """把雪花形状沿下落方向拖一段（快门时间内的运动模糊）。"""
    if length < 1:
        return kernel
    n = int(np.ceil(length)) * 2 + 1
    line = np.zeros((n, n), np.float32)
    c = n // 2
    for t in np.linspace(-length / 2, length / 2, int(length * 2) + 2):
        line[int(round(c + t * np.sin(angle))), int(round(c + t * np.cos(angle)))] = 1
    line /= line.sum()
    k = fftconvolve(kernel, line, mode="full")
    return k / k.max()


def snow_layer(rng, n, rmin, rmax, blur, alpha, length, angle, bins=4):
    """一层雪：n 片雪花，半径 rmin..rmax，按大小分几档，每档用一个核卷积撒点图。返回 alpha 图。"""
    A = np.zeros((H, W), np.float32)
    radii = np.exp(rng.uniform(np.log(rmin), np.log(rmax), n))
    edges = np.linspace(rmin, rmax, bins + 1)
    for b in range(bins):
        sel = (radii >= edges[b]) & (radii <= edges[b + 1])
        m = int(sel.sum())
        if m == 0:
            continue
        r = 0.5 * (edges[b] + edges[b + 1])
        pts = np.zeros((H, W), np.float32)
        ys, xs = rng.integers(0, H, m), rng.integers(0, W, m)
        np.add.at(pts, (ys, xs), rng.uniform(0.55, 1.0, m).astype(np.float32))
        ang_b = angle + np.deg2rad(rng.normal(0, 5))                   # 每档方向、长度略有不同（风不均匀）
        len_b = length * (0.6 + 0.4 * r / rmax) * rng.uniform(0.75, 1.25)
        k = streak(disc_kernel(r, blur + 0.15 * r), len_b, ang_b)
        A += fftconvolve(pts, k, mode="same").astype(np.float32)
    return np.clip(A * alpha, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "final.png"))
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)
    rgb = load_photo()
    lin = vignette(grade(rgb))
    dust, shade = snow_dust(rng, fox_mask(rgb))                      # 背上、头顶的积雪
    # 照片本身有景深（狐狸后半身略虚）：按局部清晰度把积雪也虚化，免得"虚的毛上贴着锐利的雪"
    L = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    sharp = ndi.gaussian_filter(np.abs(ndi.laplace(ndi.gaussian_filter(L, 0.7))), 12)
    sharp = np.clip(sharp / np.percentile(sharp[fox_mask(rgb)], 90), 0, 1)
    soft = ndi.gaussian_filter(dust, 1.6) * 1.25
    dust = np.clip(sharp * dust + (1 - sharp) * soft, 0, 0.95)
    dcol = np.array([0.86, 0.89, 0.95], np.float32) * shade[..., None]
    lin = lin * (1 - dust[..., None]) + dcol * dust[..., None]
    ang = np.deg2rad(100)                                            # 往下、略向左飘
    flake = np.array([0.97, 0.98, 1.0], np.float32)                  # 雪花（线性空间）
    for n, rmin, rmax, blur, alpha, length in [
            (2600, 0.5, 1.0, 0.9, 0.40, 3),                          # 远处：细、淡、略虚
            (800, 1.1, 2.2, 0.35, 0.85, 6),                          # 中景：清楚的雪花
            (70, 2.8, 5.0, 1.6, 0.55, 16)]:                          # 较近：大、虚、拖影长
        A = snow_layer(rng, n, rmin, rmax, blur, alpha, length, ang)
        lin = lin * (1 - A[..., None]) + flake * A[..., None]
    out = lin_to_srgb(lin)
    out = out + (rng.standard_normal((H, W, 1)).astype(np.float32) * 0.008)   # 细颗粒
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
