#!/usr/bin/env python3
"""A12 日系动画背景：夏日乡间小路和积雨云（A 赛道：只用代码画，不读任何图片、不联网）。

画法（numpy + Pillow，2 倍超采样后缩小）：
  天空    三段渐变（群青 -> 天蓝 -> 近地平线的浅青）。
  积雨云  一堆分层嵌套的球（大核 -> 表面长出的团块 -> 更小的菜花状小团），正交投影 + z 缓冲得到法线，
          按动画背景的做法分三档着色（受光白、冷灰中间调、蓝灰暗部），底部平而暗，团块交界处加暗缝，受光边缘加亮。
  地面    透视投影：柏油小路（向右弯、远处有“逃げ水”反光）、路边水渠、草边、稻田（田埂、稻行、风吹过的亮斑）。
  景物    远山两层、远处树林线、左边的神社林（同样用球团渲染）和小鸟居、右边的农家、电线杆和电线、橙色道路反光镜、
          前景草叶。
python3 draw.py  →  final.png（固定随机种子，可完全复现）
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1600, 900
SS = 2
W2, H2 = W * SS, H * SS
SEED = 1212
YH = 540.0            # 地平线（1x）
F = 1100.0            # 焦距（1x 像素）
CAMH = 1.6            # 相机高度（米）
CXS = 800.0
ROAD_W = 3.6

SUN3 = np.array([0.74, 0.48, 0.38])        # 指向太阳：右、上、朝向观者（偏侧光，云的左侧落在阴影里）
SUN3 = SUN3 / np.linalg.norm(SUN3)
SHADOW_DIR = np.array([-SUN3[0], SUN3[2]])  # 地面上影子的方向（X 左、Z 远）
SHADOW_DIR = SHADOW_DIR / np.linalg.norm(SHADOW_DIR)
SUN_ELEV = np.arcsin(SUN3[1])


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    t = np.asarray(t, np.float32)
    if t.ndim > 0:
        t = t[..., None]
    return a + (b - a) * t


def hexc(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


class Noise2:
    def __init__(self, seed, n=256):
        r = np.random.default_rng(seed)
        self.g = [ndi.spline_filter(r.random((n, n)).astype(np.float32), order=3, mode="grid-wrap") for _ in range(6)]
        self.off = (r.random((8, 2)) * n).astype(np.float32)

    def __call__(self, x, y, octaves=4, pers=0.5):
        x, y = np.broadcast_arrays(np.asarray(x, np.float32), np.asarray(y, np.float32))
        out = np.zeros(x.shape, np.float32)
        amp, tot, f = 1.0, 0.0, 1.0
        for o in range(octaves):
            out += amp * ndi.map_coordinates(self.g[o % 6], [y * f + self.off[o, 0], x * f + self.off[o, 1]],
                                             order=3, mode="grid-wrap", prefilter=False)
            tot += amp
            amp *= pers
            f *= 2.0
        return out / tot


NZ = Noise2(SEED)


def road_xc(Z):
    return -0.3 + 0.00042 * Z ** 2


def g2s(X, Z, h=0.0):
    """地面坐标（米）-> 1x 画面坐标；h 为离地高度。"""
    return CXS + F * X / Z, YH + F * (CAMH - h) / Z


def put(canvas, mask, color):
    if np.ndim(color) == 1:
        color = np.asarray(color, np.float32)[None, None, :]
    return canvas * (1 - mask[..., None]) + color * mask[..., None]


def poly_mask(polys, blur=0.0):
    im = Image.new("L", (W2, H2), 0)
    d = ImageDraw.Draw(im)
    for pts in polys:
        d.polygon([(x * SS, y * SS) for x, y in pts], fill=255)
    m = np.asarray(im, np.float32) / 255
    if blur > 0:
        m = ndi.gaussian_filter(m, blur)
    return m


# ---------------------------------------------------------------- 球团渲染（云和树冠共用）


def rand_dir(rng, up, front):
    v = rng.normal(size=3)
    v = v / np.linalg.norm(v)
    v = v + np.array([0.0, -up, front])
    return v / np.linalg.norm(v)


def grow(rng, parents, n, rscale, up, front, base_y=None, dist=0.82):
    out = []
    P = np.asarray(parents)
    for _ in range(n):
        p = P[rng.integers(len(P))]
        d = rand_dir(rng, up, front)
        r = p[3] * rng.uniform(*rscale)
        c = p[:3] + d * p[3] * dist
        if base_y is not None and c[1] + r * 0.2 > base_y:
            continue
        out.append([c[0], c[1], c[2], r])
    return out


def render_spheres(sph, box):
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    zb = np.full((h, w), -1e9, np.float32)
    NXa = np.zeros((h, w), np.float32)
    NYa = np.zeros((h, w), np.float32)
    NZa = np.zeros((h, w), np.float32)
    for (x, y, z, r) in sph:
        bx0, bx1 = max(x0, int(x - r - 1)), min(x1, int(x + r + 2))
        by0, by1 = max(y0, int(y - r - 1)), min(y1, int(y + r + 2))
        if bx0 >= bx1 or by0 >= by1:
            continue
        X = (np.arange(bx0, bx1, dtype=np.float32) + 0.5 - x)[None, :]
        Y = (np.arange(by0, by1, dtype=np.float32) + 0.5 - y)[:, None]
        d2 = r * r - X * X - Y * Y
        dz = np.sqrt(np.maximum(d2, 0))
        zf = z + dz
        sl = (slice(by0 - y0, by1 - y0), slice(bx0 - x0, bx1 - x0))
        upd = (d2 > 0) & (zf > zb[sl])
        zb[sl] = np.where(upd, zf, zb[sl])
        NXa[sl] = np.where(upd, X / r, NXa[sl])
        NYa[sl] = np.where(upd, -Y / r, NYa[sl])
        NZa[sl] = np.where(upd, dz / r, NZa[sl])
    return zb, NXa, NYa, NZa


def smooth_normals(nx, ny, nz, a, sigma, keep=0.3):
    w = ndi.gaussian_filter(a, sigma) + 1e-6
    sx = ndi.gaussian_filter(nx * a, sigma) / w
    sy = ndi.gaussian_filter(ny * a, sigma) / w
    sz = ndi.gaussian_filter(nz * a, sigma) / w
    mx, my, mz = keep * nx + (1 - keep) * sx, keep * ny + (1 - keep) * sy, keep * nz + (1 - keep) * sz
    n = np.sqrt(mx * mx + my * my + mz * mz) + 1e-6
    return mx / n, my / n, mz / n


def shade_cloud(sph, box, base_y, sky_at, haze=0.0, seed=0):
    """动画风格的积云着色。坐标为 2x 像素。返回 (rgb, alpha)。"""
    x0, y0, x1, y1 = box
    zb, nx, ny, nz = render_spheres(sph, box)
    a = (zb > -1e8).astype(np.float32)
    size = max(6.0, (base_y - y0) / SS / 45.0)
    nx, ny, nz = smooth_normals(nx, ny, nz, a, size * SS * 0.6, keep=0.45)
    yy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5) * np.ones((1, x1 - x0), np.float32)
    xx = (np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5) * np.ones((y1 - y0, 1), np.float32)
    a = a * (yy < base_y)
    l = nx * SUN3[0] + ny * SUN3[1] + nz * SUN3[2]
    SH, MID, LIT = hexc("7e93c2"), hexc("c6d3ec"), hexc("fffcf4")
    t1 = smoothstep(-0.12, 0.06, l)
    t2 = smoothstep(0.28, 0.42, l)
    col = mix(SH, MID, t1)
    col = mix(col, LIT, t2)
    # 底部被上面的云体挡住，暗而偏蓝
    fb = smoothstep(base_y - 0.50 * (base_y - y0), base_y, yy)
    col = mix(col, hexc("7488b4"), 0.75 * fb * (1 - 0.45 * t2))
    # 团块交界的暗缝（z 缓冲比周围低的地方）
    zz = np.where(a > 0, zb, np.nan)
    zfill = np.where(np.isnan(zz), np.nanmin(zz) if np.isfinite(np.nanmin(zz)) else 0, zz)
    cav = np.clip((ndi.gaussian_filter(zfill, size * 1.6 * SS) - zfill) / (size * 3.0 * SS), 0, 1)
    col = mix(col, hexc("9aaed3"), 0.35 * cav * (1 - 0.5 * t2))
    # 暗部里朝下的面接到地面/天空的反光，偏冷青
    bounce = np.clip(-ny, 0, 1) * (1 - t1)
    col = mix(col, hexc("a8c0e4"), 0.40 * bounce)
    # 受光一侧的轮廓亮边
    rim = np.clip(nx * SUN3[0] + ny * SUN3[1], 0, 1) * (1 - nz) ** 2
    col = col + (rim * 0.10)[..., None] * np.array([1.0, 0.97, 0.9], np.float32)
    # 画笔感的微弱起伏
    col = col * (1 + 0.025 * (NZ(xx / 40 + seed, yy / 40, octaves=3) - 0.5)
                 + 0.03 * (NZ(xx / 70 + seed, yy / 10, octaves=2) - 0.5) * (1 - t2))[..., None]
    # 远处的云蒙上一层天色
    sk = sky_at(yy)
    col = mix(col, sk, np.clip(haze + 0.55 * smoothstep(base_y - 0.22 * (base_y - y0), base_y, yy), 0, 0.9))
    a = ndi.gaussian_filter(a, 0.6)
    return np.clip(col, 0, 1.1), a


# ---------------------------------------------------------------- 天空


def sky_color(y1x):
    t = np.clip(y1x / YH, 0, 1)
    top, mid, hor = hexc("1f5fc8"), hexc("4d9be3"), hexc("bfe3f6")
    c = mix(top, mid, smoothstep(0.0, 0.62, t))
    return mix(c, hor, smoothstep(0.45, 1.0, t) ** 1.2)


def sky_at_2x(yy2):
    return sky_color(yy2 / SS)


def main_cloud(rng):
    base = 512.0
    cores = [(640, 440, 0, 115), (820, 430, 25, 140), (1010, 442, 0, 118), (1130, 465, -20, 80),
             (790, 318, 10, 122), (905, 312, 0, 112), (700, 350, -10, 90),
             (840, 215, 15, 112), (760, 240, 0, 92), (940, 228, 0, 98),
             (860, 135, 10, 96), (780, 160, 0, 78), (950, 162, 5, 74)]
    cores = [[x * SS, y * SS, z * SS, r * SS] for x, y, z, r in cores]
    L1 = grow(rng, cores, 46, (0.40, 0.60), 0.55, 0.10, base * SS)
    L2 = grow(rng, cores + L1, 190, (0.30, 0.50), 0.80, -0.35, base * SS)
    L3 = grow(rng, L1 + L2, 360, (0.30, 0.48), 1.00, -0.45, base * SS)
    sph = cores + L1 + L2 + L3
    return sph, base


def small_cloud(rng, cx, base, w, h, n1=16, n2=50, n3=120):
    cores = []
    k = max(2, int(w / (h * 0.9)))
    for i in range(k):
        f = (i + 0.5) / k
        x = cx - w / 2 + f * w
        r = h * (0.55 + 0.35 * np.sin(np.pi * f)) * rng.uniform(0.85, 1.1)
        cores.append([x * SS, (base - r * 0.55) * SS, 0, r * SS])
    L1 = grow(rng, cores, n1, (0.38, 0.58), 0.7, 0.0, base * SS)
    L2 = grow(rng, cores + L1, n2, (0.3, 0.5), 0.9, -0.35, base * SS)
    L3 = grow(rng, L1 + L2, n3, (0.3, 0.45), 1.0, -0.45, base * SS)
    return cores + L1 + L2 + L3


def comp_cloud(img, sph, base, haze, seed):
    s = np.asarray(sph)
    pad = 4
    x0 = max(0, int((s[:, 0] - s[:, 3]).min()) - pad)
    x1 = min(W2, int((s[:, 0] + s[:, 3]).max()) + pad)
    y0 = max(0, int((s[:, 1] - s[:, 3]).min()) - pad)
    y1 = min(H2, int(base * SS) + pad)
    if x0 >= x1 or y0 >= y1:
        return img
    col, a = shade_cloud(sph, (x0, y0, x1, y1), base * SS, sky_at_2x, haze=haze, seed=seed)
    sub = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = sub * (1 - a[..., None]) + col * a[..., None]
    return img


# ---------------------------------------------------------------- 地面


def ground_layer(img, rng):
    yy, xx = np.mgrid[0:H2, 0:W2].astype(np.float32)
    y1 = (yy + 0.5) / SS
    x1 = (xx + 0.5) / SS
    g = y1 > YH + 0.3
    dy = np.maximum(y1 - YH, 0.3)
    Z = F * CAMH / dy
    X = (x1 - CXS) * Z / F
    pix = Z / F / SS                      # 一个 2x 像素对应的地面米数
    xc = road_xc(Z)
    u = X - xc                            # 相对路中心
    au = np.abs(u)
    # ---- 稻田
    wind = NZ(X / 9 + 3, Z / 14, octaves=4)
    base = mix(hexc("4f8f22"), hexc("7fbf36"), wind)
    base = mix(base, hexc("a9d650"), smoothstep(0.62, 0.8, NZ(X / 5, Z / 7 + 9, octaves=3)) * 0.55)  # 风吹过的亮斑
    rows = 0.5 + 0.5 * np.sin(2 * np.pi * X / 0.32)
    rows_amp = 1 - smoothstep(0.012, 0.035, pix)
    base = base * (1 - 0.07 * rows * rows_amp)[..., None]
    # 每块田色相略不同
    fx, fz = np.floor((u - 3.2) / 24.0), np.floor((Z + 7) / 30.0)
    hsh = np.sin(fx * 12.9898 + fz * 78.233) * 43758.5453
    hsh = hsh - np.floor(hsh)
    base = mix(base, hexc("3f7d24"), 0.35 * smoothstep(0.55, 0.9, hsh))
    base = mix(base, hexc("93c447"), 0.30 * smoothstep(0.45, 0.1, hsh))
    # 田埂：沿 X 每 24 米、沿 Z 每 30 米一条（亮的土埂 + 一侧的暗边）
    ridge_x = np.abs(((u - 3.2) % 24.0) - 12.0)
    ridge_z = np.abs(((Z + 7) % 30.0) - 15.0)
    wpx = np.maximum(pix, 0.001)
    rx = smoothstep(12.0 - 0.30 - wpx, 12.0 - 0.30 + wpx, ridge_x)
    dzdy = Z * Z / (F * CAMH) / SS                    # 一个 2x 像素在 Z 方向的米数
    rz = smoothstep(15.0 - 0.30 - dzdy, 15.0 - 0.30 + dzdy, ridge_z)
    ridge = np.maximum(rx, rz) * (au > ROAD_W / 2 + 1.2)
    base = mix(base, hexc("b3c776"), ridge * 0.85)
    # 远处雾气
    fog = smoothstep(40, 420, Z)
    base = mix(base, hexc("9cc7c2"), fog * 0.55)
    # ---- 路边草带 + 左侧水渠
    verge = (au < ROAD_W / 2 + 1.1) & (au >= ROAD_W / 2)
    vcol = mix(hexc("5d9a2c"), hexc("8cc43e"), NZ(X * 2, Z * 0.8, octaves=3))
    ditch = (u < -(ROAD_W / 2 + 0.45)) & (u > -(ROAD_W / 2 + 1.05))
    dcol = mix(hexc("8ec6e6"), hexc("5b8fb7"), NZ(X * 3, Z * 0.5, octaves=2) * 0.6)
    dedge = (np.abs(u + ROAD_W / 2 + 0.45) < 0.08 + pix) | (np.abs(u + ROAD_W / 2 + 1.05) < 0.08 + pix)
    # ---- 路面
    road = au < ROAD_W / 2
    asph = mix(hexc("7c7f86"), hexc("9a9ca1"), NZ(X * 4, Z * 1.2, octaves=4))
    patch = smoothstep(0.66, 0.70, NZ(X * 0.7 + 20, Z * 0.18, octaves=3))
    asph = mix(asph, hexc("686b71"), patch * 0.4)
    cn = NZ(X * 1.3 + 5, Z * 0.35, octaves=3)
    crack = smoothstep(0.004 + pix * 0.3, 0.0, np.abs(cn - 0.5)) * (1 - smoothstep(0.015, 0.04, pix))
    crack = crack * smoothstep(0.45, 0.6, NZ(X * 0.5 + 40, Z * 0.2, octaves=2))
    asph = mix(asph, hexc("4a4c52"), crack * 0.6)
    edge_line = (np.abs(au - (ROAD_W / 2 - 0.22)) < 0.06 + pix * 0.5) & (NZ(X * 3, Z * 2, octaves=2) > 0.22)
    asph = mix(asph, hexc("e8e6df"), edge_line * 0.85)
    # 逃げ水：远处路面反着天光
    mir = smoothstep(55, 90, Z) * (1 - smoothstep(140, 220, Z)) * smoothstep(0.35, 0.65, NZ(Z / 6, X / 2, octaves=2))
    asph = mix(asph, hexc("b9dcf2"), mir * 0.55)
    asph = mix(asph, hexc("aebfc9"), fog * 0.6)
    col = base
    col = np.where(verge[..., None], mix(vcol, hexc("9cc7c2"), fog * 0.5), col)
    col = np.where(ditch[..., None], dcol, col)
    col = np.where(dedge[..., None], hexc("b8b8ae"), col)
    col = np.where(road[..., None], asph, col)
    # ---- 电线杆的影子（横穿路面）
    for Zp in POLES_Z[:2]:
        Xp = road_xc(Zp) + POLE_OFF
        L = min(9.5 / np.tan(SUN_ELEV), 16.0)
        ex, ez = Xp + SHADOW_DIR[0] * L, Zp + SHADOW_DIR[1] * L
        vx, vz = ex - Xp, ez - Zp
        t = np.clip(((X - Xp) * vx + (Z - Zp) * vz) / (vx * vx + vz * vz), 0, 1)
        dd = np.hypot(X - Xp - t * vx, Z - Zp - t * vz)
        sh = smoothstep(0.20 + pix, 0.20 - pix, dd)
        # 横担的影子
        cx_, cz_ = Xp + SHADOW_DIR[0] * L * 0.93, Zp + SHADOW_DIR[1] * L * 0.93
        px_, pz_ = -SHADOW_DIR[1], SHADOW_DIR[0]
        s2 = np.abs((X - cx_) * SHADOW_DIR[0] + (Z - cz_) * SHADOW_DIR[1])
        s3 = np.abs((X - cx_) * px_ + (Z - cz_) * pz_)
        sh = np.maximum(sh, smoothstep(0.1 + pix, 0.1 - pix, s2) * (s3 < 0.9))
        col = col * (1 - 0.42 * sh[..., None] * (1 - hexc("6f86b8")))
    m = g.astype(np.float32)
    img = img * (1 - m[..., None]) + col * m[..., None]
    return img


# ---------------------------------------------------------------- 远景


def ridge_line(rng, x0, x1, base, amp, scale, octaves=5):
    xs = np.arange(x0, x1 + 1, 2.0)
    y = np.zeros_like(xs)
    a, s = amp, scale
    for _ in range(octaves):
        knots = rng.uniform(-1, 1, int((x1 - x0) / s) + 4)
        y += a * np.interp(xs, np.linspace(x0 - s, x1 + s, len(knots)), knots)
        a *= 0.5
        s /= 2.2
    return xs, base - np.abs(y) * 0.6 - y * 0.4


def mountains(img, rng):
    for (base, amp, scale, colr, top_col) in ((530, 120, 460, hexc("6f96bb"), hexc("8badcf")),
                                              (539, 60, 260, hexc("3f716f"), hexc("5d8b83"))):
        xs, ys = ridge_line(rng, -20, W + 20, base, amp, scale)
        pts = [(x, y) for x, y in zip(xs, ys)] + [(W + 20, YH + 30), (-20, YH + 30)]
        m = poly_mask([pts])
        yy = (np.arange(H2, dtype=np.float32)[:, None] + 0.5) / SS * np.ones((1, W2), np.float32)
        c = mix(top_col, colr, smoothstep(base - amp, base, yy))
        c = mix(c, sky_color(np.full_like(yy, YH)), 0.18)
        img = put(img, m, c)
    return img


def treeline(img, rng):
    """地平线上一条远处的树林带（小球团，蓝绿色）。"""
    sph = []
    x = -10.0
    while x < W + 10:
        r = rng.uniform(5, 11)
        sph.append([x * SS, (YH - r * 0.4 + rng.uniform(-2, 2)) * SS, 0, r * SS])
        x += r * rng.uniform(0.9, 1.4)
    box = (0, int((YH - 30) * SS), W2, int((YH + 6) * SS))
    zb, nx, ny, nz = render_spheres(sph, box)
    a = (zb > -1e8).astype(np.float32)
    l = nx * SUN3[0] + ny * SUN3[1] + nz * SUN3[2]
    col = mix(hexc("3f6f68"), hexc("6f9a78"), smoothstep(0.0, 0.5, l))
    col = mix(col, hexc("9cc7c2"), 0.35)
    y0, y1 = box[1], box[3]
    img[y0:y1] = img[y0:y1] * (1 - a[..., None]) + col * a[..., None]
    return img


def canopy(img, rng, cores, n1, n2, n3, box1x, lit, mid, shd, haze=0.0, base_cut=None):
    cores = [[x * SS, y * SS, z * SS, r * SS] for x, y, z, r in cores]
    L1 = grow(rng, cores, n1, (0.38, 0.58), 0.35, 0.05, None, 0.85)
    L2 = grow(rng, cores + L1, n2, (0.30, 0.50), 0.35, -0.3, None, 0.88)
    L3 = grow(rng, L1 + L2, n3, (0.28, 0.45), 0.4, -0.4, None, 0.92)
    sph = cores + L1 + L2 + L3
    x0, y0, x1, y1 = [int(v * SS) for v in box1x]
    zb, nx, ny, nz = render_spheres(sph, (x0, y0, x1, y1))
    a = (zb > -1e8).astype(np.float32)
    if base_cut is not None:
        yy = (np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5) / SS
        a = a * (yy < base_cut)
    nx, ny, nz = smooth_normals(nx, ny, nz, a, 4.0 * SS, keep=0.3)
    l = nx * SUN3[0] + ny * SUN3[1] + nz * SUN3[2]
    t1 = smoothstep(-0.1, 0.2, l)
    t2 = smoothstep(0.35, 0.6, l)
    col = mix(shd, mid, t1)
    col = mix(col, lit, t2)
    yy2 = np.arange(y0, y1, dtype=np.float32)[:, None] * np.ones((1, x1 - x0), np.float32)
    xx2 = np.arange(x0, x1, dtype=np.float32)[None, :] * np.ones((y1 - y0, 1), np.float32)
    leaf = NZ(xx2 / 5.0, yy2 / 5.0, octaves=2)
    col = col * (0.88 + 0.24 * leaf)[..., None]
    spk = NZ(xx2 / 2.2 + 50, yy2 / 2.2, octaves=1)
    col = mix(col, shd * 0.7, smoothstep(0.66, 0.74, spk) * (1 - t2) * 0.8)      # 暗部里的叶隙
    col = mix(col, lit * 1.08, smoothstep(0.68, 0.76, spk) * t1 * 0.7)           # 亮部里的叶片高光
    zz = np.where(a > 0, zb, np.nan)
    zfill = np.where(np.isnan(zz), np.nanmin(zz), zz)
    cav = np.clip((ndi.gaussian_filter(zfill, 4 * SS) - zfill) / (8 * SS), 0, 1)
    col = mix(col, shd * 0.8, 0.6 * cav)
    col = mix(col, hexc("9cc7c2"), haze)
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - a[..., None]) + col * a[..., None]
    return leaf_clusters(img, rng, a, col, t2, (x0, y0), lit, shd)


def leaf_clusters(img, rng, a, col, t2, off, lit, shd, per=45.0):
    """在树冠上画一层小叶团：每团一个扁椭圆，取该处的明暗色；受光的叶团右上加一道亮边。"""
    ys, xs = np.nonzero(a > 0.5)
    if len(ys) == 0:
        return img
    n = int(len(ys) / (per * SS * SS))
    idx = rng.integers(0, len(ys), n)
    order = np.argsort(ys[idx])
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    for k in idx[order]:
        y, x = ys[k], xs[k]
        c = col[y, x] * rng.uniform(0.9, 1.08)
        r = rng.uniform(2.5, 5.5) * SS
        X, Y = x + off[0], y + off[1]
        cc = tuple(int(v * 255) for v in np.clip(c, 0, 1)) + (235,)
        d.ellipse([X - r * 1.3, Y - r, X + r * 1.3, Y + r * 0.8], fill=cc)
        if t2[y, x] > 0.5:
            hc = tuple(int(v * 255) for v in np.clip(lit * 1.12, 0, 1)) + (200,)
            d.arc([X - r * 1.3, Y - r, X + r * 1.3, Y + r * 0.8], 250, 350, fill=hc, width=max(1, SS))
    return np.asarray(im, np.float32) / 255


def cedars(img, rng, items):
    """神社林后面几棵高高的杉树：深绿、锯齿边的细长锥形，右侧受光。"""
    for (x, ybase, h, w) in items:
        tiers = int(h / 9)
        L, R = [], []
        for i in range(tiers + 1):
            f = i / tiers
            y = ybase - f * h
            hw = w * 0.5 * (1 - f) ** 0.9 * (0.75 + 0.45 * rng.random()) + 1.0
            L.append((x - hw, y + 2))
            L.append((x - hw * 0.55, y - h / tiers * 0.5))
            R.append((x + hw, y + 2))
            R.append((x + hw * 0.55, y - h / tiers * 0.5))
        pts = L + [(x, ybase - h - 4)] + R[::-1]
        img = put(img, poly_mask([pts]), hexc("24493f"))
        lit = [(x, ybase - h - 4)] + [(p[0] * 0.55 + x * 0.45, p[1]) for p in R[::-1]] + [(x, ybase)]
        img = put(img, poly_mask([lit]), hexc("3b6d4c"))
    return img


def rice_strokes(img, rng):
    """近处稻田里的一丛丛稻叶（按行排列的小笔触）。"""
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    items = []
    for Z in np.arange(7.0, 48.0, 0.36):
        xl = (0 - CXS) * Z / F - 0.5
        xr = (W - CXS) * Z / F + 0.5
        for X in np.arange(np.floor(xl / 0.34) * 0.34, xr, 0.34):
            if abs(X - road_xc(Z)) < ROAD_W / 2 + 1.25:
                continue
            items.append((Z, X + rng.normal(0, 0.03)))
    items.sort(key=lambda t: -t[0])
    for Z, X in items:
        x, y = g2s(X, Z)
        h = rng.uniform(0.28, 0.42) * F / Z
        for _ in range(3):
            ln = rng.normal(0, 0.25)
            lit = rng.random() > 0.45
            c0 = np.array([0.46, 0.72, 0.20]) if lit else np.array([0.20, 0.44, 0.15])
            c0 = c0 + rng.uniform(-0.04, 0.04, 3)
            fog = np.clip((Z - 20) / 120, 0, 0.3)
            c0 = c0 * (1 - fog) + np.array([0.61, 0.78, 0.76]) * fog
            c = tuple(int(v * 255) for v in np.clip(c0, 0, 1)) + (235,)
            w = max(0.5, 0.018 * F / Z)
            hh = h * rng.uniform(0.7, 1.0)
            pts = [((x - w) * SS, y * SS), ((x + ln * hh * 0.5) * SS, (y - hh) * SS), ((x + w) * SS, y * SS)]
            d.polygon(pts, fill=c)
    return np.asarray(im, np.float32) / 255


def trunks(img, items):
    polys = []
    for (x, ytop, ybot, w) in items:
        polys.append([(x - w / 2, ytop), (x + w / 2, ytop), (x + w * 0.7, ybot), (x - w * 0.7, ybot)])
    m = poly_mask(polys)
    return put(img, m, hexc("2d3a2c"))


def torii(img, x, ybase, h):
    """小鸟居：两根柱、笠木（上横梁，两端翘起）、贯。"""
    w = h * 1.15
    col, dark = hexc("d8452c"), hexc("25201e")
    pw = h * 0.09
    polys = [[(x - w * 0.34 - pw / 2, ybase - h * 0.86), (x - w * 0.34 + pw / 2, ybase - h * 0.86),
              (x - w * 0.36 + pw / 2, ybase), (x - w * 0.36 - pw / 2 - 1, ybase)],
             [(x + w * 0.34 - pw / 2, ybase - h * 0.86), (x + w * 0.34 + pw / 2, ybase - h * 0.86),
              (x + w * 0.36 + pw / 2 + 1, ybase), (x + w * 0.36 - pw / 2, ybase)],
             [(x - w * 0.42, ybase - h * 0.70), (x + w * 0.42, ybase - h * 0.70),
              (x + w * 0.42, ybase - h * 0.63), (x - w * 0.42, ybase - h * 0.63)],
             [(x - w * 0.48, ybase - h * 0.88), (x + w * 0.48, ybase - h * 0.88),
              (x + w * 0.44, ybase - h * 0.80), (x - w * 0.44, ybase - h * 0.80)]]
    img = put(img, poly_mask(polys), col)
    top = [[(x - w * 0.56, ybase - h * 1.02), (x, ybase - h * 0.95), (x + w * 0.56, ybase - h * 1.02),
            (x + w * 0.52, ybase - h * 0.93), (x, ybase - h * 0.88), (x - w * 0.52, ybase - h * 0.93)]]
    return put(img, poly_mask(top), dark)


def farmhouse(img, x, ybase, w, h):
    """农家：白墙、深灰瓦的四坡顶，檐下阴影。"""
    wall = [[(x - w / 2, ybase - h * 0.5), (x + w / 2, ybase - h * 0.5), (x + w / 2, ybase), (x - w / 2, ybase)]]
    img = put(img, poly_mask(wall), hexc("e9e4d6"))
    side = [[(x + w * 0.18, ybase - h * 0.5), (x + w / 2, ybase - h * 0.5), (x + w / 2, ybase), (x + w * 0.18, ybase)]]
    img = put(img, poly_mask(side), hexc("b9b8b4"))
    win = [[(x - w * 0.36, ybase - h * 0.36), (x - w * 0.12, ybase - h * 0.36), (x - w * 0.12, ybase - h * 0.12),
            (x - w * 0.36, ybase - h * 0.12)]]
    img = put(img, poly_mask(win), hexc("4a5563"))
    roof = [[(x - w * 0.62, ybase - h * 0.46), (x + w * 0.62, ybase - h * 0.46), (x + w * 0.42, ybase - h * 1.0),
             (x - w * 0.42, ybase - h * 1.0)]]
    img = put(img, poly_mask(roof), hexc("4c5561"))
    lit = [[(x - w * 0.62, ybase - h * 0.46), (x + w * 0.10, ybase - h * 0.46), (x + w * 0.02, ybase - h * 1.0),
            (x - w * 0.42, ybase - h * 1.0)]]
    img = put(img, poly_mask(lit), hexc("65707d"))
    eave = [[(x - w * 0.5, ybase - h * 0.5), (x + w * 0.5, ybase - h * 0.5), (x + w * 0.5, ybase - h * 0.42),
             (x - w * 0.5, ybase - h * 0.42)]]
    return put(img, poly_mask(eave), hexc("7d7a74"))


# ---------------------------------------------------------------- 电线杆、电线、反光镜

POLES_Z = [8.5, 38.0, 67.0, 96.0, 125.0, 154.0, 183.0]
POLE_OFF = 3.7


def poles(img):
    polys, arms, ins = [], [], []
    tops = []
    for Zp in POLES_Z:
        Xp = road_xc(Zp) + POLE_OFF
        xb, yb = g2s(Xp, Zp, 0.0)
        xt, yt = g2s(Xp, Zp, 10.0)
        wpx = 0.30 * F / Zp
        polys.append([(xt - wpx * 0.40, yt), (xt + wpx * 0.40, yt), (xb + wpx * 0.5, yb), (xb - wpx * 0.5, yb)])
        ya = g2s(Xp, Zp, 9.4)[1]
        aw = 1.8 * F / Zp
        ah = 0.12 * F / Zp
        arms.append([(xt - aw / 2, ya - ah / 2), (xt + aw / 2, ya - ah / 2), (xt + aw / 2, ya + ah / 2), (xt - aw / 2, ya + ah / 2)])
        wire_pts = [(xt - aw * 0.45, ya - ah), (xt, g2s(Xp, Zp, 10.0)[1] - ah), (xt + aw * 0.45, ya - ah),
                    (xt - aw * 0.3, g2s(Xp, Zp, 8.2)[1])]
        tops.append(wire_pts)
        for (wx, wy) in wire_pts[:3]:
            s = 0.14 * F / Zp
            ins.append([(wx - s / 2, wy - s), (wx + s / 2, wy - s), (wx + s / 2, wy + s * 0.5), (wx - s / 2, wy + s * 0.5)])
    # 杆身：圆柱明暗（右侧受光、左侧背光，中间一道高光）
    m = poly_mask(polys)
    yy, xx = np.mgrid[0:H2, 0:W2].astype(np.float32)
    x1 = (xx + 0.5) / SS
    y1 = (yy + 0.5) / SS
    rel = np.zeros_like(x1)
    for p, Zp in zip(polys, POLES_Z):
        (a0, a1, a2, a3) = p
        t = np.clip((y1 - a0[1]) / max(a3[1] - a0[1], 1e-3), 0, 1)
        xl = a0[0] + (a3[0] - a0[0]) * t
        xr = a1[0] + (a2[0] - a1[0]) * t
        inside = (y1 >= a0[1]) & (y1 <= a3[1]) & (x1 >= xl - 1) & (x1 <= xr + 1)
        rel = np.where(inside, (x1 - xl) / np.maximum(xr - xl, 1e-3), rel)
    pc = mix(hexc("5a6166"), hexc("a9adae"), smoothstep(0.1, 0.75, rel))
    pc = mix(pc, hexc("c9cbc8"), np.exp(-((rel - 0.72) / 0.08) ** 2) * 0.6)
    pc = mix(pc, hexc("7e8a93"), 0.25 * (1 - smoothstep(0.0, 0.3, rel)))           # 背光面的天光
    img = put(img, m, pc)
    # 最近那根杆：脚钉、铭牌
    Zp = POLES_Z[0]
    Xp = road_xc(Zp) + POLE_OFF
    steps, plates = [], []
    for hgt in np.arange(2.2, 9.0, 0.45):
        xs_, ys_ = g2s(Xp, Zp, hgt)
        s = 0.035 * F / Zp
        side = 1 if int(hgt / 0.45) % 2 else -1
        steps.append([(xs_ + side * 0.10 * F / Zp, ys_ - s / 2), (xs_ + side * 0.24 * F / Zp, ys_ - s / 2),
                      (xs_ + side * 0.24 * F / Zp, ys_ + s / 2), (xs_ + side * 0.10 * F / Zp, ys_ + s / 2)])
    img = put(img, poly_mask(steps), hexc("6a6e70"))
    xs_, ys_ = g2s(Xp, Zp, 1.6)
    pw_, ph_ = 0.22 * F / Zp, 0.5 * F / Zp
    plates.append([(xs_ - pw_ / 2, ys_ - ph_), (xs_ + pw_ / 2, ys_ - ph_), (xs_ + pw_ / 2, ys_), (xs_ - pw_ / 2, ys_)])
    img = put(img, poly_mask(plates), hexc("e9e4cf"))
    xs_, ys_ = g2s(Xp, Zp, 1.95)
    img = put(img, poly_mask([[(xs_ - pw_ * 0.35, ys_ - ph_ * 0.1), (xs_ + pw_ * 0.35, ys_ - ph_ * 0.1),
                               (xs_ + pw_ * 0.35, ys_ + ph_ * 0.1), (xs_ - pw_ * 0.35, ys_ + ph_ * 0.1)]]), hexc("2e62a8"))
    img = put(img, poly_mask(arms), hexc("3f4549"))
    img = put(img, poly_mask(ins), hexc("d9d4c8"))
    # 电线：相邻两杆之间悬链线下垂；最近一根杆的线从画面外（右上）拉下来
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    for k in range(len(POLES_Z) - 1):
        A, B = tops[k], tops[k + 1]
        Zm = (POLES_Z[k] + POLES_Z[k + 1]) / 2
        for wi in range(4):
            (ax, ay), (bx, by) = A[wi], B[wi]
            sag = 0.45 * F / Zm
            pts = []
            for t in np.linspace(0, 1, 40):
                x = ax + (bx - ax) * t
                y = ay + (by - ay) * t + sag * 4 * t * (1 - t)
                pts.append((x * SS, y * SS))
            wd = max(1, int(round(SS * (1.6 if k == 0 else 1.1))))
            d.line(pts, fill=(38, 44, 52, 235), width=wd)
    return np.asarray(im, np.float32) / 255


def curve_mirror(img, Z=17.0):
    X = road_xc(Z) - (ROAD_W / 2 + 0.7)
    xb, yb = g2s(X, Z, 0.0)
    xt, yt = g2s(X, Z, 2.55)
    pw = 0.09 * F / Z
    img = put(img, poly_mask([[(xt - pw / 2, yt), (xt + pw / 2, yt), (xb + pw / 2, yb), (xb - pw / 2, yb)]]), hexc("e0662a"))
    cx, cy = g2s(X + 0.1, Z, 2.75)
    R = 0.42 * F / Z
    yy, xx = np.mgrid[0:H2, 0:W2].astype(np.float32)
    X1, Y1 = (xx + 0.5) / SS - cx, (yy + 0.5) / SS - cy
    rr = np.hypot(X1 / 0.86, Y1)
    ring = np.clip((R - rr) * SS + 0.5, 0, 1)
    img = put(img, ring, hexc("e8672b"))
    inner = np.clip((R * 0.80 - rr) * SS + 0.5, 0, 1)
    refl = mix(hexc("7fb8e6"), hexc("d7ecf6"), smoothstep(-R * 0.8, R * 0.3, Y1))
    refl = mix(refl, hexc("6e9c58"), smoothstep(R * 0.15, R * 0.45, Y1))
    refl = mix(refl, hexc("8d9097"), smoothstep(R * 0.35, R * 0.7, Y1) * smoothstep(R * 0.5, 0, np.abs(X1)))
    hl = np.exp(-(((X1 + R * 0.3) / (R * 0.18)) ** 2 + ((Y1 + R * 0.35) / (R * 0.10)) ** 2))
    refl = refl + 0.5 * hl[..., None]
    img = put(img, inner, refl)
    return img


# ---------------------------------------------------------------- 前景草


def grass(img, rng, n, xr, yr, hr, lean, lit_side=1.0, dark=False):
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    blades = []
    for _ in range(n):
        x = rng.uniform(*xr)
        yb = rng.uniform(*yr)
        h = rng.uniform(*hr)
        ln = lean + rng.normal(0, 0.35)
        w = rng.uniform(2.5, 6.0) * (h / 160) ** 0.5
        blades.append((yb, x, h, ln, w))
    blades.sort()
    for yb, x, h, ln, w in blades:
        pts_l, pts_r = [], []
        for t in np.linspace(0, 1, 9):
            bx = x + ln * h * t * t
            by = yb - h * t
            ww = w * (1 - t) ** 0.8
            pts_l.append(((bx - ww / 2) * SS, by * SS))
            pts_r.append(((bx + ww / 2) * SS, by * SS))
        shade = rng.uniform(0, 1)
        lit = (shade > 0.45) and not dark
        if lit:
            c0 = np.array([0.42, 0.66, 0.16]) + rng.uniform(-0.05, 0.08, 3) * np.array([1, 1, 0.3])
        else:
            c0 = np.array([0.10, 0.28, 0.16]) + rng.uniform(-0.03, 0.05, 3)
        c = tuple(int(v * 255) for v in np.clip(c0, 0, 1)) + (255,)
        d.polygon(pts_l + pts_r[::-1], fill=c)
        if lit:
            hl = [pts_r[i] for i in range(2, 9)]
            d.line(hl, fill=(214, 238, 120, 180), width=max(1, SS))
    return np.asarray(im, np.float32) / 255


def verge_grass(img, rng):
    """路两边近处的草丛（沿路边缘撒短草叶）。"""
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    items = []
    for side in (-1, 1):
        for _ in range(2600):
            Z = np.exp(rng.uniform(np.log(5.0), np.log(60.0)))
            off = ROAD_W / 2 + rng.uniform(-0.05, 1.1)
            X = road_xc(Z) + side * off
            x, y = g2s(X, Z)
            h = rng.uniform(0.15, 0.55) * F / Z
            items.append((y, x, h, side, Z))
    items.sort()
    for y, x, h, side, Z in items:
        ln = rng.normal(0, 0.3)
        lit = rng.random() > 0.4
        c0 = np.array([0.40, 0.66, 0.18]) if lit else np.array([0.18, 0.40, 0.16])
        c0 = c0 + rng.uniform(-0.05, 0.05, 3)
        fog = np.clip((Z - 20) / 200, 0, 0.5)
        c0 = c0 * (1 - fog) + np.array([0.61, 0.78, 0.76]) * fog
        c = tuple(int(v * 255) for v in np.clip(c0, 0, 1)) + (255,)
        w = max(0.6, 0.02 * F / Z)
        pts = [((x - w / 2) * SS, y * SS), ((x + ln * h * 0.3) * SS, (y - h) * SS), ((x + w / 2) * SS, y * SS)]
        d.polygon(pts, fill=c)
    return np.asarray(im, np.float32) / 255


def flowers(img, rng):
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    for _ in range(80):
        side = rng.choice([-1, 1])
        Z = np.exp(rng.uniform(np.log(5.5), np.log(25.0)))
        X = road_xc(Z) + side * (ROAD_W / 2 + rng.uniform(0.1, 1.0))
        x, y = g2s(X, Z)
        y -= rng.uniform(0.1, 0.4) * F / Z
        r = max(0.8, 0.026 * F / Z)
        col = (250, 250, 240, 235) if rng.random() < 0.7 else (250, 214, 70, 235)
        d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=col)
    return np.asarray(im, np.float32) / 255


# ---------------------------------------------------------------- 主流程


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)
    yy = (np.arange(H2, dtype=np.float32)[:, None] + 0.5) / SS * np.ones((1, W2), np.float32)
    img = sky_color(yy)
    xx = (np.arange(W2, dtype=np.float32)[None, :] + 0.5) / SS * np.ones((H2, 1), np.float32)
    glow = np.exp(-(((xx - 1650) / 520) ** 2 + ((yy + 60) / 420) ** 2))
    img = img + glow[..., None] * (hexc("d9eeff") - img) * 0.30
    # 远处的小积云、左右两团中积云、主积雨云
    for (cx, base, w, h, hz) in ((330, 512, 260, 40, 0.35), (1250, 505, 300, 48, 0.3), (560, 508, 180, 34, 0.35)):
        img = comp_cloud(img, small_cloud(rng, cx, base, w, h, 10, 30, 80), base, hz, cx)
    img = comp_cloud(img, small_cloud(rng, 170, 478, 360, 95, 20, 70, 140), 478, 0.12, 5)
    img = comp_cloud(img, small_cloud(rng, 1420, 486, 330, 85, 18, 60, 120), 486, 0.12, 7)
    img = comp_cloud(img, small_cloud(rng, 330, 150, 150, 26, 6, 18, 40), 150, 0.05, 9)
    sph, base = main_cloud(rng)
    img = comp_cloud(img, sph, base, 0.0, 11)
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im, "RGBA")
    for (bx, by, s) in ((432, 232, 7), (452, 220, 6), (470, 246, 5.5), (410, 250, 5)):
        for sgn in (-1, 1):
            pts = [((bx + sgn * s * t) * SS, (by - s * 0.45 * np.sin(np.pi * t) + s * 0.25 * t) * SS)
                   for t in np.linspace(0, 1, 8)]
            d.line(pts, fill=(40, 52, 78, 220), width=max(1, int(1.3 * SS)))
    img = np.asarray(im, np.float32) / 255
    img = mountains(img, rng)
    img = treeline(img, rng)
    img = ground_layer(img, rng)
    # 右侧远处农家与屋后的树
    img = canopy(img, rng, [(1110, 538, 0, 20), (1140, 530, 0, 24), (1170, 540, 0, 16)], 12, 40, 90,
                 (1070, 490, 1210, 552), hexc("8bbf45"), hexc("4f8a3a"), hexc("26504a"), haze=0.25, base_cut=550)
    img = farmhouse(img, 1085, 553, 64, 34)
    img = farmhouse(img, 1250, 546, 30, 16)
    # 左侧神社林：后面几棵杉树，前面樟树团
    img = cedars(img, rng, [(120, 520, 185, 78), (215, 512, 208, 88), (330, 518, 176, 74), (420, 524, 150, 62)])
    img = canopy(img, rng, [(160, 470, 0, 70), (270, 450, 10, 85), (380, 470, 0, 70), (70, 500, 0, 55),
                            (460, 505, 0, 45), (230, 510, 0, 60)],
                 60, 200, 520, (0, 330, 560, 572), hexc("9ccc4a"), hexc("4d8a34"), hexc("1f4a45"), haze=0.08,
                 base_cut=566)
    img = trunks(img, [(205, 530, 568, 7), (318, 535, 568, 8), (420, 540, 568, 6)])
    img = torii(img, 505, 569, 36)
    img = rice_strokes(img, rng)
    img = poles(img)
    img = curve_mirror(img)
    img = verge_grass(img, rng)
    img = flowers(img, rng)
    img = grass(img, rng, 420, (-40, 330), (905, 960), (80, 330), 0.25)
    img = grass(img, rng, 380, (1300, 1640), (905, 960), (80, 300), -0.2)
    # 光晕：云的亮部轻微泛光
    lum = img @ np.array([0.3, 0.59, 0.11], np.float32)
    bloom = ndi.gaussian_filter(np.clip(lum - 0.86, 0, 1), 18 * SS)
    img = img + bloom[..., None] * np.array([0.9, 0.95, 1.0], np.float32) * 1.2
    img = np.clip(img, 0, 1)
    out = Image.fromarray((img * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    o = np.asarray(out, np.float32) / 255
    yy1, xx1 = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx1 - W / 2) / (W * 0.7), (yy1 - H / 2) / (H * 0.7))
    o = o * (1 - 0.12 * smoothstep(0.6, 1.2, r))[..., None]
    out = Image.fromarray((np.clip(o, 0, 1) * 255).astype(np.uint8))
    out.save(os.path.join(HERE, "final.png"))
    if a.round:
        os.makedirs(os.path.join(HERE, "rounds"), exist_ok=True)
        out.save(os.path.join(HERE, "rounds", f"r{a.round}.png"))


if __name__ == "__main__":
    main()
