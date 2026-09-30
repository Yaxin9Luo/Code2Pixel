#!/usr/bin/env python3
"""A02 日落时的雪山湖泊，湖面倒映着山影。

纯代码：Perlin 噪声生成山脉高度场 → 逐像素光线步进求交（地形、湖面、天空、云层）→
太阳低角度照明 + 软阴影 + 大气透视 → 湖面按菲涅尔公式反射（反射光线再次步进）→ 色调映射。
不读任何图片文件，随机种子固定。用法：python3 draw.py [输出路径]
"""
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
W, H = 1536, 1024
SEED = 7
F32 = np.float32
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def normalize(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


# ---------------- 噪声 ----------------
class Perlin:
    """二维梯度噪声，值域约 [-1, 1]。"""

    def __init__(self, seed):
        r = np.random.default_rng(seed)
        self.p = np.concatenate([r.permutation(256)] * 2).astype(np.int32)
        a = r.random(256) * 2 * np.pi
        self.gx, self.gy = np.cos(a).astype(F32), np.sin(a).astype(F32)

    def __call__(self, x, y):
        xf0, yf0 = np.floor(x), np.floor(y)
        xf, yf = (x - xf0).astype(F32), (y - yf0).astype(F32)
        xi, yi = xf0.astype(np.int64) & 255, yf0.astype(np.int64) & 255
        x1, y1 = (xi + 1) & 255, (yi + 1) & 255
        p = self.p

        def g(ix, iy, dx, dy):
            h = p[p[ix] + iy]
            return self.gx[h] * dx + self.gy[h] * dy

        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        n00, n10 = g(xi, yi, xf, yf), g(x1, yi, xf - 1, yf)
        n01, n11 = g(xi, y1, xf, yf - 1), g(x1, y1, xf - 1, yf - 1)
        a = n00 + u * (n10 - n00)
        b = n01 + u * (n11 - n01)
        return (a + v * (b - a)) * 1.4


NOISES = [Perlin(SEED * 100 + i) for i in range(24)]


def fbm(x, y, octaves, k0=0, gain=0.5, lac=2.03):
    s, amp, tot = 0.0, 1.0, 0.0
    for i in range(octaves):
        s = s + amp * NOISES[(k0 + i) % 24](x + 17.3 * i, y - 9.1 * i)
        tot += amp
        amp *= gain
        x, y = x * lac, y * lac
    return s / tot


def ridged(x, y, octaves, k0=0):
    """Musgrave 脊状多重分形：锋利的山脊，高频细节只长在高处。"""
    s, amp, wgt, tot = 0.0, 1.0, 1.0, 0.0
    for i in range(octaves):
        n = 1.0 - np.abs(NOISES[(k0 + i) % 24](x + 31.7 * i, y + 11.3 * i))
        n = n * n * wgt
        wgt = np.clip(n * 1.6, 0, 1)
        s = s + amp * n
        tot += amp
        amp *= 0.5
        # 每层旋转一点，避免网格方向感
        x, y = 1.6 * x + 1.2 * y, -1.2 * x + 1.6 * y
    return s / tot


# ---------------- 地形 ----------------
N = 3072
X0, X1, Z0, Z1 = -16.0, 16.0, -1.0, 31.0
CELL = (X1 - X0) / (N - 1)
HMAX = 3.6


def terrain_block(x, z):
    """单位 km。湖在 z∈(0, ~6.8) 的山谷里，远处是雪峰。返回 (高度, 森林密度, 雪噪声)"""
    wx = x + 0.55 * fbm(x * 0.22, z * 0.22, 3, k0=1)
    wz = z + 0.55 * fbm(x * 0.22 + 5.2, z * 0.22 + 1.3, 3, k0=4)
    r = ridged(wx * 0.42, wz * 0.42, 9, k0=7)            # 0..~0.9

    def peak(cx, cz, hgt, rad, rot, sharp):
        dx, dz = wx - cx, wz - cz
        c, s = np.cos(rot), np.sin(rot)
        u, v = c * dx - s * dz, s * dx + c * dz
        d = 0.6 * (np.abs(u) + np.abs(v)) / rad + 0.4 * np.sqrt(u * u + v * v) / rad
        return hgt * np.clip(1 - d, 0, None) ** sharp

    peaks = [peak(0.8, 13.5, 3.0, 7.5, 0.45, 1.12),      # 主峰（画面中偏右）
             peak(-4.0, 16.0, 2.5, 7.0, 0.2, 1.1),
             peak(5.8, 16.5, 2.4, 6.5, 0.9, 1.1),
             peak(-9.0, 14.0, 2.1, 6.5, 0.3, 1.1),
             peak(10.0, 13.0, 2.0, 6.0, 0.6, 1.1),
             peak(-1.5, 22.0, 2.6, 7.5, 0.1, 1.05),
             peak(4.5, 25.0, 2.8, 8.5, 0.4, 1.05),
             peak(-7.5, 24.0, 2.6, 8.0, 0.7, 1.05)]
    mass = np.maximum.reduce(peaks)
    mass = np.maximum(mass, 1.55 * smoothstep(8.0, 14.0, wz) * (0.75 + 0.25 * fbm(wx * 0.3, wz * 0.3, 2, k0=12)))
    mtn = mass * (0.6 + 0.8 * r)

    # 山谷两侧的前山（森林覆盖）
    ax = 0.35 * np.sin(0.28 * wz + 0.7)
    half = 1.05 + 0.2 * wz
    side = np.abs(wx - ax) - half
    walls = 1.15 * smoothstep(0.0, 1.8, side) * (0.65 + 0.7 * r)
    # 湖盆：谷内、z < z_end 为湖
    z_end = 6.9 + 0.7 * fbm(x * 0.5, 3.3, 2, k0=14)
    inside = np.maximum(side, z - z_end)                  # <0 在湖里
    ground = -0.3 + 0.33 * smoothstep(-0.25, 0.05, inside)
    ground = ground + 0.12 * smoothstep(0.0, 3.0, z - z_end) + 0.02 * fbm(x * 3, z * 3, 3, k0=15)
    hgt = ground + np.maximum(walls, mtn)
    # 森林：树线以下、坡度不太陡的地方，冠层略微抬高
    forest_n = fbm(x * 2.2, z * 2.2, 4, k0=16)
    forest = smoothstep(0.95, 0.7, hgt + 0.15 * forest_n) * smoothstep(0.005, 0.03, hgt) * smoothstep(-0.25, 0.15, forest_n)
    canopy = forest * 0.018 * (0.7 + 0.6 * fbm(x * 40, z * 40, 2, k0=18))
    snow_n = fbm(x * 1.3, z * 1.3, 5, k0=19)
    return (hgt + canopy).astype(F32), forest.astype(F32), snow_n.astype(F32)


def build_terrain():
    zs = np.linspace(Z0, Z1, N, dtype=F32)
    xs = np.linspace(X0, X1, N, dtype=F32)
    Hm, Fo, Sn = (np.empty((N, N), F32) for _ in range(3))
    B = 192
    for i0 in range(0, N, B):
        z, x = np.broadcast_arrays(zs[i0:i0 + B, None], xs[None, :])
        Hm[i0:i0 + B], Fo[i0:i0 + B], Sn[i0:i0 + B] = terrain_block(x, z)
    gz, gx = np.gradient(Hm, CELL)
    ny = 1.0 / np.sqrt(1 + gx * gx + gz * gz)
    # 雪：雪线以上、坡度不太陡的地方积雪；凹处（雪沟、冰斗）积得多，凸起的陡脊露出岩石
    from scipy import ndimage as ndi
    curv = ndi.gaussian_laplace(Hm, 2.5) / (CELL * CELL)          # >0 为凹
    curv = curv / (np.percentile(np.abs(curv), 90) + 1e-6)
    snowline = 1.25 + 0.3 * Sn
    zs2, xs2 = np.meshgrid(np.linspace(Z0, Z1, N, dtype=F32), np.linspace(X0, X1, N, dtype=F32), indexing="ij")
    fine = np.empty((N, N), F32)
    for i0 in range(0, N, 256):
        fine[i0:i0 + 256] = fbm(xs2[i0:i0 + 256] * 38, zs2[i0:i0 + 256] * 38, 3, k0=6)
    del xs2, zs2
    Pn = (Hm - snowline) / 0.35 + (ny - 0.57) / 0.085 + 1.0 * np.clip(curv, -1.5, 2) + 0.5 * fine
    S = smoothstep(-0.5, 0.5, Pn) * smoothstep(snowline - 0.5, snowline - 0.15, Hm)
    return Hm, gx.astype(F32), gz.astype(F32), Fo, np.clip(S, 0, 1).astype(F32), Sn


class Fields:
    pass


FD = Fields()


def bilerp(flat, x, z, outside=-1.0):
    gx = (x - X0) / CELL
    gz = (z - Z0) / CELL
    out = (gx < 0) | (gz < 0) | (gx > N - 1.01) | (gz > N - 1.01)
    gx = np.clip(gx, 0, N - 1.01)
    gz = np.clip(gz, 0, N - 1.01)
    ix, iz = gx.astype(np.int64), gz.astype(np.int64)
    fx, fz = (gx - ix).astype(F32), (gz - iz).astype(F32)
    i = iz * N + ix
    a, b, c, d = flat[i], flat[i + 1], flat[i + N], flat[i + N + 1]
    top = a + (b - a) * fx
    v = top + (c + (d - c) * fx - top) * fz
    if outside is not None:
        v = np.where(out, F32(outside), v)
    return v


def height(x, z):
    return bilerp(FD.h, x, z)


# ---------------- 光照与天空 ----------------
SUN = normalize(np.array([np.sin(np.radians(115)), 0.055, np.cos(np.radians(115))]))  # 太阳在右后方、仰角 3°
SUN_COL = np.array([1.0, 0.33, 0.16], F32) * 2.7
SKY_AMB = np.array([0.13, 0.18, 0.4], F32) * 1.0


def sky(O, D, clouds=True):
    y = np.clip(D[:, 1], -1, 1)
    e = np.arcsin(np.maximum(y, 0))
    cs = D @ SUN
    tow = ((cs + 1) * 0.5) ** 3
    hor_away = np.array([1.3, 0.62, 0.36], F32)
    hor_sun = np.array([1.6, 0.72, 0.28], F32)
    hor = hor_away + (hor_sun - hor_away) * tow[:, None]
    pink = np.array([0.78, 0.42, 0.52], F32) + np.array([0.3, 0.12, -0.08], F32) * tow[:, None]
    blue = np.array([0.2, 0.24, 0.5], F32)
    zen = np.array([0.05, 0.08, 0.26], F32)
    a = smoothstep(0.0, 0.12, e)[:, None]
    b = smoothstep(0.08, 0.3, e)[:, None]
    c = smoothstep(0.25, 0.7, e)[:, None]
    col = hor * (1 - a) + pink * a
    col = col * (1 - b) + blue * b
    col = col * (1 - c) + zen * c
    glowband = np.exp(-((e - 0.11) / 0.07) ** 2)[:, None]
    col = col + np.array([0.35, 0.14, 0.02], F32) * glowband
    col = col + np.array([1.0, 0.45, 0.15], F32) * (0.6 * np.exp(-(1 - cs) * 3.0) + 3.0 * np.exp(-(1 - cs) * 40))[:, None]
    # 云：5 km 高的云层平面
    up = (D[:, 1] > 0.005) & (O[:, 1] < 4.9) & clouds
    if up.any():
        Du, Ou = D[up], O[up]
        tc = (5.0 - Ou[:, 1]) / Du[:, 1]
        px, pz = Ou[:, 0] + tc * Du[:, 0], Ou[:, 2] + tc * Du[:, 2]
        cx, cz = px / 11.0, pz / 5.5

        def dens(u, v):
            return fbm(u + 0.4 * fbm(u * 0.5, v * 0.5, 2, k0=20), v, 6, k0=21)

        d0 = dens(cx, cz)
        cov = smoothstep(0.02, 0.3, d0)
        d1 = dens(cx + 0.12 * SUN[0], cz + 0.12 * SUN[2] * 2)
        lit = np.clip(0.55 + 4.0 * (d0 - d1), 0, 1)
        tw = tow[up]
        bright = np.array([1.9, 0.72, 0.4], F32)[None] * (0.55 + 0.6 * tw[:, None])
        dark = np.array([0.3, 0.17, 0.3], F32)[None]
        ccol = dark + (bright - dark) * lit[:, None]
        fade = np.exp(-tc / 70.0) * smoothstep(0.005, 0.05, Du[:, 1])
        alpha = (cov * fade * 0.95)[:, None]
        col[up] = col[up] * (1 - alpha) + ccol * alpha
    return col


def haze_color(D):
    Dh = D.copy()
    Dh[:, 1] = 0.1
    return sky(np.zeros_like(Dh), normalize(Dh), clouds=False) * 0.75


def aerial(col, O, D, t):
    """大气透视：整体很清澈，只在很远处和贴近湖面的低空有一点薄雾。"""
    yav = O[:, 1] + 0.5 * t * D[:, 1]
    dens = 1 / 85.0 + 0.006 * np.exp(-np.maximum(yav, 0) / 0.08) + 0.03 * np.exp(-np.maximum(yav, 0) / 0.025)
    tr = np.exp(-t * dens)[:, None]
    hz = 0.45 * haze_color(D) + 0.55 * np.array([0.24, 0.26, 0.46], F32)[None]
    return col * tr + hz * (1 - tr)


# ---------------- 光线步进 ----------------
def march(O, D, tmax, maxit=900):
    n = len(D)
    t = np.zeros(n, F32) + 0.002
    tp = t.copy()
    res = np.full(n, np.inf, F32)
    idx = np.arange(n)
    for _ in range(maxit):
        if idx.size == 0:
            break
        tt = t[idx]
        o, d = O[idx], D[idx]
        px, py, pz = o[:, 0] + tt * d[:, 0], o[:, 1] + tt * d[:, 1], o[:, 2] + tt * d[:, 2]
        dh = py - height(px, pz)
        hit = dh < 0
        if hit.any():
            hi = idx[hit]
            a, b = tp[hi].copy(), tt[hit].copy()
            oh, dd = O[hi], D[hi]
            for _ in range(10):
                m = 0.5 * (a + b)
                below = oh[:, 1] + m * dd[:, 1] < height(oh[:, 0] + m * dd[:, 0], oh[:, 2] + m * dd[:, 2])
                b = np.where(below, m, b)
                a = np.where(below, a, m)
            res[hi] = 0.5 * (a + b)
        esc = (tt > tmax[idx]) | ((py > HMAX) & (d[:, 1] >= 0))
        keep = ~(hit | esc)
        ik = idx[keep]
        tk = tt[keep]
        tp[ik] = tk
        t[ik] = tk + np.maximum(0.4 * dh[keep], 0.0012 + 0.0022 * tk)
        idx = ik
    return res


def soft_shadow(P, n_iter=110):
    n = len(P)
    t = np.full(n, 0.015, F32)
    res = np.ones(n, F32)
    idx = np.arange(n)
    for _ in range(n_iter):
        if idx.size == 0:
            break
        tt = t[idx]
        p = P[idx]
        px, py, pz = p[:, 0] + tt * SUN[0], p[:, 1] + tt * SUN[1], p[:, 2] + tt * SUN[2]
        dh = py - height(px, pz)
        res[idx] = np.minimum(res[idx], np.clip(14.0 * dh / tt, 0, 1))
        done = (res[idx] <= 0.001) | (py > HMAX) | (tt > 30)
        keep = ~done
        ik = idx[keep]
        t[ik] = tt[keep] + np.clip(0.5 * np.abs(dh[keep]), 0.01, 0.4)
        idx = ik
    return res


def shade_terrain(O, D, t):
    P = O + t[:, None] * D
    x, z = P[:, 0], P[:, 2]
    h = P[:, 1]
    gx, gz = bilerp(FD.gx, x, z, 0.0), bilerp(FD.gz, x, z, 0.0)
    nrm = normalize(np.stack([-gx, np.ones_like(gx), -gz], -1))
    S = bilerp(FD.s, x, z, 0.0)
    Fo = bilerp(FD.f, x, z, 0.0)
    Sn = bilerp(FD.sn, x, z, 0.0)
    # 细节：凹凸扰动法线（约 20 m 和 10 m 两层），雪的边缘加高频噪声变得更利落
    e = 0.003

    def bump(xx, zz):
        return fbm(xx * 45, zz * 45, 2, k0=5)

    b0 = bump(x, z)
    kb = 0.0025 * (1 - 0.6 * S)
    nrm = normalize(nrm + np.stack([-(bump(x + e, z) - b0) / e * kb, np.zeros_like(b0),
                                    -(bump(x, z + e) - b0) / e * kb], -1))
    hf = fbm(x * 120, z * 120, 2, k0=8)
    S = smoothstep(0.3, 0.7, S + 0.35 * hf)
    # 反照率
    strata = fbm(x * 6, h * 30 + 0.3 * fbm(x * 3, z * 3, 2, k0=10), 3, k0=11)
    rock = np.array([0.066, 0.061, 0.058], F32)[None] * (0.65 + 0.7 * (0.5 + 0.5 * strata) + 0.3 * b0)[:, None]
    meadow = np.array([0.07, 0.075, 0.035], F32)[None] * (0.8 + 0.4 * hf)[:, None]
    crown = fbm(x * 90, z * 90, 2, k0=12)
    forest = np.array([0.016, 0.028, 0.02], F32)[None] * (0.35 + 1.3 * np.clip(0.5 + crown, 0, 1))[:, None]
    low = smoothstep(0.9, 0.4, h)[:, None]
    alb = rock * (1 - low) + meadow * low
    alb = alb * (1 - Fo[:, None]) + forest * Fo[:, None]
    shore = smoothstep(0.012, 0.0, h)[:, None]                 # 湖岸石滩
    alb = alb * (1 - shore) + np.array([0.12, 0.11, 0.1], F32)[None] * shore
    snow = np.array([0.86, 0.88, 0.92], F32)[None]
    alb = alb * (1 - S[:, None]) + snow * S[:, None]
    # 太阳（低角度，暖色）+ 软阴影 + 越低越早进入地球阴影
    ndl = np.clip(nrm @ SUN, 0, 1)
    vis = np.zeros_like(ndl)
    lit = ndl > 0
    if lit.any():
        vis[lit] = soft_shadow(P[lit] + nrm[lit] * 0.004)
    vis = vis * smoothstep(0.15, 1.3, h)
    direct = SUN_COL[None] * (ndl * vis)[:, None]
    amb = SKY_AMB[None] * (0.55 + 0.45 * nrm[:, 1])[:, None]
    bounce = np.array([0.03, 0.022, 0.026], F32)[None] * (1 - nrm[:, 1])[:, None]
    col = alb * (direct + amb + bounce)
    return aerial(col, O, D, t)


def water_normal(x, z):
    """几乎平静的湖面：极小的波纹斜率。"""
    band = 1 + 5 * smoothstep(0.35, 0.6, fbm(x * 0.7, z * 5.0, 3, k0=13))
    sx = band * (0.0010 * fbm(x * 90, z * 900, 3, k0=22) + 0.0005 * fbm(x * 400, z * 3000, 2, k0=2))
    sz = band * 0.0018 * fbm(x * 60, z * 600, 3, k0=23)
    return normalize(np.stack([-sx, np.ones_like(sx), -sz], -1))


def render_rays(O, D):
    n = len(D)
    col = np.zeros((n, 3), F32)
    depth = np.full(n, 1e3, F32)
    down = D[:, 1] < -1e-5
    tw = np.full(n, 60.0, F32)
    tw[down] = -O[down, 1] / D[down, 1]
    tmax = np.minimum(tw, 60.0)
    t = march(O, D, tmax)
    hit = np.isfinite(t)
    log("primary hits", hit.sum(), "of", n)
    if hit.any():
        col[hit] = shade_terrain(O[hit], D[hit], t[hit])
        depth[hit] = t[hit]
    water = (~hit) & down & (tw < 60)
    if water.any():
        Pw = O[water] + tw[water, None] * D[water]
        nw = water_normal(Pw[:, 0], Pw[:, 2])
        Dw = D[water]
        R = Dw - 2 * (Dw * nw).sum(-1, keepdims=True) * nw
        R[:, 1] = np.abs(R[:, 1])
        cos_i = np.clip(-(Dw * nw).sum(-1), 0, 1)
        fr = 0.02 + 0.98 * (1 - cos_i) ** 5
        Po = Pw + np.array([0, 0.0003, 0], F32)
        tr = march(Po, R, np.full(len(R), 60.0, F32))
        rh = np.isfinite(tr)
        rc = sky(Po, R)
        if rh.any():
            rc[rh] = shade_terrain(Po[rh], R[rh], tr[rh])
        body = np.array([0.008, 0.02, 0.026], F32)[None]
        c = rc * fr[:, None] * 0.96 + body * (1 - fr[:, None])
        col[water] = aerial(c, O[water], Dw, tw[water])
        depth[water] = tw[water]
    skym = ~(hit | water)
    if skym.any():
        col[skym] = sky(O[skym], D[skym])
    kind = np.where(hit, 1, np.where(water, 2, 0)).astype(np.int8)
    return col, depth, kind


# ---------------- 相机 ----------------
CAM = np.array([0.0, 0.004, 0.0], F32)
PITCH = np.radians(2.2)
FOCAL = (W / 2) / np.tan(np.radians(30))


def camera_rays(px, py):
    fwd = np.array([0, np.sin(PITCH), np.cos(PITCH)], F32)
    right = np.array([1, 0, 0], F32)
    upv = np.array([0, np.cos(PITCH), -np.sin(PITCH)], F32)
    D = fwd[None] * FOCAL + right[None] * (px - W / 2)[:, None] - upv[None] * (py - H / 2)[:, None]
    D = normalize(D.astype(F32))
    O = np.broadcast_to(CAM, D.shape).copy()
    return O, D


def tonemap(c):
    c = np.maximum(c, 0) * 1.05
    a = (c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14)
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, 12.92 * a, 1.055 * np.power(a, 1 / 2.4) - 0.055)


# ---------------- 近景：左岸云杉剪影及其倒影（按透视算位置和大小）----------------
Y_HOR = H / 2 + FOCAL * np.tan(PITCH)


def spruce(rng, x0, yb, hpx):
    """云杉剪影：一层层轮生的枝，每层枝长随机，枝梢下垂；顶上一根细尖。"""
    n = max(80, int(hpx * 2))
    hs = np.linspace(0.0, 1.0, n)
    k = rng.uniform(13, 21)
    ph = rng.random()
    lenL, lenR = rng.uniform(0.6, 1.15, int(k) + 4), rng.uniform(0.6, 1.15, int(k) + 4)
    prof = np.clip(1 - hs, 0, 1) ** rng.uniform(0.8, 1.0)
    wb = hpx * rng.uniform(0.12, 0.18)
    pl = hs * k + ph
    pr = hs * k + ph + rng.uniform(0.3, 0.7)
    iL, iR = pl.astype(int), pr.astype(int)
    sl, sr = pl - iL, pr - iR
    wl = wb * prof * (1 - 0.55 * sl ** 0.45) * lenL[iL] * (1 + 0.07 * rng.standard_normal(n))
    wr = wb * prof * (1 - 0.55 * sr ** 0.45) * lenR[iR] * (1 + 0.07 * rng.standard_normal(n))
    spire = hs > 0.88
    wl[spire] *= 0.55
    wr[spire] *= 0.55
    lean = rng.normal(0, 0.012) * hpx * hs
    ys = yb - hs * hpx
    xl, xr = x0 + lean - np.abs(wl) - 0.35, x0 + lean + np.abs(wr) + 0.35
    top = (x0 + lean[-1], yb - hpx * 1.04)
    return list(zip(xl, ys)) + [top] + list(zip(xr[::-1], ys[::-1]))


def foreground(img, kind):
    SS = 3
    rng = np.random.default_rng(SEED + 5)
    from PIL import ImageDraw
    m_up = Image.new("L", (W * SS, H * SS), 0)
    m_dn = Image.new("L", (W * SS, H * SS), 0)
    du, dd = ImageDraw.Draw(m_up), ImageDraw.Draw(m_dn)
    cam_h = float(CAM[1])
    tip = 500.0

    def dist(xp):                      # 岸边到相机的距离（km）：越往左越近
        u = np.clip(xp / tip, 0, 1)
        return 0.2 + 0.26 * u ** 1.2

    def ybase(xp):
        return Y_HOR + FOCAL * cam_h / dist(xp)

    def put(poly, yb):
        du.polygon([(x * SS, y * SS) for x, y in poly], fill=255)
        dd.polygon([(x * SS, (2 * yb - y) * SS) for x, y in poly], fill=255)

    # 岸：低矮的灌丛带（高 2~7 m），往岬角渐低，末端几块石头
    xs = np.linspace(-20, tip + 30, 700)
    fz = 0.5 + 0.5 * fbm(xs * 0.06, np.zeros_like(xs) + 3.1, 4, k0=17)
    hb = (0.0015 + 0.006 * fz ** 1.5) * smoothstep(tip + 30, tip - 60, xs)
    top = [(x, ybase(min(x, tip)) - FOCAL * hb[i] / dist(min(x, tip))) for i, x in enumerate(xs)]
    for (x, y), (x2, y2) in zip(top[:-1], top[1:]):
        yb1, yb2 = ybase(min(x, tip)), ybase(min(x2, tip))
        quad = [(x, y), (x2, y2), (x2 + 0.6, yb2 + 0.4), (x - 0.6, yb1 + 0.4)]
        du.polygon([(a * SS, b * SS) for a, b in quad], fill=255)
        dd.polygon([(a * SS, (2 * (yb1 if a < (x + x2) / 2 else yb2) - b) * SS) for a, b in quad], fill=255)
    for _ in range(6):                  # 岬角外的小石头
        xr = tip + rng.uniform(5, 60)
        yb = ybase(tip)
        wr_, hr_ = rng.uniform(3, 9), rng.uniform(1.2, 3.0)
        th = np.linspace(0, np.pi, 12)
        put([(xr + wr_ * np.cos(a), yb - hr_ * np.sin(a) ** 0.7) for a in th], yb)
    # 树：后排小、前排大，越靠岬角越稀越矮
    trees = []
    for _ in range(260):
        x0 = rng.uniform(-60, tip - 10)
        u = np.clip(x0 / tip, 0, 1)
        if rng.random() < 0.6 * u ** 1.5:
            continue
        hm = (0.008 + 0.03 * rng.random() ** 1.4) * (1 - 0.5 * u)
        trees.append((dist(x0) + rng.uniform(0, 0.03), x0, hm))
    trees.sort(key=lambda t: -t[0])
    for d, x0, hm in trees:
        yb = Y_HOR + FOCAL * cam_h / d
        put(spruce(rng, x0, yb - rng.uniform(0.5, 3.0), FOCAL * hm / d), yb)
    a_up = np.asarray(m_up.resize((W, H), Image.BOX), F32) / 255
    a_dn = np.asarray(m_dn.resize((W, H), Image.BOX), F32) / 255
    # 倒影：随波纹轻微横向错动、略糊
    from scipy import ndimage as ndi
    yy, xx = np.mgrid[0:H, 0:W].astype(F32)
    off = 1.2 * fbm(yy * 0.35, xx * 0.004, 3, k0=3) * smoothstep(Y_HOR, Y_HOR + 60, yy)
    a_dn = ndi.map_coordinates(a_dn, [yy, xx + off], order=1, mode="nearest")
    a_dn = ndi.gaussian_filter(a_dn, (0.8, 0.4)) * (kind == 2)
    tree_lin = np.array([0.010, 0.014, 0.012], F32)
    dy = (yy - Y_HOR) / FOCAL
    fr = 0.02 + 0.98 * (1 - np.clip(dy, 0, 1)) ** 5
    refl_lin = tree_lin[None, None] * fr[..., None] + np.array([0.008, 0.02, 0.026], F32) * (1 - fr[..., None])
    t_up = tonemap(tree_lin[None])[0]
    img = img * (1 - a_dn[..., None]) + tonemap(refl_lin) * a_dn[..., None]
    img = img * (1 - a_up[..., None]) + t_up[None, None] * a_up[..., None]
    return img


def main():
    log("building terrain")
    FD.h2d, FD.gx2d, FD.gz2d, FD.f2d, FD.s2d, FD.sn2d = build_terrain()
    FD.h, FD.gx, FD.gz = FD.h2d.ravel(), FD.gx2d.ravel(), FD.gz2d.ravel()
    FD.f, FD.s, FD.sn = FD.f2d.ravel(), FD.s2d.ravel(), FD.sn2d.ravel()
    log("terrain done; max h", float(FD.h2d.max()))
    yy, xx = np.mgrid[0:H, 0:W].astype(F32)
    O, D = camera_rays(xx.ravel() + 0.5, yy.ravel() + 0.5)
    col, depth, kind = render_rays(O, D)
    img = tonemap(col).reshape(H, W, 3)
    log("first pass done")
    # 自适应抗锯齿：颜色或深度跳变大的像素再补 4 个子样本
    lum = img @ np.array([0.3, 0.59, 0.11], F32)
    dep = np.log(depth.reshape(H, W))
    e = np.zeros((H, W), bool)
    for ax in (0, 1):
        dl = np.abs(np.diff(lum, axis=ax)) > 0.06
        dd = np.abs(np.diff(dep, axis=ax)) > 0.08
        m = dl | dd
        if ax == 0:
            e[1:] |= m
            e[:-1] |= m
        else:
            e[:, 1:] |= m
            e[:, :-1] |= m
    ys, xs = np.nonzero(e)
    log("AA pixels", len(ys))
    offs = [(-0.375, -0.125), (0.125, -0.375), (0.375, 0.125), (-0.125, 0.375)]
    acc = np.zeros((len(ys), 3), F32)
    for ox, oy in offs:
        O2, D2 = camera_rays(xs.astype(F32) + 0.5 + ox, ys.astype(F32) + 0.5 + oy)
        c2, _, _ = render_rays(O2, D2)
        acc += tonemap(c2)
    img[ys, xs] = (acc + img[ys, xs]) / 5
    img = foreground(img, kind.reshape(H, W))
    # 轻微泛光 + 暗角 + 颗粒
    from scipy import ndimage as ndi
    bright = np.clip(img - 0.72, 0, 1)
    img = img + 0.35 * ndi.gaussian_filter(bright, (18, 18, 0))
    r = np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2))
    img = img * (1 - 0.18 * smoothstep(0.6, 1.5, r))[..., None]
    img = img + (np.random.default_rng(SEED).standard_normal((H, W, 1)) * 0.006).astype(F32)
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    out.save(OUT)
    log("saved", OUT)


if __name__ == "__main__":
    main()
