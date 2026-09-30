#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A09 书桌一角：台灯、打开的书、一杯咖啡、一盆绿植（纯代码，不用任何模型、不读任何图片）。

画法：numpy 光线追踪。
- 物体（摇臂台灯、打开的书、咖啡杯+碟、陶盆绿萝、铅笔）都是有向距离场（SDF），球面追踪求交：
  杯子/碟子/花盆用二维截面绕轴旋转得到，书页是高度场，叶子是弯曲的薄片。
- 桌面、墙、地面是解析平面；桌面木纹、书上的字行、陶土、叶脉都是程序化纹理。
- 光：台灯灯泡是点光源，灯罩限定成锥形光，SDF 软阴影 + AO；另有冷色的夜间环境光、书页的暖色反光、
  墙上的漫射光晕。最后加咖啡热气（2D）、轻微景深、泛光、色调映射。2 倍超采样。
运行：python3 draw.py [另存路径...]  → final.png
"""
import math
import os
import sys
import time

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, SS = 1536, 1024, 2
RW, RH = W * SS, H * SS
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


def lin(*c):
    return np.power(np.asarray(c, np.float32), 2.2)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mix3(a, b, t):
    t = np.asarray(t, np.float32)
    if t.ndim == 1:
        t = t[:, None]
    return a * (1 - t) + b * t


# ---------------------------------------------------------------- noise
M32 = 0xFFFFFFFF


def _h(ix, iy, seed):
    s = np.asarray(seed, np.int64)
    h = (ix * 374761393 + iy * 668265263 + s * 1442695041 + 12345) & M32
    h = ((h ^ (h >> 13)) * 1274126177) & M32
    h = (h ^ (h >> 16)) & 0xFFFFFF
    return h.astype(np.float32) * np.float32(1.0 / 16777216.0)


def vnoise(x, y, seed=0):
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    xf, yf = np.floor(x), np.floor(y)
    fx, fy = x - xf, y - yf
    ix, iy = xf.astype(np.int64), yf.astype(np.int64)
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = _h(ix, iy, seed)
    b = _h(ix + 1, iy, seed)
    c = _h(ix, iy + 1, seed)
    d = _h(ix + 1, iy + 1, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def fbm(x, y, octaves=4, seed=0, gain=0.5):
    x = np.asarray(x, np.float32)
    y = np.asarray(y, np.float32)
    tot = np.zeros(np.broadcast(x, y).shape, np.float32)
    amp, norm = 1.0, 0.0
    for i in range(octaves):
        tot += np.float32(amp) * vnoise(x, y, seed + 101 * i)
        norm += amp
        amp *= gain
        x, y = 1.6 * x + 1.2 * y + 3.1, -1.2 * x + 1.6 * y + 7.7
    return tot / np.float32(norm)


# ---------------------------------------------------------------- camera
CAMP = np.array([0.72, 0.60, -0.70])
TGT = np.array([-0.06, 0.11, 0.10])
HFOV = math.radians(50.0)
FW = unit(TGT - CAMP)
RT = unit(np.cross([0, 1.0, 0], FW))
UPC = np.cross(FW, RT)
FOC = (RW / 2) / math.tan(HFOV / 2)


def project(P):
    v = np.asarray(P, np.float64) - CAMP
    xc, yc, zc = v @ RT, v @ UPC, v @ FW
    return RW / 2 + FOC * xc / zc - 0.5, RH / 2 - FOC * yc / zc - 0.5, zc


# ---------------------------------------------------------------- SDF helpers
def sd_cap(x, y, z, A, B, ra, rb=None):
    rb = ra if rb is None else rb
    bax, bay, baz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
    pax, pay, paz = x - A[0], y - A[1], z - A[2]
    h = np.clip((pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz), 0, 1)
    dx, dy, dz = pax - bax * h, pay - bay * h, paz - baz * h
    return np.sqrt(dx * dx + dy * dy + dz * dz) - (ra + (rb - ra) * h), h


def seg2(px, py, x0, y0, x1, y1):
    bx, by = x1 - x0, y1 - y0
    h = np.clip(((px - x0) * bx + (py - y0) * by) / (bx * bx + by * by), 0, 1)
    return np.sqrt((px - x0 - bx * h) ** 2 + (py - y0 - by * h) ** 2)


def polyline2(px, py, pts):
    d = np.full(px.shape, 9.0, np.float32)
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        d = np.minimum(d, seg2(px, py, x0, y0, x1, y1))
    return d


def sd_rcyl(r, yy, R, hh, rr):
    qx, qy = r - R + rr, np.abs(yy) - hh + rr
    return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - rr


def sd_rbox(x, y, z, bx, by, bz, rr):
    qx, qy, qz = np.abs(x) - bx + rr, np.abs(y) - by + rr, np.abs(z) - bz + rr
    return np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2) \
        + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0) - rr


# ---------------------------------------------------------------- objects
# 材质编号
DESK, WALL, FLOOR, DESKSIDE = 1, 2, 3, 4
LAMP_PAINT, LAMP_BRASS, SHADE_OUT, SHADE_IN, BULB = 10, 11, 12, 13, 14
COVER, PAGES = 20, 21
CERAMIC, COFFEE = 30, 31
POT, SOIL, STEM, LEAF = 40, 41, 42, 43
PENCIL, PENCIL_TIP, LEAD, FERRULE, ERASER = 50, 51, 52, 53, 54
CABLE = 15

DESK_X0, DESK_X1, DESK_Z0, DESK_Z1 = -1.4, 0.46, -0.32, 0.56
WALL_Z = 0.56
FLOOR_Y = -0.74

# --- 台灯
LB = np.array([-0.43, 0.0, -0.02])         # 底座中心（书的左边）
LP0 = np.array([-0.43, 0.050, -0.02])       # 底座转轴
LP1 = np.array([-0.40, 0.40, 0.13])         # 肘（往后上方）
LP2 = np.array([-0.19, 0.42, 0.03])         # 灯头转轴（伸到书上方）
SH_A = unit((0.27, -0.95, -0.14))           # 灯罩轴（开口方向，朝下照书）
SH_S0 = LP2 + SH_A * 0.012
SH_LEN, SH_R0, SH_R1, SH_T = 0.135, 0.030, 0.080, 0.0022
BULB_C = SH_S0 + SH_A * 0.042
BULB_R = 0.021
_hd = unit(np.array([LP2[0] - LP0[0], 0, LP2[2] - LP0[2]]))
LAT = np.cross([0, 1.0, 0], _hd)            # 两根平行臂杆的横向


def lamp_sdf(x, y, z):
    ids = []
    r = np.sqrt((x - LB[0]) ** 2 + (z - LB[2]) ** 2)
    base = np.minimum(sd_rcyl(r, y - 0.009, 0.088, 0.009, 0.0045), sd_rcyl(r, y - 0.030, 0.032, 0.02, 0.006))
    ids.append((base, LAMP_PAINT))
    rods = np.full(x.shape, 9.0, np.float32)
    for off in (-0.0135, 0.0135):
        o = LAT * off
        for A, B in ((LP0, LP1), (LP1, LP2)):
            c, _ = sd_cap(x, y, z, A + o, B + o, 0.0052)
            rods = np.minimum(rods, c)
    # 弹簧（在下臂一侧，一根细一点的杆）
    c, _ = sd_cap(x, y, z, LP0 + np.array([0.0, 0.03, 0.0]) + LAT * 0.03, LP1 - (LP1 - LP0) * 0.35 + LAT * 0.03, 0.0065)
    rods = np.minimum(rods, c)
    ids.append((rods, LAMP_PAINT))
    joints = np.full(x.shape, 9.0, np.float32)
    for P in (LP0, LP1, LP2):
        c, _ = sd_cap(x, y, z, P - LAT * 0.026, P + LAT * 0.026, 0.0115)
        joints = np.minimum(joints, c)
    ids.append((joints, LAMP_BRASS))
    # 灯罩：锥形薄壳 + 后盖
    px, py, pz = x - SH_S0[0], y - SH_S0[1], z - SH_S0[2]
    s = px * SH_A[0] + py * SH_A[1] + pz * SH_A[2]
    rx, ry, rz = px - s * SH_A[0], py - s * SH_A[1], pz - s * SH_A[2]
    rad = np.sqrt(rx * rx + ry * ry + rz * rz)
    rc = SH_R0 + (SH_R1 - SH_R0) * np.clip(s / SH_LEN, 0, 1)
    ca = math.cos(math.atan((SH_R1 - SH_R0) / SH_LEN))
    shell = np.maximum(np.abs(rad - rc) * ca - SH_T, np.maximum(-s, s - SH_LEN))
    cap = np.maximum(np.abs(s) - SH_T * 1.5, rad - SH_R0)
    knob, _ = sd_cap(x, y, z, SH_S0 - SH_A * 0.004, SH_S0 - SH_A * 0.03, 0.013)
    shade = np.minimum(np.minimum(shell, cap), knob)
    inner = rad < rc - 0.0005
    ids.append((np.where(inner & (s > 0.002), 9.0, shade), SHADE_OUT))
    ids.append((np.where(inner & (s > 0.002), shade, 9.0), SHADE_IN))
    bulb = np.sqrt((x - BULB_C[0]) ** 2 + (y - BULB_C[1]) ** 2 + (z - BULB_C[2]) ** 2) - BULB_R
    ids.append((bulb, BULB))
    # 电线：从灯头沿臂下到底座，再拖到桌面
    cab = np.full(x.shape, 9.0, np.float32)
    pts = [LB + np.array([-0.07, 0.0085, 0.045]), LB + np.array([-0.11, 0.003, 0.10]), LB + np.array([-0.13, 0.003, 0.20]),
           LB + np.array([-0.2, 0.003, 0.30]), np.array([-0.80, 0.003, 0.42])]
    for A, B in zip(pts[:-1], pts[1:]):
        c, _ = sd_cap(x, y, z, A, B, 0.0028)
        cab = np.minimum(cab, c)
    ids.append((cab, CABLE))
    return ids


# --- 书
BK_C = np.array([-0.075, 0.0, -0.02])
BK_YAW = math.radians(7)
BK_CS, BK_SN = math.cos(BK_YAW), math.sin(BK_YAW)
PG_W, PG_H = 0.152, 0.112     # 单页宽、半高


def book_local(x, z):
    dx, dz = x - BK_C[0], z - BK_C[2]
    return BK_CS * dx + BK_SN * dz, -BK_SN * dx + BK_CS * dz


def page_top(s):
    return 0.0058 + 0.0135 * (1 - np.exp(-s / 0.016)) + 0.0045 * np.sin(np.pi * np.clip(s / PG_W, 0, 1))


def book_sdf(x, y, z):
    xb, zb = book_local(x, z)
    cover = sd_rbox(xb, y - 0.0028, zb, 0.162, 0.0028, 0.121, 0.0012)
    s = np.abs(xb)
    top = page_top(s)
    pages = np.maximum.reduce([(y - top) * 0.8, 0.0045 - y, s - PG_W, 0.0025 - s, np.abs(zb) - PG_H])
    return [(cover, COVER), (pages, PAGES)]


# --- 咖啡杯、碟子
CUP_C = np.array([0.175, 0.0, -0.105])
HDIR = unit((0.75, 0.0, -0.66))
HAX = np.cross(HDIR, [0, 1.0, 0])
SAUCER = [(0.0, 0.0045), (0.036, 0.0045), (0.062, 0.0095), (0.079, 0.0165)]
CUP = [(0.027, 0.0095), (0.034, 0.0145), (0.0395, 0.031), (0.0428, 0.060), (0.0442, 0.087)]
COF_Y = 0.074


def cup_sdf(x, y, z):
    r = np.sqrt((x - CUP_C[0]) ** 2 + (z - CUP_C[2]) ** 2)
    saucer = polyline2(r, y, SAUCER) - 0.0026
    cup = polyline2(r, y, CUP) - 0.0027
    bottom = seg2(r, y, 0.0, 0.0125, 0.027, 0.0105) - 0.0035
    cup = np.minimum(cup, bottom)
    coffee = np.maximum.reduce([y - COF_Y, r - 0.0404, 0.014 - y])
    # 把手：竖直平面里的圆环，只留杯壁外面的一半
    hc = CUP_C + HDIR * 0.0535 + np.array([0, 0.050, 0])
    px, py, pz = x - hc[0], y - hc[1], z - hc[2]
    a1 = px * HDIR[0] + pz * HDIR[2]
    a2 = py
    a3 = px * HAX[0] + pz * HAX[2]
    q = np.sqrt(a1 * a1 + (a2 / 1.12) ** 2) - 0.0185
    handle = np.maximum(np.sqrt(q * q + a3 * a3) - 0.0052, 0.041 - r)
    cup = np.minimum(cup, handle)
    # 小勺子搁在碟子上
    sp0 = CUP_C + np.array([0.035, 0.0, -0.045])
    sp_dir = unit((0.62, 0.10, -0.55))
    sp1 = sp0 + sp_dir * 0.085
    stem, _ = sd_cap(x, y, z, sp0 + np.array([0, 0.012, 0]), sp1 + np.array([0, 0.012, 0]), 0.0022, 0.0028)
    bw = sp0 - sp_dir * 0.018 + np.array([0, 0.012, 0])
    bowl = np.sqrt(((x - bw[0]) / 1.6) ** 2 + ((y - bw[1]) / 0.45) ** 2 + ((z - bw[2]) / 1.0) ** 2) * 1.0 - 0.0105
    spoon = np.minimum(stem, bowl * 0.45)
    return [(saucer, CERAMIC), (cup, CERAMIC), (coffee, COFFEE)]


# --- 花盆 + 绿萝
POT_C = np.array([0.255, 0.0, 0.365])
POT_WALL = [(0.051, 0.004), (0.066, 0.104)]
POT_RIM = [(0.066, 0.104), (0.0745, 0.107), (0.0745, 0.134), (0.0685, 0.136)]
SOIL_Y = 0.122


def _leaves():
    rng = np.random.default_rng(12)
    L = []
    spec = [(-150, 40, 0.10, 0.20), (-100, 55, 0.105, 0.24), (-40, 35, 0.095, 0.19), (20, 50, 0.1, 0.22),
            (75, 30, 0.09, 0.18), (130, 45, 0.1, 0.21), (170, 10, 0.095, 0.15), (-70, -25, 0.09, 0.135),
            (-15, -35, 0.085, 0.13), (100, -30, 0.09, 0.132), (-125, 0, 0.09, 0.16)]
    for az, el, ln, hb in spec:
        a, e = math.radians(az), math.radians(el)
        rad = 0.035 if el > 0 else 0.068
        base = POT_C + np.array([rad * math.cos(a), hb, rad * math.sin(a)])
        U = np.array([math.cos(a) * math.cos(e), math.sin(e), math.sin(a) * math.cos(e)])
        V = unit(np.cross([0, 1.0, 0], U))
        V = unit(V * math.cos(math.radians(rng.uniform(-20, 20))) + np.cross(U, V) * math.sin(math.radians(rng.uniform(-20, 20))))
        Wn = np.cross(U, V)
        if Wn[1] < 0:
            V, Wn = -V, -Wn
        stem0 = POT_C + np.array([0.012 * math.cos(a), SOIL_Y, 0.012 * math.sin(a)])
        L.append(dict(base=base, U=U, V=V, W=Wn, len=ln, wid=ln * 0.62, droop=rng.uniform(1.5, 3.0),
                      fold=rng.uniform(0.15, 0.3), stem0=stem0, hue=rng.uniform(-1, 1)))
    return L


LEAVES = _leaves()


def plant_sdf(x, y, z):
    r = np.sqrt((x - POT_C[0]) ** 2 + (z - POT_C[2]) ** 2)
    pot = np.minimum(polyline2(r, y, POT_WALL) - 0.0055, polyline2(r, y, POT_RIM) - 0.004)
    pot = np.minimum(pot, seg2(r, y, 0.0, 0.004, 0.051, 0.004) - 0.004)
    soil = np.maximum.reduce([y - SOIL_Y - 0.004 * (vnoise(x * 200, z * 200, 3) - 0.5), r - 0.064, 0.06 - y])
    stems = np.full(x.shape, 9.0, np.float32)
    leaves = np.full(x.shape, 9.0, np.float32)
    lid = np.full(x.shape, -1, np.int32)
    for i, lf in enumerate(LEAVES):
        b = lf['base']
        mid = 0.5 * (lf['stem0'] + b) + np.array([0, 0.02, 0])
        c1, _ = sd_cap(x, y, z, lf['stem0'], mid, 0.0026)
        c2, _ = sd_cap(x, y, z, mid, b, 0.0024)
        stems = np.minimum(stems, np.minimum(c1, c2))
        px, py, pz = x - b[0], y - b[1], z - b[2]
        U, V, Wn = lf['U'], lf['V'], lf['W']
        u = px * U[0] + py * U[1] + pz * U[2]
        v = px * V[0] + py * V[1] + pz * V[2]
        w = px * Wn[0] + py * Wn[1] + pz * Wn[2]
        Ln, Wd = lf['len'], lf['wid']
        t = np.clip(u / Ln, 0, 1)
        hw = Wd * 0.5 * np.sqrt(np.clip(t * (1 - t), 0, None)) * 2.0 * (1.15 - 0.55 * t) * (1 - 0.25 * np.exp(-((t - 0.02) / 0.06) ** 2))
        w2 = w + lf['droop'] * u * u - lf['fold'] * np.abs(v)
        d2 = np.maximum(np.maximum(np.abs(v) - hw, -u), u - Ln) * 0.7
        leaf = np.maximum(d2, np.abs(w2) * 0.8 - 0.0011)
        better = leaf < leaves
        lid = np.where(better, i, lid)
        leaves = np.minimum(leaves, leaf)
    return [(pot, POT), (soil, SOIL), (stems, STEM), (leaves, LEAF)], lid


# --- 铅笔
PC_A = np.array([0.03, 0.0048, -0.245])     # 笔尖
PC_B = np.array([0.205, 0.0048, -0.19])     # 橡皮端
PC_D = unit(PC_B - PC_A)


def pencil_sdf(x, y, z):
    tipend = PC_A + PC_D * 0.022
    tip, _ = sd_cap(x, y, z, PC_A, tipend, 0.0006, 0.0045)
    body, _ = sd_cap(x, y, z, tipend, PC_B, 0.0045)
    s = (x - PC_A[0]) * PC_D[0] + (y - PC_A[1]) * PC_D[1] + (z - PC_A[2]) * PC_D[2]
    Lp = np.linalg.norm(PC_B - PC_A)
    d = np.minimum(tip, body)
    mats = np.where(s < 0.006, LEAD, np.where(s < 0.022, PENCIL_TIP, np.where(s < Lp - 0.028, PENCIL,
                    np.where(s < Lp - 0.012, FERRULE, ERASER))))
    return d, mats


def _bbox(pts, pad):
    pts = np.asarray(pts)
    return pts.min(0) - pad, pts.max(0) + pad


GROUPS = [
    ('lamp', _bbox([LB + [-0.1, 0, -0.1], LB + [0.1, 0.06, 0.1], LP1, LP2, SH_S0 + SH_A * SH_LEN, [-0.77, 0.0, 0.42]], 0.09)),
    ('book', _bbox([BK_C + [-0.19, 0, -0.15], BK_C + [0.19, 0.03, 0.15]], 0.01)),
    ('cup', _bbox([CUP_C + [-0.09, 0, -0.14], CUP_C + [0.15, 0.1, 0.09]], 0.01)),
    ('plant', _bbox([POT_C + [-0.23, 0, -0.23], POT_C + [0.23, 0.33, 0.23]], 0.01)),
    ('pencil', _bbox([PC_A, PC_B], 0.012)),
]


def box_dist(x, y, z, lo, hi):
    qx = np.maximum(np.maximum(lo[0] - x, x - hi[0]), 0)
    qy = np.maximum(np.maximum(lo[1] - y, y - hi[1]), 0)
    qz = np.maximum(np.maximum(lo[2] - z, z - hi[2]), 0)
    return np.sqrt(qx * qx + qy * qy + qz * qz)


def scene_sdf(x, y, z, want_id=False, exact=False, no_lamp=False):
    d = np.full(x.shape, 9.0, np.float32)
    mid = np.zeros(x.shape, np.int16) if want_id else None
    extra = np.full(x.shape, -1, np.int32) if want_id else None
    for name, (lo, hi) in GROUPS:
        if no_lamp and name == 'lamp':
            continue
        bd = box_dist(x, y, z, lo, hi)
        near = np.ones(x.shape, bool) if exact else (bd < 0.02)
        dg = (bd + 0.0).astype(np.float32)
        if near.any():
            xs, ys, zs = x[near], y[near], z[near]
            if name == 'pencil':
                dd, mm = pencil_sdf(xs, ys, zs)
                comps = [(dd, None)]
            elif name == 'plant':
                comps, lid = plant_sdf(xs, ys, zs)
            else:
                comps = {'lamp': lamp_sdf, 'book': book_sdf, 'cup': cup_sdf}[name](xs, ys, zs)
            best = np.full(xs.shape, 9.0, np.float32)
            bm = np.zeros(xs.shape, np.int16)
            for cd, cm in comps:
                better = cd < best
                best = np.where(better, cd, best)
                if want_id:
                    bm = np.where(better, mm if cm is None else cm, bm)
            dg[near] = best
            if want_id:
                gm = np.zeros(x.shape, np.int16)
                gm[near] = bm
                if name == 'plant':
                    ge = np.full(x.shape, -1, np.int32)
                    ge[near] = lid
        closer = dg < d
        d = np.where(closer, dg, d)
        if want_id:
            mid = np.where(closer, gm if near.any() else 0, mid)
            if name == 'plant' and near.any():
                extra = np.where(closer, ge, extra)
    if want_id:
        return d, mid, extra
    return d


def ray_aabb(ox, oy, oz, dx, dy, dz, lo, hi):
    with np.errstate(divide='ignore', invalid='ignore'):
        t1x, t2x = (lo[0] - ox) / dx, (hi[0] - ox) / dx
        t1y, t2y = (lo[1] - oy) / dy, (hi[1] - oy) / dy
        t1z, t2z = (lo[2] - oz) / dz, (hi[2] - oz) / dz
    tn = np.maximum(np.maximum(np.minimum(t1x, t2x), np.minimum(t1y, t2y)), np.minimum(t1z, t2z))
    tf = np.minimum(np.minimum(np.maximum(t1x, t2x), np.maximum(t1y, t2y)), np.maximum(t1z, t2z))
    return tn, tf


def march(ox, oy, oz, dx, dy, dz, t0, t1, maxit=200):
    n = len(ox)
    t = t0.astype(np.float32).copy()
    hit = np.zeros(n, bool)
    act = np.arange(n)
    for it in range(maxit):
        if act.size == 0:
            break
        tt = t[act]
        d = scene_sdf(ox[act] + tt * dx[act], oy[act] + tt * dy[act], oz[act] + tt * dz[act])
        eps = 0.35 * tt / FOC + 1e-5
        h = d < eps
        hit[act[h]] = True
        tt = tt + np.where(h, 0, d * 0.9)
        t[act] = tt
        act = act[(~h) & (tt < t1[act])]
    return t, hit


def normals(px, py, pz):
    e = 0.00035
    nx = scene_sdf(px + e, py, pz) - scene_sdf(px - e, py, pz)
    ny = scene_sdf(px, py + e, pz) - scene_sdf(px, py - e, pz)
    nz = scene_sdf(px, py, pz + e) - scene_sdf(px, py, pz - e)
    n = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    return nx / n, ny / n, nz / n


# ---------------------------------------------------------------- lights
BULB_POS = BULB_C.astype(np.float32)
LAMP_COL = (lin(1.0, 0.80, 0.55) * 0.155).astype(np.float32)     # 点光源强度（除以距离平方）
AMB_COL = (lin(0.46, 0.46, 0.52) * 0.26).astype(np.float32)       # 夜里的环境光（略冷）
MOON_DIR = unit((-0.75, 0.45, 0.45)).astype(np.float32)
MOON_COL = (lin(0.55, 0.66, 0.90) * 0.22).astype(np.float32)
BOUNCE_P = np.array([0.0, 0.05, -0.06], np.float32)
BOUNCE_COL = (lin(1.0, 0.82, 0.60) * 0.0065).astype(np.float32)
COS_OUT, COS_IN = math.cos(math.radians(52)), math.cos(math.radians(30))


def lamp_light(px, py, pz, nx, ny, nz, shadows=True):
    lx, ly, lz = BULB_POS[0] - px, BULB_POS[1] - py, BULB_POS[2] - pz
    d2 = lx * lx + ly * ly + lz * lz
    dl = np.sqrt(d2)
    lx, ly, lz = lx / dl, ly / dl, lz / dl
    ndl = np.clip(nx * lx + ny * ly + nz * lz, 0, None)
    cosang = -(lx * SH_A[0] + ly * SH_A[1] + lz * SH_A[2])
    spot = smoothstep(COS_OUT, COS_IN, cosang)
    vis = np.ones(len(px), np.float32)
    idx = np.nonzero(ndl * spot > 1e-4)[0]
    if shadows and idx.size:
        vis[idx] = soft_shadow(px[idx] + nx[idx] * 0.0012, py[idx] + ny[idx] * 0.0012, pz[idx] + nz[idx] * 0.0012,
                               lx[idx], ly[idx], lz[idx], dl[idx] - BULB_R * 1.2)
    return (ndl * spot * vis / d2).astype(np.float32), (lx, ly, lz), spot * vis


def soft_shadow(px, py, pz, lx, ly, lz, tmax, k=18.0):
    n = len(px)
    res = np.ones(n, np.float32)
    t = np.full(n, 0.002, np.float32)
    act = np.arange(n)
    for it in range(110):
        if act.size == 0:
            break
        tt = t[act]
        d = scene_sdf(px[act] + tt * lx[act], py[act] + tt * ly[act], pz[act] + tt * lz[act], no_lamp=True)
        res[act] = np.minimum(res[act], k * d / tt)
        blocked = d < 1e-4
        res[act[blocked]] = 0
        tt = tt + np.clip(d, 0.001, 0.05)
        t[act] = tt
        act = act[(~blocked) & (tt < tmax[act])]
    return smoothstep(0, 1, np.clip(res, 0, 1))


def ao(px, py, pz, nx, ny, nz):
    occ = np.zeros(len(px), np.float32)
    sc = 1.0
    for i in range(5):
        hh = 0.004 + 0.012 * i
        d = np.minimum(scene_sdf(px + nx * hh, py + ny * hh, pz + nz * hh), py + ny * hh)
        occ += np.clip(hh - d, 0, None) * sc
        sc *= 0.72
    return np.clip(1 - 3.2 * occ, 0, 1)


# ---------------------------------------------------------------- materials
def desk_albedo(px, pz):
    """胡桃木桌面：扭曲的年轮线（晚材深、早材浅）、顺纹的导管细纹、按木板分色、板缝。"""
    warp = 0.07 * (fbm(px * 2.2, pz * 3.0, 4, 5) - 0.5) + 0.006 * np.sin(px * 13.0 + pz * 5.0)
    v = pz + warp
    s = v * 42.0 + 3.0 * fbm(px * 0.8, pz * 4.0, 3, 6)
    f = s - np.floor(s)
    late = smoothstep(0.35, 0.92, f) * (1 - smoothstep(0.92, 1.0, f))
    figure = fbm(px * 1.5, v * 9.0, 4, 10)
    pores = fbm(px * 3.0, pz * 300.0, 3, 7)
    fleck = vnoise(px * 40.0, pz * 600.0, 8)
    plank = (pz + 0.02) / 0.21
    pj = np.abs(plank - np.round(plank)) * 0.21
    seam = smoothstep(0.0004, 0.0016, pj)
    pv = _h(np.floor(plank).astype(np.int64), 3, 9)
    base = mix3(lin(0.50, 0.33, 0.19)[None], lin(0.33, 0.20, 0.11)[None],
                np.clip(0.17 * late + 0.55 * figure + 0.14 * (pores - 0.35) + 0.08 * (fleck - 0.5), 0, 1))
    base = base * (0.86 + 0.24 * pv)[:, None]
    return base * (0.5 + 0.5 * seam)[:, None]


def book_text(xb, zb):
    """书页上的字：行 + 随机长度的“词”；左页顶上一个标题，右页有一张小插图。"""
    s = np.abs(xb)
    left = xb < 0
    col = np.ones(len(xb), np.float32)
    inm = (s > 0.020) & (s < 0.136) & (zb > -0.094) & (zb < 0.090)
    lh = 0.0062
    li = np.floor((zb + 0.094) / lh)
    fy = (zb + 0.094) / lh - li
    inline = (fy > 0.30) & (fy < 0.66)
    ww = (s - 0.020) / 0.0115
    wi = np.floor(ww + _h(li.astype(np.int64), 5, 3) * 3)
    fw = ww + _h(li.astype(np.int64), 5, 3) * 3 - wi
    wl = 0.55 + 0.4 * _h(wi.astype(np.int64), li.astype(np.int64) + 100 * left, 4)
    word = fw < wl
    lastline = _h(li.astype(np.int64), 7, 5) < 0.12
    lineend = np.where(lastline, 0.06 + 0.07 * _h(li.astype(np.int64), 8, 6), 0.136)
    txt = inm & inline & word & (s < lineend)
    # 字的笔画疏密
    txt = txt & (vnoise(s * 2400, zb * 1800, 11) > 0.30)
    title = left & (zb > 0.066) & (zb < 0.078) & (s > 0.045) & (s < 0.112) & (vnoise(s * 900, zb * 900, 12) > 0.25)
    txt = np.where(left & (zb > 0.06), title, txt)
    pic = (~left) & (zb > 0.02) & (zb < 0.082) & (s > 0.032) & (s < 0.124)
    txt = np.where(pic, False, txt)
    col = np.where(txt, 0.25, col)
    # 插图：淡墨画的远山
    pu, pv = (s - 0.032) / 0.092, (zb - 0.02) / 0.062
    hill = 0.45 + 0.22 * np.sin(pu * 7.0) * np.exp(-pu) + 0.12 * fbm(pu * 6, np.zeros_like(pu), 3, 13)
    ink = np.where(pv < hill, 0.62 + 0.25 * pv, 1.0)
    frame = (np.minimum(np.minimum(pu, 1 - pu), np.minimum(pv, 1 - pv)) < 0.015)
    col = np.where(pic, np.where(frame, 0.45, ink), col)
    return col


def materials(mid, px, py, pz, nx, ny, nz, lid):
    n = len(px)
    alb = np.zeros((n, 3), np.float32)
    rough = np.full(n, 0.5, np.float32)      # 高光指数的反向（越小越亮越锐）
    spec = np.zeros(n, np.float32)
    emit = np.zeros((n, 3), np.float32)

    def put(m, a, sp, ro):
        alb[m] = a
        spec[m] = sp
        rough[m] = ro

    m = mid == LAMP_PAINT
    if m.any():
        g = vnoise(px[m] * 300, (py[m] + pz[m]) * 300, 21)
        put(m, lin(0.14, 0.30, 0.31)[None] * (0.92 + 0.12 * g)[:, None], 0.7, 0.16)
    m = mid == SHADE_OUT
    if m.any():
        put(m, lin(0.14, 0.30, 0.31)[None].repeat(m.sum(), 0), 0.8, 0.16)
    m = mid == SHADE_IN
    if m.any():
        put(m, lin(0.95, 0.92, 0.85)[None].repeat(m.sum(), 0), 0.0, 0.5)
    m = mid == LAMP_BRASS
    if m.any():
        put(m, lin(0.78, 0.58, 0.28)[None].repeat(m.sum(), 0), 0.9, 0.12)
    m = mid == BULB
    if m.any():
        put(m, lin(1.0, 0.95, 0.85)[None].repeat(m.sum(), 0), 0.0, 0.5)
        emit[m] = lin(1.0, 0.86, 0.62) * 9.0
    m = mid == CABLE
    if m.any():
        put(m, lin(0.05, 0.05, 0.05)[None].repeat(m.sum(), 0), 0.3, 0.3)
    m = mid == COVER
    if m.any():
        xb, zb = book_local(px[m], pz[m])
        cl = 0.9 + 0.1 * vnoise(xb * 900, zb * 900, 31)
        put(m, lin(0.46, 0.09, 0.08)[None] * cl[:, None], 0.06, 0.6)
    m = mid == PAGES
    if m.any():
        xb, zb = book_local(px[m], pz[m])
        s = np.abs(xb)
        top = page_top(s)
        on_top = py[m] > top - 0.0012
        txt = book_text(xb, zb)
        paper = lin(0.93, 0.90, 0.81)[None] * (0.97 + 0.04 * vnoise(xb * 500, zb * 500, 32))[:, None]
        edge_lines = 0.82 + 0.18 * (0.5 + 0.5 * np.sin(py[m] * 5200.0 + 3 * vnoise(xb * 60, zb * 60, 33)))
        a = np.where(on_top[:, None], paper * txt[:, None], paper * edge_lines[:, None] * 0.92)
        gut = 1 - 0.35 * np.exp(-s / 0.006)
        put(m, a * gut[:, None], 0.03, 0.6)
    m = mid == CERAMIC
    if m.any():
        put(m, lin(0.94, 0.93, 0.90)[None].repeat(m.sum(), 0), 1.0, 0.03)
    m = mid == COFFEE
    if m.any():
        r = np.sqrt((px[m] - CUP_C[0]) ** 2 + (pz[m] - CUP_C[2]) ** 2)
        crema = smoothstep(0.030, 0.0395, r)
        swirl = fbm(px[m] * 320, pz[m] * 320, 3, 41)
        c = mix3(lin(0.16, 0.08, 0.035)[None].repeat(m.sum(), 0), lin(0.55, 0.36, 0.20)[None].repeat(m.sum(), 0),
                 np.clip(crema * 0.85 + 0.25 * smoothstep(0.55, 0.8, swirl) * smoothstep(0.02, 0.035, r), 0, 1))
        put(m, c, 1.0, 0.02)
    m = mid == POT
    if m.any():
        r = np.sqrt((px[m] - POT_C[0]) ** 2 + (pz[m] - POT_C[2]) ** 2)
        ang = np.arctan2(pz[m] - POT_C[2], px[m] - POT_C[0])
        g = fbm(ang * 12, py[m] * 60, 4, 51)
        salt = smoothstep(0.62, 0.8, fbm(ang * 5, py[m] * 20, 3, 52)) * smoothstep(0.08, 0.02, py[m])
        c = lin(0.70, 0.36, 0.22)[None] * (0.82 + 0.3 * g)[:, None]
        c = mix3(c, lin(0.80, 0.74, 0.66)[None].repeat(m.sum(), 0), salt * 0.5)
        put(m, c, 0.05, 0.6)
    m = mid == SOIL
    if m.any():
        g = vnoise(px[m] * 900, pz[m] * 900, 53)
        put(m, lin(0.16, 0.11, 0.08)[None] * (0.6 + 0.8 * g)[:, None], 0.05, 0.6)
    m = mid == STEM
    if m.any():
        put(m, lin(0.35, 0.50, 0.20)[None].repeat(m.sum(), 0), 0.2, 0.3)
    m = mid == LEAF
    if m.any():
        li = np.clip(lid[m], 0, len(LEAVES) - 1)
        ub = np.zeros(m.sum(), np.float32)
        vb = np.zeros(m.sum(), np.float32)
        hue = np.zeros(m.sum(), np.float32)
        for i, lf in enumerate(LEAVES):
            k = li == i
            if not k.any():
                continue
            b, U, V = lf['base'], lf['U'], lf['V']
            dxx, dyy, dzz = px[m][k] - b[0], py[m][k] - b[1], pz[m][k] - b[2]
            ub[k] = (dxx * U[0] + dyy * U[1] + dzz * U[2]) / lf['len']
            vb[k] = (dxx * V[0] + dyy * V[1] + dzz * V[2]) / lf['wid']
            hue[k] = lf['hue']
        rib = smoothstep(0.03, 0.008, np.abs(vb)) * smoothstep(0.95, 0.6, ub)
        vein = smoothstep(0.82, 0.97, 0.5 + 0.5 * np.sin((ub - 1.6 * np.abs(vb)) * 38)) * smoothstep(0.35, 0.05, np.abs(vb) - 0.05)
        var = fbm(ub * 5, vb * 5, 3, 61)
        c = mix3(lin(0.10, 0.30, 0.09)[None].repeat(m.sum(), 0), lin(0.28, 0.52, 0.14)[None].repeat(m.sum(), 0),
                 np.clip(0.35 + 0.35 * var + 0.18 * hue, 0, 1))
        # 绿萝的黄绿斑纹
        streak = smoothstep(0.62, 0.72, fbm(ub * 3 + hue * 7, vb * 9, 4, 62)) * 0.8
        c = mix3(c, lin(0.72, 0.78, 0.35)[None].repeat(m.sum(), 0), streak)
        c = mix3(c, lin(0.55, 0.68, 0.30)[None].repeat(m.sum(), 0), np.clip(rib + 0.4 * vein, 0, 1))
        put(m, c, 0.55, 0.08)
    for mm, cc, sp, ro in ((PENCIL, (0.96, 0.72, 0.12), 0.3, 0.15), (PENCIL_TIP, (0.86, 0.70, 0.50), 0.02, 0.6),
                           (LEAD, (0.12, 0.12, 0.13), 0.3, 0.2), (FERRULE, (0.78, 0.78, 0.80), 1.0, 0.06),
                           (ERASER, (0.88, 0.50, 0.52), 0.02, 0.6)):
        m = mid == mm
        if m.any():
            put(m, lin(*cc)[None].repeat(m.sum(), 0), sp, ro)
    return alb, spec, rough, emit


# ---------------------------------------------------------------- render
def render():
    N = RW * RH
    ys, xs = np.divmod(np.arange(N), RW)
    sx = ((xs + 0.5) - RW / 2) / FOC
    sy = -((ys + 0.5) - RH / 2) / FOC
    dx = (FW[0] + sx * RT[0] + sy * UPC[0]).astype(np.float32)
    dy = (FW[1] + sx * RT[1] + sy * UPC[1]).astype(np.float32)
    dz = (FW[2] + sx * RT[2] + sy * UPC[2]).astype(np.float32)
    nrm = np.sqrt(dx * dx + dy * dy + dz * dz)
    dx, dy, dz = dx / nrm, dy / nrm, dz / nrm
    del ys, xs, sx, sy, nrm
    ox, oy, oz = (np.full(N, CAMP[i], np.float32) for i in range(3))
    # --- 解析平面：桌面、桌边、墙、地面
    tb = np.full(N, np.inf, np.float32)
    mat = np.zeros(N, np.int16)
    NX, NY, NZ = np.zeros(N, np.float32), np.zeros(N, np.float32), np.zeros(N, np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (0.0 - CAMP[1]) / dy
        x_, z_ = CAMP[0] + t * dx, CAMP[2] + t * dz
        m = (t > 0) & (x_ > DESK_X0) & (x_ < DESK_X1) & (z_ > DESK_Z0) & (z_ < WALL_Z)
        tb[m], mat[m], NY[m] = t[m], DESK, 1
        for (axis, val, sgn) in (('x', DESK_X1, 1), ('z', DESK_Z0, -1)):
            if axis == 'x':
                t = (val - CAMP[0]) / dx
                a_, y_ = CAMP[2] + t * dz, CAMP[1] + t * dy
                m = (t > 0) & (t < tb) & (a_ > DESK_Z0) & (a_ < WALL_Z) & (y_ < 0) & (y_ > -0.035)
                tb[m], mat[m], NX[m], NY[m] = t[m], DESKSIDE, sgn, 0
            else:
                t = (val - CAMP[2]) / dz
                a_, y_ = CAMP[0] + t * dx, CAMP[1] + t * dy
                m = (t > 0) & (t < tb) & (a_ > DESK_X0) & (a_ < DESK_X1) & (y_ < 0) & (y_ > -0.035)
                tb[m], mat[m], NZ[m], NY[m] = t[m], DESKSIDE, sgn, 0
        t = (WALL_Z - CAMP[2]) / dz
        m = (t > 0) & (t < tb)
        tb[m], mat[m], NZ[m], NY[m], NX[m] = t[m], WALL, -1, 0, 0
        t = (FLOOR_Y - CAMP[1]) / dy
        m = (t > 0) & (t < tb)
        tb[m], mat[m], NY[m], NX[m], NZ[m] = t[m], FLOOR, 1, 0, 0
    log('planes')
    # --- SDF 物体
    lo = np.min([g[1][0] for g in GROUPS], 0)
    hi = np.max([g[1][1] for g in GROUPS], 0)
    tn, tf = ray_aabb(ox, oy, oz, dx, dy, dz, lo, hi)
    cand = np.nonzero((tf > np.maximum(tn, 0)) & (tn < tb))[0]
    tc, hitc = march(ox[cand], oy[cand], oz[cand], dx[cand], dy[cand], dz[cand], np.maximum(tn[cand], 0.05),
                     np.minimum(tf[cand], tb[cand]))
    oi = cand[hitc]
    to = tc[hitc]
    log('march', cand.size, oi.size)
    col = np.zeros((N, 3), np.float32)
    depth = tb.copy()
    depth[oi] = to
    # --- 物体着色
    px, py, pz = CAMP[0] + to * dx[oi], CAMP[1] + to * dy[oi], CAMP[2] + to * dz[oi]
    nx, ny, nz = normals(px, py, pz)
    _, mid, lid = scene_sdf(px, py, pz, want_id=True)
    alb, spec, rough, emit = materials(mid, px, py, pz, nx, ny, nz, lid)
    log('object materials')
    col[oi] = shade(px, py, pz, nx, ny, nz, dx[oi], dy[oi], dz[oi], alb, spec, rough, emit, mid)
    log('object shade')
    # --- 平面着色
    objm = np.zeros(N, bool)
    objm[oi] = True
    pi = np.nonzero(~objm & np.isfinite(tb))[0]
    t = tb[pi]
    px, py, pz = CAMP[0] + t * dx[pi], CAMP[1] + t * dy[pi], CAMP[2] + t * dz[pi]
    mp = mat[pi]
    n = len(pi)
    alb = np.zeros((n, 3), np.float32)
    spec = np.zeros(n, np.float32)
    rough = np.full(n, 0.5, np.float32)
    k = mp == DESK
    alb[k] = desk_albedo(px[k], pz[k])
    spec[k] = 0.35
    rough[k] = 0.10
    k = mp == DESKSIDE
    alb[k] = desk_albedo(px[k] * 0.3 + pz[k], py[k] * 3) * 0.8
    spec[k] = 0.2
    k = mp == WALL
    g = fbm(px[k] * 30, py[k] * 30, 4, 71)
    alb[k] = lin(0.62, 0.58, 0.52)[None] * (0.95 + 0.08 * g)[:, None]
    k = mp == FLOOR
    alb[k] = lin(0.22, 0.15, 0.10)[None] * (0.8 + 0.3 * fbm(px[k] * 2, pz[k] * 30, 3, 72))[:, None]
    spec[k] = 0.1
    c = shade(px, py, pz, NX[pi], NY[pi], NZ[pi], dx[pi], dy[pi], dz[pi], alb, spec, rough,
              np.zeros((n, 3), np.float32), mp)
    # 墙上的暖色光晕（灯的散射/桌面反光）
    k = mp == WALL
    wg = np.exp(-(((px[k] - (-0.12)) / 0.65) ** 2 + ((py[k] - 0.12) / 0.45) ** 2))
    c[k] += alb[k] * (lin(1.0, 0.80, 0.58) * 0.30)[None] * wg[:, None]
    col[pi] = c
    log('plane shade')
    # --- 桌面清漆的模糊倒影：从桌面点沿镜面方向再追一次物体
    dk = pi[mp == DESK]
    t = tb[dk]
    qx, qy, qz = CAMP[0] + t * dx[dk], np.zeros(len(dk), np.float32), CAMP[2] + t * dz[dk]
    rx, ry, rz = dx[dk], -dy[dk], dz[dk]
    tn2, tf2 = ray_aabb(qx, qy, qz, rx, ry, rz, lo, hi)
    c2 = np.nonzero(tf2 > np.maximum(tn2, 0.003))[0]
    tr, hr = march(qx[c2], qy[c2], qz[c2], rx[c2], ry[c2], rz[c2], np.maximum(tn2[c2], 0.003), tf2[c2], maxit=120)
    hi_ = c2[hr]
    tr = tr[hr]
    ex, ey, ez = qx[hi_] + tr * rx[hi_], qy[hi_] + tr * ry[hi_], qz[hi_] + tr * rz[hi_]
    enx, eny, enz = normals(ex, ey, ez)
    _, emid, elid = scene_sdf(ex, ey, ez, want_id=True)
    ealb, espec, erough, eemit = materials(emid, ex, ey, ez, enx, eny, enz, elid)
    Ll, _, _ = lamp_light(ex, ey, ez, enx, eny, enz, shadows=False)
    glow = (emid == BULB) | (emid == SHADE_IN)
    rc_ = ealb * (LAMP_COL[None] * Ll[:, None] + AMB_COL[None])
    rc_[glow] = 0.0
    refl = np.zeros((N, 3), np.float32)
    wgt = np.zeros(N, np.float32)
    refl[dk[hi_]] = rc_
    wgt[dk[hi_]] = 1.0
    refl = ndi.gaussian_filter(refl.reshape(RH, RW, 3), (5, 5, 0)).reshape(N, 3)
    wgt = ndi.gaussian_filter(wgt.reshape(RH, RW), 5).ravel()
    cosv = np.clip(-dy[dk], 0, 1)
    F = (0.05 + 0.95 * (1 - cosv) ** 5) * 0.9
    col[dk] += refl[dk] * F[:, None]
    log('desk reflections', hi_.size)
    return col.reshape(RH, RW, 3), depth.reshape(RH, RW)


def shade(px, py, pz, nx, ny, nz, dx, dy, dz, alb, spec, rough, emit, mid):
    Ll, (lx, ly, lz), spotvis = lamp_light(px, py, pz, nx, ny, nz)
    occ = ao(px, py, pz, nx, ny, nz)
    # 冷色环境光 + 月光方向的轮廓
    amb = AMB_COL[None] * (0.55 + 0.45 * ny)[:, None] * occ[:, None]
    moon = MOON_COL[None] * np.clip(nx * MOON_DIR[0] + ny * MOON_DIR[1] + nz * MOON_DIR[2], 0, None)[:, None] * occ[:, None]
    # 书页上反上来的暖光（无阴影）
    bx, by, bz = BOUNCE_P[0] - px, BOUNCE_P[1] - py, BOUNCE_P[2] - pz
    bd2 = bx * bx + by * by + bz * bz + 0.004
    bnd = np.clip((nx * bx + ny * by + nz * bz) / np.sqrt(bd2), 0, None)
    bounce = BOUNCE_COL[None] * (bnd / bd2)[:, None] * occ[:, None]
    irr = LAMP_COL[None] * Ll[:, None] + amb + moon + bounce
    c = alb * irr
    # 灯罩内壁：直接被灯泡照亮
    k = mid == SHADE_IN
    if np.any(k):
        d2 = (px[k] - BULB_POS[0]) ** 2 + (py[k] - BULB_POS[1]) ** 2 + (pz[k] - BULB_POS[2]) ** 2
        c[k] = alb[k] * (LAMP_COL * 0.5)[None] / d2[:, None]
    # 高光（Blinn-Phong，灯泡的反射）+ 菲涅尔反射环境
    vx, vy, vz = -dx, -dy, -dz
    hx, hy, hz = lx + vx, ly + vy, lz + vz
    hn = np.sqrt(hx * hx + hy * hy + hz * hz) + 1e-9
    ndh = np.clip((nx * hx + ny * hy + nz * hz) / hn, 0, 1)
    expo = 2.0 / np.maximum(rough, 0.01) ** 2
    ph = ndh ** expo * (expo + 8) / 60.0
    d2 = (BULB_POS[0] - px) ** 2 + (BULB_POS[1] - py) ** 2 + (BULB_POS[2] - pz) ** 2
    ndv = np.clip(nx * vx + ny * vy + nz * vz, 0, 1)
    fres = 0.04 + 0.96 * (1 - ndv) ** 5
    c += (spec * ph * (0.25 + fres))[:, None] * (LAMP_COL[None] / d2[:, None]) * spotvis[:, None] * 0.6
    c += (spec * fres * 0.8)[:, None] * AMB_COL[None] * occ[:, None]
    # 被照亮的书页/桌面反上来的暖色高光
    bhx, bhy, bhz = bx / np.sqrt(bd2) + vx, by / np.sqrt(bd2) + vy, bz / np.sqrt(bd2) + vz
    bhn = np.sqrt(bhx * bhx + bhy * bhy + bhz * bhz) + 1e-9
    bndh = np.clip((nx * bhx + ny * bhy + nz * bhz) / bhn, 0, 1)
    c += (spec * bndh ** (expo * 0.15) * 1.5)[:, None] * (BOUNCE_COL[None] / bd2[:, None])
    # 月光方向的高光（让深色灯罩、陶瓷的轮廓更立体）
    mhx, mhy, mhz = MOON_DIR[0] + vx, MOON_DIR[1] + vy, MOON_DIR[2] + vz
    mhn = np.sqrt(mhx * mhx + mhy * mhy + mhz * mhz) + 1e-9
    mndh = np.clip((nx * mhx + ny * mhy + nz * mhz) / mhn, 0, 1)
    c += (spec * mndh ** (expo * 0.25) * 0.9)[:, None] * MOON_COL[None] * occ[:, None]
    # 叶子透光
    k = mid == LEAF
    if np.any(k):
        back = np.clip(-(nx[k] * lx[k] + ny[k] * ly[k] + nz[k] * lz[k]), 0, None)
        c[k] += alb[k] * lin(0.9, 1.0, 0.5)[None] * (LAMP_COL * 0.35)[None] * (back * spotvis[k] / d2[k])[:, None]
    return c + emit


def steam(img, rng):
    """咖啡热气：几缕半透明、往上飘、逐渐散开的烟。"""
    sx, sy, _ = project(CUP_C + np.array([0, COF_Y + 0.01, 0]))
    Hs = FOC * 0.16 / np.linalg.norm(CUP_C - CAMP)
    yy, xx = np.mgrid[0:RH, 0:RW]
    y0, y1 = int(max(0, sy - Hs)), int(sy)
    x0, x1 = int(max(0, sx - Hs * 0.6)), int(min(RW, sx + Hs * 0.6))
    Y = yy[y0:y1, x0:x1].astype(np.float32)
    X = xx[y0:y1, x0:x1].astype(np.float32)
    t = (sy - Y) / Hs
    acc = np.zeros(Y.shape, np.float32)
    for i in range(4):
        ph = rng.uniform(0, 6.28)
        cxw = sx + (i - 1.5) * Hs * 0.05 + Hs * (0.05 + 0.03 * i) * np.sin(t * (5.0 + i) + ph) * t \
            + Hs * 0.12 * (fbm(t * 3 + i * 7, np.full_like(t, i * 1.3), 3, 81 + i) - 0.5) * t
        w = Hs * (0.012 + 0.07 * t)
        a = np.exp(-((X - cxw) / w) ** 2) * smoothstep(0.0, 0.12, t) * smoothstep(1.0, 0.35, t)
        a = a * (0.6 + 0.8 * fbm(X / Hs * 6, t * 8 + i, 3, 91 + i))
        acc += a * 0.13
    acc = np.clip(acc, 0, 0.5)
    img[y0:y1, x0:x1] += acc[..., None] * lin(1.0, 0.92, 0.80)[None, None] * 0.55


def tonemap(x):
    x = np.maximum(x, 0)
    y = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return np.clip(y, 0, 1) ** (1 / 2.2)


def main():
    for nm, P in (('lamp head', LP2), ('bulb', BULB_C), ('lamp base', LB), ('book', BK_C), ('cup', CUP_C),
                  ('pot top', POT_C + [0, 0.33, 0]), ('desk corner', [DESK_X1, 0, DESK_Z0]), ('pencil', PC_A)):
        x, y, z = project(np.array([P]))
        print(f"  {nm:12s} -> ({x[0] / SS:7.1f}, {y[0] / SS:7.1f})")
    col, depth = render()
    steam(col, np.random.default_rng(5))
    # 轻微景深：焦点在书上
    fd = float(np.linalg.norm(BK_C - CAMP))
    coc = np.clip(np.abs(1 / np.maximum(depth, 0.05) - 1 / fd) * 7.0, 0, 3.0)
    b1 = ndi.gaussian_filter(col, (2.5, 2.5, 0))
    b2 = ndi.gaussian_filter(col, (6.0, 6.0, 0))
    w1 = np.clip(coc, 0, 1)[..., None]
    w2 = np.clip(coc - 1, 0, 2)[..., None] / 2
    col = col * (1 - w1) + b1 * w1
    col = col * (1 - w2) + b2 * w2
    bright = np.maximum(col - 1.2, 0)
    col = col + 0.4 * ndi.gaussian_filter(bright, (10, 10, 0)) + 0.25 * ndi.gaussian_filter(bright, (45, 45, 0))
    img = tonemap(col * 1.6)
    img = img.reshape(H, SS, W, SS, 3).mean((1, 3))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx - W * 0.45) / (W * 0.65)) ** 2 + ((yy - H * 0.52) / (H * 0.62)) ** 2
    img = img * (1 - 0.25 * np.clip(r2, 0, 1.5))[..., None]
    img = img + np.random.default_rng(4).normal(0, 0.008, img.shape).astype(np.float32)
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    out.save(os.path.join(HERE, 'final.png'))
    for extra in sys.argv[1:]:
        out.save(os.path.join(HERE, extra))
    log('saved', out.size)


if __name__ == '__main__':
    main()
