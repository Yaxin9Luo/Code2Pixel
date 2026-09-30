#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A01 雨后江南水乡（纯代码，不用任何模型、不读任何图片）。

画法：numpy 写的小型光线投射渲染器。场景是几百个 3D 平面面片（白墙、瓦顶、马头墙、石驳岸、石拱桥、乌篷船、船夫……），
逐像素和面片求交 + 深度缓冲；倒影 = 把场景按水面镜像再渲一遍，加涟漪扰动和菲涅尔混合；
薄雾 = 随距离和高度变化的雾；材质（白墙水渍、瓦垄、条石、木格窗）都是程序化噪声纹理；
最后 2D 叠加前景柳枝和红灯笼。2 倍超采样抗锯齿。随机数全部固定种子。

运行：python3 draw.py                  → final.png
      python3 draw.py rounds/r1.png    → 同时另存一份
"""
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, SS = 1536, 1024, 2
RW, RH = W * SS, H * SS
FOC = 1250.0 * SS
CXs, HYs = RW / 2.0, 0.40 * RH
CAM = np.array([1.6, 5.0, 0.0])
CAMM = np.array([CAM[0], -CAM[1], CAM[2]])
NEAR = 0.5
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def lin(*c):
    return np.power(np.asarray(c, np.float32), 2.2)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


LDIR = unit((-0.30, 0.80, 0.50)).astype(np.float32)

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
    xf = np.floor(x)
    yf = np.floor(y)
    fx = x - xf
    fy = y - yf
    ix = xf.astype(np.int64)
    iy = yf.astype(np.int64)
    ux = fx * fx * (3 - 2 * fx)
    uy = fy * fy * (3 - 2 * fy)
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
    sd = np.asarray(seed, np.int64)
    for i in range(octaves):
        tot += np.float32(amp) * vnoise(x, y, sd + 101 * i)
        norm += amp
        amp *= gain
        x, y = 1.6 * x + 1.2 * y + 3.1, -1.2 * x + 1.6 * y + 7.7
    return tot / np.float32(norm)


# ---------------------------------------------------------------- scene
FACES = []
LANTERNS = []
(WALL, STONE, ROOF, WOOD, WINDOW, DARK, CAP, EAVE, HULL, AWNING, CLOTH, HAT, TREE, GUNWALE,
 BRIDGE, INTRADOS, PAVE, DECK, SKIN, INTERIOR) = range(20)
XA, YA, ZA = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])


def face(O, U, V, poly=None, rect=None, mat=0, seed=0, tint=(1, 1, 1), p=(), mask=None):
    O = np.asarray(O, np.float64)
    U = unit(U)
    V = np.asarray(V, np.float64)
    V = unit(V - np.dot(V, U) * U)
    pp = list(p) + [0.0] * (4 - len(p))
    FACES.append(dict(O=O, U=U, V=V, N=np.cross(U, V), poly=poly, rect=rect, mat=mat, seed=int(seed),
                      tint=np.asarray(tint, np.float32), p=np.asarray(pp[:4], np.float32), mask=mask))


def tri(p0, p1, p2, grow=0.012, **kw):
    p0, p1, p2 = (np.asarray(q, np.float64) for q in (p0, p1, p2))
    e1, e2 = p1 - p0, p2 - p0
    if np.linalg.norm(np.cross(e1, e2)) < 1e-9:
        return
    U = unit(e1)
    V = unit(e2 - np.dot(e2, U) * U)
    pts = np.array([[0.0, 0.0], [np.dot(e1, U), 0.0], [np.dot(e2, U), np.dot(e2, V)]])
    d = pts - pts.mean(0)
    pts = pts + d / np.linalg.norm(d, axis=1, keepdims=True) * grow
    face(p0, U, V, poly=[tuple(q) for q in pts], **kw)


def quad4(p0, p1, p2, p3, **kw):
    tri(p0, p1, p2, **kw)
    tri(p0, p2, p3, **kw)


def horsehead(s, xf, z0, He, Hr, Dr, seed):
    """马头墙：在 z0 处、朝向镜头的阶梯形山墙，顶上盖瓦、端头起翘。"""
    c = -s
    U = (s, 0, 0)
    h1, h3 = He + 0.5, Hr + 0.55
    h2 = 0.5 * (h1 + h3)
    a1, a2 = 0.45 * Dr, 0.85 * Dr
    b1, b2 = 2 * Dr - a1, 2 * Dr - a2
    e0, e1 = -0.35, 2 * Dr + 0.35
    zf = z0 - 0.2
    poly = [(e0, 0), (e0, h1), (a1, h1), (a1, h2), (a2, h2), (a2, h3), (b2, h3), (b2, h2), (b1, h2), (b1, h1),
            (e1, h1), (e1, 0)]
    face((xf, 0, zf), U, YA, poly=poly, mat=WALL, seed=seed, p=(1e3, 0, 1.2))
    for ua, ub, h, side in [(e0, a1, h1, -1), (a1, a2, h2, -1), (a2, b2, h3, 0), (b2, b1, h2, 1), (b1, e1, h1, 1)]:
        if side == -1:
            pl = [(ua - 0.14, h - 0.07), (ub + 0.14, h - 0.07), (ub + 0.14, h + 0.15), (ua + 0.3, h + 0.15),
                  (ua + 0.02, h + 0.3), (ua - 0.32, h + 0.40), (ua - 0.24, h + 0.17)]
        elif side == 1:
            pl = [(ub + 0.14, h - 0.07), (ua - 0.14, h - 0.07), (ua - 0.14, h + 0.15), (ub - 0.3, h + 0.15),
                  (ub - 0.02, h + 0.3), (ub + 0.32, h + 0.40), (ub + 0.24, h + 0.17)]
        else:
            pl = [(ua - 0.14, h - 0.07), (ub + 0.14, h - 0.07), (ub + 0.14, h + 0.15), (ua - 0.14, h + 0.15)]
        face((xf, 0, zf - 0.03), U, YA, poly=pl, mat=CAP, seed=seed + 3)
    face((xf + c * 0.35, 0, zf - 0.2), ZA, YA, rect=(0, 0.4, 0, h1), mat=WALL, seed=seed + 5, p=(1e3, 0, 1.2))
    face((xf + c * 0.40, 0, zf - 0.25), ZA, YA, rect=(0, 0.5, h1 - 0.07, h1 + 0.15), mat=CAP, seed=seed + 6)


def gable(s, xf, z0, He, Hr, Dr, ov, seed):
    """普通硬山：山墙三角 + 博风（深色瓦边）+ 屋脊端头起翘。"""
    U = (s, 0, 0)
    face((xf, 0, z0), U, YA, poly=[(0, 0), (0, He), (Dr, Hr - 0.12), (2 * Dr, He), (2 * Dr, 0)], mat=WALL,
         seed=seed, p=(1e3, 0, 1.2))
    pl = [(-ov, He - 0.02), (Dr, Hr + 0.06), (2 * Dr + ov, He - 0.02), (2 * Dr + ov, He - 0.27), (Dr, Hr - 0.2),
          (-ov, He - 0.27)]
    face((xf, 0, z0 - 0.3), U, YA, poly=pl, mat=CAP, seed=seed + 1)
    face((xf + s * Dr, Hr, z0 - 0.32), U, YA,
         poly=[(-0.2, -0.05), (0.2, -0.05), (0.24, 0.38), (0.06, 0.62), (-0.2, 0.42)], mat=CAP, seed=seed + 2)


def steps(s, xf, zc, hb, n=4, width=1.8, seed=0):
    """河埠头：从门口下到水里的石阶。"""
    c = -s
    rise, run = (hb + 0.1) / n, 0.34
    z0 = zc - width / 2

    def xa(k):
        return xf + c * (0.15 + k * run)

    for i in range(1, n + 1):
        yi = hb - i * rise
        face((xa(i - 1), yi, z0), ZA, (c, 0, 0), rect=(0, width, 0, run), mat=STONE, seed=seed + i)
        face((xa(i - 1), 0, z0), ZA, YA, rect=(0, width, yi, yi + rise), mat=STONE, seed=seed + 10 + i)
    face((xa(n), 0, z0), ZA, YA, rect=(0, width, -0.5, hb - n * rise), mat=STONE, seed=seed + 30)
    poly = [(0, -0.5), (0, hb)]
    for i in range(1, n + 1):
        poly += [((i - 1) * run, hb - i * rise), (i * run, hb - i * rise)]
    poly += [(n * run, -0.5)]
    face((xf + c * 0.15, 0, z0), (c, 0, 0), YA, poly=poly, mat=STONE, seed=seed + 40)


def house(s, xf, z0, z1, He, style, hh, seed, ivy=0.0, near_end=True, lanterns=True):
    """一栋临河民居。s=-1 左岸（立面朝 +x），s=+1 右岸（立面朝 -x）。"""
    rng = np.random.default_rng(seed)
    w = z1 - z0
    c = -s
    hb = 1.0 + 0.35 * rng.random()
    Dr = 4.0 + 0.6 * rng.random()
    Hr = He + Dr * math.tan(math.radians(27 + 4 * rng.random()))
    ov = 0.65
    tint = [(1.0, 0.99, 0.965), (0.96, 0.965, 0.97), (0.985, 0.975, 0.95), (0.94, 0.94, 0.93)][int(rng.integers(4))]
    face((xf + c * 0.15, 0, z0), ZA, YA, rect=(0, w, -0.5, hb), mat=STONE, seed=seed + 1)
    face((xf, hb, z0), ZA, (c, 0, 0), rect=(0, w, 0, 0.15), mat=STONE, seed=seed + 2)
    face((xf, 0, z0), ZA, YA, rect=(0, w, hb, He), mat=WALL, seed=seed + 3, tint=tint, p=(He, ivy, hb, w))
    xo = xf + c * 0.03
    # ---- ground floor
    if style in ('shop', 'wood'):
        face((xo, 0, z0), ZA, YA, rect=(0.3, w - 0.3, hb, hb + 2.45), mat=WOOD, seed=seed + 4)
        if style == 'shop':
            nopen = 1 + int(w > 6.0)
            seg = (w - 0.6) / nopen
            for k in range(nopen):
                ua = 0.3 + k * seg + 0.35
                face((xf + c * 0.05, 0, z0), ZA, YA, rect=(ua, ua + seg - 0.7, hb + 0.05, hb + 2.2), mat=INTERIOR,
                     seed=seed + 5 + k, p=(ua, ua + seg - 0.7, hb + 0.05, hb + 2.2))
            if lanterns:
                LANTERNS.append((xf + c * 0.42, He - 0.95, z0 + w * 0.28))
                LANTERNS.append((xf + c * 0.42, He - 0.95, z0 + w * 0.72))
        else:
            for k in range(max(1, int(w // 2.2))):
                uc = w * (k + 0.5) / max(1, int(w // 2.2))
                face((xf + c * 0.05, hb + 0.9, z0 + uc - 0.5), ZA, YA, rect=(0, 1.0, 0, 1.1), mat=WINDOW,
                     seed=seed + 6 + k, p=(1.0, 1.1, 1 if k % 2 == 0 else 0, 4))
    elif style == 'door':
        ud = w * (0.3 + 0.3 * rng.random())
        face((xo, 0, z0), ZA, YA, rect=(ud - 0.7, ud + 0.7, hb, hb + 2.35), mat=WOOD, seed=seed + 4,
             tint=(0.8, 0.8, 0.8))
        face((xf + c * 0.05, 0, z0), ZA, YA, rect=(ud - 0.06, ud + 0.06, hb + 0.05, hb + 2.25), mat=DARK,
             seed=seed + 5)
        steps(s, xf, z0 + ud, hb, n=4, width=1.7, seed=seed + 60)
        uw = ud + 1.9 if ud + 2.6 < w else max(0.3, ud - 2.4)
        face((xf + c * 0.04, hb + 1.0, z0 + uw), ZA, YA, rect=(0, 0.8, 0, 0.9), mat=WINDOW, seed=seed + 7,
             p=(0.8, 0.9, 0, 3))
    else:  # wallwin
        for k in range(max(1, int(w // 3.0))):
            uc = w * (k + 0.5) / max(1, int(w // 3.0))
            face((xf + c * 0.04, hb + 1.0, z0 + uc - 0.4), ZA, YA, rect=(0, 0.8, 0, 0.9), mat=WINDOW,
                 seed=seed + 7 + k, p=(0.8, 0.9, 0, 3))
    # ---- 腰檐
    has_mid = style in ('shop', 'wallwin', 'door') and rng.random() < 0.8
    ym = hb + 2.75
    if has_mid:
        mo = 0.7
        Lm = math.hypot(mo, 0.35)
        face((xf + c * mo, ym, z0), ZA, (-c * mo, 0.35, 0), rect=(-0.05, w + 0.05, 0, Lm), mat=ROOF,
             seed=seed + 20, p=(Lm,))
        face((xf, ym - 0.02, z0), ZA, (c, 0, 0), rect=(0, w, 0, mo), mat=EAVE, seed=seed + 21)
        face((xf + c * mo, 0, z0), ZA, YA, rect=(-0.05, w + 0.05, ym - 0.12, ym + 0.02), mat=CAP, seed=seed + 22)
    up0 = (ym + 0.5) if has_mid else hb + 2.9
    # ---- upper floor
    if style == 'wood':
        n = max(2, int(round(w / 1.15)))
        pw = (w - 0.4) / n
        top = He - 0.3
        face((xo, 0, z0), ZA, YA, rect=(0.2, w - 0.2, up0 - 0.1, top), mat=WOOD, seed=seed + 30)
        for k in range(n):
            ua = 0.2 + k * pw + 0.07
            ww, wh = pw - 0.14, top - up0 - 0.55
            kind = [1, 0, 1, 2][int(rng.integers(4))]
            face((xf + c * 0.06, up0 + 0.35, z0 + ua), ZA, YA, rect=(0, ww, 0, wh), mat=WINDOW, seed=seed + 31 + k,
                 p=(ww, wh, kind, 4))
    else:
        nw = max(1, int(w // 2.4))
        for k in range(nw):
            uc = w * (k + 0.5) / nw + rng.uniform(-0.25, 0.25)
            ww, wh = 1.05, 1.25
            vb = He - 0.85 - wh
            kind = [1, 0, 1, 2][int(rng.integers(4))]
            face((xf + c * 0.04, vb, z0 + uc - ww / 2), ZA, YA, rect=(0, ww, 0, wh), mat=WINDOW, seed=seed + 31 + k,
                 p=(ww, wh, kind, 4))
            face((xf, vb - 0.03, z0 + uc - ww / 2 - 0.1), ZA, (c, 0, 0), rect=(0, ww + 0.2, 0, 0.12), mat=STONE,
                 seed=seed + 40 + k)
    # ---- eave, roof, ridge
    face((xf, He - 0.02, z0), ZA, (c, 0, 0), rect=(0, w, 0, ov), mat=EAVE, seed=seed + 50)
    if z0 < 33:
        EAVES.append((xf + c * ov, He, z0, z1))
    ro0 = 0.0 if hh else -0.3
    face((xf + c * ov, 0, z0), ZA, YA, rect=(ro0, w - ro0, He - 0.2, He + 0.04), mat=CAP, seed=seed + 51)
    Lr = math.hypot(ov + Dr, Hr - He)
    face((xf + c * ov, He, z0), ZA, (-c * (ov + Dr), Hr - He, 0), rect=(ro0, w - ro0, 0, Lr), mat=ROOF,
         seed=seed + 52, p=(Lr,))
    face((xf - c * Dr, 0, z0), ZA, YA, rect=(ro0, w - ro0, Hr - 0.05, Hr + 0.26), mat=CAP, seed=seed + 53)
    if near_end:
        if hh:
            horsehead(s, xf, z0, He, Hr, Dr, seed + 70)
        else:
            gable(s, xf, z0, He, Hr, Dr, ov, seed + 70)
    return Hr


# bridge geometry
XM, Y0, RA, ZB, TB, SPAN = -0.35, 0.45, 4.6, 35.0, 4.2, 9.6


def deck_h(u):
    q = np.clip(np.abs(u) / SPAN, 0, 1)
    return 1.3 + 5.35 * (1 - q ** 2) ** 0.8


def bridge():
    us = np.linspace(-(SPAN + 3.5), SPAN + 3.5, 141)
    top = deck_h(us) + 0.9
    poly = [(float(us[0]), -0.5)] + [(float(a), float(b)) for a, b in zip(us, top)] + [(float(us[-1]), -0.5)]
    face((XM, 0, ZB), XA, YA, poly=poly, mat=BRIDGE, seed=900,
         mask=lambda u, v: (u * u + (v - Y0) ** 2) > RA * RA)
    # 望柱
    for up in np.arange(-SPAN - 2.7, SPAN + 3.0, 1.8):
        dk = float(deck_h(np.array([up]))[0]) + 0.9
        face((XM, 0, ZB - 0.02), XA, YA, rect=(up - 0.13, up + 0.13, dk - 0.1, dk + 0.28), mat=BRIDGE, seed=903)
    n = 30
    th = np.linspace(0, np.pi, n + 1)
    for i in range(n):
        p0 = np.array([XM + RA * math.cos(th[i]), Y0 + RA * math.sin(th[i]), ZB])
        p1 = np.array([XM + RA * math.cos(th[i + 1]), Y0 + RA * math.sin(th[i + 1]), ZB])
        ch = p1 - p0
        L = float(np.linalg.norm(ch))
        face(p0, ZA, ch, rect=(0, TB, -0.02, L + 0.02), mat=INTRADOS, seed=901, p=(RA * th[i],))
    for sx in (-1, 1):
        face((XM + sx * RA, 0, ZB), ZA, YA, rect=(0, TB, -0.5, Y0 + 0.02), mat=INTRADOS, seed=902, p=(-5.0,))
    for i in range(len(us) - 1):
        a0, a1 = us[i], us[i + 1]
        h0, h1 = float(deck_h(np.array([a0]))[0]), float(deck_h(np.array([a1]))[0])
        seg = np.array([a1 - a0, h1 - h0, 0.0])
        face((XM + a0, h0, ZB), ZA, seg, rect=(0, TB, 0, float(np.linalg.norm(seg)) + 0.01), mat=PAVE, seed=904)


def tree(xc, zc, hgt, wid, seed):
    rng = np.random.default_rng(seed)
    blobs = []
    for k in range(10):
        blobs.append((rng.normal(0, wid * 0.2), hgt * (0.5 + 0.35 * rng.random()), wid * (0.2 + 0.12 * rng.random())))
    blobs = np.array(blobs, np.float32)

    def mask(u, v, blobs=blobs, seed=seed):
        u = u.astype(np.float32)
        v = v.astype(np.float32)
        d = np.full(u.shape, 9.0, np.float32)
        for cu, cv, r in blobs:
            d = np.minimum(d, ((u - cu) ** 2 + (v - cv) ** 2) / (r * r))
        return (d + 0.9 * (fbm(u * 0.45, v * 0.45, 3, seed) - 0.5) + 0.45 * (vnoise(u * 2.5, v * 2.5, seed + 1) - 0.5)
                + 0.35 * (vnoise(u * 7.0, v * 7.0, seed + 2) - 0.5)) < 1.0

    face((xc, 0, zc), XA, YA, rect=(-wid, wid, 0, hgt * 1.1), mat=TREE, seed=seed, p=(hgt,), mask=mask)
    face((xc, 0, zc + 0.1), XA, YA, rect=(-0.3, 0.3, 0, hgt * 0.6), mat=WOOD, seed=seed + 1, tint=(0.6, 0.6, 0.6))


BOAT = dict(cx=-1.9, cz=19.0, psi=math.radians(52), L=6.4, B=1.4)


def boat():
    cx, cz, psi, L, B = BOAT['cx'], BOAT['cz'], BOAT['psi'], BOAT['L'], BOAT['B']
    hd = np.array([math.sin(psi), 0, math.cos(psi)])
    rd = np.array([math.cos(psi), 0, -math.sin(psi)])
    up = YA
    base = np.array([cx, 0, cz])

    def P(a, b, y):
        return base + a * hd + b * rd + y * up

    def hw(a):
        q = min(1.0, abs(2 * a / L))
        return 0.5 * B * max(0.0, 1 - q ** 1.8) ** 0.65

    def top(a):
        q = abs(2 * a / L)
        return 0.38 + 0.5 * q ** 2.4 + (0.16 * q ** 3 if a > 0 else 0.0)

    As = np.linspace(-L / 2, L / 2, 31)
    for i in range(len(As) - 1):
        a0, a1 = As[i], As[i + 1]
        for sb in (1, -1):
            q00, q10 = P(a0, sb * hw(a0) * 0.78, -0.25), P(a1, sb * hw(a1) * 0.78, -0.25)
            q01, q11 = P(a0, sb * hw(a0), top(a0) - 0.09), P(a1, sb * hw(a1), top(a1) - 0.09)
            quad4(q00, q10, q11, q01, mat=HULL, seed=700)
            g0, g1 = P(a0, sb * hw(a0) * 1.03, top(a0)), P(a1, sb * hw(a1) * 1.03, top(a1))
            quad4(q01, q11, g1, g0, mat=GUNWALE, seed=701)
        quad4(P(a0, -hw(a0) * 0.9, 0.2), P(a1, -hw(a1) * 0.9, 0.2), P(a1, hw(a1) * 0.9, 0.2), P(a0, hw(a0) * 0.9, 0.2),
              mat=DECK, seed=702)
    for a_s, a_e, r, yb in [(-1.55, 0.25, 0.74, 0.40), (0.38, 1.3, 0.70, 0.41), (-2.35, -1.62, 0.66, 0.42)]:
        th = np.linspace(0, np.pi, 17)
        for j in range(16):
            c0, s0 = math.cos(th[j]), math.sin(th[j])
            c1, s1 = math.cos(th[j + 1]), math.sin(th[j + 1])
            quad4(P(a_s, r * c0, yb + 1.05 * r * s0), P(a_e, r * c0, yb + 1.05 * r * s0),
                  P(a_e, r * c1, yb + 1.05 * r * s1), P(a_s, r * c1, yb + 1.05 * r * s1), mat=AWNING, seed=710)
        for a in (a_s, a_e):
            poly = [(r * math.cos(t), 1.05 * r * math.sin(t)) for t in np.linspace(0, np.pi, 17)]
            face(P(a, 0, yb), rd, up, poly=poly, mat=DARK, seed=711)
    # 船夫：站在船尾，面朝船头，双手握橹
    ab = -2.55

    def slab(a, y0, y1, da, db0, db1, mat, seed, b=0.0):
        """上下宽度不同的方柱（身体用）。"""
        lo = [P(a + sa * da / 2, b + sb2 * db0 / 2, y0) for sa, sb2 in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        hi = [P(a + sa * da / 2, b + sb2 * db1 / 2, y1) for sa, sb2 in [(-1, -1), (1, -1), (1, 1), (-1, 1)]]
        for k in range(4):
            quad4(lo[k], lo[(k + 1) % 4], hi[(k + 1) % 4], hi[k], mat=mat, seed=seed)
        quad4(*hi, mat=mat, seed=seed)

    slab(ab, 0.2, 0.95, 0.16, 0.13, 0.15, CLOTH, 719, b=-0.11)       # 左腿
    slab(ab + 0.06, 0.2, 0.95, 0.16, 0.13, 0.15, CLOTH, 719, b=0.11)  # 右腿
    slab(ab + 0.02, 0.92, 1.56, 0.26, 0.36, 0.46, CLOTH, 721)        # 上身（上宽下窄）
    slab(ab + 0.03, 1.54, 1.78, 0.18, 0.17, 0.19, SKIN, 722)         # 头
    apex = P(ab + 0.03, 0, 2.12)
    rim = [P(ab + 0.03 + 0.46 * math.cos(t), 0.46 * math.sin(t), 1.76) for t in np.linspace(0, 2 * np.pi, 25)]
    for j in range(24):
        tri(apex, rim[j], rim[j + 1], mat=HAT, seed=723)
    hand = P(ab + 0.38, 0.30, 1.12)
    blade = P(ab - 2.7, 0.62, -0.25)
    for off in (0.04 * rd, 0.04 * up):
        quad4(hand + 0.5 * (hand - blade) / np.linalg.norm(hand - blade) + off, blade + off, blade - off,
              hand + 0.5 * (hand - blade) / np.linalg.norm(hand - blade) - off, mat=WOOD, seed=724, tint=(0.55, 0.5, 0.45))
    for sh, hnd in ((P(ab + 0.02, -0.22, 1.5), hand + 0.06 * rd), (P(ab + 0.02, 0.22, 1.5), hand - 0.04 * rd)):
        elbow = 0.5 * (sh + hnd) + P(0, 0, 0) * 0 - 0.08 * up + 0.08 * hd - np.array([BOAT['cx'], 0, BOAT['cz']]) * 0
        for p0, p1 in ((sh, elbow), (elbow, hnd)):
            for off in (0.055 * rd, 0.055 * up, 0.055 * hd):
                quad4(p0 + off, p1 + off, p1 - off, p0 - off, mat=CLOTH, seed=725)


def build():
    # 右岸（近处）：z0, z1, 檐高, 样式, 马头墙
    R = [(2.0, 8.5, 6.9, 'shop', True, 0.0), (8.5, 14.5, 6.3, 'wallwin', True, 0.0),
         (14.5, 19.5, 7.3, 'wood', False, 0.0), (19.5, 26.0, 6.0, 'door', True, 0.5),
         (26.0, 32.5, 6.8, 'shop', True, 0.0)]
    L = [(9.0, 16.0, 6.6, 'wood', True, 0.0), (16.0, 22.0, 5.9, 'wallwin', True, 0.6),
         (22.0, 27.5, 7.0, 'shop', False, 0.0), (27.5, 32.5, 6.2, 'door', True, 0.0)]
    for i, (z0, z1, He, st, hh, ivy) in enumerate(R):
        house(+1, 5.8 + 0.25 * math.sin(i * 1.7), z0, z1, He, st, hh, 100 + 97 * i, ivy=ivy)
    for i, (z0, z1, He, st, hh, ivy) in enumerate(L):
        house(-1, -6.4 + 0.25 * math.sin(i * 2.3), z0, z1, He, st, hh, 1000 + 97 * i, ivy=ivy)
    rng = np.random.default_rng(42)
    for s, xf0, sd in [(1, 5.8, 3000), (-1, -6.4, 5000)]:
        z = 41.0
        k = 0
        while z < 150:
            w = rng.uniform(4.5, 8.5)
            st = ['shop', 'wallwin', 'wood', 'door'][int(rng.integers(4))]
            house(s, xf0 + rng.uniform(-0.6, 0.6), z, z + w, rng.uniform(5.6, 7.4), st, bool(rng.random() < 0.6),
                  sd + 97 * k, ivy=0.0, lanterns=bool(z < 70))
            z += w
            k += 1
    # 桥头平台（驳岸 + 湿石板）
    for s, xf in [(1, 5.8), (-1, -6.4)]:
        c = -s
        face((xf + c * 0.15, 0, 32.5), ZA, YA, rect=(0, 8.5, -0.5, 1.3), mat=STONE, seed=801 + s)
        face((xf + c * 0.15, 1.3, 32.5), ZA, (-c, 0, 0), rect=(0, 8.5, 0, 12.0), mat=PAVE, seed=803 + s)
    bridge()
    tree(-8.2, 33.6, 2.6, 2.0, 1301)
    tree(7.4, 33.4, 2.2, 1.7, 1302)
    tree(-7.6, 42.5, 3.2, 2.2, 1303)
    tree(-17.0, 46.0, 15.0, 7.0, 1201)
    tree(15.0, 58.0, 17.0, 8.0, 1202)
    tree(-13.0, 88.0, 16.0, 8.0, 1203)
    tree(10.0, 112.0, 18.0, 9.0, 1204)
    tree(-20.0, 125.0, 20.0, 10.0, 1205)
    boat()


# ---------------------------------------------------------------- materials
def mix3(a, b, t):
    t = np.asarray(t, np.float32)[:, None]
    return a * (1 - t) + b * t


def m_wall(u, v, X, Y, Z, f):
    sd = FSEED[f]
    top, ivy, hb = FP[f, 0], FP[f, 1], FP[f, 2]
    big = fbm(u * 0.28, v * 0.28, 3, sd)
    stk = fbm(u * 2.6, v * 0.10, 5, sd + 7)
    stk2 = fbm(u * 7.0, v * 0.35, 3, sd + 8)
    grain = vnoise(u * 16.0, v * 16.0, sd + 3)
    near_top = smoothstep(top - 3.6, top - 0.1, v)
    # 雨水从檐口往下挂的水渍：竖条，越靠近檐口越重
    streak = smoothstep(0.46, 0.80, stk) * (0.25 + 0.75 * near_top) + 0.35 * smoothstep(0.55, 0.85, stk2) * near_top
    drip = smoothstep(top - 1.1, top - 0.05, v) * (0.5 + 0.5 * stk)
    shade = 1.0 - 0.42 * np.clip(streak, 0, 1) - 0.25 * drip - 0.26 * (big - 0.5)
    alb = lin(0.88, 0.875, 0.855)[None] * FTINT[f] * shade[:, None]
    stain = smoothstep(0.58, 0.75, fbm(u * 0.5 + 4.0, v * 0.35, 4, sd + 17))
    alb = mix3(alb, lin(0.60, 0.59, 0.54)[None] * (0.85 + 0.3 * big)[:, None], 0.5 * stain)
    mot = fbm(u * 1.4, v * 1.4, 4, sd + 19)
    alb = alb * (0.93 + 0.14 * mot)[:, None]
    dh = hb + 0.5 + 1.5 * fbm(u * 0.6, np.full_like(u, 3.3), 4, sd + 11)
    damp = smoothstep(dh, dh - 1.2, v)
    alb = mix3(alb, lin(0.42, 0.45, 0.40)[None] * (0.75 + 0.5 * big)[:, None], 0.8 * damp)
    pl = smoothstep(0.74, 0.755, fbm(u * 0.6 + 11.0, v * 0.6, 4, sd + 21)) * (v < top - 0.6)
    row = np.floor(v / 0.11)
    bu = (u + (row % 2) * 0.13) / 0.26
    fu = bu - np.floor(bu)
    fv = v / 0.11 - row
    j = np.minimum(np.minimum(fu, 1 - fu) * 0.26, np.minimum(fv, 1 - fv) * 0.11)
    bcol = lin(0.52, 0.47, 0.43)[None] * (0.8 + 0.35 * _h(np.floor(bu).astype(np.int64), row.astype(np.int64), 5))[:, None]
    bcol = bcol * (0.55 + 0.45 * smoothstep(0.004, 0.012, j))[:, None]
    alb = mix3(alb, bcol, pl)
    # 爬藤：只在墙根一小片，边缘是一簇簇叶子
    lv = vnoise(u * 9.0, v * 9.0, sd + 41)
    lv2 = vnoise(u * 23.0, v * 23.0, sd + 42)
    iv = smoothstep(0.62, 0.66, fbm(u * 0.5 + 2.0, v * 0.5, 4, sd + 40) + 0.3 * ivy * np.exp(-np.clip(v - hb, 0, None) / 1.2)
                    + 0.18 * (lv - 0.5) + 0.12 * (lv2 - 0.5) - 0.25) * (ivy > 0)
    ivc = mix3(lin(0.10, 0.16, 0.07)[None], lin(0.28, 0.38, 0.15)[None], lv) * (0.6 + 0.6 * lv2)[:, None]
    alb = mix3(alb, ivc, iv)
    ao = 1 - 0.55 * np.exp(-np.clip(top - v, 0, None) / 0.55)
    wid = FP[f, 3]
    edge = np.where(wid > 0, np.minimum(u, wid - u), 9.0)
    ao = ao * (1 - 0.14 * np.exp(-np.clip(edge, 0, None) / 0.35)) * (1 - 0.18 * np.exp(-np.clip(v - hb, 0, None) / 0.3))
    alb = alb * (ao * (0.965 + 0.07 * grain))[:, None]
    return alb, np.full(len(u), 0.03, np.float32)


def m_stone(u, v, X, Y, Z, f):
    sd = FSEED[f]
    rh = 0.34
    row = np.floor(v / rh)
    ri = row.astype(np.int64)
    off = _h(ri, 3, sd) * 1.3
    bl = 0.75 + 0.55 * _h(ri, 5, sd)
    bu = (u + off) / bl
    bi = np.floor(bu)
    fu = bu - bi
    fv = v / rh - row
    e = np.minimum(np.minimum(fu, 1 - fu) * bl, np.minimum(fv, 1 - fv) * rh)
    joint = smoothstep(0.008, 0.03, e)
    var = _h(bi.astype(np.int64), ri, sd + 1)
    tex = fbm(u * 3.0, v * 3.0, 3, sd + 2)
    alb = lin(0.44, 0.435, 0.415)[None] * (0.68 + 0.4 * var + 0.35 * (tex - 0.5))[:, None]
    alb = alb * (0.35 + 0.65 * joint)[:, None]
    stk = fbm(u * 3.0, v * 0.25, 4, sd + 4)
    alb = alb * (1 - 0.3 * smoothstep(0.5, 0.8, stk))[:, None]
    wet = smoothstep(1.3, 0.0, Y)
    alg = fbm(u * 1.2, Y * 3.0, 3, sd + 6)
    alb = mix3(alb * (1 - 0.5 * wet)[:, None], lin(0.11, 0.15, 0.10)[None] * (0.7 + 0.6 * alg)[:, None], 0.55 * wet)
    moss = smoothstep(0.62, 0.72, fbm(u * 0.9, v * 0.9, 3, sd + 9))
    alb = mix3(alb, lin(0.22, 0.29, 0.15)[None], 0.45 * moss)
    return alb, (0.10 + 0.3 * wet).astype(np.float32)


def m_roof(u, v, X, Y, Z, f):
    sd = FSEED[f]
    Lr = FP[f, 0]
    p = 0.22
    cu = u / p + 0.25 * (vnoise(v * 0.7, u * 0.05, sd) - 0.5)
    ci = np.floor(cu)
    ph = cu - ci
    prof = np.cos(2 * np.pi * ph)
    course = v / 0.17 + 0.5 * (ci % 2)
    cph = course - np.floor(course)
    lip = smoothstep(0.0, 0.2, cph)
    tv = _h(ci.astype(np.int64), np.floor(course).astype(np.int64), sd)
    pr = 0.5 + 0.5 * prof
    alb = lin(0.175, 0.185, 0.205)[None] * (0.8 + 0.3 * tv)[:, None]
    alb = alb * ((0.45 + 0.55 * pr) * (0.72 + 0.28 * lip))[:, None]
    grime = fbm(u * 0.3, v * 0.6, 4, sd + 3)
    alb = alb * (0.85 + 0.3 * grime)[:, None]
    moss = smoothstep(0.66, 0.76, fbm(u * 0.4, v * 0.5, 3, sd + 5))
    alb = mix3(alb, lin(0.22, 0.26, 0.16)[None], 0.5 * moss)
    edge = smoothstep(0.16, 0.06, v)
    alb = alb * (1 - 0.35 * edge * pr)[:, None]
    ridge = smoothstep(Lr - 0.3, Lr - 0.22, v)
    alb = alb * (1 - 0.3 * ridge)[:, None]
    # 湿瓦：只有盖瓦的脊背反一点天光，瓦沟是暗的 → 出瓦垄条纹
    gl = 0.015 + 0.11 * pr ** 3 * (0.7 + 0.3 * lip)
    return alb, gl.astype(np.float32)


def m_wood(u, v, X, Y, Z, f):
    sd = FSEED[f]
    pu = u / 0.19
    pi_ = np.floor(pu)
    fu = pu - pi_
    seam = smoothstep(0.0, 0.07, np.minimum(fu, 1 - fu))
    var = _h(pi_.astype(np.int64), 1, sd)
    grain = fbm(u * 22.0, v * 1.1, 3, sd + 3)
    weather = fbm(u * 0.5, v * 0.5, 3, sd + 4)
    alb = lin(0.34, 0.22, 0.15)[None] * FTINT[f] * (0.75 + 0.3 * var + 0.35 * (grain - 0.5))[:, None]
    alb = mix3(alb, lin(0.36, 0.33, 0.30)[None] * FTINT[f], 0.35 * smoothstep(0.55, 0.8, weather))
    alb = alb * (0.5 + 0.5 * seam)[:, None]
    return alb, np.full(len(u), 0.06, np.float32)


def m_window(u, v, X, Y, Z, f):
    sd = FSEED[f]
    ww, wh, kind, nc = FP[f, 0], FP[f, 1], FP[f, 2], FP[f, 3]
    fr = 0.075
    frame = (u < fr) | (u > ww - fr) | (v < fr) | (v > wh - fr)
    iw = np.maximum(ww - 2 * fr, 0.1)
    ih = np.maximum(wh - 2 * fr, 0.1)
    nr = np.maximum(np.round(nc * ih / iw), 2)
    gu = (u - fr) / iw * nc
    gv = (v - fr) / ih * nr
    lu = np.abs(gu - np.round(gu)) * iw / nc
    lv = np.abs(gv - np.round(gv)) * ih / nr
    # 细一点的第二层格子（步步锦的意思）
    gu2 = gu * 2
    gv2 = gv * 2
    lu2 = np.abs(gu2 - np.round(gu2)) * iw / nc / 2
    lv2 = np.abs(gv2 - np.round(gv2)) * ih / nr / 2
    bar = (lu < 0.018) | (lv < 0.018) | (((lu2 < 0.009) | (lv2 < 0.009)) & (kind > 0.5))
    fill = np.where((kind < 0.5)[:, None], lin(0.07, 0.06, 0.055)[None],
                    np.where((kind < 1.5)[:, None], lin(0.72, 0.68, 0.58)[None], lin(0.47, 0.52, 0.54)[None]))
    tex = vnoise(u * 6, v * 6, sd)
    fill = fill * (0.85 + 0.3 * tex)[:, None] * (1 - 0.5 * smoothstep(wh - 0.4, wh - 0.08, v))[:, None]
    wood = lin(0.28, 0.18, 0.12)[None] * (0.85 + 0.3 * vnoise(u * 30, v * 2, sd + 1))[:, None]
    alb = np.where((frame | bar)[:, None], wood, fill)
    gl = np.where(kind > 1.5, 0.35, 0.04).astype(np.float32)
    return alb, gl


def m_interior(u, v, X, Y, Z, f):
    """铺子里面：暗，顶上一盏暖灯，隐约有货架。"""
    sd = FSEED[f]
    ua, ub, v0, v1 = FP[f, 0], FP[f, 1], FP[f, 2], FP[f, 3]
    cu = (u - ua) / (ub - ua)
    cv = (v - v0) / (v1 - v0)
    glow = np.exp(-((cu - 0.5) ** 2 / 0.06 + (cv - 0.8) ** 2 / 0.12))
    shelf = 1 - 0.5 * ((np.abs(cv - 0.38) < 0.02) | (np.abs(cv - 0.62) < 0.02) | (np.abs(cu - 0.5) < 0.012))
    n = fbm(u * 3, v * 3, 3, sd)
    alb = (lin(0.08, 0.06, 0.045)[None] * (0.7 + 0.6 * n)[:, None] + lin(0.62, 0.40, 0.18)[None] * (0.45 * glow)[:, None])
    alb = alb * (shelf * (1 - 0.6 * smoothstep(0.3, 0.0, cv)))[:, None]
    return alb, np.zeros(len(u), np.float32)


def m_dark(u, v, X, Y, Z, f):
    n = fbm(u * 1.5, v * 1.5, 3, FSEED[f])
    alb = lin(0.055, 0.048, 0.042)[None] * (0.75 + 0.5 * n)[:, None]
    return alb, np.zeros(len(u), np.float32)


def m_cap(u, v, X, Y, Z, f):
    n = vnoise(u * 12, v * 12, FSEED[f])
    stripe = 0.9 + 0.1 * np.cos(2 * np.pi * u / 0.2)
    alb = lin(0.17, 0.175, 0.185)[None] * ((0.85 + 0.3 * n) * stripe)[:, None]
    return alb, np.full(len(u), 0.15, np.float32)


def m_eave(u, v, X, Y, Z, f):
    fr = u / 0.3 - np.floor(u / 0.3)
    r = smoothstep(0.02, 0.07, np.minimum(fr, 1 - fr) * 0.3)
    alb = lin(0.25, 0.18, 0.12)[None] * (0.5 + 0.5 * r)[:, None]
    return alb, np.zeros(len(u), np.float32)


def m_hull(u, v, X, Y, Z, f):
    fy = (Y + 0.3) / 0.1
    fi = np.floor(fy)
    j = smoothstep(0.0, 0.12, np.minimum(fy - fi, 1 - (fy - fi)))
    var = _h(fi.astype(np.int64), 3, 700)
    g = fbm(X * 3 + Z * 3, Y * 30, 3, 701)
    alb = lin(0.10, 0.083, 0.07)[None] * ((0.75 + 0.3 * var + 0.3 * (g - 0.5)) * (0.6 + 0.4 * j))[:, None]
    return alb, np.full(len(u), 0.32, np.float32)


def m_gunwale(u, v, X, Y, Z, f):
    g = fbm(X * 4 + Z * 4, Y * 40, 3, 702)
    alb = lin(0.30, 0.22, 0.15)[None] * (0.8 + 0.4 * g)[:, None]
    return alb, np.full(len(u), 0.2, np.float32)


def m_deck(u, v, X, Y, Z, f):
    g = fbm(X * 6, Z * 6, 3, 703)
    alb = lin(0.33, 0.24, 0.16)[None] * (0.7 + 0.5 * g)[:, None]
    return alb, np.full(len(u), 0.1, np.float32)


def m_awning(u, v, X, Y, Z, f):
    a = (X - BOAT['cx']) * math.sin(BOAT['psi']) + (Z - BOAT['cz']) * math.cos(BOAT['psi'])
    fa = a / 0.28 - np.floor(a / 0.28)
    rib = smoothstep(0.0, 0.12, np.minimum(fa, 1 - fa))
    wv = np.sin(a * 90) * np.sin(Y * 90)
    n = fbm(X * 2, Z * 2 + Y, 3, 710)
    alb = lin(0.08, 0.077, 0.074)[None] * ((0.8 + 0.2 * wv + 0.4 * (n - 0.5)) * (0.55 + 0.45 * rib))[:, None]
    return alb, (0.25 * (0.4 + 0.6 * rib)).astype(np.float32)


def m_flat(col, gl=0.03):
    c = lin(*col)

    def fn(u, v, X, Y, Z, f):
        n = vnoise(u * 8, v * 8, FSEED[f])
        return c[None] * (0.88 + 0.24 * n)[:, None], np.full(len(u), gl, np.float32)
    return fn


def m_hat(u, v, X, Y, Z, f):
    a = np.arctan2(Z - BOAT['cz'], X - BOAT['cx'])
    st = 0.85 + 0.15 * np.cos(a * 60)
    alb = lin(0.74, 0.63, 0.42)[None] * st[:, None]
    return alb, np.full(len(u), 0.05, np.float32)


def m_tree(u, v, X, Y, Z, f):
    sd = FSEED[f]
    hgt = FP[f, 0]
    n = fbm(u * 0.9, v * 0.9, 4, sd + 5)
    n2 = vnoise(u * 5, v * 5, sd + 6)
    alb = lin(0.20, 0.29, 0.16)[None] * ((0.55 + 0.7 * n + 0.2 * n2) * (0.65 + 0.35 * smoothstep(0, hgt, v)))[:, None]
    return alb, np.zeros(len(u), np.float32)


def m_bridge(u, v, X, Y, Z, f):
    sd = FSEED[f]
    dk = deck_h(u)
    r = np.sqrt(u * u + (v - Y0) ** 2)
    ring = (r < RA + 0.55) & (v > Y0 - 0.05)
    par = v > dk + 0.02
    rh = 0.40
    row = np.floor(v / rh)
    ri = row.astype(np.int64)
    off = _h(ri, 3, sd) * 1.4
    bl = 0.9 + 0.6 * _h(ri, 4, sd)
    bu = (u + off) / bl
    bi = np.floor(bu)
    fu = bu - bi
    fv = v / rh - row
    e = np.minimum(np.minimum(fu, 1 - fu) * bl, np.minimum(fv, 1 - fv) * rh)
    bid = _h(bi.astype(np.int64), ri, sd + 1)
    ang = np.arctan2(v - Y0, u)
    na = 44
    sa = ang / np.pi * na
    sai = np.floor(sa)
    fa = sa - sai
    er = np.minimum(np.minimum(fa, 1 - fa) * (np.pi / na) * r, np.minimum(np.abs(r - RA), np.abs(RA + 0.55 - r)))
    e = np.where(ring, er, e)
    bid = np.where(ring, _h(sai.astype(np.int64), 7, sd + 2), bid)
    pp = 1.8
    pu = (u + SPAN + 2.7) / pp + 0.5
    pfu = pu - np.floor(pu)
    epar = np.minimum(np.minimum(pfu, 1 - pfu) * pp - 0.13, np.abs(v - (dk + 0.8)))
    epar = np.minimum(np.abs(epar), v - dk)
    e = np.where(par, epar, e)
    joint = smoothstep(0.01, 0.035, e)
    tex = fbm(u * 2.5, v * 2.5, 4, sd + 5)
    alb = lin(0.60, 0.595, 0.57)[None] * (0.78 + 0.3 * bid + 0.3 * (tex - 0.5))[:, None]
    alb = alb * (0.5 + 0.5 * joint)[:, None]
    stk = fbm(u * 1.8, v * 0.15, 4, sd + 9)
    alb = alb * (1 - 0.28 * smoothstep(0.5, 0.75, stk))[:, None]
    moss = smoothstep(0.58, 0.68, fbm(u * 0.6, v * 0.9, 4, sd + 12)) * (0.4 + 0.6 * smoothstep(0.5, 2.0, v))
    alb = mix3(alb, lin(0.30, 0.36, 0.22)[None], 0.6 * moss)
    # 桥身上垂下来的薜荔藤
    drape = smoothstep(0.55, 0.62, fbm(u * 0.7, v * 0.22, 4, sd + 13) + 0.35 * smoothstep(dk - 2.2, dk, v)
                       - 0.2) * (~ring) * (v < dk + 0.1)
    lv = vnoise(u * 10, v * 10, sd + 14)
    alb = mix3(alb, mix3(lin(0.10, 0.17, 0.07)[None], lin(0.28, 0.38, 0.14)[None], lv), 0.9 * drape)
    wet = smoothstep(1.2, 0.0, v)
    alb = mix3(alb * (1 - 0.5 * wet)[:, None], lin(0.15, 0.19, 0.14)[None], 0.3 * wet)
    return alb, (0.08 + 0.2 * wet).astype(np.float32)


def m_intrados(u, v, X, Y, Z, f):
    sd = FSEED[f]
    s = FP[f, 0] + v
    rh = 0.42
    row = np.floor(s / rh)
    ri = row.astype(np.int64)
    off = _h(ri, 3, sd) * 0.8
    bu = (u + off) / 0.8
    bi = np.floor(bu)
    fu = bu - bi
    fs = s / rh - row
    e = np.minimum(np.minimum(fu, 1 - fu) * 0.8, np.minimum(fs, 1 - fs) * rh)
    joint = smoothstep(0.01, 0.03, e)
    var = _h(bi.astype(np.int64), ri, sd + 1)
    alb = lin(0.50, 0.49, 0.47)[None] * ((0.75 + 0.3 * var) * (0.55 + 0.45 * joint))[:, None]
    wet = smoothstep(1.0, 0.0, Y)
    alb = mix3(alb * (1 - 0.4 * wet)[:, None], lin(0.13, 0.17, 0.12)[None], 0.4 * wet)
    ao = 0.4 + 0.6 * np.exp(-np.minimum(u, TB - u) / 0.9)
    return alb * ao[:, None], np.full(len(u), 0.1, np.float32)


def m_pave(u, v, X, Y, Z, f):
    sd = FSEED[f]
    bu = u / 0.9
    bv = v / 0.6 + 0.5 * (np.floor(bu) % 2)
    fu = bu - np.floor(bu)
    fv = bv - np.floor(bv)
    e = np.minimum(np.minimum(fu, 1 - fu) * 0.9, np.minimum(fv, 1 - fv) * 0.6)
    joint = smoothstep(0.008, 0.025, e)
    var = _h(np.floor(bu).astype(np.int64), np.floor(bv).astype(np.int64), sd)
    pud = smoothstep(0.55, 0.62, fbm(u * 0.5, v * 0.5, 3, sd + 3))
    alb = lin(0.44, 0.44, 0.43)[None] * ((0.7 + 0.35 * var) * (0.5 + 0.5 * joint) * (1 - 0.35 * pud))[:, None]
    return alb, (0.3 + 0.5 * pud).astype(np.float32)


MATS = {WALL: m_wall, STONE: m_stone, ROOF: m_roof, WOOD: m_wood, WINDOW: m_window, DARK: m_dark, CAP: m_cap,
        EAVE: m_eave, HULL: m_hull, AWNING: m_awning, CLOTH: m_flat((0.13, 0.16, 0.24)), HAT: m_hat, TREE: m_tree,
        GUNWALE: m_gunwale, BRIDGE: m_bridge, INTRADOS: m_intrados, PAVE: m_pave, DECK: m_deck,
        SKIN: m_flat((0.55, 0.40, 0.31)), INTERIOR: m_interior}

# ---------------------------------------------------------------- lighting / sky / fog
SKY_HOR = lin(0.865, 0.885, 0.89)
SKY_ZEN = lin(0.62, 0.68, 0.74)
FOGC = lin(0.845, 0.865, 0.87)
GLOW = lin(0.98, 0.96, 0.90)
SKY_I = np.array([1.10, 1.12, 1.15], np.float32)
GROUND_I = np.array([0.30, 0.33, 0.32], np.float32)
DIR_I = np.array([0.32, 0.30, 0.27], np.float32)
WATER = lin(0.15, 0.20, 0.18)
ENV_LOW = lin(0.30, 0.34, 0.33)


def sky(dx, dy, dz):
    n = np.sqrt(dx * dx + dy * dy + dz * dz)
    x, y, z = dx / n, dy / n, dz / n
    e = np.clip(y, 0, 1)
    t = smoothstep(0.0, 0.6, e) ** 0.8
    col = mix3(SKY_HOR[None].repeat(len(x), 0), SKY_ZEN[None].repeat(len(x), 0), t)
    k = 1.0 / (np.clip(y, 0, None) + 0.15)
    cl = fbm(x * k * 0.9 + 3.0, z * k * 0.35, 5, 77)
    cl2 = fbm(x * k * 0.3 + 1.0, z * k * 0.12, 4, 78)
    col = col * (0.84 + 0.16 * cl + 0.16 * cl2)[:, None]
    brk = smoothstep(0.58, 0.74, cl2) * smoothstep(0.02, 0.2, y)
    col = col + (GLOW * 0.12)[None] * brk[:, None]
    g = np.clip(x * LDIR[0] + y * LDIR[1] + z * LDIR[2], 0, 1) ** 5
    col = col + (GLOW * 0.22)[None] * g[:, None]
    col[y < 0] = ENV_LOW
    return col.astype(np.float32)


def fogcol(dx, dy, dz):
    n = np.sqrt(dx * dx + dz * dz) + 1e-6
    g = np.clip((dx * LDIR[0] + dz * LDIR[2]) / n / math.hypot(LDIR[0], LDIR[2]), 0, 1) ** 4
    return (FOGC[None] + (GLOW * 0.13)[None] * g[:, None]).astype(np.float32)


def fogamt(t, y, x=None):
    a = 1 - np.exp(-(t / 85.0) ** 1.4)
    low = 0.6 * np.exp(-np.clip(y, 0, None) / 2.4) * smoothstep(26.0, 75.0, t)
    if x is not None:   # 贴着水面、一缕一缕的薄雾
        low = low * (0.45 + 0.9 * fbm(x * 0.06, t * 0.05, 3, 4242))
    return np.clip(1 - (1 - a) * (1 - low), 0, 1).astype(np.float32)


# ---------------------------------------------------------------- raster + shade
def pip(u, v, poly):
    ins = np.zeros(u.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if y1 == y2:
            continue
        c = (y1 > v) != (y2 > v)
        xi = x1 + (v - y1) * ((x2 - x1) / (y2 - y1))
        ins ^= c & (u < xi)
    return ins


def raster(mirror):
    zb = np.full((RH, RW), np.inf, np.float32)
    fid = np.full((RH, RW), -1, np.int32)
    ub = np.zeros((RH, RW), np.float32)
    vb = np.zeros((RH, RW), np.float32)
    for k, fc in enumerate(FACES):
        O, U, V = fc['O'].copy(), fc['U'].copy(), fc['V'].copy()
        if mirror:
            O[1], U[1], V[1] = -O[1], -U[1], -V[1]
        N = np.cross(U, V)
        if fc['rect'] is not None:
            u0, u1, v0, v1 = fc['rect']
            puv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        else:
            puv = fc['poly']
        P = np.array([O + a * U + b * V for a, b in puv]) - CAM
        if P[:, 2].max() < NEAR:
            continue
        if mirror and (P[:, 1] + CAM[1]).min() > 0.05:
            continue
        if P[:, 2].min() < NEAR:
            x0, x1, y0, y1 = 0, RW, 0, RH
        else:
            sx = CXs + FOC * P[:, 0] / P[:, 2]
            sy = HYs - FOC * P[:, 1] / P[:, 2]
            x0, x1 = max(0, int(math.floor(sx.min())) - 1), min(RW, int(math.ceil(sx.max())) + 2)
            y0, y1 = max(0, int(math.floor(sy.min())) - 1), min(RH, int(math.ceil(sy.max())) + 2)
        if mirror:
            y0 = max(y0, int(HYs) - 2)
        if x0 >= x1 or y0 >= y1:
            continue
        dx = ((np.arange(x0, x1, dtype=np.float32) + 0.5) - CXs) / FOC
        dy = -((np.arange(y0, y1, dtype=np.float32) + 0.5) - HYs) / FOC
        oc = O - CAM
        num = float(np.dot(oc, N))
        den = dx[None, :] * np.float32(N[0]) + dy[:, None] * np.float32(N[1]) + np.float32(N[2])
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            t = num / den
        cand = (t > NEAR) & (t < zb[y0:y1, x0:x1])
        if mirror:
            cand &= (CAM[1] + t * dy[:, None]) < 0.02
        iy, ix = np.nonzero(cand)
        if iy.size == 0:
            continue
        tt = t[iy, ix]
        ddx, ddy = dx[ix], dy[iy]
        u = tt * (ddx * U[0] + ddy * U[1] + U[2]) - float(np.dot(oc, U))
        v = tt * (ddx * V[0] + ddy * V[1] + V[2]) - float(np.dot(oc, V))
        if fc['rect'] is not None:
            ok = (u >= u0) & (u <= u1) & (v >= v0) & (v <= v1)
        else:
            ok = pip(u, v, puv)
        if fc['mask'] is not None and ok.any():
            ok2 = np.zeros_like(ok)
            ok2[ok] = fc['mask'](u[ok], v[ok])
            ok = ok2
        if not ok.any():
            continue
        iy, ix = iy[ok] + y0, ix[ok] + x0
        zb[iy, ix] = tt[ok]
        fid[iy, ix] = k
        ub[iy, ix] = u[ok]
        vb[iy, ix] = v[ok]
    return zb, fid, ub, vb


def shade(zb, fid, ub, vb, mirror):
    cam = CAMM if mirror else CAM
    d = cam[None, :] - FO
    sg = np.sign(np.einsum('ij,ij->i', d, FN))
    sg[sg == 0] = 1
    NO = (FN * sg[:, None]).astype(np.float32)
    out = np.empty((RH * RW, 3), np.float32)
    ff, zf, uf, vf = fid.ravel(), zb.ravel(), ub.ravel(), vb.ravel()
    CH = 1 << 20
    for s0 in range(0, RH * RW, CH):
        s1 = min(RH * RW, s0 + CH)
        ids = np.arange(s0, s1)
        f = ff[s0:s1]
        py_, px_ = np.divmod(ids, RW)
        dx = ((px_ + 0.5) - CXs).astype(np.float32) / FOC
        dy = (-((py_ + 0.5) - HYs)).astype(np.float32) / FOC
        dyt = -dy if mirror else dy
        dz = np.ones_like(dx)
        res = np.empty((s1 - s0, 3), np.float32)
        hit = f >= 0
        nh = ~hit
        if nh.any():
            res[nh] = sky(dx[nh], dyt[nh], dz[nh])
        if hit.any():
            fh = f[hit]
            t = zf[s0:s1][hit]
            u = uf[s0:s1][hit]
            v = vf[s0:s1][hit]
            X = CAM[0] + t * dx[hit]
            Yw = CAM[1] + t * dy[hit]
            if mirror:
                Yw = -Yw
            Zw = CAM[2] + t
            alb = np.empty((len(fh), 3), np.float32)
            gl = np.zeros(len(fh), np.float32)
            mats = FMAT[fh]
            for m in np.unique(mats):
                sel = mats == m
                a, g = MATS[int(m)](u[sel], v[sel], X[sel], Yw[sel], Zw[sel], fh[sel])
                alb[sel] = a
                gl[sel] = g
            N = NO[fh]
            k = (0.5 + 0.5 * N[:, 1])[:, None]
            ndl = np.clip(N @ LDIR, 0, None)[:, None]
            irr = GROUND_I[None] * (1 - k) + SKY_I[None] * k + DIR_I[None] * ndl
            col = alb * irr
            D = np.stack([dx[hit], dyt[hit], dz[hit]], 1)
            D /= np.linalg.norm(D, axis=1, keepdims=True)
            dn = np.sum(D * N, 1)
            R = D - 2 * dn[:, None] * N
            fres = np.minimum(0.04 + 0.96 * (1 - np.clip(-dn, 0, 1)) ** 5, 0.55)
            col += (gl * fres)[:, None] * sky(R[:, 0], R[:, 1], R[:, 2])
            fa = fogamt(t, Yw, X)[:, None]
            col = col * (1 - fa) + fogcol(D[:, 0], D[:, 1], D[:, 2]) * fa
            res[hit] = col
        out[s0:s1] = res
    return out.reshape(RH, RW, 3)


def draw_lanterns(col, zb, mirror):
    for (x, y, z) in LANTERNS:
        yy = -y if mirror else y
        rel = np.array([x, yy, z]) - CAM
        if rel[2] < 1:
            continue
        sx = CXs + FOC * rel[0] / rel[2]
        sy = HYs - FOC * rel[1] / rel[2]
        rx, ry = FOC * 0.23 / rel[2], FOC * 0.29 / rel[2]
        x0, x1 = int(sx - rx * 1.3), int(sx + rx * 1.3) + 2
        cord = FOC * 0.9 / rel[2]
        y0, y1 = int(sy - ry * 1.3 - (0 if mirror else cord)), int(sy + ry * 1.9 + (cord if mirror else 0)) + 2
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(RW, x1), min(RH, y1)
        if x0 >= x1 or y0 >= y1:
            continue
        gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float32) + 0.5
        ex = (gx - sx) / rx
        ey = (gy - sy) / ry
        if mirror:
            ey = -ey
        r = np.sqrt(ex * ex + ey * ey)
        cov = np.clip((1 - r) * rx, 0, 1)
        phi = np.arcsin(np.clip(ex / np.sqrt(np.clip(1 - ey * ey, 1e-3, 1)), -1, 1)) / (np.pi / 6)
        rib = 1 - 0.3 * np.exp(-(phi - np.round(phi)) ** 2 / 0.012)
        shade = (0.55 + 0.45 * np.clip(1 - ex * ex, 0, 1)) * (0.8 + 0.2 * (1 - ey)) * rib
        body = lin(0.80, 0.12, 0.07)[None, None] * shade[..., None] + lin(0.95, 0.45, 0.2)[None, None] * (
            0.35 * np.exp(-(ex * ex + (ey + 0.1) ** 2) * 2.5))[..., None]
        capm = ((np.abs(ey) > 0.82) & (np.abs(ey) < 1.08) & (np.abs(ex) < 0.42)).astype(np.float32)
        body = body * (1 - capm[..., None]) + lin(0.30, 0.22, 0.12)[None, None] * capm[..., None]
        cov = np.maximum(cov, capm)
        # 吊绳和穗子
        pxw = np.abs(gx - sx)
        cordm = ((pxw < max(1.0, rx * 0.05)) & (ey < -1.0) & (ey > -1.0 - 0.9 / 0.29)).astype(np.float32)
        tas = ((pxw < rx * 0.18) & (ey > 1.05) & (ey < 1.75)).astype(np.float32) * 0.9
        body = body * (1 - cordm[..., None]) + lin(0.12, 0.1, 0.08)[None, None] * cordm[..., None]
        body = body * (1 - tas[..., None]) + lin(0.7, 0.1, 0.06)[None, None] * tas[..., None]
        cov = np.maximum(np.maximum(cov, cordm), tas)
        fa = float(fogamt(np.array([rel[2]]), np.array([y]))[0])
        body = body * (1 - fa) + FOGC[None, None] * fa
        vis = (zb[y0:y1, x0:x1] > rel[2]).astype(np.float32)
        a = (cov * vis)[..., None]
        col[y0:y1, x0:x1] = col[y0:y1, x0:x1] * (1 - a) + body * a


def water(col, zb, colm):
    r0 = int(math.ceil(HYs)) + 1
    rows = np.arange(r0, RH, dtype=np.float32)
    dy = -((rows + 0.5) - HYs) / FOC
    tw = (CAM[1] / (-dy)).astype(np.float32)
    dx = ((np.arange(RW, dtype=np.float32) + 0.5) - CXs) / FOC
    TW = np.repeat(tw[:, None], RW, 1)
    WX = CAM[0] + TW * dx[None, :]
    WZ = TW
    persp = np.clip(12.0 / TW, 0.12, 1.3)
    n1 = fbm(WX * 0.55, WZ * 2.4, 4, 501) - 0.5
    n2 = fbm(WX * 0.45 + 7.1, WZ * 3.1, 4, 502) - 0.5
    ox = 14.0 * SS * n1 * persp
    oy = 24.0 * SS * n2 * persp
    rng = np.random.default_rng(9)
    ring_sum = np.zeros_like(TW)
    centers = [(rng.uniform(-5.5, 4.5), rng.uniform(10.5, 30.0)) for _ in range(22)]
    centers += [(rng.uniform(4.9, 5.3), rng.uniform(9.0, 31.0)) for _ in range(7)]      # 右岸檐下滴水
    centers += [(rng.uniform(-6.0, -5.6), rng.uniform(15.0, 31.0)) for _ in range(5)]   # 左岸檐下滴水
    for i, (xc, zc) in enumerate(centers):
        r0d = rng.uniform(0.15, 0.8)
        rr = np.sqrt((WX - xc) ** 2 + (WZ - zc) ** 2) + 1e-4
        ring = np.zeros_like(TW)
        for rad, amp in [(r0d, 1.0), (r0d * 0.55, 0.6)]:
            ring += amp * np.sin((rr - rad) * 2 * np.pi / 0.12) * np.exp(-((rr - rad) / 0.09) ** 2)
        ox += ring * (WX - xc) / rr * 8.0 * SS * persp
        oy += ring * (WZ - zc) / rr * 14.0 * SS * persp
        ring_sum += np.abs(ring)
    blurred = ndi.uniform_filter1d(colm, size=5, axis=0)
    blurred = ndi.gaussian_filter(blurred, (1.0, 1.0, 0))
    gy = np.clip(rows[:, None] + oy, 0, RH - 1)
    gx = np.clip(np.arange(RW, dtype=np.float32)[None, :] + ox, 0, RW - 1)
    refl = np.stack([ndi.map_coordinates(blurred[..., c], [gy, gx], order=1, mode='nearest') for c in range(3)], -1)
    cosv = (-dy[:, None] / np.sqrt(dx[None, :] ** 2 + dy[:, None] ** 2 + 1))
    Rf = 0.32 + 0.60 * (1 - cosv) ** 4
    fa = fogamt(TW, np.zeros_like(TW), WX)
    Dx = np.repeat(dx[None, :], len(rows), 0).ravel()
    fc = fogcol(Dx, np.zeros_like(Dx), np.ones_like(Dx)).reshape(len(rows), RW, 3)
    base = WATER[None, None] * (1 - fa[..., None]) + fc * fa[..., None]
    wcol = refl * Rf[..., None] + base * (1 - Rf[..., None])
    wcol = wcol * (1 + 0.12 * np.clip(ring_sum, 0, 1))[..., None]
    mask = TW < zb[r0:]
    sub = col[r0:]
    sub[mask] = wcol[mask]


def curve(ctrl, n):
    ctrl = np.asarray(ctrl, np.float64)
    t = np.linspace(0, 1, n)
    m = len(ctrl) - 1
    out = np.zeros((n, 2))
    for i, p in enumerate(ctrl):
        out += (math.comb(m, i) * (t ** i) * ((1 - t) ** (m - i)))[:, None] * p[None]
    return out


def willow(col):
    """前景：从左上角垂下来的柳枝（2D 叠加），枝叶带雨滴。"""
    rng = np.random.default_rng(11)
    S = SS
    lay = Image.new('RGBA', (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    br = curve([(-80, 190), (60, 60), (250, 25), (560, -60)], 80)
    for i in range(len(br) - 1):
        wdt = 26 - 20 * i / len(br)
        d.line([tuple(br[i] * S), tuple(br[i + 1] * S)], fill=(52, 44, 38, 255), width=int(wdt * S))
    tw = curve([(140, 40), (220, 70), (300, 60), (380, 95)], 30)
    for i in range(len(tw) - 1):
        d.line([tuple(tw[i] * S), tuple(tw[i + 1] * S)], fill=(56, 48, 40, 255), width=int(6 * S))
    greens = [(88, 112, 52), (104, 128, 58), (70, 94, 44), (120, 140, 66), (60, 82, 40)]
    for i in range(85):
        x0 = rng.uniform(-40, 500)
        if rng.random() < 0.3:
            k = int(np.argmin(np.abs(tw[:, 0] - x0)))
            y0 = tw[k, 1] if abs(tw[k, 0] - x0) < 20 else -10
        else:
            k = int(np.argmin(np.abs(br[:, 0] - x0)))
            y0 = br[k, 1] if abs(br[k, 0] - x0) < 25 else -10
        Ls = rng.uniform(120, 520) * (1.15 - 0.6 * max(0.0, x0) / 540)
        sway = rng.uniform(6, 26)
        drift = rng.uniform(-10, 30)
        ph = rng.uniform(0, 6.28)
        ts = np.linspace(0, 1, 50)
        xs = x0 + drift * ts ** 1.6 + sway * np.sin(ts * 3.2 + ph) * ts
        ys = y0 + Ls * ts
        stem = [(float(a * S), float(b * S)) for a, b in zip(xs, ys)]
        d.line(stem, fill=(74, 84, 46, 235), width=max(1, int(1.7 * S)))
        nleaf = int(Ls / 8.5)
        for j in range(nleaf):
            t = (j + 0.5) / nleaf
            idx = min(48, int(t * 49))
            px, py = xs[idx], ys[idx]
            tx, ty = xs[idx + 1] - xs[idx], ys[idx + 1] - ys[idx]
            ang = math.atan2(ty, tx) + (0.55 if j % 2 else -0.55) * rng.uniform(0.6, 1.2)
            ll = rng.uniform(13, 22) * (0.75 + 0.35 * (1 - t))
            lw = ll * 0.17
            ca, sa = math.cos(ang), math.sin(ang)
            pts = []
            for q in np.linspace(0, 1, 7):
                pts.append((px + ca * ll * q - sa * lw * math.sin(q * math.pi), py + sa * ll * q + ca * lw * math.sin(q * math.pi)))
            for q in np.linspace(1, 0, 7)[1:-1]:
                pts.append((px + ca * ll * q + sa * lw * math.sin(q * math.pi), py + sa * ll * q - ca * lw * math.sin(q * math.pi)))
            g = greens[int(rng.integers(len(greens)))]
            sh = rng.uniform(0.85, 1.15)
            d.polygon([(a * S, b * S) for a, b in pts], fill=(int(min(255, g[0] * sh)), int(min(255, g[1] * sh)), int(min(255, g[2] * sh)), 240))
            if rng.random() < 0.06:
                ex, ey = px + ca * ll, py + sa * ll + 2
                d.ellipse([(ex - 1.6) * S, (ey - 1.6) * S, (ex + 1.6) * S, (ey + 1.6) * S], fill=(235, 240, 242, 230))
    lay = lay.filter(ImageFilter.GaussianBlur(1.2 * S))
    a = np.asarray(lay, np.float32) / 255.0
    rgb = np.power(a[..., :3], 2.2)
    al = a[..., 3:4]
    col[:] = col * (1 - al) + rgb * al


EAVES = []


def drips(col, zb):
    """雨刚停：檐口还在往下滴水，水滴拉成细亮线，落到水面处有小涟漪（在 water 里）。"""
    rng = np.random.default_rng(77)
    for (x, y, z0, z1) in EAVES:
        for k in range(int((z1 - z0) * 1.2)):
            z = rng.uniform(z0 + 0.2, z1 - 0.2)
            y0 = y - 0.05
            y1 = y0 - rng.uniform(0.15, 0.5)
            p0 = np.array([x, y0 - rng.uniform(0, 2.2), z]) - CAM
            if p0[2] < 3:
                continue
            ln = FOC * (y0 - y1) / p0[2]
            sx = CXs + FOC * p0[0] / p0[2]
            sy = HYs - FOC * p0[1] / p0[2]
            if not (0 <= sx < RW - 2 and 0 <= sy < RH - ln - 2):
                continue
            if zb[int(sy), int(sx)] < p0[2] - 0.3:
                continue
            ys = np.arange(int(sy), int(sy + ln))
            a = np.linspace(0.2, 0.7, len(ys))[:, None]
            xi = int(sx)
            col[ys, xi] = col[ys, xi] * (1 - a) + lin(0.92, 0.94, 0.95)[None] * a
            col[ys, xi + 1] = col[ys, xi + 1] * (1 - 0.5 * a) + lin(0.92, 0.94, 0.95)[None] * 0.5 * a


def main():
    build()
    global FO, FN, FMAT, FSEED, FTINT, FP
    FO = np.array([f['O'] for f in FACES])
    FN = np.array([f['N'] for f in FACES])
    FMAT = np.array([f['mat'] for f in FACES], np.int32)
    FSEED = np.array([f['seed'] for f in FACES], np.int64)
    FTINT = np.array([f['tint'] for f in FACES], np.float32)
    FP = np.array([f['p'] for f in FACES], np.float32)
    log('faces', len(FACES), 'lanterns', len(LANTERNS))
    zb, fid, ub, vb = raster(False)
    log('raster main')
    col = shade(zb, fid, ub, vb, False)
    log('shade main')
    zbm, fidm, ubm, vbm = raster(True)
    log('raster mirror')
    colm = shade(zbm, fidm, ubm, vbm, True)
    log('shade mirror')
    del fidm, ubm, vbm
    draw_lanterns(col, zb, False)
    draw_lanterns(colm, zbm, True)
    water(col, zb, colm)
    log('water')
    drips(col, zb)
    del colm
    willow(col)
    log('willow')
    img = col.reshape(H, SS, W, SS, 3).mean((1, 3))
    img = np.power(np.clip(img, 0, 1), 1 / 2.2)
    # 雨后空气湿：轻微的柔光扩散
    img = 0.88 * img + 0.12 * ndi.gaussian_filter(img, (6, 6, 0))
    # 调色：轻微 S 曲线、暗部偏青、四角压暗、细颗粒
    img = img + 0.10 * (img - 0.5) * (1 - np.abs(2 * img - 1))
    lum = img @ np.array([0.299, 0.587, 0.114], np.float32)
    img = lum[..., None] + 1.08 * (img - lum[..., None])
    img = img + (0.025 * (1 - lum))[..., None] * np.array([-0.4, 0.1, 0.3], np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    img = img * (1 - 0.10 * r2)[..., None]
    img = img + np.random.default_rng(3).normal(0, 0.006, img.shape).astype(np.float32)
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    out.save(os.path.join(HERE, 'final.png'))
    for extra in sys.argv[1:]:
        out.save(os.path.join(HERE, extra))
    log('saved', out.size)


if __name__ == '__main__':
    main()
