#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A05 窗台上晒太阳的橘猫（纯代码，不用任何模型、不读任何图片）。

画法：numpy 光线追踪。
- 猫：几十个椭球/胶囊用平滑并（smooth-min）拼成的有向距离场（SDF），球面追踪求交；
  虎斑条纹、白下巴、闭着的眼睛、粉鼻子都是按猫身/猫头局部坐标算出来的程序化花纹。
- 窗台、窗框、墙、窗洞侧壁是解析几何（盒子+平面），窗外是程序化生成、再大幅虚化的花园（带光斑）。
- 光：太阳从窗外左上方照进来，窗框遮挡算出光斑形状，猫对自己和窗台投软阴影（SDF 软阴影），
  另有窗口天光、室内暖色环境光、窗台反光、AO、毛发边缘的逆光。
- 毛：用 stylize.py 的 LIC（线积分卷积）沿投影到屏幕的毛流方向抹出毛丝纹理，
  轮廓处再用 2D 画上一根根短毛、胡须和阳光里的浮尘。2 倍超采样。
运行：python3 draw.py [另存路径...]   → final.png
"""
import math
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', 'stylize'))
import stylize  # noqa: E402  (只用它的 LIC 线积分卷积)

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


# ---------------------------------------------------------------- camera / light
CAMP = np.array([-0.60, 0.43, -1.13])
TGT = np.array([0.04, 0.115, -0.03])
HFOV = math.radians(44.0)
FW = unit(TGT - CAMP)
RT = unit(np.cross([0, 1.0, 0], FW))
UPC = np.cross(FW, RT)
FOC = (RW / 2) / math.tan(HFOV / 2)
SUN = unit((-0.47, 0.625, 0.625)).astype(np.float32)
SUN_COL = (lin(1.0, 0.86, 0.66) * 3.3).astype(np.float32)
SKY_FILL = (lin(0.70, 0.76, 0.84) * 0.80).astype(np.float32)
ROOM_FILL = (lin(0.66, 0.60, 0.54) * 0.24).astype(np.float32)
BOUNCE = (lin(1.0, 0.86, 0.68) * 0.55).astype(np.float32)
WDIR = unit((0.0, 0.35, 0.94)).astype(np.float32)


def project(P):
    v = np.asarray(P, np.float64) - CAMP
    xc, yc, zc = v @ RT, v @ UPC, v @ FW
    return RW / 2 + FOC * xc / zc - 0.5, RH / 2 - FOC * yc / zc - 0.5, zc


# ---------------------------------------------------------------- cat SDF
CAT_O = np.array([0.02, 0.0, -0.03])
CAT_H = unit((-1.0, 0.0, -0.28))                 # 猫身朝向（朝头）
CAT_S = np.array([CAT_H[2], 0.0, -CAT_H[0]])     # 横向，指向窗外一侧
HC = np.array([0.222, 0.185, 0.0])               # 头中心（猫身局部坐标 a, y, b）
HSC = 1.13                                       # 头整体放大一点，比例更可爱


def _head_frame():
    yaw, pitch, roll = math.radians(36), math.radians(9), math.radians(9)
    f = np.array([math.cos(yaw) * math.cos(pitch), math.sin(pitch), -math.sin(yaw) * math.cos(pitch)])
    s = unit(np.cross([0, 1.0, 0], f))
    u = np.cross(f, s)
    cr, sr = math.cos(roll), math.sin(roll)
    s, u = cr * s + sr * u, -sr * s + cr * u
    return f, s, u


HF, HS, HU = _head_frame()

TAIL = np.array([(-0.24, 0.07, 0.02), (-0.29, 0.045, -0.06), (-0.265, 0.025, -0.15), (-0.205, 0.02, -0.215),
                 (-0.17, -0.005, -0.262), (-0.16, -0.10, -0.272), (-0.152, -0.19, -0.266), (-0.132, -0.245, -0.25)])
TAIL_R = np.linspace(0.023, 0.016, len(TAIL))


def to_local(px, py, pz):
    dx, dy, dz = px - CAT_O[0], py - CAT_O[1], pz - CAT_O[2]
    a = dx * CAT_H[0] + dz * CAT_H[2]
    b = dx * CAT_S[0] + dz * CAT_S[2]
    return a.astype(np.float32), dy.astype(np.float32), b.astype(np.float32)


def local_dir_to_world(da, dy, db):
    return (da * CAT_H[0] + db * CAT_S[0], dy, da * CAT_H[2] + db * CAT_S[2])


def to_head(a, y, b):
    x, yy, z = a - HC[0], y - HC[1], b - HC[2]
    return (x * HF[0] + yy * HF[1] + z * HF[2], x * HS[0] + yy * HS[1] + z * HS[2], x * HU[0] + yy * HU[1] + z * HU[2])


def sd_ell(x, y, z, rx, ry, rz):
    x0, y0, z0 = x / rx, y / ry, z / rz
    k0 = np.sqrt(x0 * x0 + y0 * y0 + z0 * z0)
    k1 = np.sqrt((x0 / rx) ** 2 + (y0 / ry) ** 2 + (z0 / rz) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def sd_cap(x, y, z, A, B, ra, rb):
    bax, bay, baz = B[0] - A[0], B[1] - A[1], B[2] - A[2]
    pax, pay, paz = x - A[0], y - A[1], z - A[2]
    h = np.clip((pax * bax + pay * bay + paz * baz) / (bax * bax + bay * bay + baz * baz), 0, 1)
    dx, dy, dz = pax - bax * h, pay - bay * h, paz - baz * h
    return np.sqrt(dx * dx + dy * dy + dz * dz) - (ra + (rb - ra) * h), h


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


EAR = [((-0.004, s * 0.033, 0.036), (-0.013, s * 0.052, 0.094)) for s in (-1, 1)]


def head_sdf(qf, qs, qu, parts=False):
    skull = sd_ell(qf, qs, qu, 0.056, 0.063, 0.054)
    cheek = np.minimum(sd_ell(qf - 0.018, qs - 0.034, qu + 0.017, 0.036, 0.031, 0.03),
                       sd_ell(qf - 0.018, qs + 0.034, qu + 0.017, 0.036, 0.031, 0.03))
    muzzle = sd_ell(qf - 0.047, qs, qu + 0.02, 0.026, 0.031, 0.021)
    nose = sd_ell(qf - 0.041, qs, qu - 0.004, 0.028, 0.017, 0.02)
    chin = sd_ell(qf - 0.036, qs, qu + 0.037, 0.02, 0.017, 0.012)
    pads = np.minimum(sd_ell(qf - 0.058, qs - 0.0125, qu + 0.0215, 0.016, 0.0155, 0.0135),
                      sd_ell(qf - 0.058, qs + 0.0125, qu + 0.0215, 0.016, 0.0155, 0.0135))
    d = smin(skull, cheek, 0.016)
    d = smin(d, muzzle, 0.012)
    d = smin(d, pads, 0.006)
    d = smin(d, nose, 0.014)
    d = smin(d, chin, 0.01)
    ears = np.full(qf.shape, 9.0, np.float32)
    inner = np.full(qf.shape, 9.0, np.float32)
    K = 1.9
    for A, B in EAR:
        e, _ = sd_cap(qf * K, qs, qu, (A[0] * K, A[1], A[2]), (B[0] * K, B[1], B[2]), 0.024, 0.0035)
        e = e / K
        i, _ = sd_cap((qf - 0.0085) * K, qs, qu, (A[0] * K, A[1] * 0.97, A[2] + 0.006), (B[0] * K, B[1] * 0.97, B[2] - 0.006),
                      0.016, 0.0015)
        i = i / K
        e = np.maximum(e, -i)
        ears = np.minimum(ears, e)
        inner = np.minimum(inner, i)
    d = smin(d, ears, 0.012)
    if parts:
        return d, dict(skull=skull, cheek=cheek, muzzle=muzzle, nose=nose, chin=chin, ears=ears, inner=inner)
    return d


def cat_sdf(a, y, b, parts=False, exact=False):
    torso = sd_ell(a + 0.005, y - 0.083, b, 0.185, 0.083, 0.100)
    chest = sd_ell(a - 0.125, y - 0.097, b, 0.088, 0.088, 0.088)
    hips = sd_ell(a + 0.12, y - 0.086, b, 0.098, 0.086, 0.102)
    th = np.minimum(sd_ell(a + 0.10, y - 0.07, b + 0.066, 0.092, 0.066, 0.062),
                    sd_ell(a + 0.10, y - 0.07, b - 0.066, 0.092, 0.066, 0.062))
    sh = np.minimum(sd_ell(a - 0.10, y - 0.125, b + 0.045, 0.06, 0.05, 0.04),
                    sd_ell(a - 0.10, y - 0.125, b - 0.045, 0.06, 0.05, 0.04))
    neck = sd_ell(a - 0.172, y - 0.137, b, 0.052, 0.066, 0.06)
    body = smin(smin(torso, chest, 0.04), hips, 0.04)
    body = smin(body, th, 0.025)
    body = smin(body, sh, 0.03)
    body = smin(body, neck, 0.04)
    body = np.maximum(body, 0.0015 - y)
    # 前腿和爪子
    legs = np.full(a.shape, 9.0, np.float32)
    near_leg = (a > 0.05) & (y < 0.1)
    if exact:
        near_leg = np.ones(a.shape, bool)
    if near_leg.any():
        aa, yy, bb = a[near_leg], y[near_leg], b[near_leg]
        lg = np.full(aa.shape, 9.0, np.float32)
        for sb in (-1, 1):
            c, _ = sd_cap(aa, yy, bb, (0.12, 0.036, sb * 0.046), (0.262, 0.024, sb * 0.044), 0.023, 0.021)
            p = sd_ell(aa - 0.276, yy - 0.019, bb - sb * 0.044, 0.032, 0.019, 0.027)
            lg = np.minimum(lg, smin(c, p, 0.012))
        legs[near_leg] = lg
    legs = np.where(near_leg, legs, np.maximum(0.05 - a, y - 0.1) + 0.02)
    hind = sd_ell(a - 0.01, y - 0.016, b + 0.092, 0.044, 0.016, 0.026)
    # 头（包围球外只用球距离）
    qf, qs, qu = to_head(a, y, b)
    qf, qs, qu = qf / HSC, qs / HSC, qu / HSC
    rr = np.sqrt(qf * qf + qs * qs + qu * qu)
    head = (rr - 0.125) * HSC
    near_h = rr < 0.155
    if exact:
        near_h = np.ones(a.shape, bool)
    if near_h.any():
        head = head.copy()
        head[near_h] = head_sdf(qf[near_h], qs[near_h], qu[near_h]) * HSC
    # 尾巴（包围盒外用盒距离）
    lo, hi = TAIL.min(0) - 0.03, TAIL.max(0) + 0.03
    qx = np.maximum(np.maximum(lo[0] - a, a - hi[0]), 0)
    qy = np.maximum(np.maximum(lo[1] - y, y - hi[1]), 0)
    qz = np.maximum(np.maximum(lo[2] - b, b - hi[2]), 0)
    tail = np.sqrt(qx * qx + qy * qy + qz * qz) + 0.005
    near_t = (qx + qy + qz) < 0.01
    if exact:
        near_t = np.ones(a.shape, bool)
    tpar = np.zeros(a.shape, np.float32)
    if near_t.any():
        aa, yy, bb = a[near_t], y[near_t], b[near_t]
        tt = np.full(aa.shape, 9.0, np.float32)
        tp = np.zeros(aa.shape, np.float32)
        for i in range(len(TAIL) - 1):
            c, hh = sd_cap(aa, yy, bb, TAIL[i], TAIL[i + 1], TAIL_R[i], TAIL_R[i + 1])
            better = c < tt
            tp = np.where(better, i + hh, tp)
            tt = smin(tt, c, 0.006)
        tail = tail.copy()
        tail[near_t] = tt
        tpar[near_t] = tp
    d = smin(body, legs, 0.018)
    d = smin(d, head, 0.03)
    d = smin(d, tail, 0.012)
    if parts:
        return d, dict(body=body, legs=legs, hind=hind, head=head, tail=tail, tpar=tpar, qf=qf, qs=qs, qu=qu)
    return d


def cat_sdf_world(px, py, pz, exact=False):
    a, y, b = to_local(px, py, pz)
    return cat_sdf(a, y, b, exact=exact)


# 猫的世界坐标包围盒
_corn = []
for a_ in (-0.34, 0.40):
    for y_ in (-0.28, 0.35):
        for b_ in (-0.31, 0.14):
            _corn.append(CAT_O + a_ * CAT_H + b_ * CAT_S + np.array([0, y_, 0]))
_corn = np.array(_corn)
CAT_BOX = (_corn.min(0), _corn.max(0))


def ray_aabb(ox, oy, oz, dx, dy, dz, lo, hi):
    with np.errstate(divide='ignore', invalid='ignore'):
        t1x, t2x = (lo[0] - ox) / dx, (hi[0] - ox) / dx
        t1y, t2y = (lo[1] - oy) / dy, (hi[1] - oy) / dy
        t1z, t2z = (lo[2] - oz) / dz, (hi[2] - oz) / dz
    tn = np.maximum(np.maximum(np.minimum(t1x, t2x), np.minimum(t1y, t2y)), np.minimum(t1z, t2z))
    tf = np.minimum(np.minimum(np.maximum(t1x, t2x), np.maximum(t1y, t2y)), np.maximum(t1z, t2z))
    return tn, tf


def march(ox, oy, oz, dx, dy, dz, t0, t1, maxit=140):
    n = len(ox)
    t = t0.astype(np.float32).copy()
    hit = np.zeros(n, bool)
    act = np.arange(n)
    for it in range(maxit):
        if act.size == 0:
            break
        tt = t[act]
        d = cat_sdf_world(ox[act] + tt * dx[act], oy[act] + tt * dy[act], oz[act] + tt * dz[act])
        eps = 0.4 * tt / FOC + 2e-5
        h = d < eps
        hit[act[h]] = True
        tt = tt + np.where(h, 0, d * 0.85)
        t[act] = tt
        keep = (~h) & (tt < t1[act])
        act = act[keep]
    return t, hit


def cat_normal(px, py, pz):
    e = 0.0006
    nx = cat_sdf_world(px + e, py, pz) - cat_sdf_world(px - e, py, pz)
    ny = cat_sdf_world(px, py + e, pz) - cat_sdf_world(px, py - e, pz)
    nz = cat_sdf_world(px, py, pz + e) - cat_sdf_world(px, py, pz - e)
    n = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
    return nx / n, ny / n, nz / n


def soft_shadow(px, py, pz, k=14.0):
    """沿太阳方向在猫的 SDF 里走，返回 0–1 的可见度（半影柔和）。"""
    res = np.ones(len(px), np.float32)
    tn, tf = ray_aabb(px, py, pz, np.full_like(px, SUN[0]), np.full_like(px, SUN[1]), np.full_like(px, SUN[2]),
                      CAT_BOX[0], CAT_BOX[1])
    cand = np.nonzero((tf > np.maximum(tn, 0)) & (tf > 0))[0]
    if cand.size == 0:
        return res
    t = np.maximum(tn[cand], 0.004).astype(np.float32)
    tfar = tf[cand]
    r = np.ones(cand.size, np.float32)
    act = np.arange(cand.size)
    for it in range(90):
        if act.size == 0:
            break
        tt = t[act]
        d = cat_sdf_world(px[cand[act]] + tt * SUN[0], py[cand[act]] + tt * SUN[1], pz[cand[act]] + tt * SUN[2], exact=True)
        r[act] = np.minimum(r[act], k * d / tt)
        tt = tt + np.clip(d, 0.0015, 0.03)
        t[act] = tt
        keep = (d > 1e-4) & (tt < tfar[act])
        r[act[d <= 1e-4]] = 0
        act = act[keep]
    res[cand] = np.clip(r, 0, 1)
    return smoothstep(0, 1, res)


def cat_ao(px, py, pz, nx, ny, nz):
    occ = np.zeros(len(px), np.float32)
    sc = 1.0
    for i in range(5):
        hh = 0.008 + 0.018 * i
        d = cat_sdf_world(px + nx * hh, py + ny * hh, pz + nz * hh, exact=True)
        occ += (hh - d) * sc
        sc *= 0.7
    return np.clip(1 - 2.2 * occ, 0, 1)


# ---------------------------------------------------------------- room
SILL, JAMB, FRAME, WALL = 1, 2, 3, 4
BOXES = [(-0.78, 0.78, -0.035, 0.0, -0.22, 0.215, SILL),
         (-0.80, -0.60, -0.035, 1.30, 0.0, 0.215, JAMB),
         (0.60, 0.80, -0.035, 1.30, 0.0, 0.215, JAMB),
         (-0.60, 0.60, 0.0, 0.07, 0.19, 0.24, FRAME),
         (-0.60, -0.54, 0.0, 1.25, 0.19, 0.24, FRAME),
         (0.54, 0.60, 0.0, 1.25, 0.19, 0.24, FRAME),
         (0.27, 0.33, 0.0, 1.25, 0.19, 0.24, FRAME),
         (-0.60, 0.60, 1.19, 1.25, 0.19, 0.24, FRAME)]
GLASS_Z = 0.215


def window_vis(px, py, pz):
    e = 0.0025
    s0 = (0.0 - pz) / SUN[2]
    x0, y0 = px + s0 * SUN[0], py + s0 * SUN[1]
    v0 = smoothstep(-e, e, 0.6 - np.abs(x0)) * smoothstep(-e, e, y0 + 0.001) * smoothstep(-e, e, 1.25 - y0)
    vis = np.where(pz < 0, v0, 1.0)
    s1 = (0.19 - pz) / SUN[2]
    x1, y1 = px + s1 * SUN[0], py + s1 * SUN[1]
    v1 = smoothstep(-e, e, 0.54 - np.abs(x1)) * smoothstep(-e, e, y1 - 0.07) * smoothstep(-e, e, 1.19 - y1)
    v1 = v1 * (1 - smoothstep(-e, e, 0.03 - np.abs(x1 - 0.30)))
    vis = vis * np.where(pz < 0.19, v1, 1.0)
    return (0.92 * vis).astype(np.float32)


def outside_panorama():
    """窗外：阳光下的花园，程序化生成后大幅虚化，再加光斑。返回 (图, yaw 范围, pitch 范围)。"""
    Wp, Hp = 1700, 1100
    y0d, y1d, p0d, p1d = -10.0, 75.0, -40.0, 15.0
    yaw = np.linspace(y0d, y1d, Wp, dtype=np.float32)[None, :].repeat(Hp, 0)
    pit = np.linspace(p1d, p0d, Hp, dtype=np.float32)[:, None].repeat(Wp, 1)
    img = np.zeros((Hp, Wp, 3), np.float32)
    t = smoothstep(0, 40, pit)
    sky = mix3(lin(0.96, 0.95, 0.88)[None, None], lin(0.62, 0.76, 0.95)[None, None], t[..., None]) * 2.2
    tl = 10 + 9 * (fbm(yaw / 14.0, np.zeros_like(yaw) + 0.5, 4, 3) - 0.5) * 2 + 4 * (vnoise(yaw / 3.0, 1.5, 4) - 0.5)
    clump = fbm(yaw / 3.5, pit / 3.5, 5, 7)
    leaf = vnoise(yaw / 0.8, pit / 0.8, 8)
    lit = smoothstep(0.45, 0.65, clump + 0.25 * (leaf - 0.5) + 0.004 * (pit - 0))
    tree = mix3(lin(0.12, 0.25, 0.10)[None, None], lin(0.55, 0.74, 0.28)[None, None], lit[..., None])
    tree = tree * (1.0 + 1.2 * lit[..., None])
    # 远处一道暖色的墙和屋檐（邻居家）
    wallm = (pit < 3 + 2 * np.sin(yaw / 9)) & (pit > -9) & (yaw > 55) & (yaw < 100)
    grass_t = smoothstep(-8, -22, pit)
    gl = fbm(yaw / 4, pit / 2.5, 4, 11)
    grass = mix3(lin(0.22, 0.34, 0.12)[None, None], lin(0.62, 0.72, 0.30)[None, None], smoothstep(0.35, 0.65, gl)[..., None]) * 1.7
    fl = (vnoise(yaw / 1.2, pit / 1.2, 13) > 0.83) & (pit < -14)
    grass[fl] = lin(0.95, 0.55, 0.62) * 2.2
    below = pit < tl
    img = np.where(below[..., None], tree, sky)
    img = np.where((grass_t > 0.5)[..., None], grass * 1.0, img)
    img[wallm] = lin(0.93, 0.80, 0.62) * 2.0
    img = ndi.gaussian_filter(img, (22, 22, 0))
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:Hp, 0:Wp].astype(np.float32)
    for i in range(260):
        cx, cy = rng.uniform(0, Wp), rng.uniform(0, Hp * 0.8)
        py = p1d - cy / Hp * (p1d - p0d)
        if py > tl[int(cy), int(cx)] + 3:
            continue
        if lit[int(cy), int(cx)] < 0.35 and rng.random() < 0.7:
            continue
        r = rng.uniform(10, 26) * (1.0 if rng.random() < 0.8 else 1.4)
        x0, x1, y0, y1 = int(max(0, cx - r - 3)), int(min(Wp, cx + r + 4)), int(max(0, cy - r - 3)), int(min(Hp, cy + r + 4))
        dd = np.sqrt((xx[y0:y1, x0:x1] - cx) ** 2 + (yy[y0:y1, x0:x1] - cy) ** 2)
        disc = np.clip((r - dd) / 3.0, 0, 1) * (0.7 + 0.3 * (dd / r) ** 3)
        tint = [lin(1.0, 0.97, 0.80), lin(0.85, 1.0, 0.62), lin(1.0, 0.90, 0.65)][int(rng.integers(3))]
        img[y0:y1, x0:x1] += disc[..., None] * (tint * (0.12 + 0.9 * rng.random() ** 2.2))[None, None]
    return img, (y0d, y1d, p0d, p1d)


PANO = None


def outside(dx, dy, dz):
    img, (y0d, y1d, p0d, p1d) = PANO
    Hp, Wp = img.shape[:2]
    yaw = np.degrees(np.arctan2(dx, dz))
    pit = np.degrees(np.arcsin(np.clip(dy, -1, 1)))
    gx = (yaw - y0d) / (y1d - y0d) * (Wp - 1)
    gy = (p1d - pit) / (p1d - p0d) * (Hp - 1)
    return np.stack([ndi.map_coordinates(img[..., c], [gy, gx], order=1, mode='nearest') for c in range(3)], -1)


def room_albedo(mat, px, py, pz, nx, ny, nz):
    n = len(px)
    alb = np.zeros((n, 3), np.float32)
    gl = np.zeros(n, np.float32)
    m = mat == SILL
    if m.any():
        g = fbm(px[m] * 60, pz[m] * 4, 3, 21)
        sc = vnoise(px[m] * 300, pz[m] * 40, 22)
        alb[m] = lin(0.88, 0.86, 0.82)[None] * (0.94 + 0.08 * g - 0.04 * (sc > 0.93))[:, None]
        gl[m] = 0.12
    for mm, base, s in ((JAMB, lin(0.87, 0.81, 0.71), 31), (WALL, lin(0.84, 0.77, 0.66), 41)):
        m = mat == mm
        if m.any():
            u = np.where(np.abs(nx[m]) > 0.5, pz[m], px[m])
            g = fbm(u * 25, py[m] * 25, 4, s)
            alb[m] = base[None] * (0.93 + 0.1 * g)[:, None]
            gl[m] = 0.02
    m = mat == FRAME
    if m.any():
        g = fbm(px[m] * 40, py[m] * 40, 3, 51)
        alb[m] = lin(0.90, 0.89, 0.86)[None] * (0.95 + 0.06 * g)[:, None]
        gl[m] = 0.15
    return alb, gl


# ---------------------------------------------------------------- cat colours
ORANGE = lin(0.92, 0.53, 0.21)
DORANGE = lin(0.66, 0.30, 0.09)
CREAM = lin(0.98, 0.88, 0.72)
PINK = lin(0.93, 0.62, 0.58)
NOSEC = lin(0.84, 0.46, 0.44)
EYEC = lin(0.13, 0.08, 0.05)


def seg_dist(ps, pu, s0, u0, s1, u1):
    bs, bu = s1 - s0, u1 - u0
    h = np.clip(((ps - s0) * bs + (pu - u0) * bu) / (bs * bs + bu * bu), 0, 1)
    return np.sqrt((ps - s0 - bs * h) ** 2 + (pu - u0 - bu * h) ** 2)


def cat_albedo(px, py, pz, nx, ny, nz):
    """返回 反照率、毛流方向（世界坐标）、耳朵透光权重。"""
    a, y, b = to_local(px, py, pz)
    d, P = cat_sdf(a, y, b, parts=True)
    n = len(a)
    comp = np.stack([P['body'], P['legs'], np.full_like(P['body'], 9.0), P['head'], P['tail']], 1)
    reg = np.argmin(comp, 1)            # 0 身 1 前腿 2 后爪 3 头 4 尾
    qf, qs, qu = P['qf'], P['qs'], P['qu']
    alb = np.repeat(ORANGE[None], n, 0)
    # --- 身上的虎斑：绕脊背的横纹，上深下浅，肚子和胸口是奶油色
    th = np.arctan2(y - 0.08, b)
    ph = a * 19.0 + 0.22 * np.sin(th * 2.2 + a * 9) + 1.1 * (fbm(a * 7.0, th * 1.6, 4, 61) - 0.5)
    brk = fbm(a * 14.0, th * 3.0, 3, 62)
    stripe = smoothstep(0.42, 0.80, 0.5 + 0.5 * np.sin(2 * np.pi * ph)) * smoothstep(0.25, 0.5, brk)
    top = smoothstep(0.03, 0.12, y)
    spine = np.exp(-(b / 0.022) ** 2) * smoothstep(0.1, 0.16, y) * 0.5
    dark = np.clip(stripe * top * 0.9 + spine, 0, 1)
    body_col = mix3(np.repeat(ORANGE[None], n, 0), np.repeat(DORANGE[None], n, 0), dark)
    belly = smoothstep(0.075, 0.03, y) * smoothstep(-0.12, 0.0, a)
    bib = smoothstep(0.10, 0.2, a) * smoothstep(0.125, 0.07, y) * smoothstep(0.075, 0.03, np.abs(b))
    body_col = mix3(body_col, np.repeat(CREAM[None], n, 0), np.clip(belly * 0.8 + bib, 0, 1))
    # --- 尾巴：环纹，尖端深
    tp = P['tpar'] / (len(TAIL) - 1)
    ring = smoothstep(0.35, 0.7, 0.5 + 0.5 * np.sin(2 * np.pi * tp * 9.5))
    tail_col = mix3(np.repeat(ORANGE[None], n, 0), np.repeat(DORANGE[None], n, 0), np.clip(ring * 0.85 + smoothstep(0.85, 1.0, tp), 0, 1))
    # --- 腿爪：浅
    lring = smoothstep(0.5, 0.85, 0.5 + 0.5 * np.sin(2 * np.pi * a * 24)) * smoothstep(0.24, 0.16, a) * 0.45
    leg_col = mix3(np.repeat(ORANGE[None], n, 0), np.repeat(DORANGE[None], n, 0), lring)
    leg_col = mix3(leg_col, np.repeat(CREAM[None], n, 0), smoothstep(0.19, 0.27, a) * 0.85 + 0.1)
    rel = np.abs(np.abs(b) - 0.044)
    toes = np.minimum(np.abs(rel - 0.0085), np.abs(rel - 0.0)) if False else np.minimum(np.abs(np.abs(b) - 0.044 - 0.0095), np.abs(np.abs(b) - 0.044 + 0.0095))
    groove = smoothstep(0.0022, 0.0008, np.minimum(toes, np.abs(np.abs(b) - 0.044))) * smoothstep(0.285, 0.30, a) * smoothstep(0.0, 0.01, y)
    leg_col = leg_col * (1 - 0.55 * groove)[:, None]
    hind_col = np.repeat(mix3(ORANGE[None], CREAM[None], np.array([0.6], np.float32)), n, 0)
    # --- 头
    head_col = np.repeat(ORANGE[None], n, 0)
    fore = smoothstep(0.012, 0.03, qu) * smoothstep(-0.03, 0.0, qf)
    mline = np.minimum(np.minimum(np.abs(qs + 0.0135), np.abs(qs)), np.abs(qs - 0.0135))
    mstripe = smoothstep(0.0045, 0.0025, mline) * fore * smoothstep(0.055, 0.03, qu)
    back = smoothstep(0.0, -0.035, qf) * smoothstep(0.0, 0.02, qu)
    bstripe = smoothstep(0.35, 0.75, 0.5 + 0.5 * np.sin(qs * 140 + 1.0)) * back
    cheekl = np.minimum(seg_dist(qf, qu, 0.022, 0.004, -0.018, -0.006), seg_dist(qf, qu, 0.018, -0.008, -0.012, -0.02))
    cst = smoothstep(0.0035, 0.0018, cheekl) * smoothstep(0.03, 0.045, np.abs(qs))
    head_col = mix3(head_col, np.repeat(DORANGE[None], n, 0), np.clip(mstripe + bstripe * 0.8 + cst * 0.9, 0, 1))
    front = smoothstep(0.03, 0.045, qf)
    muz = np.clip(smoothstep(0.052, 0.036, np.sqrt((qf - 0.05) ** 2 * 0.3 + qs ** 2 * 0.9 + (qu + 0.022) ** 2)) * front
                  + smoothstep(-0.02, -0.035, qu) * smoothstep(0.0, 0.03, qf), 0, 1)
    head_col = mix3(head_col, np.repeat(CREAM[None], n, 0), muz * 0.92)
    # 眼周浅色一圈 + 闭着的眼睛（向下弯的弧线）
    for s0 in (-0.0245, 0.0245):
        ds = (qs - s0) / 0.0125
        ul = 0.010 - 0.0038 * (1 - ds ** 2)
        inside = np.abs(ds) < 1.0
        dl = np.where(inside, np.abs(qu - ul), 1.0)
        ring_e = smoothstep(0.009, 0.004, np.sqrt(((qs - s0) / 1.4) ** 2 + (qu - 0.008) ** 2)) * (qf > 0.02)
        head_col = mix3(head_col, np.repeat(CREAM[None], n, 0), ring_e * 0.55)
        eye = smoothstep(0.0021, 0.0011, dl) * (qf > 0.02) * smoothstep(1.15, 0.8, np.abs(ds))
        head_col = mix3(head_col, np.repeat(EYEC[None], n, 0), eye)
    # 鼻子（倒三角）和嘴
    nw = 0.0098 * np.clip((qu + 0.0135) / 0.0105, 0, 1)
    nosem = (np.abs(qs) < nw) & (qu > -0.0135) & (qu < -0.002) & (qf > 0.045)
    head_col = np.where(nosem[:, None], NOSEC[None] * (0.8 + 0.4 * smoothstep(-0.012, -0.004, qu))[:, None], head_col)
    mouth = np.minimum(seg_dist(qs, qu, 0.0, -0.0135, 0.0, -0.0205),
                       np.minimum(np.minimum(seg_dist(qs, qu, 0.0, -0.0205, 0.006, -0.0212), seg_dist(qs, qu, 0.006, -0.0212, 0.0105, -0.0196)),
                                  np.minimum(seg_dist(qs, qu, 0.0, -0.0205, -0.006, -0.0212), seg_dist(qs, qu, -0.006, -0.0212, -0.0105, -0.0196))))
    head_col = mix3(head_col, np.repeat(EYEC[None], n, 0), smoothstep(0.0016, 0.0008, mouth) * (qf > 0.045) * 0.85)
    # 耳朵：内侧粉色，耳尖深
    hd, hp = head_sdf(qf, qs, qu, parts=True)
    is_ear = (hp['ears'] < hp['skull'] - 0.002) & (qu > 0.03)
    inner_m = (np.abs(hp['inner']) < 0.0045) & is_ear
    head_col = np.where(is_ear[:, None], mix3(head_col, np.repeat(DORANGE[None], n, 0), smoothstep(0.08, 0.1, qu) * 0.7), head_col)
    head_col = np.where(inner_m[:, None], mix3(np.repeat(PINK[None], n, 0), np.repeat(CREAM[None], n, 0),
                                                smoothstep(0.45, 0.8, vnoise(qs * 900, qu * 300, 71))), head_col)
    alb = np.select([reg[:, None] == 0, reg[:, None] == 1, reg[:, None] == 2, reg[:, None] == 3, reg[:, None] == 4],
                    [body_col, leg_col, hind_col, head_col, tail_col])
    # 毛的细碎明暗
    fn = vnoise(px * 900, (py + pz) * 900, 81)
    alb = alb * (0.9 + 0.2 * fn)[:, None]
    # --- 毛流方向（局部 → 世界），投到切平面
    fa, fy, fb = -np.ones(n, np.float32), -0.55 * smoothstep(0.02, 0.1, np.abs(b)), 0.35 * np.sign(b)
    # 头：从鼻尖往外
    nose_l = HC + 0.07 * HSC * HF
    ha, hy_, hb = a - nose_l[0], y - nose_l[1], b - nose_l[2]
    fa = np.where(reg == 3, ha, fa)
    fy = np.where(reg == 3, hy_ + 0.02, fy)
    fb = np.where(reg == 3, hb, fb)
    fa = np.where(reg == 1, 1.0, fa)
    fy = np.where(reg == 1, -0.1, fy)
    fb = np.where(reg == 1, 0.0, fb)
    ti = np.clip(P['tpar'].astype(np.int64), 0, len(TAIL) - 2)
    tdir = TAIL[ti + 1] - TAIL[ti]
    fa = np.where(reg == 4, tdir[:, 0], fa)
    fy = np.where(reg == 4, tdir[:, 1], fy)
    fb = np.where(reg == 4, tdir[:, 2], fb)
    fy = np.where(is_ear & (reg == 3), 1.0, fy)
    wx, wy, wz = local_dir_to_world(fa, fy, fb)
    dn = wx * nx + wy * ny + wz * nz
    wx, wy, wz = wx - dn * nx, wy - dn * ny, wz - dn * nz
    nn = np.sqrt(wx * wx + wy * wy + wz * wz) + 1e-9
    ear_w = (is_ear & (reg == 3)).astype(np.float32)
    return alb.astype(np.float32), (wx / nn, wy / nn, wz / nn), ear_w


# ---------------------------------------------------------------- render
def render():
    global PANO
    PANO = outside_panorama()
    log('panorama')
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
    # --- 解析几何
    tbest = np.full(N, np.inf, np.float32)
    mat = np.zeros(N, np.int8)
    nx = np.zeros(N, np.float32)
    ny = np.zeros(N, np.float32)
    nz = np.zeros(N, np.float32)
    with np.errstate(divide='ignore', invalid='ignore'):
        tw = (0.0 - CAMP[2]) / dz
    wx_, wy_ = CAMP[0] + tw * dx, CAMP[1] + tw * dy
    inhole = (np.abs(wx_) < 0.6) & (wy_ > 0.0) & (wy_ < 1.25)
    m = (tw > 0) & ~inhole
    tbest[m] = tw[m]
    mat[m] = WALL
    nz[m] = -1
    for (x0, x1, y0, y1, z0, z1, mm) in BOXES:
        tn, tf = ray_aabb(ox, oy, oz, dx, dy, dz, (x0, y0, z0), (x1, y1, z1))
        m = (tf >= tn) & (tn > 0) & (tn < tbest)
        if not m.any():
            continue
        tbest[m] = tn[m]
        mat[m] = mm
        px, py, pz = CAMP[0] + tn[m] * dx[m], CAMP[1] + tn[m] * dy[m], CAMP[2] + tn[m] * dz[m]
        e = 1e-4
        fx = np.where(np.abs(px - x0) < e, -1, np.where(np.abs(px - x1) < e, 1, 0))
        fy = np.where(np.abs(py - y0) < e, -1, np.where(np.abs(py - y1) < e, 1, 0))
        fz = np.where(np.abs(pz - z0) < e, -1, np.where(np.abs(pz - z1) < e, 1, 0))
        nx[m], ny[m], nz[m] = fx, np.where(fx != 0, 0, fy), np.where((fx != 0) | (fy != 0), 0, fz)
    with np.errstate(divide='ignore', invalid='ignore'):
        tg = (GLASS_Z - CAMP[2]) / dz
    gx_, gy_ = CAMP[0] + tg * dx, CAMP[1] + tg * dy
    glass = (tg > 0) & (tg < tbest) & (np.abs(gx_) < 0.6) & (gy_ > 0) & (gy_ < 1.25)
    log('room geometry')
    # --- 猫
    tn, tf = ray_aabb(ox, oy, oz, dx, dy, dz, CAT_BOX[0], CAT_BOX[1])
    tlim = np.where(glass, tg, tbest)
    cand = np.nonzero((tf > tn) & (tn < tlim) & (tf > 0))[0]
    tc, hitc = march(ox[cand], oy[cand], oz[cand], dx[cand], dy[cand], dz[cand], np.maximum(tn[cand], 0.05),
                     np.minimum(tf[cand], tlim[cand]))
    cat_idx = cand[hitc]
    tcat = tc[hitc]
    log('cat march', cand.size, cat_idx.size)
    col = np.zeros((N, 3), np.float32)
    # --- 窗外
    catmask = np.zeros(N, bool)
    catmask[cat_idx] = True
    gi = np.nonzero(glass & ~catmask)[0]
    outc = outside(dx[gi], dy[gi], dz[gi])
    col[gi] = outc * 0.9 + lin(0.5, 0.45, 0.4)[None] * 0.03
    # --- 室内表面
    ri = np.nonzero((~glass) & (~catmask) & np.isfinite(tbest))[0]
    t = tbest[ri]
    px, py, pz = CAMP[0] + t * dx[ri], CAMP[1] + t * dy[ri], CAMP[2] + t * dz[ri]
    alb, gl = room_albedo(mat[ri], px, py, pz, nx[ri], ny[ri], nz[ri])
    NX, NY, NZ = nx[ri], ny[ri], nz[ri]
    ndl = np.clip(NX * SUN[0] + NY * SUN[1] + NZ * SUN[2], 0, None)
    vis = window_vis(px + NX * 1e-3, py + NY * 1e-3, pz + NZ * 1e-3)
    lit = np.nonzero(vis * ndl > 1e-3)[0]
    if lit.size:
        vis[lit] *= soft_shadow(px[lit] + NX[lit] * 2e-3, py[lit] + NY[lit] * 2e-3, pz[lit] + NZ[lit] * 2e-3)
    near = (px > CAT_BOX[0][0] - 0.08) & (px < CAT_BOX[1][0] + 0.08) & (pz > CAT_BOX[0][2] - 0.08) & (pz < CAT_BOX[1][2] + 0.08) \
        & (py > CAT_BOX[0][1] - 0.08) & (py < CAT_BOX[1][1] + 0.08)
    ao = np.ones(len(ri), np.float32)
    ni = np.nonzero(near)[0]
    if ni.size:
        dd = cat_sdf_world(px[ni] + NX[ni] * 0.01, py[ni] + NY[ni] * 0.01, pz[ni] + NZ[ni] * 0.01, exact=True)
        dd2 = cat_sdf_world(px[ni] + NX[ni] * 0.035, py[ni] + NY[ni] * 0.035, pz[ni] + NZ[ni] * 0.035, exact=True)
        ao[ni] = np.clip(0.35 + 0.65 * np.minimum(smoothstep(-0.005, 0.03, dd), smoothstep(0.0, 0.06, dd2)), 0, 1)
    # 角落 AO：窗台与窗框、侧壁的交角，窗台下沿
    corner = np.ones(len(ri), np.float32)
    corner *= 1 - 0.45 * np.exp(-np.abs(pz - 0.19) / 0.02) * (NY > 0.5)
    dcor = np.where(pz > 0, np.abs(0.6 - np.abs(px)), np.where(np.abs(px) > 0.6, np.abs(pz), 9.0))
    corner *= 1 - 0.35 * np.exp(-dcor / 0.025) * (NY > 0.5)
    corner *= 1 - 0.5 * np.exp(-np.maximum(-0.035 - py, 0) / 0.03) * (NZ < -0.5) * (py < -0.03)
    corner *= 1 - 0.3 * np.exp(-np.maximum(py, 0) / 0.05) * (np.abs(NX) > 0.5)
    fill_sky = SKY_FILL[None] * np.clip(0.3 + 0.7 * (NX * WDIR[0] + NY * WDIR[1] + NZ * WDIR[2]), 0, 1)[:, None] \
        * np.exp(-np.maximum(-pz, 0) / 0.9)[:, None] * (1.0 + 0.45 * (NY > 0.5))[:, None]
    # 被晒亮的窗台把光反到侧壁/墙上
    bounce = BOUNCE[None] * 0.35 * np.clip(-NY + 0.3, 0, 1)[:, None] * np.exp(-np.abs(py) / 0.3)[:, None]
    irr = SUN_COL[None] * (vis * ndl)[:, None] + (fill_sky + ROOM_FILL[None] + bounce) * (ao * corner)[:, None]
    c = alb * irr
    # 太阳在窗台漆面上的高光
    Vx, Vy, Vz = -dx[ri], -dy[ri], -dz[ri]
    hx, hy, hz = SUN[0] + Vx, SUN[1] + Vy, SUN[2] + Vz
    hn = np.sqrt(hx * hx + hy * hy + hz * hz)
    spec = np.clip((NX * hx + NY * hy + NZ * hz) / hn, 0, 1) ** 60
    c += (gl * spec * vis * 1.5)[:, None] * SUN_COL[None]
    col[ri] = c
    log('room shade')
    # --- 猫的着色
    t = tcat
    ci = cat_idx
    px, py, pz = CAMP[0] + t * dx[ci], CAMP[1] + t * dy[ci], CAMP[2] + t * dz[ci]
    NX, NY, NZ = cat_normal(px, py, pz)
    alb, fdir, ear_w = cat_albedo(px, py, pz, NX, NY, NZ)
    ndl = NX * SUN[0] + NY * SUN[1] + NZ * SUN[2]
    vis = window_vis(px, py, pz) * soft_shadow(px + NX * 0.002, py + NY * 0.002, pz + NZ * 0.002, k=10.0)
    wrap = np.clip((ndl + 0.35) / 1.35, 0, 1)
    ao = cat_ao(px, py, pz, NX, NY, NZ)
    fill_sky = SKY_FILL[None] * np.clip(0.35 + 0.65 * (NX * WDIR[0] + NY * WDIR[1] + NZ * WDIR[2]), 0, 1)[:, None]
    under = np.clip(-NY + 0.25, 0, 1.25) * np.exp(-np.maximum(py, 0) / 0.12)
    bounce = BOUNCE[None] * under[:, None]
    irr = SUN_COL[None] * (vis * wrap)[:, None] + (fill_sky + ROOM_FILL[None] + bounce) * ao[:, None]
    c = alb * irr
    Vx, Vy, Vz = -dx[ci], -dy[ci], -dz[ci]
    ndv = np.clip(NX * Vx + NY * Vy + NZ * Vz, 0, 1)
    rim = (1 - ndv) ** 3 * np.clip(ndl + 0.45, 0, 1) * vis
    c += (rim * 0.55)[:, None] * SUN_COL[None] * np.sqrt(alb + 0.02)
    trans = ear_w * np.clip(-ndl + 0.2, 0, 1) * window_vis(px, py, pz)
    c += (trans * 0.9)[:, None] * SUN_COL[None] * lin(1.0, 0.55, 0.42)[None]
    col[ci] = c
    log('cat shade')
    # --- 右边一幅半透明的纱帘，被阳光透亮
    tsc = np.where(glass, np.inf, tbest)
    tsc[ci] = t
    ZCUR = -0.035
    with np.errstate(divide='ignore', invalid='ignore'):
        tcu = (ZCUR - CAMP[2]) / dz
    cx_, cy_ = CAMP[0] + tcu * dx, CAMP[1] + tcu * dy
    edge_x = 0.50 + 0.018 * np.sin(cy_ * 9.0) + 0.01 * np.sin(cy_ * 23.0)
    cm_ = (tcu > 0) & (tcu < tsc) & (cx_ > edge_x) & (cx_ < 0.95) & (cy_ > 0.015) & (cy_ < 1.6)
    k = np.nonzero(cm_)[0]
    if k.size:
        xk, yk = cx_[k], cy_[k]
        phs = xk * 62 + 1.6 * np.sin(yk * 3.1 + xk * 7)
        fold = 0.5 + 0.5 * np.sin(phs)
        alpha = (0.42 + 0.3 * fold) * smoothstep(0.0, 0.03, xk - edge_x[k]) * smoothstep(0.0, 0.02, yk - 0.015)
        weave = 0.96 + 0.04 * vnoise(xk * 900, yk * 900, 91)
        vs = window_vis(xk, yk, np.full_like(xk, ZCUR))
        cc = lin(0.97, 0.95, 0.92)[None] * ((ROOM_FILL + SKY_FILL * 0.9)[None] * (0.7 + 0.3 * fold)[:, None]
                                             + SUN_COL[None] * (vs * (0.30 + 0.25 * fold))[:, None]) * weave[:, None]
        col[k] = col[k] * (1 - alpha)[:, None] + cc * alpha[:, None]
    # --- 光柱里的空气微微发亮（沿视线积分窗洞可见度）
    tend = np.minimum(tsc, 2.2)
    haze = np.zeros(N, np.float32)
    nstep = 28
    jit = np.random.default_rng(31).random(N).astype(np.float32)      # 每个像素的采样位置抖一下，去掉分层条纹
    for i in range(nstep):
        ts = 0.35 + (i + jit) / nstep * (tend - 0.35)
        pxh, pyh, pzh = CAMP[0] + ts * dx, CAMP[1] + ts * dy, CAMP[2] + ts * dz
        inside = (pzh < 0.19) & (pyh > 0.0)
        haze += np.where(inside, window_vis(pxh, pyh, pzh), 0) * np.maximum(tend - 0.35, 0) / nstep
    haze = ndi.gaussian_filter(haze.reshape(RH, RW), 5).ravel()
    col += (0.035 * haze)[:, None] * SUN_COL[None]
    # --- 屏幕上的毛流方向
    fx_, fy_, fz_ = fdir
    p0x, p0y, _ = project(np.stack([px, py, pz], 1))
    p1x, p1y, _ = project(np.stack([px + fx_ * 0.01, py + fy_ * 0.01, pz + fz_ * 0.01], 1))
    ddx, ddy = p1x - p0x, p1y - p0y
    dn = np.sqrt(ddx * ddx + ddy * ddy) + 1e-6
    tx = np.ones(N, np.float32)
    ty = np.zeros(N, np.float32)
    tx[ci] = ddx / dn
    ty[ci] = ddy / dn
    depth = np.full(N, 9.0, np.float32)
    depth[ci] = t
    lit_map = np.zeros(N, np.float32)
    lit_map[ci] = vis
    shp = (RH, RW)
    return (col.reshape(RH, RW, 3), catmask.reshape(shp), tx.reshape(shp), ty.reshape(shp), depth.reshape(shp),
            lit_map.reshape(shp))


def dust(col, depth_scene):
    """阳光里的浮尘：只在光柱里、且在物体前面的才画。"""
    rng = np.random.default_rng(17)
    n = 420
    P = np.stack([rng.uniform(-0.55, 0.9, n), rng.uniform(0.02, 0.55, n), rng.uniform(-0.55, 0.17, n)], 1).astype(np.float32)
    vis = window_vis(P[:, 0], P[:, 1], P[:, 2])
    keep = vis > 0.5
    P = P[keep]
    sx, sy, zc = project(P)
    dist = np.linalg.norm(P - CAMP[None].astype(np.float32), axis=1)
    yy, xx = np.mgrid[0:9, 0:9].astype(np.float32) - 4
    for (x, y, z) in zip(sx, sy, dist):
        ix, iy = int(round(x)), int(round(y))
        if not (5 <= ix < RW - 5 and 5 <= iy < RH - 5):
            continue
        if depth_scene[iy, ix] < z:
            continue
        foc = abs(z - 1.2)
        r = 0.7 + 8.0 * foc
        a = min(0.7, 0.35 / (0.25 + 0.3 * r))
        bgl = float(col[iy, ix].mean())
        if bgl > 0.9:
            continue
        rr = int(min(4, math.ceil(r + 1)))
        g = np.exp(-((xx[4 - rr:5 + rr, 4 - rr:5 + rr] ** 2 + yy[4 - rr:5 + rr, 4 - rr:5 + rr] ** 2) / (r * r)))
        col[iy - rr:iy + rr + 1, ix - rr:ix + rr + 1] += (a * g)[..., None] * SUN_COL[None, None] * 0.35


def tonemap(x):
    x = np.maximum(x, 0)
    y = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14)
    return np.clip(y, 0, 1) ** (1 / 2.2)


def main():
    col, cat, tx, ty, depth, litm = render()
    # 场景深度（给浮尘做遮挡）：猫的深度，其他地方近似用窗台/墙
    depth_scene = np.where(cat, depth, 9.0)
    # --- 毛：沿毛流 LIC 抹开颜色（条纹边缘变毛糙），再叠一层毛丝明暗
    cm = cat.astype(np.float32)
    txc = np.ascontiguousarray(tx)
    tyc = np.ascontiguousarray(ty)
    sm = np.stack([stylize.lic(np.ascontiguousarray(col[..., c] * cm), txc, tyc, 9) for c in range(3)], -1)
    wgt = stylize.lic(cm, txc, tyc, 9)
    sm = sm / np.maximum(wgt[..., None], 1e-3)
    inner = ndi.binary_erosion(cat, iterations=3)
    col = np.where(inner[..., None], 0.35 * col + 0.65 * sm, col)
    nz = np.random.default_rng(7).random((RH, RW)).astype(np.float32)
    fur = stylize.lic(nz, txc, tyc, 16)
    fur = (fur - fur.mean()) / (fur.std() + 1e-6)
    fur2 = stylize.lic(np.random.default_rng(8).random((RH, RW)).astype(np.float32), txc, tyc, 6)
    fur2 = (fur2 - fur2.mean()) / (fur2.std() + 1e-6)
    col = np.where(cat[..., None], col * (1 + 0.16 * fur + 0.08 * fur2)[..., None], col)
    log('fur lic')
    dust(col, depth_scene)
    # 泛光
    bright = np.maximum(col - 1.4, 0)
    col = col + 0.35 * ndi.gaussian_filter(bright, (14, 14, 0)) + 0.15 * ndi.gaussian_filter(bright, (50, 50, 0))
    img = tonemap(col * 0.95)
    log('tonemap')
    # --- 轮廓上的短毛（2D）：猫和背景、头和身体的交界，往外长
    lay = Image.fromarray((img * 255 + 0.5).astype(np.uint8))
    d = ImageDraw.Draw(lay, 'RGBA')
    dc = np.minimum(depth, 2.0)
    dcb = ndi.gaussian_filter(dc, 1.5)
    gy, gx = np.gradient(dcb)
    edge = cat & ((ndi.maximum_filter(dc, 3) - dc) > 0.012)
    ey, ex = np.nonzero(edge)
    rng = np.random.default_rng(3)
    sel = rng.random(ey.size) < 0.45
    ey, ex = ey[sel], ex[sel]
    for y, x in zip(ey, ex):
        g0, g1 = gx[y, x], gy[y, x]
        gn = math.hypot(g0, g1) + 1e-9
        ox_, oy_ = g0 / gn, g1 / gn
        fx_, fy_ = tx[y, x], ty[y, x]
        vx, vy = ox_ + 0.9 * fx_ + rng.normal(0, 0.35), oy_ + 0.9 * fy_ + rng.normal(0, 0.35)
        vn = math.hypot(vx, vy) + 1e-9
        L = rng.uniform(5, 15) * (1.0 + 0.6 * litm[y, x])
        xi, yi = max(0, min(RW - 1, x - int(2 * ox_))), max(0, min(RH - 1, y - int(2 * oy_)))
        c = img[yi, xi] * (1.0 + 0.25 * litm[y, x])
        cc = tuple(int(min(255, v * 255)) for v in c) + (int(150 + 60 * rng.random()),)
        d.line([(x - 2 * ox_, y - 2 * oy_), (x + vx / vn * L, y + vy / vn * L)], fill=cc, width=1)
    log('edge hairs', ey.size)
    # --- 胡须（3D 曲线投影），晒到的地方发亮
    for sgn in (-1, 1):
        for k in range(5):
            root = HC + HSC * (0.050 * HF + sgn * (0.019 + 0.002 * k) * HS - (0.017 + 0.0035 * k) * HU)
            pts = []
            for tt in np.linspace(0, 1, 18):
                ln = 0.075 + 0.012 * (2 - abs(k - 2))
                o = root + tt * ln * (0.35 * HF + sgn * 0.93 * HS + (0.12 - 0.09 * k) * HU) - (0.018 * tt * tt) * np.array([0, 1.0, 0])
                pw = CAT_O + o[0] * CAT_H + o[2] * CAT_S + np.array([0, o[1], 0])
                pts.append(pw)
            pts = np.array(pts)
            sx, sy, zc = project(pts)
            dist = np.linalg.norm(pts - CAMP[None], axis=1)
            seg = []
            for i in range(len(pts)):
                ix, iy = int(sx[i]), int(sy[i])
                visible = 0 <= ix < RW and 0 <= iy < RH and (depth[iy, ix] > dist[i] - 0.004 or not cat[iy, ix])
                if visible:
                    seg.append((sx[i], sy[i]))
                elif len(seg) > 1:
                    d.line(seg, fill=(250, 240, 222, 170), width=2)
                    seg = []
                else:
                    seg = []
            if len(seg) > 1:
                d.line(seg, fill=(250, 240, 222, 170), width=2)
    img = np.asarray(lay, np.float32) / 255
    img = img.reshape(H, SS, W, SS, 3).mean((1, 3))
    # 调色：暖一点、四角压暗、细颗粒
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r2 = ((xx - W * 0.45) / (W * 0.62)) ** 2 + ((yy - H * 0.5) / (H * 0.62)) ** 2
    img = img * (1 - 0.22 * np.clip(r2, 0, 1.4))[..., None]
    img = img * np.array([1.02, 1.0, 0.96], np.float32)
    img = img + np.random.default_rng(4).normal(0, 0.008, img.shape).astype(np.float32)
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    out.save(os.path.join(HERE, 'final.png'))
    for extra in sys.argv[1:]:
        out.save(os.path.join(HERE, extra))
    log('saved', out.size)


if __name__ == '__main__':
    main()
