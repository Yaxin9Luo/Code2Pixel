#!/usr/bin/env python3
"""A08 木桌上的一碗水果和一个陶罐，侧光（A 赛道：只用代码画，不读任何图片、不联网）。

画法：用 numpy 写的一个小型 SDF 光线步进渲染器。
  场景  木桌（木板 + 木纹）、深色墙；釉面瓷碗（球壳 + 圈足）、碗里红苹果、橙子、梨、青苹果、垂下碗沿的一串葡萄、
        桌上一只柠檬，右后方一只上半截挂釉的陶罐（旋转体 + 双耳）。
  光照  左上前方一盏暖色点光源（侧光），SDF 软阴影 + 环境光遮蔽 + 桌面暖色反光 + 右侧很弱的冷补光，
        Blinn-Phong 高光，各物体用三维噪声做纹理（苹果条纹、橙皮凹点、梨的锈斑、葡萄的果粉、木纹、釉的流淌）。
  输出  2 倍超采样后缩小，ACES 色调映射，暗角。
python3 draw.py  →  final.png（固定随机种子，可完全复现）
"""
import argparse
import os
import time

import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402  只 import，用它的油画笔触把我们自己渲染的图画成油画

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1536, 1024
SEED = 808

# ---------------------------------------------------------------- 工具


def srgb2lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def mixc(a, b, t):
    """a, b: (N,3) 或 (3,)；t: (N,)"""
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    return a + (b - a) * np.asarray(t, np.float32)[:, None]


class Noise3:
    """三维值噪声（周期晶格 + 平滑三线性插值），多倍频。"""

    def __init__(self, seed, n=64):
        self.n = n
        self.g = np.random.default_rng(seed).random((n, n, n)).astype(np.float32)

    def base(self, x, y, z):
        n = self.n
        xf, yf, zf = np.floor(x), np.floor(y), np.floor(z)
        fx, fy, fz = x - xf, y - yf, z - zf
        fx = fx * fx * (3 - 2 * fx)
        fy = fy * fy * (3 - 2 * fy)
        fz = fz * fz * (3 - 2 * fz)
        x0, y0, z0 = xf.astype(np.int64) % n, yf.astype(np.int64) % n, zf.astype(np.int64) % n
        x1, y1, z1 = (x0 + 1) % n, (y0 + 1) % n, (z0 + 1) % n
        g = self.g
        c00 = g[x0, y0, z0] * (1 - fx) + g[x1, y0, z0] * fx
        c10 = g[x0, y1, z0] * (1 - fx) + g[x1, y1, z0] * fx
        c01 = g[x0, y0, z1] * (1 - fx) + g[x1, y0, z1] * fx
        c11 = g[x0, y1, z1] * (1 - fx) + g[x1, y1, z1] * fx
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        return c0 * (1 - fz) + c1 * fz

    def __call__(self, x, y, z, octaves=4, pers=0.5):
        out = 0.0
        amp, tot, f = 1.0, 0.0, 1.0
        for o in range(octaves):
            out = out + amp * self.base(x * f + 13.1 * o, y * f + 7.7 * o, z * f + 3.3 * o)
            tot += amp
            amp *= pers
            f *= 2.0
        return out / tot


NZ = Noise3(SEED)
NZ2 = Noise3(SEED + 1)


def length3(x, y, z):
    return np.sqrt(x * x + y * y + z * z)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def capsule(x, y, z, a, b, r):
    pax, pay, paz = x - a[0], y - a[1], z - a[2]
    bax, bay, baz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    h = np.clip((pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz), 0, 1)
    return length3(pax - bax * h, pay - bay * h, paz - baz * h) - r


def unit(v):
    v = np.asarray(v, np.float64)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------- 场景

ZF, ZB, TT = -13.0, 62.0, 5.0            # 桌子前沿、后沿、桌面厚度
WALLZ = 80.0
LP = np.array([-95.0, 72.0, -34.0])      # 点光源（左上前方）
LCOL = srgb2lin((1.0, 0.90, 0.76)) * 5.2

# 碗
BX, BZ = -8.0, 12.0
RB, TH, FOOT = 15.0, 0.8, 1.2
BYC = FOOT + RB
YRIM = FOOT + 9.5
RM = RB - TH / 2
RIM_R = float(np.sqrt(RM ** 2 - (BYC - YRIM) ** 2))


def sd_bowl(x, y, z):
    dx, dz, dy = x - BX, z - BZ, y - BYC
    r = length3(dx, dy, dz)
    shell = np.abs(r - RM) - TH / 2
    cap = np.maximum(shell, y - YRIM)
    rr = np.sqrt(dx * dx + dz * dz)
    tor = np.sqrt((rr - RIM_R) ** 2 + (y - YRIM) ** 2) - TH * 0.55
    cap = np.minimum(cap, tor)
    foot = np.maximum(np.abs(rr - 5.4) - 0.75, np.abs(y - 1.3) - 1.3)
    return np.minimum(cap, foot)


def rest_in_bowl(r, dirx, dirz, dh):
    n = np.hypot(dirx, dirz)
    dirx, dirz = dirx / n, dirz / n
    dv = np.sqrt((RB - TH - r) ** 2 - dh ** 2)
    return np.array([BX + dirx * dh, BYC - dv, BZ + dirz * dh])


APPLE_A = dict(c=rest_in_bowl(4.7, -0.88, -0.47, 5.8), r=4.7, axis=unit((-0.45, 1, -0.25)))
ORANGE = dict(c=rest_in_bowl(4.3, 0.80, -0.60, 5.8), r=4.3, axis=unit((0.3, 1, -0.4)))
PEAR_C1 = rest_in_bowl(3.8, 0.70, 0.71, 6.5)
PEAR_AX = unit((0.22, 1.0, 0.06))
PEAR = dict(c1=PEAR_C1, r1=3.8, c2=PEAR_C1 + PEAR_AX * 4.6, r2=2.45, axis=PEAR_AX)
def _rest_on(cs, rs, r, guess):
    """解一个位置，使半径 r 的球同时贴着几个已放好的球（最小二乘）。"""
    from scipy.optimize import least_squares
    f = lambda p: [np.linalg.norm(p - c) - (r + rc) for c, rc in zip(cs, rs)]   # noqa: E731
    return least_squares(f, np.asarray(guess, float)).x


APPLE_D = dict(c=_rest_on([APPLE_A["c"], ORANGE["c"], PEAR["c1"]], [4.7, 4.3, 3.8], 4.4, (-8.0, 15.0, 12.5)),
               r=4.4, axis=unit((-0.35, 1, 0.1)))
LEMON = dict(c=np.array([-20.5, 2.75, -3.0]), rad=np.array([4.3, 2.75, 2.75]), ang=np.radians(-28))
JX, JZ, JH = 18.5, 23.0, 25.5
_JPROF = np.array([[0.0, 5.6], [0.6, 6.4], [2.5, 7.9], [6.0, 9.4], [9.5, 9.8], [13.0, 9.3], [16.5, 7.8],
                   [19.5, 5.4], [21.3, 3.9], [22.8, 3.7], [24.3, 4.3], [25.2, 4.7], [25.5, 4.5]])
_JY = np.linspace(-1, JH + 1, 6000)
_JR = np.interp(_JY, _JPROF[:, 0], _JPROF[:, 1])
_JR = ndi.gaussian_filter1d(_JR, 60)


def jar_r(y):
    return np.interp(y, _JY, _JR)


def sd_jar(x, y, z):
    dx, dz = x - JX, z - JZ
    rr = np.sqrt(dx * dx + dz * dz)
    ry = jar_r(y)
    d = (rr - ry) * 0.78
    d = np.maximum(d, -y)
    d = np.maximum(d, y - JH)
    inner = np.maximum(rr - (ry - 0.65), (JH - 6.0) - y)
    d = np.maximum(d, -inner)
    # 双耳（肩部两侧的环）
    for sgn in (-1.0, 1.0):
        cx, cy = JX + sgn * (jar_r(17.6) + 0.9), 17.6
        qx = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - 2.1
        tor = np.sqrt(qx * qx + (z - JZ) ** 2) - 0.62
        d = np.minimum(d, tor)
    return d


def sd_apple(x, y, z, A):
    c, r, ax = A["c"], A["r"], A["axis"]
    px, py, pz = x - c[0], y - c[1], z - c[2]
    h = px * ax[0] + py * ax[1] + pz * ax[2]
    rad = np.sqrt(np.maximum(px * px + py * py + pz * pz - h * h, 0))
    # 苹果：略扁，赤道略鼓
    d = np.sqrt(rad * rad + (h * 1.08) ** 2) - r
    top = c + ax * r * 0.98
    d = smax(d, -(length3(x - top[0], y - top[1], z - top[2]) - r * 0.30), r * 0.28)
    bot = c - ax * r * 1.0
    d = smax(d, -(length3(x - bot[0], y - bot[1], z - bot[2]) - r * 0.18), r * 0.2)
    s0 = c + ax * r * 0.72
    s1 = s0 + ax * r * 0.42 + unit(np.cross(ax, (0, 0, 1))) * r * 0.10
    d = np.minimum(d, capsule(x, y, z, s0, s1, 0.20))
    return d


def sd_orange(x, y, z):
    c, r = ORANGE["c"], ORANGE["r"]
    return length3(x - c[0], y - c[1], z - c[2]) - r


def sd_pear(x, y, z):
    P = PEAR
    d1 = length3(x - P["c1"][0], y - P["c1"][1], z - P["c1"][2]) - P["r1"]
    d2 = length3(x - P["c2"][0], y - P["c2"][1], z - P["c2"][2]) - P["r2"]
    d = smin(d1, d2, 3.2)
    s0 = P["c2"] + P["axis"] * (P["r2"] - 0.3)
    s1 = s0 + unit(P["axis"] + np.array([0.5, 0.1, 0])) * 2.0
    return np.minimum(d, capsule(x, y, z, s0, s1, 0.24))


def sd_lemon(x, y, z):
    L = LEMON
    px, py, pz = x - L["c"][0], y - L["c"][1], z - L["c"][2]
    ca, sa = np.cos(L["ang"]), np.sin(L["ang"])
    lx, lz = ca * px - sa * pz, sa * px + ca * pz
    r = L["rad"]
    k0 = length3(lx / r[0], py / r[1], lz / r[2])
    k1 = length3(lx / r[0] ** 2, py / r[1] ** 2, lz / r[2] ** 2)
    d = k0 * (k0 - 1) / np.maximum(k1, 1e-6)
    for s in (-1, 1):
        d = smin(d, length3(lx - s * (r[0] + 0.1), py, lz) - 0.75, 0.9)
    return d


def make_grapes():
    """一串葡萄搭在碗的右前沿：上端的梗搭在碗沿里，果粒贴着碗的外壁垂下来，上宽下窄。"""
    rng = np.random.default_rng(SEED + 3)
    Cb = np.array([BX, BYC, BZ])
    phi0 = np.arctan2(-0.80, 0.60)                     # 右前方（x 右，z 朝向镜头为负）
    pts, rads = [], []
    for layer, (R0, n_try) in enumerate(((RB + 1.25, 2500), (RB + 3.2, 1500))):
        for _ in range(n_try):
            th = np.radians(rng.uniform(36, 74) if layer == 0 else rng.uniform(52, 76))
            wid = 0.05 + 0.27 * (np.degrees(th) - 36) / 38
            ph = phi0 + rng.uniform(-wid, wid)
            rr = R0 + rng.uniform(-0.25, 0.25)
            p = Cb + rr * np.array([np.sin(th) * np.cos(ph), -np.cos(th), np.sin(th) * np.sin(ph)])
            r = rng.uniform(1.10, 1.30)
            if p[1] < r:
                continue
            if all(np.linalg.norm(p - q) > (r + rq) * 0.96 for q, rq in zip(pts, rads)):
                pts.append(p)
                rads.append(r)
    for p in ([10.2, 1.22, -8.2], [7.9, 1.25, -10.4], [12.4, 1.2, -5.9]):
        pts.append(np.array(p))
        rads.append(1.22)
    return np.array(pts), np.array(rads), None


GR_P, GR_R, GR_AXIS = make_grapes()
GR_STEM = [np.array([-0.6, 12.5, 2.4]), np.array([0.8, 12.9, 1.0]), np.array([2.0, 12.3, -0.2])]


def sd_grapes(x, y, z):
    d = np.full(x.shape, 1e9, np.float32)
    for p, r in zip(GR_P, GR_R):
        qx, qy, qz = x - p[0], y - p[1], z - p[2]
        k0 = length3(qx / r, qy / (1.13 * r), qz / r)
        k1 = length3(qx / r ** 2, qy / (1.13 * r) ** 2, qz / r ** 2)
        d = np.minimum(d, k0 * (k0 - 1) / np.maximum(k1, 1e-6))
    for a, b in zip(GR_STEM[:-1], GR_STEM[1:]):
        d = np.minimum(d, capsule(x, y, z, a, b, 0.22))
    return d


OBJS = [
    dict(id=1, fn=sd_bowl, bound=(np.array([BX, 8.0, BZ]), 17.0)),
    dict(id=2, fn=lambda x, y, z: sd_apple(x, y, z, APPLE_A), bound=(APPLE_A["c"], APPLE_A["r"] + 2.5)),
    dict(id=3, fn=sd_orange, bound=(ORANGE["c"], ORANGE["r"] + 0.5)),
    dict(id=4, fn=sd_pear, bound=((PEAR["c1"] + PEAR["c2"]) / 2, 8.5)),
    dict(id=5, fn=lambda x, y, z: sd_apple(x, y, z, APPLE_D), bound=(APPLE_D["c"], APPLE_D["r"] + 2.5)),
    dict(id=6, fn=sd_grapes, bound=(np.array([4.0, 6.0, -2.5]), 16.0)),
    dict(id=7, fn=sd_jar, bound=(np.array([JX, JH / 2, JZ]), 16.5)),
    dict(id=8, fn=sd_lemon, bound=(LEMON["c"], 5.6)),
]
FN = {o["id"]: o["fn"] for o in OBJS}


def sd_table(x, y, z):
    qx = np.abs(x) - 400.0
    qy = np.abs(y + TT / 2) - TT / 2
    qz = np.abs(z - (ZF + ZB) / 2) - (ZB - ZF) / 2
    out = length3(np.maximum(qx, 0), np.maximum(qy, 0), np.maximum(qz, 0))
    return out + np.minimum(np.maximum(np.maximum(qx, qy), qz), 0)


def scene(x, y, z, env=True):
    if env:
        d = sd_table(x, y, z)
        oid = np.full(x.shape, 9, np.int16)
        dw = WALLZ - z
        m = dw < d
        d = np.where(m, dw, d)
        oid[m] = 10
        dfl = y + 70.0
        m = dfl < d
        d = np.where(m, dfl, d)
        oid[m] = 11
    else:
        d = np.full(x.shape, 1e9, np.float32)
        oid = np.full(x.shape, -1, np.int16)
    for o in OBJS:
        c, R = o["bound"]
        db = length3(x - c[0], y - c[1], z - c[2]) - R
        idx = np.nonzero(db < d)[0]
        if idx.size:
            do = o["fn"](x[idx], y[idx], z[idx])
            b = do < d[idx]
            j = idx[b]
            d[j] = do[b]
            oid[j] = o["id"]
    return d, oid


# ---------------------------------------------------------------- 渲染


def camera(w, h):
    C = np.array([-1.5, 30.0, -80.0])
    T = np.array([-1.0, 9.0, 12.0])
    fwd = unit(T - C)
    right = unit(np.cross((0, 1, 0), fwd))
    up = np.cross(fwd, right)
    vf = np.radians(26.0)
    sy = np.tan(vf / 2)
    sx = sy * w / h
    j, i = np.meshgrid((np.arange(w) + 0.5) / w * 2 - 1, (np.arange(h) + 0.5) / h * 2 - 1)
    d = fwd[None, None, :] + right[None, None, :] * (j * sx)[..., None] - up[None, None, :] * (i * sy)[..., None]
    d = d / np.linalg.norm(d, axis=-1, keepdims=True)
    d = d.reshape(-1, 3).astype(np.float32)
    return C.astype(np.float32), d


def march(C, D, steps=220, tmax=600.0):
    N = D.shape[0]
    t = np.zeros(N, np.float32)
    oid = np.full(N, 10, np.int16)
    act = np.arange(N)
    for _ in range(steps):
        if act.size == 0:
            break
        ta = t[act]
        px, py, pz = C[0] + D[act, 0] * ta, C[1] + D[act, 1] * ta, C[2] + D[act, 2] * ta
        d, oi = scene(px, py, pz)
        hit = d < 0.0025 + 0.00004 * ta
        oid[act[hit]] = oi[hit]
        t[act] = ta + d * 0.9
        keep = (~hit) & (t[act] < tmax)
        act = act[keep]
    return t, oid


def normals(px, py, pz, oid):
    N = px.shape[0]
    n = np.zeros((N, 3), np.float32)
    e = 0.004
    K = [(1, -1, -1), (-1, -1, 1), (-1, 1, -1), (1, 1, 1)]
    for i, fn in FN.items():
        idx = np.nonzero(oid == i)[0]
        if idx.size == 0:
            continue
        x, y, z = px[idx], py[idx], pz[idx]
        acc = np.zeros((idx.size, 3), np.float32)
        ei = 0.025 if i == 7 else e
        for k in K:
            v = fn(x + k[0] * ei, y + k[1] * ei, z + k[2] * ei)
            acc += np.array(k, np.float32)[None, :] * v[:, None]
        n[idx] = acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-9)
    idx = np.nonzero(oid == 9)[0]
    if idx.size:
        x, y, z = px[idx], py[idx], pz[idx]
        acc = np.zeros((idx.size, 3), np.float32)
        for k in K:
            v = sd_table(x + k[0] * 0.01, y + k[1] * 0.01, z + k[2] * 0.01)
            acc += np.array(k, np.float32)[None, :] * v[:, None]
        n[idx] = acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-9)
    n[oid == 10] = (0, 0, -1)
    n[oid == 11] = (0, 1, 0)
    return n


def soft_shadow(px, py, pz, n, k=5.0, steps=90):
    lx, ly, lz = LP[0] - px, LP[1] - py, LP[2] - pz
    dist = length3(lx, ly, lz)
    lx, ly, lz = lx / dist, ly / dist, lz / dist
    ox, oy, oz = px + n[:, 0] * 0.07, py + n[:, 1] * 0.07, pz + n[:, 2] * 0.07
    N = px.shape[0]
    res = np.ones(N, np.float32)
    t = np.full(N, 0.15, np.float32)
    act = np.arange(N)
    for _ in range(steps):
        if act.size == 0:
            break
        ta = t[act]
        d, _ = scene(ox[act] + lx[act] * ta, oy[act] + ly[act] * ta, oz[act] + lz[act] * ta, env=False)
        # 桌子也会挡光（桌面以下的点）
        dt = sd_table(ox[act] + lx[act] * ta, oy[act] + ly[act] * ta, oz[act] + lz[act] * ta)
        d = np.minimum(d, dt)
        res[act] = np.minimum(res[act], k * d / ta)
        t[act] = ta + np.clip(d, 0.03, 3.0)
        keep = (res[act] > 0.001) & (t[act] < dist[act] - 1)
        act = act[keep]
    return np.clip(res, 0, 1), np.stack([lx, ly, lz], 1), dist


def ambient_occ(px, py, pz, n):
    occ = np.zeros(px.shape[0], np.float32)
    w = 1.0
    for i in range(1, 6):
        hh = 0.45 * i
        d, _ = scene(px + n[:, 0] * hh, py + n[:, 1] * hh, pz + n[:, 2] * hh)
        occ += (hh - d) * w
        w *= 0.62
    return np.clip(1 - 0.55 * occ, 0, 1)


# ---------------------------------------------------------------- 材质


def local_axis_coords(px, py, pz, c, ax):
    """相对物体中心、以 ax 为竖轴的坐标：高度 h、方位角 az、离轴距离 rad。"""
    x, y, z = px - c[0], py - c[1], pz - c[2]
    h = x * ax[0] + y * ax[1] + z * ax[2]
    ref = unit(np.cross(ax, (0, 0, 1)))
    ref2 = np.cross(ax, ref)
    a = x * ref[0] + y * ref[1] + z * ref[2]
    b = x * ref2[0] + y * ref2[1] + z * ref2[2]
    return h, np.arctan2(b, a), np.sqrt(a * a + b * b)


def bump(n, px, py, pz, scale, amp, noise=NZ2):
    e = 0.02
    f0 = noise(px * scale, py * scale, pz * scale, octaves=2)
    gx = (noise((px + e) * scale, py * scale, pz * scale, octaves=2) - f0) / e
    gy = (noise(px * scale, (py + e) * scale, pz * scale, octaves=2) - f0) / e
    gz = (noise(px * scale, py * scale, (pz + e) * scale, octaves=2) - f0) / e
    g = np.stack([gx, gy, gz], 1)
    g = g - (g * n).sum(1, keepdims=True) * n
    m = n - amp * g
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def material(oid, px, py, pz, n, V):
    """返回 albedo(线性)、高光强度、高光指数、以及可能被凹凸扰动后的法线。"""
    N = px.shape[0]
    alb = np.zeros((N, 3), np.float32)
    ks = np.zeros(N, np.float32)
    kp = np.full(N, 20.0, np.float32)
    nn = n.copy()

    def sel(i):
        return np.nonzero(oid == i)[0]

    # 桌面：沿 x 方向的木板，木纹
    i = sel(9)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        top = n[i, 1] > 0.5
        pw = 11.5
        u = (z - ZF) / pw
        plank = np.floor(u)
        fu = u - plank
        rnd = np.sin(plank * 12.9898) * 43758.5453
        rnd = rnd - np.floor(rnd)
        g1 = NZ(x * 0.012 + plank * 7.3, z * 0.55, plank * 3.1, octaves=4)
        lines = 0.5 + 0.5 * np.sin(g1 * 38 + z * 1.3)
        g2 = NZ2(x * 0.04, z * 1.6, plank, octaves=3)
        light = srgb2lin((0.47, 0.33, 0.20))
        dark = srgb2lin((0.22, 0.14, 0.08))
        t = np.clip(0.42 + 0.40 * (g1 - 0.5) * 2 + 0.14 * lines ** 4 + 0.40 * (rnd - 0.5) + 0.2 * (g2 - 0.5), 0, 1)
        col = mixc(dark, light, t)
        gap = np.maximum(smoothstep(0.018, 0.0, fu), smoothstep(0.982, 1.0, fu))
        col = mixc(col, srgb2lin((0.06, 0.035, 0.02)), gap * top)
        # 桌面前沿侧面：更暗的端面木纹
        side = ~top
        col[side] = col[side] * 0.55
        wear = NZ(x * 0.08, z * 0.08, 1.0, octaves=3)
        col = col * (0.85 + 0.3 * wear)[:, None]
        alb[i] = col
        ks[i] = 0.10 * (1 - gap)
        kp[i] = 28.0
    # 墙
    i = sel(10)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        m = NZ(x * 0.025, y * 0.025, 5.0, octaves=6)
        halo = np.exp(-((x - 8.0) / 55.0) ** 2 - ((y - 14.0) / 30.0) ** 2)
        alb[i] = mixc(srgb2lin((0.10, 0.09, 0.07)), srgb2lin((0.22, 0.19, 0.14)), m) * (1 + 1.6 * halo)[:, None]
    i = sel(11)
    if i.size:
        alb[i] = srgb2lin((0.03, 0.025, 0.02))
    # 碗：乳白釉，外壁口沿下一道钴蓝宽带和细线
    i = sel(1)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        rr = length3(x - BX, y - BYC, z - BZ)
        outer = rr > RM
        col = np.broadcast_to(srgb2lin((0.90, 0.86, 0.77)), (i.size, 3)).copy()
        yb = YRIM - y
        band = (smoothstep(1.5, 1.7, yb) - smoothstep(3.0, 3.2, yb)) + (smoothstep(0.55, 0.65, yb) - smoothstep(0.85, 0.95, yb))
        band = band * outer * (0.8 + 0.2 * NZ(x * 2, y * 2, z * 2, octaves=2))
        col = mixc(col, srgb2lin((0.10, 0.17, 0.42)), np.clip(band, 0, 1))
        foot = y < 2.6
        col[foot] = col[foot] * np.array([0.93, 0.88, 0.80], np.float32)
        col = col * (0.95 + 0.1 * NZ(x * 0.5, y * 0.5, z * 0.5, octaves=3))[:, None]
        alb[i] = col
        ks[i] = 0.55
        kp[i] = 90.0
    # 红苹果、青苹果
    for oi, A, red, yel in ((2, APPLE_A, (0.58, 0.06, 0.05), (0.85, 0.55, 0.16)),
                            (5, APPLE_D, (0.60, 0.70, 0.22), (0.80, 0.80, 0.36))):
        i = sel(oi)
        if i.size == 0:
            continue
        x, y, z = px[i], py[i], pz[i]
        h, az, rad = local_axis_coords(x, y, z, A["c"], A["axis"])
        streak = NZ(np.cos(az) * 3 + 10, np.sin(az) * 3, h * 0.45, octaves=4)
        streak2 = NZ2(az * 6.0, h * 0.3, 2.0, octaves=3)
        t = np.clip((streak - 0.35) * 1.6 + 0.35 * streak2, 0, 1)
        col = mixc(srgb2lin(red), srgb2lin(yel), t * 0.55)
        topc = smoothstep(0.55, 0.95, h / A["r"])
        col = mixc(col, srgb2lin(yel), topc * 0.45)
        if oi == 5:        # 青苹果一侧有淡淡的红晕
            blush = smoothstep(0.2, 0.9, -(x - A["c"][0]) / A["r"]) * NZ(x, y, z, octaves=2)
            col = mixc(col, srgb2lin((0.78, 0.35, 0.12)), blush * 0.55)
        spk = smoothstep(0.80, 0.83, NZ2(x * 11, y * 11, z * 11, octaves=1))
        col = mixc(col, srgb2lin((0.92, 0.82, 0.5)), spk * 0.22)
        stem = h > A["r"] * 0.8
        stem &= rad < 0.5
        col[stem] = srgb2lin((0.28, 0.18, 0.08))
        cav = smoothstep(0.75, 0.95, h / A["r"]) * smoothstep(1.6, 0.4, rad)
        col = mixc(col, srgb2lin((0.55, 0.50, 0.20)), cav * 0.6 * (~stem))
        alb[i] = col
        ks[i] = np.where(stem, 0.02, 0.32)
        kp[i] = 45.0
    # 橙子：橙皮凹点
    i = sel(3)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        nn[i] = bump(n[i], x, y, z, 3.2, 0.020)
        col = np.broadcast_to(srgb2lin((0.95, 0.47, 0.06)), (i.size, 3)).copy()
        col = col * (0.9 + 0.2 * NZ(x * 0.8, y * 0.8, z * 0.8, octaves=3))[:, None]
        h, az, rad = local_axis_coords(x, y, z, ORANGE["c"], ORANGE["axis"])
        spot = smoothstep(0.7, 0.2, rad) * (h > 0)
        col = mixc(col, srgb2lin((0.45, 0.35, 0.10)), spot * 0.8)
        alb[i] = col
        ks[i] = 0.22
        kp[i] = 22.0
    # 梨：黄绿底、锈斑、受光面红晕
    i = sel(4)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        col = np.broadcast_to(srgb2lin((0.76, 0.70, 0.26)), (i.size, 3)).copy()
        rus = smoothstep(0.62, 0.72, NZ2(x * 3.5, y * 3.5, z * 3.5, octaves=2))
        col = mixc(col, srgb2lin((0.52, 0.38, 0.17)), rus * 0.7)
        blush = smoothstep(0.0, 1.0, -(x - PEAR["c1"][0]) / 4.0) * (0.6 + 0.4 * NZ(x * 0.7, y * 0.7, z * 0.7))
        col = mixc(col, srgb2lin((0.78, 0.36, 0.13)), blush * 0.5)
        s0 = PEAR["c2"] + PEAR["axis"] * (PEAR["r2"] - 0.5)
        stem = length3(x - s0[0], y - s0[1], z - s0[2]) > 0.2
        stem &= ((x - s0[0]) * PEAR["axis"][0] + (y - s0[1]) * PEAR["axis"][1] + (z - s0[2]) * PEAR["axis"][2]) > 0.15
        col[stem] = srgb2lin((0.30, 0.20, 0.09))
        alb[i] = col
        ks[i] = np.where(stem, 0.02, 0.18)
        kp[i] = 30.0
    # 葡萄：深紫，果粉，每颗色相略不同
    i = sel(6)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        dmin = np.full(i.size, 1e9, np.float32)
        gid = np.zeros(i.size, np.int64)
        for k, (p, r) in enumerate(zip(GR_P, GR_R)):
            dd = length3(x - p[0], y - p[1], z - p[2]) - r
            b = dd < dmin
            dmin[b] = dd[b]
            gid[b] = k
        hue = np.sin(gid * 91.7) * 0.5 + 0.5
        col = mixc(srgb2lin((0.20, 0.06, 0.18)), srgb2lin((0.30, 0.08, 0.22)), hue)
        bloom = NZ(x * 2.5, y * 2.5, z * 2.5, octaves=2)
        graze = 1 - np.abs((nn[i] * V[i]).sum(1))
        col = mixc(col, srgb2lin((0.46, 0.43, 0.56)), np.clip(0.45 * bloom + 0.6 * graze ** 2, 0, 0.8))
        stem = dmin > 0.2
        col[stem] = srgb2lin((0.30, 0.24, 0.12))
        alb[i] = col
        ks[i] = np.where(stem, 0.02, 0.18 * (0.5 + bloom))
        kp[i] = 32.0
    # 陶罐：素烧红陶 + 上半截深色釉（流淌的釉边）
    i = sel(7)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        az = np.arctan2(z - JZ, x - JX)
        mott = NZ(x * 0.6, y * 0.6, z * 0.6, octaves=4)
        col = mixc(srgb2lin((0.52, 0.26, 0.15)), srgb2lin((0.72, 0.42, 0.26)), mott)
        drip = np.zeros(i.size, np.float32)
        rngd = np.random.default_rng(SEED + 9)
        for _ in range(16):
            a0 = rngd.uniform(-np.pi, np.pi)
            L = rngd.uniform(0.6, 3.2)
            wd = rngd.uniform(0.04, 0.10)
            dd = np.angle(np.exp(1j * (az - a0)))
            drip = np.maximum(drip, L * np.exp(-(dd / wd) ** 2))
        yg = 11.0 - drip + 0.6 * (NZ2(az * 3, 1.0, 2.0, octaves=2) - 0.5)
        glaze = smoothstep(yg - 0.15, yg + 0.15, y)
        inside = length3(x - JX, 0, z - JZ) < jar_r(y) - 0.3
        gv = NZ(x * 0.8, y * 0.35, z * 0.8, octaves=3)
        gcol = mixc(srgb2lin((0.11, 0.11, 0.05)), srgb2lin((0.19, 0.18, 0.08)), gv)
        gcol = mixc(gcol, srgb2lin((0.30, 0.22, 0.10)), smoothstep(yg + 1.6, yg + 0.1, y) * 0.6)   # 釉边薄处透出红陶
        col = mixc(col, gcol, glaze)
        col[inside] = srgb2lin((0.05, 0.035, 0.025))
        alb[i] = col
        ks[i] = 0.04 + 0.30 * glaze
        kp[i] = 8.0 + 160.0 * glaze
    # 柠檬
    i = sel(8)
    if i.size:
        x, y, z = px[i], py[i], pz[i]
        nn[i] = bump(n[i], x, y, z, 3.6, 0.015)
        col = np.broadcast_to(srgb2lin((0.95, 0.80, 0.16)), (i.size, 3)).copy()
        col = col * (0.92 + 0.16 * NZ(x * 0.9, y * 0.9, z * 0.9, octaves=3))[:, None]
        alb[i] = col
        ks[i] = 0.2
        kp[i] = 26.0
    return alb, ks, kp, nn


def render(w, h, log=print):
    t0 = time.time()
    C, D = camera(w, h)
    t, oid = march(C, D)
    log(f"  march {time.time() - t0:.1f}s")
    px, py, pz = C[0] + D[:, 0] * t, C[1] + D[:, 1] * t, C[2] + D[:, 2] * t
    n = normals(px, py, pz, oid)
    V = -D
    sh, Ld, dist = soft_shadow(px, py, pz, n)
    log(f"  shadow {time.time() - t0:.1f}s")
    ao = ambient_occ(px, py, pz, n)
    log(f"  ao {time.time() - t0:.1f}s")
    alb, ks, kp, nn = material(oid, px, py, pz, n, V)
    att = 1.0 / (1.0 + (dist / 120.0) ** 2)
    sp_ax = unit(np.array([-2.0, 7.0, 14.0]) - LP)
    cosang = -(Ld @ sp_ax)
    att = att * (0.30 + 0.70 * smoothstep(np.cos(np.radians(40)), np.cos(np.radians(16)), cosang))
    ndl = np.clip((nn * Ld).sum(1), 0, 1)
    Hh = Ld + V
    Hh /= np.linalg.norm(Hh, axis=1, keepdims=True)
    ndh = np.clip((nn * Hh).sum(1), 0, 1)
    fres = 0.04 + 0.96 * (1 - np.clip((nn * V).sum(1), 0, 1)) ** 5
    direct = (ndl * sh * att)[:, None] * LCOL[None, :]
    amb = srgb2lin((0.30, 0.27, 0.24)) * 0.31 * (0.6 + 0.4 * np.clip(nn[:, 1], 0, 1))[:, None] * ao[:, None]
    fill_dir = unit((1.0, 0.35, -0.7))
    fill = srgb2lin((0.62, 0.60, 0.58)) * 0.10 * np.clip(nn @ fill_dir, 0, 1)[:, None] * ao[:, None]
    bounce = srgb2lin((0.55, 0.38, 0.22)) * 0.30 * np.clip(-nn[:, 1], 0, 1)[:, None] * ao[:, None]
    col = alb * (direct + amb + fill + bounce)
    spec = (ks * (ndh ** kp) * (kp + 8) / 40.0 * sh * att)[:, None] * LCOL[None, :]
    spec = spec + (ks * fres * 0.25)[:, None] * amb * 4
    col = col + spec
    return col.reshape(h, w, 3), oid.reshape(h, w), t.reshape(h, w)


def tonemap(x):
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=0)
    ap.add_argument("--ss", type=float, default=2.0)
    ap.add_argument("--oil", action="store_true", help="第 4 轮试过的油画笔触版本（效果更差，默认不用）")
    a = ap.parse_args()
    w, h = int(W * a.ss), int(H * a.ss)
    img, oid, depth = render(w, h)
    im = Image.fromarray((lin2srgb(tonemap(img * 1.0)) * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    if a.oil:
        im = stylize.oil(im, strength=1.0, seed=SEED, size=W,
                         params=dict(radii=(24, 12, 6, 3), T=(0.0, 0.07, 0.09, 0.11), max_len=14, min_len=2,
                                     bristle=0.4, impasto=0.45, canvas=0.05, warm=0.30, sat=1.04, contrast=1.02,
                                     tempo=0.25, abstract=0.02, light=(-0.7, -0.7)))
    out = np.asarray(im, np.float32) / 255
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx - W * 0.45) / (W * 0.62), (yy - H * 0.52) / (H * 0.62))
    out = out * (1 - 0.35 * smoothstep(0.6, 1.3, r))[..., None]
    if not a.oil:
        # 很淡的亚麻画布纹理 + 颗粒，只给一点“画”的质感，不动形体
        cvt = stylize.canvas_texture(H, W, 1.0, SEED)
        out = out * (1 + 0.025 * cvt)[..., None]
        grain = np.random.default_rng(SEED).normal(0, 0.007, (H, W, 1)).astype(np.float32)
        out = np.clip(out + grain, 0, 1)
    fin = Image.fromarray((out * 255).astype(np.uint8))
    fin.save(os.path.join(HERE, "final.png"))
    if a.round:
        os.makedirs(os.path.join(HERE, "rounds"), exist_ok=True)
        fin.save(os.path.join(HERE, "rounds", f"r{a.round}.png"))


if __name__ == "__main__":
    main()
