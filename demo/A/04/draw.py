#!/usr/bin/env python3
"""A04 雪地里一只回头看的红狐（A 赛道：只用代码画，不读任何图片、不联网）。

画法：
  背景  numpy 算天空渐变、三层雪松林（PIL 多边形 + 高斯虚化模拟景深）、透视雪地（噪声高度场 + 光照）、脚印。
  狐狸  各部位用 Catmull-Rom 样条轮廓，距离场算“圆管”法线做体积光照（左侧低角度暖光 + 天空冷光 + 雪地反光），
        再按毛流方向用 Pillow 画几万根短笔触当毛发；眼睛、鼻子、嘴线、胡须用解析形状单独画。
  最后  投影到雪面的影子、腿陷进雪里的雪线、飘雪、调色。
python3 draw.py  →  final.png（固定随机种子，可完全复现）
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1536, 1024
SEED = 404
HOR = 505.0            # 远处雪原与树林交界（相机很低，大约在狐狸肩高）
YG = 818.0             # 狐狸站立处的雪面（画面坐标）

# ---------------------------------------------------------------- 基础工具


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


class Noise:
    """周期值噪声：可在任意浮点坐标取样（三次样条插值），多倍频叠加。"""

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


def catmull(pts, closed=True, n=10):
    P = np.asarray(pts, np.float64)
    P = np.vstack([P[-1:], P, P[:2]]) if closed else np.vstack([P[:1], P, P[-1:]])
    out = []
    ts = np.linspace(0, 1, n, endpoint=False)
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in ts:
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    if not closed:
        out.append(P[-2])
    return np.array(out)


def to_img(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def from_img(im):
    return np.asarray(im, np.float32) / 255.0


def put(canvas, mask, color):
    return canvas * (1 - mask[..., None]) + color * mask[..., None]


# ---------------------------------------------------------------- 背景


def spruce(x, base, h, w, r):
    """一棵云杉的剪影：一层层下垂的枝梢。"""
    tiers = max(5, int(h / 15))
    Lp, Rp = [], []
    for i in range(tiers):
        f = i / tiers
        yt = base - f * h
        env = (1 - f) ** 1.1
        hl = w * 0.5 * env * (0.75 + 0.5 * r.random())
        hr = w * 0.5 * env * (0.75 + 0.5 * r.random())
        yn = yt - h / tiers * 0.8
        Lp += [(x - hl, yt + 3), (x - hl * 0.3, yn)]
        Rp += [(x + hr, yt + 3), (x + hr * 0.3, yn)]
    return [(x - w * 0.05, base + 40)] + Lp + [(x, base - h - 5)] + Rp[::-1] + [(x + w * 0.05, base + 40)]


def ground_to_screen(X, Z):
    return W * 0.5 + X * 900.0 / Z, HOR + 2600.0 / Z


def screen_to_ground(x, y):
    Z = 2600.0 / max(y - HOR, 0.5)
    return (x - W * 0.5) * Z / 900.0, Z


def background(nz, rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # 天空：上冷下暖，左上是低低的冬日太阳
    t = np.clip(yy / HOR, 0, 1)
    img = mix((0.62, 0.68, 0.77), (0.91, 0.88, 0.84), t ** 0.9)
    sun = np.exp(-(((xx - 100) / 650) ** 2 + ((yy - 280) / 380) ** 2))
    img = img + sun[..., None] * np.array([0.10, 0.07, 0.02], np.float32)
    # 三层雪松林：远的淡、近的深，都虚化（焦点在狐狸上）
    layers = [(70, (80, 160), 0.36, (0.70, 0.74, 0.79), 0.20, 2.0, HOR + 2),
              (40, (140, 250), 0.38, (0.50, 0.55, 0.60), 0.28, 2.8, HOR + 4),
              (22, (220, 390), 0.40, (0.27, 0.31, 0.33), 0.33, 3.8, HOR + 6)]
    for li, (n, (h0, h1), wf, col, snow, sig, base) in enumerate(layers):
        m = Image.new("L", (W * 2, H * 2), 0)
        d = ImageDraw.Draw(m)
        for x in np.sort(rng.uniform(-80, W + 80, n)):
            h = rng.uniform(h0, h1)
            d.polygon([(px * 2, py * 2) for px, py in spruce(x, base, h, h * wf, rng)], fill=255)
        m = np.asarray(m.resize((W, H), Image.BOX), np.float32) / 255
        sn = smoothstep(0.50, 0.62, nz(xx / 5 + 40 * li, yy / 3.2, octaves=2)) * snow
        c = mix(col, (0.92, 0.93, 0.95), sn)
        pm = ndi.gaussian_filter(m[..., None] * c, (sig, sig, 0))
        mb = ndi.gaussian_filter(m, sig)
        img = img * (1 - mb[..., None]) + pm
    # 林下一层淡淡的雾
    fog = np.exp(-((yy - HOR + 25) / 60) ** 2) * 0.45
    img = mix(img, (0.87, 0.88, 0.90), fog)

    # 透视雪地：平缓的雪浪
    dz = np.maximum(yy - HOR, 0.6)
    Z = 2600.0 / dz
    X = (xx - W * 0.5) * Z / 900.0
    amp = smoothstep(2, 90, dz)
    hgt = (nz(X / 5.0 + 7, Z / 2.6, octaves=4, pers=0.45) - 0.5) * amp
    gy, gx = np.gradient(hgt)
    dhdX = gx * 900.0 / Z
    dhdZ = gy * (-2600.0 / Z ** 2)
    A = 1.25
    nx, ny, nzz = -A * dhdX, np.ones_like(dhdX), -A * dhdZ
    nn = np.sqrt(nx * nx + ny * ny + nzz * nzz)
    Lw = np.array([-0.75, 0.40, -0.35])
    Lw /= np.linalg.norm(Lw)
    ndl = (nx * Lw[0] + ny * Lw[1] + nzz * Lw[2]) / nn
    shade = np.clip(0.88 + 1.3 * (ndl - Lw[1]), 0, 1.05)
    snow = mix((0.68, 0.75, 0.88), (0.99, 0.975, 0.95), np.clip(shade, 0, 1))
    # 雪面细微的颗粒
    snow = snow * (0.985 + 0.03 * nz(xx / 1.5, yy / 1.5, octaves=2))[..., None]
    snow = mix(snow, (0.86, 0.87, 0.90), np.exp(-dz / 30) * 0.85)
    # 近景树影（画面外的树投下来的淡蓝影子）
    fs = smoothstep(905, 975, yy + 40 * (nz(xx / 90, 2.0, octaves=3) - 0.5))
    snow = snow * (1 - 0.28 * fs[..., None] * np.array([0.30, 0.22, 0.05], np.float32) / 0.30)
    # 亮晶点
    sp = (rng.random((H, W)) > 0.9978) & (shade > 0.9) & (dz > 15) & (fs < 0.5)
    snow = snow + ndi.gaussian_filter(sp.astype(np.float32), 0.6)[..., None] * 1.5
    edge = smoothstep(HOR - 2.0, HOR + 2.0, yy + 5 * (nz(xx / 25, 3.0, octaves=3) - 0.5))
    img = img * (1 - edge[..., None]) + snow * edge[..., None]
    # 地平线处再蒙一层雾，把林子根部和雪原接起来
    img = mix(img, (0.88, 0.89, 0.91), np.exp(-((yy - HOR - 4) / 14) ** 2) * 0.55)
    img = footprints(img, rng)
    # 前景近处的雪也虚一点
    fb = smoothstep(880, 1020, yy)
    img = mix(img, ndi.gaussian_filter(img, (3, 3, 0)), fb)
    return np.clip(img, 0, 1.2).astype(np.float32)


def footprints(img, rng):
    """狐狸走过来的一串脚印：从左后方一直延伸到后脚。深雪里是一个个小坑。"""
    X0, Z0 = screen_to_ground(-40, 690)
    X1, Z1 = screen_to_ground(640, 822)
    L = np.hypot(X1 - X0, Z1 - Z0)
    n = int(L / 0.66)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    out = img.copy()
    for i in range(n):
        t = i / n
        X = X0 + (X1 - X0) * t + (0.06 if i % 2 else -0.06)
        Z = Z0 + (Z1 - Z0) * t
        sx, sy = ground_to_screen(X, Z)
        w = 0.19 * 900 / Z
        hgt = max(2.0, w * 0.42)
        x0, x1, y0, y1 = int(sx - w - 4), int(sx + w + 4), int(sy - hgt - 4), int(sy + hgt + 6)
        if x1 < 0 or x0 >= W:
            continue
        x0, y0 = max(x0, 0), max(y0, 0)
        X_, Y_ = xx[y0:y1, x0:x1], yy[y0:y1, x0:x1]
        r = np.hypot((X_ - sx) / w, (Y_ - sy) / hgt)
        hole = np.clip((1 - r) * 2.5, 0, 1)
        # 坑里：左侧（背光的坑壁）和靠近镜头的下沿发暗，右上被照亮
        k = smoothstep(-0.9, 0.7, (X_ - sx) / w * 0.8 - (Y_ - sy) / hgt * 0.6)
        sh = mix((0.55, 0.62, 0.80), (0.86, 0.89, 0.96), k)
        sub = out[y0:y1, x0:x1]
        sub = put(sub, hole * 0.85, sh)
        lip = np.clip(1 - np.abs(r - 1.15) * 5, 0, 1) * ((X_ - sx) > 0)
        sub = sub + 0.035 * lip[..., None]
        out[y0:y1, x0:x1] = sub
    return out


# ---------------------------------------------------------------- 狐狸几何（设计坐标，再整体放大到画面）

S2 = 2                                   # 狐狸图层 2 倍超采样
FX0, FY0, FX1, FY1 = 270, 215, 1160, 850
FW, FH = (FX1 - FX0) * S2, (FY1 - FY0) * S2
CX, CY, SC = 720.0, 795.0, 1.08          # 以脚下为中心放大（设计坐标 -> 画面坐标）

TORSO = [(630, 540), (700, 522), (790, 518), (870, 512), (930, 505), (985, 512), (1030, 535), (1058, 575),
         (1066, 620), (1054, 660), (1022, 690), (975, 706), (925, 704), (860, 690), (790, 680), (730, 672),
         (680, 664), (640, 650), (612, 620), (608, 580)]
NEAR_HIND = [(626, 552), (672, 548), (706, 578), (722, 628), (716, 670), (696, 704), (668, 742), (662, 774),
             (668, 836), (642, 836), (634, 792), (617, 764), (611, 722), (604, 672), (600, 625), (608, 580)]
FAR_HIND = [(700, 660), (738, 668), (744, 705), (730, 750), (728, 828), (704, 828), (702, 752), (700, 705)]
NEAR_FORE = [(972, 636), (1022, 636), (1022, 700), (1012, 752), (1010, 836), (984, 836), (984, 752), (978, 700)]
FAR_FORE = [(1012, 648), (1052, 648), (1056, 700), (1054, 750), (1062, 828), (1038, 828), (1030, 750), (1020, 700)]
NECK = [(960, 470), (1000, 440), (1040, 445), (1068, 480), (1078, 530), (1072, 585), (1050, 615), (1010, 600),
        (975, 560), (945, 530), (935, 500)]
THROAT = [(906, 490), (945, 488), (978, 494), (990, 512), (970, 530), (934, 527), (908, 510)]
TAIL_SPINE = [(622, 566), (575, 592), (520, 634), (468, 688), (426, 738), (392, 770), (362, 786)]
TAIL_W = [20, 36, 48, 54, 52, 44, 30]
LEG_X = (712, 1050, 656, 997)           # 远后、远前、近后、近前腿在雪面处的 x（设计坐标）

# 头：局部坐标（近侧眼睛为原点，x 向右，y 向下），再缩放平移到设计坐标
HX, HY, HK, HROT = 950.0, 438.0, 0.82, 0.0
HEAD = [(-15, -62), (25, -54), (58, -35), (80, -5), (94, 30), (74, 58), (35, 76), (-25, 74), (-68, 64), (-104, 56),
        (-124, 47), (-130, 36), (-122, 26), (-100, 18), (-84, 12), (-72, 5), (-80, -10), (-78, -34), (-52, -56)]
FACE_WHITE = [(-120, 42), (-100, 33), (-78, 27), (-55, 23), (-30, 22), (-8, 20), (15, 16), (40, 12), (70, 8),
              (90, 14), (98, 34), (78, 62), (35, 80), (-25, 78), (-68, 68), (-104, 60), (-124, 50)]
RUFF = [(40, 12), (74, 4), (94, 26), (88, 52), (60, 72), (20, 80), (-24, 78), (-50, 70), (-20, 56), (22, 38)]
FAR_EAR = [(-76, -34), (-88, -78), (-82, -122), (-74, -154), (-54, -122), (-36, -86), (-20, -56)]
FAR_EAR_IN = [(-72, -46), (-78, -88), (-73, -138), (-56, -110), (-42, -80), (-30, -60)]
NEAR_EAR = [(4, -56), (18, -100), (38, -140), (54, -158), (66, -122), (72, -80), (64, -34)]
NEAR_EAR_IN = [(12, -62), (24, -100), (42, -138), (52, -112), (48, -72), (38, -52)]


def to_glob(x, y):
    return CX + SC * (x - CX), CY + SC * (y - CY)


def to_design(gx, gy):
    return CX + (gx - CX) / SC, CY + (gy - CY) / SC


def head_pt(u, v):
    c, s = np.cos(np.radians(HROT)), np.sin(np.radians(HROT))
    return (HX + HK * (c * u - s * v), HY + HK * (s * u + c * v))


def head_pts(lst):
    return [head_pt(u, v) for u, v in lst]


def lay(pts):
    out = []
    for x, y in pts:
        gx, gy = to_glob(x, y)
        out.append(((gx - FX0) * S2, (gy - FY0) * S2))
    return out


def pmask(pts, smooth=True, ss=2):
    q = lay(catmull(pts) if smooth else pts)
    im = Image.new("L", (FW * ss, FH * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in q], fill=255)
    return np.asarray(im.resize((FW, FH), Image.BOX), np.float32) / 255.0


def tail_outline():
    sp = catmull(TAIL_SPINE, closed=False, n=12)
    wv = np.interp(np.linspace(0, 1, len(sp)), np.linspace(0, 1, len(TAIL_W)), TAIL_W)
    d = np.gradient(sp, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    left, right = sp + nrm * wv[:, None], sp - nrm * wv[:, None]
    cap = [sp[-1] + wv[-1] * (np.cos(a) * nrm[-1] + np.sin(a) * d[-1]) for a in np.linspace(0, np.pi, 11)]
    return np.vstack([left, cap, right[::-1]]), sp, wv, d, nrm


# ---------------------------------------------------------------- 光照

LIGHT = np.array([-0.72, -0.45, 0.53])
LIGHT /= np.linalg.norm(LIGHT)
AMB = np.array([0.62, 0.67, 0.80], np.float32)
KEY = np.array([1.12, 0.97, 0.80], np.float32)
BOUNCE = np.array([0.55, 0.62, 0.76], np.float32)


def tube_normals(mask, R, smooth=3.0):
    m = mask > 0.5
    d = ndi.distance_transform_edt(m).astype(np.float32)
    d = ndi.gaussian_filter(d, smooth)
    t = np.clip(d / R, 0, 1)
    h = np.sqrt(np.clip(1 - (1 - t) ** 2, 0, 1)) * R
    gy, gx = np.gradient(h)
    nx, ny, nz_ = -gx, -gy, np.ones_like(gx)
    nn = np.sqrt(nx * nx + ny * ny + nz_ * nz_) + 1e-6
    return nx / nn, ny / nn, nz_ / nn


def lit(base, normals, occl=None, amb=0.52, key=0.90, bounce=0.40, rim=0.55):
    nx, ny, nz_ = normals
    ndl = nx * LIGHT[0] + ny * LIGHT[1] + nz_ * LIGHT[2]
    k = np.clip((ndl + 0.25) / 1.25, 0, 1) ** 1.3
    r2 = np.clip(nx * LIGHT[0] + ny * LIGHT[1], 0, 1) * (1 - nz_) ** 1.5
    if occl is not None:
        k = k * (1 - occl)
        r2 = r2 * (1 - occl)
    b = np.clip(ny, 0, 1)
    lv = AMB * amb + KEY * (key * k + rim * r2)[..., None] + BOUNCE * (bounce * b)[..., None]
    return base * lv


def dirn(dx, dy):
    n = np.hypot(dx, dy) + 1e-6
    return dx / n, dy / n


# ---------------------------------------------------------------- 毛发笔触


def strokes(img, mask, colimg, dirfn, rng, step, length, width, jit=0.22, alpha=(0.55, 0.95), bright=0.13,
            curl=0.2, lighten=0.0, thresh=0.5):
    """在 mask 里随机撒点，每点顺着毛流方向画一根两段式、渐细的短线，颜色取该点的受光颜色再随机明暗。"""
    ys, xs = np.nonzero(mask > 0.02)
    if len(ys) == 0:
        return
    wgt = mask[ys, xs].astype(np.float64)
    wgt = np.where(wgt > thresh, 1.0, wgt / thresh * 0.5)
    n = int(wgt.sum() / step)
    idx = rng.choice(len(ys), n, p=wgt / wgt.sum())
    py = ys[idx] + rng.random(n)
    px = xs[idx] + rng.random(n)
    dx_, dy_ = to_design(px / S2 + FX0, py / S2 + FY0)
    dx, dy = dirfn(dx_, dy_)
    ang = np.arctan2(dy, dx) + rng.normal(0, jit, n)
    Ls = length * S2 * SC * (0.55 + 0.9 * rng.random(n))
    cu = rng.normal(0, curl, n)
    base = colimg[ys[idx], xs[idx]]
    b = np.clip(1 + rng.normal(0, bright, n) + lighten * rng.random(n), 0.4, 1.7)
    cols = np.clip(base * b[:, None], 0, 1)
    al = rng.uniform(alpha[0], alpha[1], n)
    wd = width * S2 * SC * (0.6 + 0.7 * rng.random(n))
    a1, a2 = ang + 0.5 * cu, ang + 1.5 * cu
    x1, y1 = px + 0.5 * Ls * np.cos(a1), py + 0.5 * Ls * np.sin(a1)
    x2, y2 = x1 + 0.5 * Ls * np.cos(a2), y1 + 0.5 * Ls * np.sin(a2)
    C = (cols * 255).astype(int).tolist()
    A = (al * 255).astype(int).tolist()
    Wd = np.maximum(1, np.round(wd)).astype(int).tolist()
    P0 = np.stack([px, py], 1).tolist()
    P1 = np.stack([x1, y1], 1).tolist()
    P2 = np.stack([x2, y2], 1).tolist()
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(n):
        c = C[i]
        d.line([tuple(P0[i]), tuple(P1[i])], fill=(c[0], c[1], c[2], A[i]), width=Wd[i])
        d.line([tuple(P1[i]), tuple(P2[i])], fill=(c[0], c[1], c[2], int(A[i] * 0.7)), width=max(1, Wd[i] - 1))


# ---------------------------------------------------------------- 颜色

ORANGE = (0.80, 0.40, 0.14)
RUFOUS = (0.56, 0.23, 0.09)
GOLD = (0.88, 0.57, 0.27)
WHITE = (0.96, 0.94, 0.90)
CREAM = (0.92, 0.85, 0.74)
BLACK = (0.10, 0.07, 0.06)
DARKB = (0.19, 0.12, 0.08)
BELLY = (0.72, 0.60, 0.50)


def lens(u, v, hw, ht, hb):
    t = np.clip(1 - (u / hw) ** 2, 0, 1)
    sd = np.minimum(v + ht * t, hb * t - v)
    return np.clip(sd + 0.5, 0, 1) * (np.abs(u) < hw)


def draw_eye(cv, cx, cy, hw, ht, hb, ang, look=(0.0, 0.0)):
    """杏仁形眼睛：黑眼线、琥珀色虹膜（上眼睑投影）、竖瞳孔、高光。坐标为图层像素。"""
    x0, x1, y0, y1 = int(cx - hw - 14), int(cx + hw + 14), int(cy - hw - 14), int(cy + hw + 14)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    c, s = np.cos(ang), np.sin(ang)
    X, Y = xx - cx, yy - cy
    u, v = c * X + s * Y, -s * X + c * Y
    sub = cv[y0:y1, x0:x1]
    rim = lens(u, v, hw + 4.0, ht + 3.2, hb + 3.0)
    sub = put(sub, rim, np.array((0.07, 0.05, 0.04), np.float32))
    inner = lens(u, v, hw, ht, hb)
    ri = (ht + hb) * 0.62
    icx, icy = cx + look[0] * hw, cy + look[1] * hb + (hb - ht) * 0.25
    r = np.hypot(xx - icx, yy - icy) / ri
    iris = mix((0.98, 0.80, 0.36), (0.72, 0.40, 0.08), np.clip(r, 0, 1) ** 1.4)
    iris = mix(iris, (0.40, 0.20, 0.05), smoothstep(0.85, 1.05, r))
    iris = mix(iris, (0.30, 0.17, 0.07), smoothstep(1.0, 1.15, r))
    lid = smoothstep(-ht * 1.0, ht * 0.15, v)
    iris = iris * (0.45 + 0.55 * lid)[..., None]
    pup = np.clip((1 - np.hypot((xx - icx) / (ri * 0.20), (yy - icy) / (ri * 0.70))) * ri * 0.5 + 0.5, 0, 1)
    iris = put(iris, pup, np.array((0.03, 0.02, 0.02), np.float32))
    hl = np.clip((ri * 0.20 - np.hypot(xx - (icx - ri * 0.38), yy - (icy - ri * 0.36))) + 0.5, 0, 1)
    iris = put(iris, hl * 0.95, np.array((1.0, 0.98, 0.95), np.float32))
    hl2 = np.clip((ri * 0.09 - np.hypot(xx - (icx + ri * 0.30), yy - (icy + ri * 0.30))) + 0.5, 0, 1)
    iris = put(iris, hl2 * 0.5, np.array((1.0, 0.95, 0.85), np.float32))
    sub = put(sub, inner, iris)
    cv[y0:y1, x0:x1] = sub


def seg_dist(U, V, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = np.clip(((U - a[0]) * vx + (V - a[1]) * vy) / (vx * vx + vy * vy), 0, 1)
    return np.hypot(U - a[0] - t * vx, V - a[1] - t * vy), t


def paint_fox(bg2, nz, rng):
    cv = bg2.copy()
    LY, LX = np.mgrid[0:FH, 0:FW].astype(np.float32)
    GX, GY = LX / S2 + FX0, LY / S2 + FY0
    DX, DY = to_design(GX, GY)
    mott = nz(DX / 7, DY / 7, octaves=3)
    big = nz(DX / 40 + 11, DY / 40, octaves=2)

    def paint(mask, base, R, dirfn, st, occl=None, fill_dark=0.88, lightk=None, shape=None):
        nonlocal cv
        nrm = tube_normals(mask if shape is None else shape, R * S2 * SC)
        col = lit(base, nrm, occl, **(lightk or {}))
        cv = put(cv, mask, col * fill_dark)
        im = to_img(cv)
        for kw in st:
            strokes(im, mask, col, dirfn, rng, **kw)
        cv = from_img(im)
        return col

    down = lambda sx: (lambda x, y: dirn(sx + 0 * x, 1 + 0 * y))   # noqa: E731

    # ---- 远侧两条腿（在身体的影子里，更暗更冷）
    for poly in (FAR_HIND, FAR_FORE):
        m = pmask(poly)
        base = mix(mix(ORANGE, DARKB, 0.4), DARKB, smoothstep(680, 730, DY)) * 0.62
        paint(m, base, 14, down(-0.1), [dict(step=10, length=7, width=1.2, lighten=0.2)])

    # ---- 尾巴
    outline, sp, wv, td, tn = tail_outline()
    tm = pmask(outline, smooth=False)
    spL = np.array(lay(sp))
    tree = cKDTree(spL)
    _, ti = tree.query(np.stack([LX.ravel(), LY.ravel()], 1), workers=-1)
    ti = ti.reshape(LX.shape)
    tu = ti / (len(sp) - 1)
    wl = wv * S2 * SC
    side = ((LX - spL[ti, 0]) * tn[ti, 0] + (LY - spL[ti, 1]) * tn[ti, 1]) / wl[ti]   # -1..1，正为上侧
    tb = mix(ORANGE, RUFOUS, 0.25 + 0.35 * np.clip(side, 0, 1))
    tb = mix(tb, (0.30, 0.20, 0.14), 0.45 * smoothstep(0.35, 0.7, tu) * (0.6 + 0.4 * mott))   # 黑色针毛
    tb = mix(tb, CREAM, 0.35 * np.clip(-side, 0, 1) * smoothstep(0.1, 0.5, tu))               # 尾巴下侧浅
    tb = mix(tb, WHITE, smoothstep(0.78, 0.86, tu + 0.05 * (mott - 0.5)))                    # 白尾尖
    tb = tb * (0.9 + 0.2 * mott)[..., None]

    def tail_dir(x, y):
        gx, gy = to_glob(x, y)
        lx, ly = (gx - FX0) * S2, (gy - FY0) * S2
        _, i = tree.query(np.stack([lx, ly], 1), workers=-1)
        sd = ((lx - spL[i, 0]) * tn[i, 0] + (ly - spL[i, 1]) * tn[i, 1]) / wl[i]
        return dirn(td[i, 0] + 0.75 * sd * tn[i, 0], td[i, 1] + 0.75 * sd * tn[i, 1])

    paint(tm, tb, 45, tail_dir, [dict(step=16, length=20, width=1.6, jit=0.18, curl=0.15),
                                 dict(step=30, length=26, width=1.2, jit=0.25, curl=0.2, lighten=0.25)])

    # ---- 身体
    torso = pmask(TORSO)
    headm = pmask(head_pts(HEAD))
    neckm = pmask(NECK)
    v = np.clip((DY - 510) / 190, 0, 1)
    b = mix(RUFOUS, ORANGE, smoothstep(0.0, 0.40, v + 0.1 * (big - 0.5)))
    b = mix(b, GOLD, 0.55 * smoothstep(0.45, 0.85, v))
    b = mix(b, (0.40, 0.17, 0.07), 0.35 * smoothstep(0.14, 0.0, v) * smoothstep(640, 720, DX))   # 背脊深色
    b = mix(b, BELLY, 0.7 * smoothstep(0.88, 1.0, v + 0.06 * (mott - 0.5)))
    chest = smoothstep(1030, 1056, DX + 14 * (mott - 0.5)) * smoothstep(560, 610, DY)
    b = mix(b, WHITE, chest)
    b = b * (0.9 + 0.2 * mott)[..., None]

    def torso_dir(x, y):
        t = np.clip((y - 512) / 190, 0, 1)
        dx, dy = -1 + 0.6 * t, 0.15 + 1.1 * t
        f = np.clip((x - 1000) / 55, 0, 1)
        dx, dy = dx * (1 - f) + 0.1 * f, dy * (1 - f) + 1.0 * f
        r = np.clip((660 - x) / 60, 0, 1)
        dx, dy = dx * (1 - r) - 0.7 * r, dy * (1 - r) + 0.7 * r
        return dirn(dx, dy)

    occ_t = np.clip(ndi.gaussian_filter(np.roll(np.maximum(headm, neckm), (26, 34), (0, 1)), 14) * 0.55, 0, 1)
    paint(torso, b, 85, torso_dir, [dict(step=14, length=13, width=1.7),
                                    dict(step=40, length=16, width=1.2, lighten=0.3, jit=0.3)], occl=occ_t)

    # ---- 近侧后腿（大腿 + 跗关节）、前腿（黑“袜子”）
    nh0 = pmask(NEAR_HIND)
    inside = ndi.gaussian_filter(ndi.binary_erosion(torso > 0.5, iterations=6).astype(np.float32), 3)
    nh = (nh0 * (1 - inside) + ndi.gaussian_filter(nh0, 5) * inside) * smoothstep(565, 630, DY)
    b = mix(mix(RUFOUS, ORANGE, smoothstep(550, 640, DY)), DARKB, smoothstep(712, 752, DY))
    b = mix(b, CREAM, 0.30 * smoothstep(625, 600, DX) * smoothstep(610, 670, DY) * (1 - smoothstep(705, 740, DY)))
    b = b * (0.9 + 0.2 * mott)[..., None]
    paint(nh, b, 32, down(-0.3), [dict(step=12, length=10, width=1.5), dict(step=40, length=12, width=1.1,
                                                                                 lighten=0.35)],
          shape=np.maximum(nh0, torso))
    nf0 = pmask(NEAR_FORE)
    nf = (nf0 * (1 - inside) + ndi.gaussian_filter(nf0, 4) * inside) * smoothstep(646, 692, DY)
    b = mix(ORANGE, DARKB, smoothstep(655, 700, DY + 10 * (mott - 0.5)))
    b = b * (0.9 + 0.2 * mott)[..., None]
    paint(nf, b, 13, down(-0.05), [dict(step=10, length=8, width=1.3), dict(step=30, length=9, width=1.0,
                                                                                 lighten=0.4)],
          shape=np.maximum(nf0, torso))

    # ---- 脖子（毛领）
    b = mix(ORANGE, RUFOUS, 0.35 * smoothstep(1020, 1075, DX) * smoothstep(560, 470, DY))
    b = mix(b, WHITE, smoothstep(1045, 1070, DX + 10 * (mott - 0.5)) * smoothstep(545, 600, DY))
    b = b * (0.92 + 0.16 * mott)[..., None]
    occ_n = np.clip(ndi.gaussian_filter(np.roll(headm, (22, 30), (0, 1)), 12) * 0.65, 0, 1)
    paint(neckm, b, 60, lambda x, y: dirn(x - 960, y - 400),
          [dict(step=12, length=16, width=1.6, jit=0.3), dict(step=30, length=20, width=1.2, lighten=0.3)], occl=occ_n)
    # 下巴底下露出的白喉
    thm = pmask(THROAT)
    paint(thm, np.broadcast_to(np.array(WHITE, np.float32), cv.shape) * (0.92 + 0.1 * mott)[..., None], 30,
          lambda x, y: dirn(0.25 + 0 * x, 1 + 0 * y), [dict(step=7, length=11, width=1.4, jit=0.35, curl=0.3)],
          occl=np.clip(ndi.gaussian_filter(np.roll(headm, (14, 6), (0, 1)), 8) * 0.5, 0, 1),
          lightk=dict(amb=0.82, key=0.75, bounce=0.2))

    # ---- 耳朵（先画，头盖住耳根）
    c_, s_ = np.cos(np.radians(HROT)), np.sin(np.radians(HROT))
    U = ((DX - HX) * c_ + (DY - HY) * s_) / HK
    V = (-(DX - HX) * s_ + (DY - HY) * c_) / HK
    for outer, inner, tipuv in ((FAR_EAR, FAR_EAR_IN, (-74, -154)), (NEAR_EAR, NEAR_EAR_IN, (54, -158))):
        mo = pmask(head_pts(outer))
        tip = head_pt(*tipuv)
        base = mix(RUFOUS, BLACK, smoothstep(-70, -105, V + 8 * (mott - 0.5)))
        cen = np.mean(np.array(head_pts(outer)), 0)
        paint(mo, base, 16, lambda x, y, t=tip, cc=cen: dirn(t[0] - cc[0] + 0 * x, t[1] - cc[1] + 0 * y),
              [dict(step=8, length=6, width=1.2)])
        mi = pmask(head_pts(inner))
        ib = mix(CREAM, (0.45, 0.33, 0.28), smoothstep(-60, -115, V) * 0.55)
        paint(mi, ib, 12, lambda x, y, t=tip: dirn(t[0] - x, t[1] - y),
              [dict(step=6, length=9, width=1.1, lighten=0.2, jit=0.35)], lightk=dict(amb=0.75, key=0.6))

    # ---- 头
    fw = ndi.gaussian_filter(pmask(head_pts(FACE_WHITE)), 2.5)
    fw = np.clip(fw * (0.9 + 0.25 * mott), 0, 1)
    b = mix(ORANGE, RUFOUS, 0.55 * smoothstep(-20, -58, V))                         # 头顶偏深
    b = mix(b, RUFOUS, 0.35 * smoothstep(-40, -100, U) * smoothstep(40, 5, V))      # 鼻梁偏深
    b = mix(b, GOLD, 0.35 * np.exp(-((U + 5) ** 2 + (V + 14) ** 2) / 500))          # 眼周略浅
    b = mix(b, WHITE, fw)
    dd, tt = seg_dist(U, V, (-12, 4), (-44, 31))                                    # 泪线：内眼角斜向嘴角
    b = mix(b, (0.24, 0.12, 0.06), 0.8 * np.exp(-(dd / (4.2 - 1.8 * tt)) ** 2) * (1 - 0.55 * tt))
    dd, _ = seg_dist(U, V, (-112, 40), (-86, 44))                                   # 胡须垫上的深色
    b = mix(b, (0.30, 0.22, 0.18), 0.5 * np.exp(-(dd / 4.0) ** 2))
    b = b * (0.92 + 0.16 * mott)[..., None]
    nose = head_pt(-126, 36)
    paint(headm, b, 55, lambda x, y: dirn(x - nose[0], y - nose[1] + 0.3 * (x - nose[0])),
          [dict(step=7, length=6, width=1.2, jit=0.18), dict(step=25, length=8, width=1.0, lighten=0.3)],
          lightk=dict(amb=0.58, key=0.85))
    # 脸颊毛领：长而蓬松、向外翻
    rm = pmask(head_pts(RUFF)) * (fw > 0.3)
    cen = head_pt(-10, 10)
    wcol = lit(np.broadcast_to(np.array(WHITE, np.float32), cv.shape).copy(), tube_normals(headm, 55 * S2 * SC),
               amb=0.84, key=0.72, bounce=0.2)
    im = to_img(cv)
    strokes(im, rm, wcol, lambda x, y: dirn(x - cen[0], y - cen[1] + 0.2 * (x - cen[0])), rng, step=6, length=10,
            width=1.3, jit=0.3, curl=0.25)
    cv = from_img(im)

    # ---- 五官细节
    def P(u, v_):
        return lay([head_pt(u, v_)])[0]

    k2 = HK * S2 * SC
    im = to_img(cv)
    d = ImageDraw.Draw(im, "RGBA")
    mouth = [P(-117, 49), P(-100, 53.5), P(-80, 56.5), P(-62, 58), P(-46, 57), P(-38, 54)]
    for i in range(len(mouth) - 1):
        d.line([mouth[i], mouth[i + 1]], fill=(28, 18, 14, int(235 - 25 * i)), width=max(2, int(4.5 - 0.5 * i)))
    cv = from_img(im)
    # 鼻子
    nx0, ny0 = P(-121, 36)
    ang = np.radians(-12)
    x0, x1, y0, y1 = int(nx0 - 40), int(nx0 + 40), int(ny0 - 40), int(ny0 + 40)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    uu = (xx - nx0) * np.cos(ang) + (yy - ny0) * np.sin(ang)
    vv = -(xx - nx0) * np.sin(ang) + (yy - ny0) * np.cos(ang)
    rr = ((np.abs(uu) / (10 * k2)) ** 2.4 + (np.abs(vv) / (7.8 * k2)) ** 2.4) ** (1 / 2.4)
    nm = np.clip((1 - rr) * 10 * k2 * 0.6 + 0.5, 0, 1)
    ncol = mix((0.07, 0.06, 0.06), (0.40, 0.38, 0.40), smoothstep(0.2, -0.9, vv / (7.8 * k2)) * 0.8)
    cv[y0:y1, x0:x1] = put(cv[y0:y1, x0:x1], nm, ncol)
    # 眼睛
    ex, ey = P(0, 0)
    draw_eye(cv, ex, ey, 14.5 * k2, 7.2 * k2, 5.6 * k2, np.radians(-15), look=(-0.12, 0.0))
    ex, ey = P(-62, -8)
    draw_eye(cv, ex, ey, 9.5 * k2, 6.0 * k2, 4.6 * k2, np.radians(12), look=(-0.1, 0.0))
    # 胡须
    im = to_img(cv)
    d = ImageDraw.Draw(im, "RGBA")
    wr = np.random.default_rng(SEED + 5)
    for k in range(9):
        u0, v0 = -104 + wr.uniform(-10, 12), 42 + wr.uniform(-5, 5)
        a = np.radians(wr.uniform(150, 205))
        Lw_ = wr.uniform(40, 75)
        pts = [P(u0 + Lw_ * t * np.cos(a), v0 + Lw_ * t * np.sin(a) + 10 * t * t) for t in np.linspace(0, 1, 6)]
        d.line(pts, fill=(25, 20, 18, 150) if k % 3 else (235, 232, 228, 150), width=2)
    for k in range(5):
        u0, v0 = -80 + wr.uniform(-8, 8), 44 + wr.uniform(-4, 4)
        a = np.radians(wr.uniform(15, 45))
        Lw_ = wr.uniform(35, 60)
        pts = [P(u0 + Lw_ * t * np.cos(a), v0 + Lw_ * t * np.sin(a) + 6 * t * t) for t in np.linspace(0, 1, 6)]
        d.line(pts, fill=(240, 238, 235, 130), width=2)
    cv = from_img(im)

    # ---- 背上、头顶落的雪（只在朝上的边缘）
    fox_m = np.clip(torso * (1 - headm), 0, 1)
    top = fox_m * (1 - ndi.shift(fox_m, (14, 0), order=0)) * (DX < 900)
    ys, xs = np.nonzero(top > 0.5)
    im = to_img(cv)
    d = ImageDraw.Draw(im, "RGBA")
    for i in rng.integers(0, len(ys), 7):
        x, y = xs[i] + rng.normal(0, 6), ys[i] + rng.uniform(4, 30)
        r = rng.uniform(1.5, 3.4)
        d.ellipse([x - r, y - r + 1.5, x + r, y + r + 1.5], fill=(150, 160, 185, 90))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(246, 247, 250, 230))
    cv = from_img(im)

    # ---- 腿陷进雪里：雪线以下恢复成雪，腿边有一圈被踩开的雪
    xs1 = np.arange(FW) / S2 + FX0
    ycut = YG + 2.5 * np.sin(xs1 / 17.0) + 1.5 * np.sin(xs1 / 5.3)
    legs_g = [to_glob(x, YG)[0] for x in LEG_X]
    for cxl, hgt in zip(legs_g, (10, 10, 5, 5)):
        ycut = ycut - hgt * np.exp(-((xs1 - cxl) / 22) ** 2)
    ycut2 = (ycut - FY0) * S2
    ms = smoothstep(ycut2[None, :] - 1.0, ycut2[None, :] + 1.0, LY)
    legm = np.clip(pmask(NEAR_FORE) + pmask(NEAR_HIND) + pmask(FAR_FORE) + pmask(FAR_HIND) + tm, 0, 1)
    anyleg = np.clip(ndi.gaussian_filter(ndi.maximum_filter(legm, size=(1, 30)), 6), 0, 1)
    lip = np.exp(-((LY - ycut2[None, :] - 3) / 3.0) ** 2) * anyleg
    hole = np.exp(-((LY - ycut2[None, :] - 10) / 8.0) ** 2) * anyleg
    snowc = bg2 * (1 - 0.22 * hole[..., None] * np.array([1.0, 0.8, 0.45], np.float32))
    snowc = snowc + 0.05 * lip[..., None]
    # 每条腿前面被带起的一小堆雪：左边受光、右边发蓝
    for cxl in legs_g:
        lx = (cxl - FX0) * S2
        ly = (np.interp(cxl, xs1, ycut) - FY0) * S2 + 6
        rx, ry = 34.0, 11.0
        q = np.hypot((LX - lx) / rx, (LY - ly) / ry)
        mound = np.clip((1 - q) * 4, 0, 1) * (LY > ly - ry)
        k = smoothstep(-1, 1, -(LX - lx) / rx * 0.9 - (LY - ly) / ry * 0.5)
        mc = mix((0.72, 0.78, 0.90), (1.0, 0.985, 0.96), k)
        snowc = put(snowc, mound, mc)
    cv = cv * (1 - ms[..., None]) + snowc * ms[..., None]
    return cv


def fox_union_mask():
    outline = tail_outline()[0]
    m = np.zeros((FH, FW), np.float32)
    for p, sm in ((TORSO, True), (NEAR_HIND, True), (FAR_HIND, True), (NEAR_FORE, True), (FAR_FORE, True),
                  (NECK, True), (head_pts(HEAD), True), (head_pts(FAR_EAR), True), (head_pts(NEAR_EAR), True),
                  (outline, False)):
        m = np.maximum(m, pmask(p, smooth=sm))
    full = np.zeros((H, W), np.float32)
    full[FY0:FY1, FX0:FX1] = m.reshape(FH // S2, S2, FW // S2, S2).mean((1, 3))
    return full


def ground_shadow(img, fm):
    """太阳在左前方低处：狐狸的影子被拉长投到右后方的雪面上。"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    b, a = 0.085, 0.95
    h = (YG - yy) / b
    valid = (yy <= YG + 2) & (h < 560)
    sx, sy = xx - a * h, YG - np.maximum(h, 0)
    s = ndi.map_coordinates(fm, [sy, sx], order=1, mode="constant", cval=0) * valid
    s = 0.5 * ndi.gaussian_filter(s, 2) + 0.5 * ndi.gaussian_filter(s, 6)
    s = s * smoothstep(HOR + 20, HOR + 60, yy)
    tint = np.array([0.70, 0.78, 0.93], np.float32)
    return img * (1 - 0.75 * s[..., None] * (1 - tint))


def snowfall(img, rng):
    acc = np.zeros((H, W), np.float32)
    for n, sig, amp in ((1400, 0.7, 1.0), (500, 1.3, 1.6), (110, 2.4, 2.4)):
        lay_ = np.zeros((H, W), np.float32)
        ys, xs = rng.integers(0, H, n), rng.integers(0, W, n)
        np.add.at(lay_, (ys, xs), amp * rng.uniform(0.5, 1.0, n))
        acc += ndi.gaussian_filter(lay_, sig) * (2 * np.pi * sig * sig) ** 0.5
    big = np.zeros((H, W), np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for cx, cy in ((60, 880), (1450, 780), (1300, 965)):
        r = rng.uniform(9, 18)
        big += np.clip((r - np.hypot(xx - cx, yy - cy)) / 3.0, 0, 1) * rng.uniform(0.15, 0.28)
    big = ndi.gaussian_filter(big, 2.0)
    a = np.clip(acc * 0.55 + big, 0, 0.95)
    return img * (1 - a[..., None]) + np.array([0.97, 0.98, 1.0], np.float32) * a[..., None]


def grade(img):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx - W * 0.55) / (W * 0.7), (yy - H * 0.5) / (H * 0.75))
    vig = 1 - 0.18 * smoothstep(0.55, 1.25, r)
    img = img * vig[..., None]
    lum = img @ np.array([0.299, 0.587, 0.114], np.float32)
    img = img + (0.03 * smoothstep(0.5, 0.95, lum))[..., None] * np.array([1.0, 0.5, -0.4], np.float32)
    return np.clip(img, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--crop", default="")
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)
    nz = Noise(SEED)
    img = background(nz, rng)
    fm = fox_union_mask()
    img = ground_shadow(img, fm)
    crop = img[FY0:FY1, FX0:FX1]
    bg2 = from_img(to_img(crop).resize((FW, FH), Image.BICUBIC))
    fox2 = paint_fox(bg2, nz, rng)
    img[FY0:FY1, FX0:FX1] = fox2.reshape(FH // S2, S2, FW // S2, S2, 3).mean((1, 3))
    img = snowfall(img, np.random.default_rng(SEED + 1))
    img = grade(img)
    out = to_img(img)
    out.save(os.path.join(HERE, "final.png"))
    if a.round:
        os.makedirs(os.path.join(HERE, "rounds"), exist_ok=True)
        out.save(os.path.join(HERE, "rounds", f"r{a.round}.png"))
    if a.crop:
        out.crop((740, 240, 1140, 540)).resize((800, 600), Image.LANCZOS).save(a.crop)


if __name__ == "__main__":
    main()
