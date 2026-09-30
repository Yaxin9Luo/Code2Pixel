#!/usr/bin/env python3
"""A03 夜晚的日式小巷：红灯笼、发光的自动售货机、被雨打湿的石板路。

纯代码渲染（numpy + Pillow + scipy），不读取任何图片文件：
- 自写的透视光栅化：场景由 3D 平面多边形组成（墙面、屋檐、灯笼公告板、售货机的面……），
  每个面贴程序化绘制的纹理，用面积表（summed-area table）按像素足迹过滤，避免掠射角摩尔纹；
- 延迟光照：灯笼、售货机、门洞都是点光源 / 面光源采样；
- 湿地反射：把整个场景关于地面做镜像再渲染一遍，按菲涅尔系数、水洼遮罩和粗糙度模糊叠加到地面上；
- 高度雾、泛光、色调映射、暗角、颗粒。
灯笼、招牌上的文字用系统字体（ヒラギノ）排版。
运行：python3 draw.py  → 输出 final.png（固定随机种子，可完全复现）
"""
import os
import sys
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1152, 1536
F = 820.0
CX, CY = 560.0, 730.0
CAM = np.array([-0.15, 1.35, 0.0])
f32 = np.float32
FM = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"      # index 2 = W6
FG = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


# ----------------------------------------------------------------------------- noise
def _hash(ix, iy, seed):
    ix = np.asarray(ix, np.int64)
    iy = np.asarray(iy, np.int64)
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF).astype(np.float64) / 16777216.0


def vnoise(x, y, seed=0):
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    ix = np.floor(x)
    iy = np.floor(y)
    fx = x - ix
    fy = y - iy
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    u = fx * fx * (3 - 2 * fx)
    v = fy * fy * (3 - 2 * fy)
    a = _hash(ix, iy, seed)
    b = _hash(ix + 1, iy, seed)
    c = _hash(ix, iy + 1, seed)
    d = _hash(ix + 1, iy + 1, seed)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm(x, y, octaves=4, seed=0, lac=2.03, gain=0.5):
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    tot = 0.0
    amp = 1.0
    norm = 0.0
    for o in range(octaves):
        tot = tot + amp * vnoise(x, y, seed + 31 * o)
        norm += amp
        amp *= gain
        x = x * lac + 5.3
        y = y * lac + 1.7
    return tot / norm


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------- textures
class Tex:
    """程序化纹理：albedo / alpha / emission，坐标用米（u 向右，v 向上）。build() 后可按像素足迹过滤采样。"""

    def __init__(self, wu, hv, res, alb=(0.1, 0.1, 0.1), a=1.0):
        self.wu, self.hv, self.res = float(wu), float(hv), float(res)
        self.w = max(2, int(round(wu / res)))
        self.h = max(2, int(round(hv / res)))
        self.alb = np.empty((self.h, self.w, 3), f32)
        self.alb[:] = alb
        self.a = np.full((self.h, self.w), a, f32)
        self.emi = np.zeros((self.h, self.w, 3), f32)
        self.S = None

    def sl(self, u0, v0, u1, v1):
        c0 = int(np.clip(round(u0 / self.res), 0, self.w))
        c1 = int(np.clip(round(u1 / self.res), 0, self.w))
        r0 = int(np.clip(round((self.hv - v1) / self.res), 0, self.h))
        r1 = int(np.clip(round((self.hv - v0) / self.res), 0, self.h))
        return (slice(r0, max(r1, r0)), slice(c0, max(c1, c0)))

    def uv(self, sl):
        U = (np.arange(sl[1].start, sl[1].stop) + 0.5) * self.res
        V = self.hv - (np.arange(sl[0].start, sl[0].stop) + 0.5) * self.res
        return np.meshgrid(U, V)

    def fill(self, u0, v0, u1, v1, alb=None, emi=None, a=None):
        s = self.sl(u0, v0, u1, v1)
        if alb is not None:
            self.alb[s] = alb
        if emi is not None:
            self.emi[s] = emi
        if a is not None:
            self.a[s] = a
        return s

    def text(self, s, u0, v0, u1, v1, alb=None, emi=None, font=FM, idx=2, vertical=False, scale=0.9):
        sl = self.sl(u0, v0, u1, v1)
        hh = sl[0].stop - sl[0].start
        ww = sl[1].stop - sl[1].start
        if hh < 3 or ww < 3:
            return None
        img = Image.new('L', (ww, hh), 0)
        d = ImageDraw.Draw(img)
        n = len(s)
        if vertical:
            size = int(min(ww, hh / n) * scale)
            fnt = ImageFont.truetype(font, max(size, 4), index=idx)
            for i, ch in enumerate(s):
                d.text((ww / 2, (i + 0.5) * hh / n), ch, fill=255, font=fnt, anchor='mm')
        else:
            size = int(min(hh, ww / max(n, 1)) * scale)
            fnt = ImageFont.truetype(font, max(size, 4), index=idx)
            d.text((ww / 2, hh / 2), s, fill=255, font=fnt, anchor='mm')
        m = (np.asarray(img, f32) / 255.0)[..., None]
        if alb is not None:
            self.alb[sl] = self.alb[sl] * (1 - m) + np.asarray(alb, f32) * m
        if emi is not None:
            self.emi[sl] = self.emi[sl] * (1 - m) + np.asarray(emi, f32) * m
        return m

    def build(self):
        a = self.a[..., None]
        pm = np.concatenate([self.alb * a, a, self.emi * a], axis=2).astype(np.float64)
        S = np.zeros((self.h + 1, self.w + 1, 7))
        S[1:, 1:] = pm.cumsum(0).cumsum(1)
        self.S = S
        return self

    def _S(self, r, c):
        r0 = np.clip(np.floor(r).astype(np.int64), 0, self.h - 1)
        c0 = np.clip(np.floor(c).astype(np.int64), 0, self.w - 1)
        fr = (r - r0)[..., None]
        fc = (c - c0)[..., None]
        S = self.S
        return (S[r0, c0] * (1 - fr) * (1 - fc) + S[r0 + 1, c0] * fr * (1 - fc)
                + S[r0, c0 + 1] * (1 - fr) * fc + S[r0 + 1, c0 + 1] * fr * fc)

    def sample(self, u, v, du, dv):
        tc = u / self.res
        tr = (self.hv - v) / self.res
        hc = np.maximum(du / self.res, 1.0) * 0.5
        hr = np.maximum(dv / self.res, 1.0) * 0.5
        c0 = np.clip(tc - hc, 0, self.w)
        c1 = np.clip(tc + hc, 0, self.w)
        r0 = np.clip(tr - hr, 0, self.h)
        r1 = np.clip(tr + hr, 0, self.h)
        area = (c1 - c0) * (r1 - r0)
        tot = self._S(r1, c1) - self._S(r0, c1) - self._S(r1, c0) + self._S(r0, c0)
        out = tot / np.maximum(area, 1e-9)[..., None]
        out[area < 1e-6] = 0
        return out.astype(f32)


# ----------------------------------------------------------------------------- render passes
class Pass:
    def __init__(self, mirror):
        self.mirror = mirror
        self.s = -1.0 if mirror else 1.0
        self.alb = np.zeros((H, W, 3), f32)
        self.emi = np.zeros((H, W, 3), f32)
        self.P = np.zeros((H, W, 3), f32)
        self.N = np.zeros((H, W, 3), f32)
        self.dist = np.zeros((H, W), f32)
        self.G = np.zeros((H, W), f32)          # visible wet-ground coverage
        self.ao = np.ones((H, W), f32)
        self.gk = np.zeros((H, W), f32)         # ground reflectivity
        self.grough = np.ones((H, W), f32)      # ground roughness (0 = mirror puddle)
        self.gX = np.zeros((H, W), f32)
        self.gZ = np.ones((H, W), f32)
        self.wire = np.zeros((H, W), f32)
        self.goy = np.zeros((H, W), f32)
        self.gox = np.zeros((H, W), f32)

    def blend(self, sl, cov, alb_pm, emi_pm, P, N, dist, ao):
        c = cov[..., None]
        self.alb[sl] = self.alb[sl] * (1 - c) + alb_pm
        self.emi[sl] = self.emi[sl] * (1 - c) + emi_pm
        self.P[sl] = self.P[sl] * (1 - c) + P * c
        self.N[sl] = self.N[sl] * (1 - c) + N * c
        self.dist[sl] = self.dist[sl] * (1 - cov) + dist * cov
        self.ao[sl] = self.ao[sl] * (1 - cov) + ao * cov
        self.G[sl] *= (1 - cov)


def clip_near(P, zn=0.12):
    out = []
    n = len(P)
    for i in range(n):
        A = P[i]
        B = P[(i + 1) % n]
        ia = A[2] >= zn
        ib = B[2] >= zn
        if ia:
            out.append(A)
        if ia != ib:
            t = (zn - A[2]) / (B[2] - A[2])
            out.append(A + t * (B - A))
    return np.array(out) if out else np.zeros((0, 3))


def poly_cov(xs, ys, ss=4):
    x0 = int(max(np.floor(xs.min()), 0))
    x1 = int(min(np.ceil(xs.max()), W))
    y0 = int(max(np.floor(ys.min()), 0))
    y1 = int(min(np.ceil(ys.max()), H))
    if x1 <= x0 or y1 <= y0:
        return None
    xs = np.clip(xs, -20000, 20000)
    ys = np.clip(ys, -20000, 20000)
    img = Image.new('L', ((x1 - x0) * ss, (y1 - y0) * ss), 0)
    pts = [((x - x0) * ss - 0.5, (y - y0) * ss - 0.5) for x, y in zip(xs, ys)]
    ImageDraw.Draw(img).polygon(pts, fill=255)
    m = np.asarray(img, f32).reshape(y1 - y0, ss, x1 - x0, ss).mean(axis=(1, 3)) / 255.0
    return m, y0, x0


def draw_quad(ps, O, U, V, wu, hv, N, tex=None, alb=(0.05, 0.05, 0.05), emi=None, ao=True, ss=4):
    O = np.asarray(O, float)
    U = np.asarray(U, float)
    V = np.asarray(V, float)
    N = np.asarray(N, float)
    corners = np.array([O, O + U * wu, O + U * wu + V * hv, O + V * hv])
    mv = np.array([1.0, ps.s, 1.0])
    cm = clip_near(corners * mv)
    if len(cm) < 3:
        return
    xs = CX + F * (cm[:, 0] - CAM[0]) / cm[:, 2]
    ys = CY - F * (cm[:, 1] - CAM[1]) / cm[:, 2]
    r = poly_cov(xs, ys, ss)
    if r is None:
        return
    m, y0, x0 = r
    if m.max() <= 0:
        return
    h, w = m.shape
    sl = (slice(y0, y0 + h), slice(x0, x0 + w))
    Nm = N * mv
    Om = O * mv
    num = float(np.dot(Om - CAM, Nm))
    xg = np.arange(x0, x0 + w) + 0.5
    yg = np.arange(y0, y0 + h) + 0.5

    def isect(ox, oy):
        dx = ((xg + ox - CX) / F)[None, :]
        dy = ((CY - (yg + oy)) / F)[:, None]
        den = dx * Nm[0] + dy * Nm[1] + Nm[2]
        den = np.where(np.abs(den) < 1e-9, 1e-9, den)
        t = np.clip(num / den, 0.01, 1e4)
        Px = CAM[0] + t * dx
        Py = ps.s * (CAM[1] + t * dy)
        Pz = t + 0 * dx
        Px, Py, Pz = np.broadcast_arrays(Px, Py, Pz)
        return np.stack([Px, Py, Pz], -1), t, dx, dy

    P, t, dx, dy = isect(0, 0)
    dist = (t * np.sqrt(dx * dx + dy * dy + 1)).astype(f32)
    u = (P - O) @ U
    v = (P - O) @ V
    if tex is not None:
        P1 = isect(1, 0)[0]
        P2 = isect(0, 1)[0]
        du = np.abs((P1 - O) @ U - u) + np.abs((P2 - O) @ U - u)
        dv = np.abs((P1 - O) @ V - v) + np.abs((P2 - O) @ V - v)
        smp = tex.sample(np.nan_to_num(u), np.nan_to_num(v), np.nan_to_num(du), np.nan_to_num(dv))
        cov = m * smp[..., 3]
        alb_pm = smp[..., :3] * m[..., None]
        emi_pm = smp[..., 4:7] * m[..., None]
    else:
        cov = m
        alb_pm = np.asarray(alb, f32)[None, None, :] * m[..., None]
        e = np.zeros(3, f32) if emi is None else np.asarray(emi, f32)
        emi_pm = e[None, None, :] * m[..., None]
    Nn = np.broadcast_to(N.astype(f32), P.shape)
    if ao and abs(N[1]) < 0.5:
        aov = (1 - 0.5 * np.exp(-np.maximum(P[..., 1], 0) / 0.35)).astype(f32)
    else:
        aov = np.ones(m.shape, f32)
    ps.blend(sl, cov.astype(f32), alb_pm.astype(f32), emi_pm.astype(f32), P.astype(f32), Nn, dist, aov)


def box_faces(x0, x1, y0, y1, z0, z1):
    return {
        'front': dict(O=(x0, y0, z0), U=(1, 0, 0), V=(0, 1, 0), wu=x1 - x0, hv=y1 - y0, N=(0, 0, -1)),
        'back': dict(O=(x1, y0, z1), U=(-1, 0, 0), V=(0, 1, 0), wu=x1 - x0, hv=y1 - y0, N=(0, 0, 1)),
        'px': dict(O=(x1, y0, z0), U=(0, 0, 1), V=(0, 1, 0), wu=z1 - z0, hv=y1 - y0, N=(1, 0, 0)),
        'nx': dict(O=(x0, y0, z1), U=(0, 0, -1), V=(0, 1, 0), wu=z1 - z0, hv=y1 - y0, N=(-1, 0, 0)),
        'top': dict(O=(x0, y1, z0), U=(1, 0, 0), V=(0, 0, 1), wu=x1 - x0, hv=z1 - z0, N=(0, 1, 0)),
        'bot': dict(O=(x0, y0, z1), U=(1, 0, 0), V=(0, 0, -1), wu=x1 - x0, hv=z1 - z0, N=(0, -1, 0)),
    }


def draw_box(ps, x0, x1, y0, y1, z0, z1, mats, default=None):
    faces = box_faces(x0, x1, y0, y1, z0, z1)
    mv = np.array([1.0, ps.s, 1.0])
    for name, fc in faces.items():
        mat = mats.get(name, default)
        if mat is None:
            continue
        O = np.asarray(fc['O'], float)
        c = O + np.asarray(fc['U'], float) * fc['wu'] / 2 + np.asarray(fc['V'], float) * fc['hv'] / 2
        n = np.asarray(fc['N'], float) * mv
        if np.dot(n, c * mv - CAM) >= 0:
            continue
        draw_quad(ps, **fc, **mat)


# ----------------------------------------------------------------------------- painters
WARM = np.array([1.0, 0.5, 0.2], f32)
AMBER = np.array([1.0, 0.45, 0.15], f32)


def grain(t, sl, base, var=0.3, su=0.004, sv=0.5, seed=0):
    U, V = t.uv(sl)
    n = fbm(U / su, V / sv, 3, seed)
    t.alb[sl] = (np.asarray(base, f32) * (1 + var * (n - 0.5) * 2)[..., None]).astype(f32)


def paint_izakaya(L, seed, door, noren, sign, inten=1.5, res=0.005, H1=2.8):
    t = Tex(L, H1, res)
    grain(t, t.sl(0, 0, L, H1), (0.05, 0.03, 0.018), 0.35, 0.004, 0.6, seed)
    d0, d1 = door
    s = t.sl(0, 0, L, 0.34)
    U, V = t.uv(s)
    t.alb[s] *= np.where(np.mod(V, 0.113) < 0.01, 0.45, 1.0)[..., None].astype(f32)
    # 格子 + 透出来的店内暖光
    s = t.sl(0, 0.34, L, 2.18)
    U, V = t.uv(s)
    n = fbm(U / 0.4, V / 0.6, 3, seed + 7)
    I = inten * 0.5 * (0.3 + 0.9 * n) * (0.55 + 0.45 * smoothstep(0.4, 1.8, V))
    rng = np.random.default_rng(seed)
    for _ in range(int(L / 1.0)):
        pu = rng.uniform(0.3, L - 0.3)
        ph = rng.uniform(1.15, 1.42)
        head = ((U - pu) / 0.1) ** 2 + ((V - ph) / 0.12) ** 2 < 1
        body = (np.abs(U - pu) < 0.2 + 0.12 * (ph - V)) & (V < ph - 0.07)
        I = np.where(head | body, I * 0.22, I)
    gap = np.mod(U, 0.046) > 0.03
    e = np.zeros(U.shape + (3,), f32)
    e[gap] = WARM[None, :] * I[gap][:, None]
    a = t.alb[s]
    a[gap] = (0.02, 0.012, 0.008)
    t.emi[s] = e
    for (v0, v1) in [(0.32, 0.37), (1.22, 1.245), (2.15, 2.25)]:
        ss_ = t.fill(0, v0, L, v1, emi=(0, 0, 0))
        grain(t, ss_, (0.04, 0.025, 0.015), 0.3, 0.5, 0.004, seed + 1)
    for (u0, u1) in [(0, 0.13), (L - 0.13, L), (d0 - 0.1, d0), (d1, d1 + 0.1)]:
        ss_ = t.fill(u0, 0, u1, H1, emi=(0, 0, 0))
        grain(t, ss_, (0.045, 0.028, 0.017), 0.3, 0.004, 0.8, seed + 3)
    # 门：磨砂玻璃拉门透出暖光 + 暖帘
    s = t.sl(d0, 0, d1, 2.05)
    U, V = t.uv(s)
    n = fbm(U / 0.06, V / 0.06, 3, seed + 11)
    g = (0.55 + 0.55 * smoothstep(0.2, 2.0, V)) * (0.85 + 0.3 * n)
    t.alb[s] = (0.05, 0.035, 0.02)
    t.emi[s] = (np.array([1.0, 0.42, 0.14], f32) * (inten * 0.26 * g)[..., None]).astype(f32)
    mid = (d0 + d1) / 2
    for (u0, v0, u1, v1) in [(d0, 0, d0 + 0.045, 2.05), (d1 - 0.045, 0, d1, 2.05), (mid - 0.03, 0, mid + 0.03, 2.05),
                             (d0, 0, d1, 0.1), (d0, 0.86, d1, 0.9), (d0, 1.98, d1, 2.05)]:
        t.fill(u0, v0, u1, v1, alb=(0.05, 0.032, 0.02), emi=(0, 0, 0))
    s = t.sl(d0, 0.1, d1, 0.86)
    U, V = t.uv(s)
    bars = np.mod(U - d0, 0.05) < 0.014
    t.emi[s] = np.where(bars[..., None], np.float32(0), t.emi[s])
    t.alb[s] = np.where(bars[..., None], np.array([0.05, 0.032, 0.02], f32), t.alb[s])
    nu0, nu1 = d0 + 0.02, d1 - 0.02
    s = t.sl(nu0, 1.28, nu1, 2.02)
    U, V = t.uv(s)
    npan = max(len(noren), 2)
    pw = (nu1 - nu0) / npan
    slit = (np.mod(U - nu0, pw) < 0.014) & (U > nu0 + 0.02)
    cl = ~slit
    fold = (0.72 + 0.28 * np.sin(2 * np.pi * (U - nu0) / 0.07)) * (0.9 + 0.2 * fbm(U / 0.05, V / 0.4, 2, seed + 12))
    hem = V < 1.28 + 0.02 * (0.5 + 0.5 * np.sin(2 * np.pi * (U - nu0) / 0.07))
    a = t.alb[s]
    a[cl] = np.array([0.025, 0.036, 0.12], f32)[None, :] * fold[cl][:, None]
    e = t.emi[s]
    e[cl] = np.array([0.02, 0.014, 0.016], f32) * inten * fold[cl][:, None]
    a[hem] = t.alb[s][hem]
    if len(noren) == 1:
        t.text(noren, nu0, 1.34, nu1, 1.92, alb=(0.92, 0.9, 0.85), emi=(0.1, 0.08, 0.06))
    else:
        for i, ch in enumerate(noren):
            t.text(ch, nu0 + i * pw + 0.02, 1.36, nu0 + (i + 1) * pw - 0.01, 1.9,
                   alb=(0.92, 0.9, 0.85), emi=(0.1, 0.08, 0.06))
    t.fill(d0 - 0.05, 2.0, d1 + 0.05, 2.045, alb=(0.04, 0.03, 0.02), emi=(0, 0, 0))
    if sign:
        su0 = max(0.25, L - 0.25 - 0.55 * len(sign))
        s = t.fill(su0, 2.3, L - 0.25, 2.66, emi=(0, 0, 0))
        grain(t, s, (0.15, 0.1, 0.055), 0.25, 0.5, 0.004, seed + 2)
        t.text(sign, su0 + 0.08, 2.32, L - 0.33, 2.64, alb=(0.03, 0.02, 0.015), scale=0.8)
    return t


def paint_bar(L, seed, door, window, sign, inten=0.3, res=0.005, H1=2.8):
    t = Tex(L, H1, res)
    s = t.sl(0, 0, L, H1)
    U, V = t.uv(s)
    tile = (np.mod(U + 0.1 * (np.floor(V / 0.1) % 2), 0.2) < 0.006) | (np.mod(V, 0.1) < 0.006)
    n = fbm(U / 0.2, V / 0.1, 2, seed)
    t.alb[s] = (np.array([0.075, 0.07, 0.068], f32) * (0.8 + 0.4 * n)[..., None]
                * np.where(tile, 0.5, 1.0)[..., None]).astype(f32)
    d0, d1 = door
    s = t.sl(d0, 0, d1, 2.0)
    U, V = t.uv(s)
    n = fbm(U / 0.05, V / 0.05, 3, seed + 5)
    g = (0.55 + 0.5 * smoothstep(0.0, 2.0, V)) * (0.85 + 0.3 * n)
    t.alb[s] = (0.05, 0.04, 0.03)
    t.emi[s] = (AMBER * (inten * g)[..., None]).astype(f32)
    mid = (d0 + d1) / 2
    for (u0, v0, u1, v1) in [(d0, 0, d0 + 0.05, 2.0), (d1 - 0.05, 0, d1, 2.0), (mid - 0.03, 0, mid + 0.03, 2.0),
                             (d0, 0, d1, 0.12), (d0, 1.95, d1, 2.06), (d0, 0.9, d1, 0.93), (d0, 1.45, d1, 1.48)]:
        t.fill(u0, v0, u1, v1, alb=(0.05, 0.035, 0.025), emi=(0, 0, 0))
    pu = mid + 0.1
    t.fill(pu, 1.52, pu + 0.13, 1.82, alb=(0.45, 0.32, 0.18), emi=(0, 0, 0))
    t.text('営業中', pu, 1.53, pu + 0.13, 1.81, alb=(0.04, 0.03, 0.02), vertical=True)
    if window:
        w0, w1 = window
        t.fill(w0 - 0.05, 0.9, w1 + 0.05, 1.9, alb=(0.05, 0.035, 0.025), emi=(0, 0, 0))
        s = t.sl(w0, 0.95, w1, 1.85)
        U, V = t.uv(s)
        blind = np.mod(V, 0.012) < 0.004
        lit = AMBER * (inten * 0.9 * (0.7 + 0.3 * fbm(U / 0.3, V / 0.3, 2, seed + 9)))[..., None]
        t.alb[s] = (0.25, 0.2, 0.12)
        t.emi[s] = (lit * np.where(blind, 0.25, 0.8)[..., None]).astype(f32)
    if sign:
        t.fill(0.3, 2.25, L - 0.3, 2.65, alb=(0.8, 0.78, 0.72), emi=(0.55, 0.45, 0.32))
        t.text(sign, 0.4, 2.27, L - 0.4, 2.63, alb=(0.05, 0.03, 0.03), emi=(0.1, 0.02, 0.02), scale=0.8)
    return t


def paint_shutter(L, seed, res=0.006, H1=2.8):
    t = Tex(L, H1, res)
    s = t.sl(0, 0, L, H1)
    U, V = t.uv(s)
    n = fbm(U / 0.3, V / 0.3, 3, seed)
    t.alb[s] = (np.array([0.16, 0.16, 0.155], f32) * (0.8 + 0.4 * n)[..., None]).astype(f32)
    s = t.sl(0.2, 0.0, L - 0.2, 2.35)
    U, V = t.uv(s)
    rib = 0.75 + 0.25 * np.cos(2 * np.pi * V / 0.075)
    dirt = fbm(U / 0.05, V / 1.2, 3, seed + 3)
    t.alb[s] = (np.array([0.30, 0.32, 0.34], f32) * (rib * (0.7 + 0.4 * dirt) * (0.6 + 0.4 * smoothstep(0, 0.8, V)))[..., None]).astype(f32)
    t.fill(0.12, 2.35, L - 0.12, 2.72, alb=(0.22, 0.23, 0.24))
    return t


def paint_upper(L, Hh, seed, style, wins, res=0.008):
    t = Tex(L, Hh, res)
    s = t.sl(0, 0, L, Hh)
    U, V = t.uv(s)
    if style == 'plank':
        grain(t, s, (0.07, 0.045, 0.03), 0.35, 0.6, 0.004, seed)
        t.alb[s] *= np.where(np.mod(V, 0.19) < 0.015, 0.4, 1.0)[..., None].astype(f32)
    elif style == 'plaster':
        n = fbm(U / 0.4, V / 0.4, 4, seed)
        streak = fbm(U / 0.06, V / 2.0, 3, seed + 1)
        t.alb[s] = (np.array([0.19, 0.18, 0.165], f32) * (0.75 + 0.35 * n - 0.5 * np.clip(streak - 0.5, 0, 1))[..., None]).astype(f32)
    else:
        n = fbm(U / 0.4, V / 0.4, 3, seed)
        t.alb[s] = (np.array([0.13, 0.135, 0.14], f32) * (0.85 + 0.3 * n)[..., None]
                    * np.where(np.mod(V, 0.3) < 0.01, 0.6, 1)[..., None]).astype(f32)
    for (u0, u1, v0, v1, kind) in wins:
        t.fill(u0 - 0.05, v0 - 0.05, u1 + 0.05, v1 + 0.05, alb=(0.1, 0.1, 0.1))
        s = t.sl(u0, v0, u1, v1)
        U, V = t.uv(s)
        if kind == 'shoji':
            grid = (np.mod(U - u0, 0.24) < 0.015) | (np.mod(V - v0, 0.3) < 0.015)
            e = np.array([1.0, 0.72, 0.42], f32) * 0.55 * (0.85 + 0.2 * fbm(U / 0.5, V / 0.5, 2, seed + 4))[..., None]
            t.alb[s] = (0.5, 0.45, 0.35)
            t.emi[s] = (e * np.where(grid, 0.12, 1.0)[..., None]).astype(f32)
        elif kind == 'lit':
            curtain = 0.6 + 0.4 * np.cos(2 * np.pi * (U - u0) / 0.09)
            t.alb[s] = (0.3, 0.2, 0.1)
            t.emi[s] = (np.array([1.0, 0.66, 0.38], f32) * 0.55 * curtain[..., None]).astype(f32)
        elif kind == 'tv':
            t.alb[s] = (0.05, 0.05, 0.07)
            t.emi[s] = (np.array([0.35, 0.5, 1.0], f32) * 0.45 * (0.6 + 0.6 * fbm(U / 0.3, V / 0.3, 2, seed + 8))[..., None]).astype(f32)
        else:
            g = smoothstep(v0, v1, V)
            t.alb[s] = (np.array([0.02, 0.025, 0.035], f32)[None, None, :] * (1 + 0.6 * g)[..., None]).astype(f32)
            t.emi[s] = (np.array([0.008, 0.011, 0.02], f32) * g[..., None]).astype(f32)
        mid = (u0 + u1) / 2
        t.fill(mid - 0.015, v0, mid + 0.015, v1, alb=(0.12, 0.12, 0.12), emi=(0, 0, 0))
        s = t.sl(u0 - 0.05, v0 - 0.05, u1 + 0.05, v0 + 0.35)
        U, V = t.uv(s)
        bars = (np.mod(U, 0.06) < 0.012) | (np.abs(V - (v0 + 0.33)) < 0.012)
        t.alb[s] = np.where(bars[..., None], np.array([0.05, 0.05, 0.05], f32), t.alb[s])
        t.emi[s] = np.where(bars[..., None], np.float32(0), t.emi[s])
    return t


def paint_eave(L, depth, seed, res=0.01, base=(0.055, 0.037, 0.025)):
    t = Tex(L, depth, res)
    s = t.sl(0, 0, L, depth)
    U, V = t.uv(s)
    grain(t, s, base, 0.3, 0.5, 0.004, seed)
    t.alb[s] *= np.where(np.mod(U, 0.3) < 0.045, 0.55, 1.0)[..., None].astype(f32)
    return t


def paint_lantern(w, h, text, seed, I=1.8, hang=0.2, res=0.0025, hot=(1.0, 0.2, 0.04), edge=(0.30, 0.012, 0.006)):
    Ht = h + hang
    t = Tex(w, Ht, res, alb=(0.0, 0.0, 0.0), a=0.0)
    s = t.sl(0, 0, w, Ht)
    U, V = t.uv(s)
    x = (U - w / 2) / (w / 2)
    y = (V - h / 2) / (h / 2)
    wy = np.sqrt(np.clip(1 - y * y, 0, 1))
    covb = np.clip((wy - np.abs(x)) * (w / 2) / res + 0.5, 0, 1) * (np.abs(y) <= 0.9)
    xr = np.clip(x / np.maximum(wy, 1e-3), -1, 1)
    lim = np.sqrt(np.clip(1 - xr * xr, 0, 1))
    hot = np.array(hot, f32)
    edge = np.array(edge, f32)
    col = edge + (hot - edge) * (lim ** 6.0)[..., None]
    vert = 1 - 0.35 * y * y
    ph = (y + 0.07 * lim) * 24 / 2
    dd = np.abs(ph - np.round(ph))
    rib = np.exp(-(dd / 0.09) ** 2)
    E = col * (I * vert * (1 - 0.45 * rib))[..., None]
    alb = np.array([0.55, 0.1, 0.05], f32) * np.ones_like(E)
    if text:
        n = len(text)
        tw, th = 300, 480
        img = Image.new('L', (tw, th), 0)
        d = ImageDraw.Draw(img)
        size = int(min(tw, th / n) * 0.92)
        fnt = ImageFont.truetype(FM, size, index=2)
        for i, ch in enumerate(text):
            d.text((tw / 2, (i + 0.5) * th / n), ch, fill=255, font=fnt, anchor='mm')
        mimg = np.asarray(img, f32) / 255.0
        sx = np.arcsin(xr) / (np.pi / 2) * 2.2
        sy = y / 0.64
        cc = (sx + 1) / 2 * (tw - 1)
        rr = (1 - sy) / 2 * (th - 1)
        inside = (np.abs(sx) < 1) & (np.abs(sy) < 1)
        mt = ndimage.map_coordinates(mimg, [rr.ravel(), cc.ravel()], order=1, mode='constant').reshape(x.shape)
        mt = mt * inside
        E = E * (1 - 0.94 * mt)[..., None]
        alb = alb * (1 - mt)[..., None] + np.array([0.02, 0.015, 0.012], f32) * mt[..., None]
    capw = 0.5
    capx = np.clip((capw - np.abs(x)) * (w / 2) / res + 0.5, 0, 1)
    top = capx * ((y > 0.86) & (y < 1.0))
    bot = capx * ((y < -0.86) & (y > -1.0))
    caps = np.maximum(top, bot)
    cap_alb = np.array([0.035, 0.026, 0.022], f32)[None, None, :] * (0.5 + 1.2 * np.clip(1 - np.abs(x) / capw, 0, 1))[..., None]
    wire = ((np.abs(x) * w / 2) < 0.006) & (y >= 0.98)
    a = np.maximum(np.maximum(covb, caps), wire.astype(f32))
    albf = np.where((caps > 0)[..., None] | wire[..., None], cap_alb, alb)
    Ef = np.where((caps > 0)[..., None] | wire[..., None], 0.0, E)
    t.alb[s] = albf.astype(f32)
    t.emi[s] = Ef.astype(f32)
    t.a[s] = a.astype(f32)
    return t


def paint_sign(wu, hv, text, bg_alb, bg_emi, txt_alb, txt_emi, res=0.004, mark=None):
    t = Tex(wu, hv, res, alb=(0.04, 0.04, 0.045))
    s = t.fill(0.025, 0.025, wu - 0.025, hv - 0.025, alb=bg_alb, emi=bg_emi)
    U, V = t.uv(s)
    t.emi[s] *= (0.8 + 0.2 * smoothstep(0, hv, V))[..., None].astype(f32)
    top = hv - 0.06
    if mark is not None:
        s2 = t.sl(0.06, hv - wu + 0.06, wu - 0.06, hv - 0.06)
        U, V = t.uv(s2)
        r = np.hypot(U - wu / 2, V - (hv - wu / 2))
        circ = r < (wu / 2 - 0.08)
        t.emi[s2] = np.where(circ[..., None], np.asarray(mark, f32), t.emi[s2])
        t.alb[s2] = np.where(circ[..., None], np.float32(0.5), t.alb[s2])
        top = hv - wu + 0.04
    t.text(text, 0.05, 0.07, wu - 0.05, top, alb=txt_alb, emi=txt_emi, vertical=True)
    return t


def paint_ac(seed, res=0.004):
    t = Tex(0.8, 0.6, res, alb=(0.46, 0.47, 0.46))
    s = t.sl(0, 0, 0.8, 0.6)
    U, V = t.uv(s)
    r = np.hypot(U - 0.3, V - 0.3)
    ang = np.arctan2(V - 0.3, U - 0.3)
    grill = r < 0.22
    pat = (np.mod(r, 0.025) < 0.006) | (np.mod(ang, np.pi / 2) < 0.03)
    t.alb[s] = np.where(grill[..., None], np.where(pat[..., None], np.float32(0.3), np.float32(0.05)), t.alb[s])
    vent = (U > 0.58) & (U < 0.76) & (np.mod(V, 0.03) < 0.012) & (V > 0.08) & (V < 0.52)
    t.alb[s] = np.where(vent[..., None], np.float32(0.18), t.alb[s])
    n = fbm(U / 0.05, V / 0.8, 3, seed)
    t.alb[s] *= (0.7 + 0.4 * n)[..., None].astype(f32)
    return t


def paint_crate_side(wu, hv, color, res=0.003):
    t = Tex(wu, hv, res, alb=color)
    s = t.sl(0, 0, wu, hv)
    U, V = t.uv(s)
    hole = (np.mod(U, 0.05) > 0.013) & (np.mod(V, 0.05) > 0.013) & (U > 0.03) & (U < wu - 0.03) & (V > 0.03) & (V < hv - 0.07)
    handle = (np.abs(U - wu / 2) < 0.07) & (V > hv - 0.06) & (V < hv - 0.025)
    t.alb[s] = np.where((hole | handle)[..., None], np.array([0.015, 0.013, 0.01], f32), t.alb[s])
    return t


def paint_crate_top(wu, dv, color, res=0.003):
    t = Tex(wu, dv, res, alb=(0.015, 0.013, 0.01))
    s = t.sl(0, 0, wu, dv)
    U, V = t.uv(s)
    cu = np.mod(U, wu / 4) - wu / 8
    cv = np.mod(V, dv / 5) - dv / 10
    r = np.hypot(cu, cv)
    alb = np.where((r < 0.03)[..., None], np.array([0.16, 0.07, 0.02], f32), t.alb[s])
    alb = np.where((r < 0.013)[..., None], np.array([0.55, 0.45, 0.2], f32), alb)
    rim = (U < 0.015) | (U > wu - 0.015) | (V < 0.015) | (V > dv - 0.015)
    alb = np.where(rim[..., None], np.asarray(color, f32), alb)
    t.alb[s] = alb
    return t


def paint_plant(wu, hv, seed, res=0.004):
    t = Tex(wu, hv, res, alb=(0, 0, 0), a=0.0)
    rng = np.random.default_rng(seed)
    s = t.sl(0, 0, wu, hv)
    U, V = t.uv(s)
    ph = 0.3
    xx = np.abs(U - wu / 2)
    pot = (V < ph) & (xx < 0.12 + 0.05 * V / ph)
    alb = np.zeros(U.shape + (3,), f32)
    a = np.zeros(U.shape, f32)
    shade = (0.5 + 0.5 * np.clip(1 - xx / 0.17, 0, 1))
    alb[pot] = (np.array([0.23, 0.1, 0.05], f32)[None, :] * shade[pot][:, None])
    a[pot] = 1
    for _ in range(260):
        cx = wu / 2 + rng.normal(0, 0.13)
        cy = ph + rng.uniform(0.0, 1.0) ** 0.7 * (hv - ph - 0.06)
        ang = rng.uniform(0, np.pi)
        L1 = rng.uniform(0.04, 0.09)
        L2 = L1 * rng.uniform(0.3, 0.5)
        dx = U - cx
        dy = V - cy
        p = dx * np.cos(ang) + dy * np.sin(ang)
        q = -dx * np.sin(ang) + dy * np.cos(ang)
        leaf = (p / L1) ** 2 + (q / L2) ** 2 < 1
        g = rng.uniform(0.5, 1.2)
        col = np.array([0.04, 0.11, 0.035], f32) * g
        alb[leaf] = col
        a[leaf] = 1
    t.alb[s] = alb
    t.a[s] = a
    return t


def paint_vending(seed, res=0.002):
    Wv, Hv = 0.9, 1.83
    t = Tex(Wv, Hv, res, alb=(0.78, 0.8, 0.82))
    rng = np.random.default_rng(seed)
    s = t.sl(0, 0, Wv, Hv)
    U, V = t.uv(s)
    t.alb[s] *= (0.9 + 0.1 * fbm(U / 0.2, V / 0.2, 2, seed))[..., None].astype(f32)
    # 顶部灯箱
    t.fill(0.0, 1.73, Wv, 1.83, alb=(0.1, 0.25, 0.6), emi=(0.25, 0.65, 1.6))
    t.text('のみもの', 0.25, 1.745, 0.65, 1.815, alb=(1, 1, 1), emi=(2.6, 2.7, 2.8), font=FG, idx=0)
    # 展示窗
    u0, u1, v0, v1 = 0.05, 0.85, 1.0, 1.71
    t.fill(u0 - 0.012, v0 - 0.012, u1 + 0.012, v1 + 0.012, alb=(0.55, 0.57, 0.6), emi=(0, 0, 0))
    s = t.sl(u0, v0, u1, v1)
    U, V = t.uv(s)
    t.alb[s] = (0.8, 0.8, 0.8)
    t.emi[s] = (np.array([0.84, 0.95, 1.0], f32) * (3.6 * (0.8 + 0.2 * smoothstep(v0, v1, V)))[..., None]).astype(f32)
    drinks = [
        ('b', (0.55, 0.78, 0.35), (0.1, 0.45, 0.15), (0.1, 0.5, 0.2)),     # green tea
        ('b', (0.78, 0.9, 1.0), (0.15, 0.45, 0.9), (0.2, 0.4, 0.9)),       # water
        ('c', (0.8, 0.05, 0.05), (0.95, 0.95, 0.95), (0.7, 0.7, 0.7)),     # cola
        ('c', (0.14, 0.08, 0.04), (0.8, 0.6, 0.2), (0.7, 0.7, 0.7)),       # coffee
        ('b', (1.0, 0.55, 0.05), (1.0, 0.85, 0.2), (1.0, 0.6, 0.1)),       # orange
        ('b', (0.9, 0.95, 1.0), (0.1, 0.35, 0.85), (0.1, 0.3, 0.8)),       # sports
        ('c', (0.85, 0.7, 0.5), (0.95, 0.9, 0.85), (0.7, 0.7, 0.7)),       # milk tea
        ('b', (1.0, 0.9, 0.2), (0.2, 0.6, 0.2), (0.9, 0.8, 0.1)),          # lemon
        ('c', (0.1, 0.1, 0.1), (1.0, 0.85, 0.1), (0.7, 0.7, 0.7)),         # energy
        ('b', (0.6, 0.85, 0.95), (0.9, 0.3, 0.4), (0.9, 0.9, 0.9)),        # soda
    ]
    rows = [1.49, 1.27, 1.05]
    iw, gp, n = 0.083, 0.013, 8
    st = u0 + ((u1 - u0) - (n * iw + (n - 1) * gp)) / 2
    for ri, vb in enumerate(rows):
        t.fill(u0, vb, u1, vb + 0.042, alb=(0.1, 0.1, 0.12), emi=(0.2, 0.22, 0.26))
        for k in range(n):
            ua = st + k * (iw + gp)
            t.fill(ua + 0.01, vb + 0.024, ua + iw - 0.01, vb + 0.038, alb=(0.9, 0.9, 0.9), emi=(1.8, 1.8, 1.8))
            led = (0.2, 0.7, 3.2) if (ri < 2 or k < 3) else (3.2, 0.35, 0.2)
            t.fill(ua + 0.028, vb + 0.005, ua + iw - 0.028, vb + 0.018, alb=(0.2, 0.2, 0.2), emi=led)
            kind, cb, cl, cc = drinks[rng.integers(len(drinks))]
            ss_ = t.sl(ua, vb + 0.05, ua + iw, vb + 0.21)
            Uu, Vv = t.uv(ss_)
            xq = (Uu - (ua + iw / 2)) / (iw / 2)
            yq = (Vv - (vb + 0.05)) / 0.16
            if kind == 'c':
                hw = np.where(yq < 0.72, 0.78, np.where(yq < 0.76, 0.7, 0.0))
                lab = (yq > 0.2) & (yq < 0.55)
                capm = np.zeros_like(yq, bool)
            else:
                hw = np.where(yq < 0.6, 0.8, np.where(yq < 0.8, 0.8 - (yq - 0.6) / 0.2 * 0.5,
                              np.where(yq < 0.9, 0.3, np.where(yq < 1.0, 0.34, 0.0))))
                lab = (yq > 0.22) & (yq < 0.5)
                capm = (yq >= 0.9)
            inside = np.abs(xq) < hw
            cyl = np.sqrt(np.clip(1 - (xq / np.maximum(hw, 1e-3)) ** 2, 0, 1))
            colr = np.where(lab[..., None], np.asarray(cl, f32), np.asarray(cb, f32))
            colr = np.where(capm[..., None], np.asarray(cc, f32), colr)
            shade = 0.45 + 0.55 * cyl
            spec = np.exp(-((xq / np.maximum(hw, 1e-3) + 0.45) / 0.12) ** 2) * 0.8
            ecol = colr * (1.5 * shade)[..., None] + spec[..., None] * 2.0
            t.emi[ss_] = np.where(inside[..., None], ecol, t.emi[ss_]).astype(f32)
            t.alb[ss_] = np.where(inside[..., None], colr * 0.5, t.alb[ss_]).astype(f32)
    # 下部灯箱广告
    s = t.fill(0.05, 0.47, 0.62, 0.93, alb=(0.2, 0.4, 0.8))
    U, V = t.uv(s)
    gcol = np.array([0.1, 0.35, 1.3], f32) + np.array([0.15, 0.3, 0.5], f32) * smoothstep(0.47, 0.93, V)[..., None]
    wave = np.abs(V - (0.6 + 0.05 * np.sin((U - 0.05) * 14))) < 0.018
    mount = V < 0.52 + 0.14 * np.clip(1 - np.abs(U - 0.34) / 0.2, 0, 1)
    gcol = np.where(mount[..., None], np.array([0.5, 0.9, 1.8], f32), gcol)
    gcol = np.where(wave[..., None], np.array([2.4, 2.5, 2.6], f32), gcol)
    t.emi[s] = gcol.astype(f32)
    t.text('天然水', 0.1, 0.7, 0.57, 0.9, alb=(1, 1, 1), emi=(2.8, 2.9, 3.0), font=FG, idx=0, scale=0.85)
    # 投币区
    t.fill(0.65, 0.47, 0.85, 0.93, alb=(0.42, 0.43, 0.45), emi=(0, 0, 0))
    t.fill(0.69, 0.82, 0.81, 0.88, alb=(0.02, 0.02, 0.02), emi=(0.1, 0.9, 0.2))
    t.text('120', 0.695, 0.823, 0.805, 0.877, alb=(0.02, 0.02, 0.02), emi=(3.0, 0.3, 0.15), font=FG, idx=0, scale=0.9)
    t.fill(0.73, 0.7, 0.77, 0.78, alb=(0.03, 0.03, 0.03), emi=(0, 0, 0))
    t.fill(0.68, 0.6, 0.82, 0.63, alb=(0.03, 0.03, 0.03), emi=(0.05, 0.5, 0.1))
    t.fill(0.72, 0.5, 0.78, 0.56, alb=(0.25, 0.25, 0.27), emi=(0, 0, 0))
    # 取物口
    t.fill(0.06, 0.1, 0.62, 0.42, alb=(0.55, 0.57, 0.6))
    s = t.fill(0.09, 0.13, 0.59, 0.37, alb=(0.02, 0.02, 0.025))
    U, V = t.uv(s)
    t.emi[s] = (np.array([0.05, 0.06, 0.08], f32) * smoothstep(0.13, 0.37, V)[..., None]).astype(f32)
    t.fill(0.0, 0.0, Wv, 0.07, alb=(0.07, 0.07, 0.08), emi=(0, 0, 0))
    return t


def paint_vending_side(seed, res=0.004):
    t = Tex(0.8, 1.83, res, alb=(0.75, 0.77, 0.8))
    s = t.sl(0, 0, 0.8, 1.83)
    U, V = t.uv(s)
    band = np.abs(V - (0.9 + 0.7 * (U - 0.4))) < 0.22
    band2 = np.abs(V - (0.9 + 0.7 * (U - 0.4))) < 0.26
    alb = np.where(band2[..., None], np.array([0.85, 0.87, 0.9], f32), t.alb[s])
    alb = np.where(band[..., None], np.array([0.08, 0.25, 0.65], f32), alb)
    alb = alb * (0.75 + 0.25 * smoothstep(0.0, 0.5, V))[..., None]
    t.alb[s] = alb.astype(f32)
    t.fill(0, 0, 0.8, 0.07, alb=(0.07, 0.07, 0.08))
    return t


def paint_pole(seed, res=0.006):
    t = Tex(0.34, 10.0, res, alb=(0.35, 0.35, 0.34))
    s = t.sl(0, 0, 0.34, 10.0)
    U, V = t.uv(s)
    x = (U - 0.17) / 0.17
    r = 0.17 - 0.012 * V / 10
    inside = np.abs(U - 0.17) < r
    cyl = np.sqrt(np.clip(1 - x * x, 0, 1))
    n = fbm(U / 0.05, V / 0.6, 3, seed)
    alb = np.array([0.33, 0.33, 0.32], f32) * (0.55 + 0.5 * cyl * (0.8 + 0.4 * n))[..., None]
    stripe = (V < 1.8) & (np.mod(V + U * 0.8, 0.3) < 0.15)
    alb = np.where(((V < 1.8) & stripe)[..., None], np.array([0.75, 0.6, 0.05], f32) * (0.5 + 0.5 * cyl)[..., None], alb)
    alb = np.where(((V < 1.8) & ~stripe)[..., None], np.array([0.03, 0.03, 0.03], f32), alb)
    plate = (np.abs(U - 0.17) < 0.07) & (V > 2.3) & (V < 2.7)
    alb = np.where(plate[..., None], np.array([0.7, 0.7, 0.68], f32), alb)
    bolts = (np.abs(U - 0.17) < 0.1) & (np.mod(V, 0.45) < 0.03) & (V > 2.8) & (np.abs(U - 0.17) > 0.07)
    alb = np.where(bolts[..., None], np.float32(0.08), alb)
    t.alb[s] = alb.astype(f32)
    t.a[s] = inside.astype(f32)
    return t


def paint_far(seed):
    t = Tex(24, 16, 0.04, alb=(0.03, 0.03, 0.035))
    rng = np.random.default_rng(seed)
    for i in range(20):
        for j in range(7):
            u = 0.3 + i * 1.2
            v = 4.0 + j * 1.7
            r = rng.random()
            if r < 0.45:
                e = np.array([1.0, 0.75, 0.45]) * rng.uniform(0.6, 1.4)
            elif r < 0.6:
                e = np.array([0.6, 0.8, 1.0]) * rng.uniform(0.5, 1.0)
            else:
                e = np.array([0.0, 0.0, 0.0])
            t.fill(u, v, u + 0.75, v + 1.0, alb=(0.04, 0.04, 0.05), emi=e)
    t.fill(0, 0, 24, 3.6, alb=(0.05, 0.05, 0.05))
    x = 0.5
    while x < 23.5:
        w = rng.uniform(2.0, 4.0)
        c = [np.array([2.4, 2.0, 1.5]), np.array([1.6, 2.1, 2.4]), np.array([2.6, 1.6, 0.9])][rng.integers(3)]
        t.fill(x, 0.2, x + w - 0.3, 3.0, emi=c * rng.uniform(0.35, 0.7))
        x += w
    t.fill(12.6, 4.2, 13.3, 9.6, alb=(0.1, 0.1, 0.1), emi=(2.6, 0.35, 1.5))
    t.text('カラオケ', 12.6, 4.3, 13.3, 9.5, alb=(1, 1, 1), emi=(3, 3, 3), font=FG, idx=0, vertical=True)
    return t


# ----------------------------------------------------------------------------- scene description
def build_scene():
    log('painting textures')
    sc = dict(walls=[], eaves=[], objects=[], lights=[], wires=[])
    WL, WR = -1.5, 1.5
    left = [
        dict(z0=0.0, z1=4.2, kind='izakaya', door=(2.65, 3.45), noren='鳥よし', sign='炭火焼鳥', roof=6.3, up='plank',
             wins=[(0.5, 1.7, 3.7, 4.8, 'shoji'), (2.3, 3.5, 3.7, 4.8, 'dark')]),
        dict(z0=4.2, z1=8.0, kind='bar', door=(0.9, 1.75), window=(2.4, 3.3), sign='スナック雨音', roof=5.6, up='plaster',
             wins=[(0.8, 2.0, 3.5, 4.6, 'lit'), (2.6, 3.4, 3.5, 4.6, 'tv')]),
        dict(z0=8.0, z1=12.5, kind='izakaya', door=(1.8, 2.7), noren='酒', sign='居酒屋まる', roof=7.1, up='plank',
             wins=[(0.6, 1.8, 3.6, 4.7, 'dark'), (2.6, 3.8, 3.6, 4.7, 'shoji'), (1.0, 3.0, 5.2, 6.3, 'tv')]),
        dict(z0=12.5, z1=17.0, kind='shutter', roof=6.2, up='siding', wins=[(1.0, 2.4, 3.6, 4.6, 'dark')]),
        dict(z0=17.0, z1=22.5, kind='izakaya', door=(2.0, 2.9), noren='おでん', sign='おでん処', roof=6.7, up='plank',
             wins=[(0.8, 2.2, 3.6, 4.7, 'shoji'), (3.2, 4.4, 3.6, 4.7, 'lit')]),
        dict(z0=22.5, z1=29.0, kind='bar', door=(1.0, 1.9), window=(3.0, 4.2), sign='BAR', roof=6.0, up='plaster',
             wins=[(1.0, 2.4, 3.5, 4.6, 'lit'), (4.0, 5.4, 3.5, 4.6, 'dark')]),
        dict(z0=29.0, z1=36.0, kind='izakaya', door=(2.5, 3.4), noren='とり', sign='', roof=7.3, up='plank',
             wins=[(1.0, 2.4, 3.6, 4.7, 'shoji'), (4.0, 5.4, 3.6, 4.7, 'dark')]),
        dict(z0=36.0, z1=42.0, kind='shutter', roof=6.4, up='siding', wins=[(1.5, 3.0, 3.6, 4.6, 'lit')]),
    ]
    right = [
        dict(z0=4.8, z1=9.6, kind='bar', door=(2.6, 3.45), window=(0.9, 1.9), sign='BAR灯', roof=6.5, up='siding',
             wins=[(1.0, 2.4, 3.6, 4.6, 'lit'), (3.0, 4.2, 3.6, 4.6, 'shoji')]),
        dict(z0=9.6, z1=14.5, kind='izakaya', door=(2.2, 3.1), noren='やきとり', sign='やきとり', roof=6.0, up='plank',
             wins=[(0.8, 2.0, 3.6, 4.6, 'shoji'), (2.8, 4.2, 3.6, 4.6, 'lit')]),
        dict(z0=14.5, z1=20.0, kind='izakaya', door=(1.5, 2.4), noren='酒', sign='大衆酒場', roof=7.2, up='plaster',
             wins=[(0.6, 1.8, 3.6, 4.6, 'dark'), (3.0, 4.4, 3.6, 4.6, 'shoji'), (1.5, 3.5, 5.4, 6.4, 'lit')]),
        dict(z0=20.0, z1=26.0, kind='shutter', roof=6.3, up='siding', wins=[(2.0, 3.4, 3.6, 4.6, 'dark')]),
        dict(z0=26.0, z1=33.0, kind='izakaya', door=(3.0, 3.9), noren='酒', sign='', roof=6.8, up='plank',
             wins=[(1.0, 2.4, 3.6, 4.7, 'lit'), (4.5, 5.9, 3.6, 4.7, 'shoji')]),
        dict(z0=33.0, z1=42.0, kind='bar', door=(2.0, 2.9), window=(5.0, 6.2), sign='', roof=6.0, up='plaster',
             wins=[(1.0, 2.4, 3.5, 4.6, 'lit')]),
    ]

    def facade_tex(b, seed):
        L = b['z1'] - b['z0']
        res = 0.005 if b['z0'] < 13 else 0.01
        if b['kind'] == 'izakaya':
            return paint_izakaya(L, seed, b['door'], b['noren'], b['sign'], res=res)
        if b['kind'] == 'bar':
            return paint_bar(L, seed, b['door'], b.get('window'), b['sign'], res=res)
        return paint_shutter(L, seed, res=max(res, 0.006))

    def add_building(b, side, seed):
        L = b['z1'] - b['z0']
        X = WL if side < 0 else WR
        if side < 0:
            O = (X, 0, b['z0']); U = (0, 0, 1); N = (1, 0, 0)
        else:
            O = (X, 0, b['z1']); U = (0, 0, -1); N = (-1, 0, 0)
        t1 = facade_tex(b, seed).build()
        sc['walls'].append(dict(O=O, U=U, V=(0, 1, 0), wu=L, hv=2.8, N=N, tex=t1))
        Hup = b['roof'] + 0.3 - 2.8
        t2 = paint_upper(L, Hup, seed + 50, b['up'], [(u0, u1, v0 - 2.8, v1 - 2.8, k) for (u0, u1, v0, v1, k) in b['wins']]).build()
        O2 = (O[0], 2.8, O[2])
        sc['walls'].append(dict(O=O2, U=U, V=(0, 1, 0), wu=L, hv=Hup, N=N, tex=t2))
        # 一楼小屋檐 + 屋顶檐
        for (ya, yb, dep, base, zk) in [(3.02, 2.76, 0.5, (0.055, 0.037, 0.025), 'e1'), (b['roof'] + 0.3, b['roof'] - 0.05, 0.65, (0.04, 0.03, 0.025), 'e2')]:
            et = paint_eave(L, np.hypot(dep, ya - yb), seed + (3 if zk == 'e1' else 4), base=base).build()
            xe = X - side * dep
            if side < 0:
                Oe = (X, ya, b['z0']); Ue = (0, 0, 1)
                Ve = np.array([xe - X, yb - ya, 0.0])
            else:
                Oe = (X, ya, b['z1']); Ue = (0, 0, -1)
                Ve = np.array([xe - X, yb - ya, 0.0])
            ln = np.linalg.norm(Ve)
            Ve = Ve / ln
            Ne = np.cross(Ve, Ue) if side < 0 else np.cross(Ue, Ve)
            if Ne[1] > 0:
                Ne = -Ne
            sc['eaves'].append(dict(z=b['z0'], q=dict(O=Oe, U=Ue, V=tuple(Ve), wu=L, hv=ln, N=tuple(Ne), tex=et)))
            fz = b['z0'] if side < 0 else b['z1']
            sc['eaves'].append(dict(z=b['z0'] - 0.01, q=dict(O=(xe, yb - 0.07, fz), U=Ue, V=(0, 1, 0), wu=L, hv=0.09,
                                                             N=(-side, 0, 0), alb=(0.09, 0.09, 0.1))))
        # 门洞暖光
        if b['kind'] in ('izakaya', 'bar'):
            u = (b['door'][0] + b['door'][1]) / 2
            z = b['z0'] + u if side < 0 else b['z1'] - u
            col = np.array([1.0, 0.66, 0.36]) if b['kind'] == 'izakaya' else np.array([1.0, 0.7, 0.4])
            sc['lights'].append(dict(pos=np.array([X - side * 0.45, 1.3, z]), col=col, I=0.35 if b['kind'] == 'izakaya' else 0.25, r=0.4))

    for i, b in enumerate(left):
        add_building(b, -1, 100 + i * 7)
    for i, b in enumerate(right):
        add_building(b, +1, 300 + i * 7)
    # 右侧近处凹进去的空地（售货机所在）
    nook = paint_upper(4.8, 6.3, 555, 'plank', [(1.2, 2.2, 1.0, 1.8, 'dark'), (1.0, 2.4, 3.7, 4.8, 'dark')]).build()
    sc['walls'].append(dict(O=(2.3, 0, 4.8), U=(0, 0, -1), V=(0, 1, 0), wu=4.8, hv=6.3, N=(-1, 0, 0), tex=nook))
    step = paint_upper(0.8, 6.8, 556, 'plaster', []).build()
    sc['walls'].append(dict(O=(1.5, 0, 4.8), U=(1, 0, 0), V=(0, 1, 0), wu=0.8, hv=6.8, N=(0, 0, -1), tex=step))
    # 远端较高建筑的山墙
    for side, blds in [(-1, left), (1, right)]:
        for a, b in zip(blds[:-1], blds[1:]):
            if b['roof'] > a['roof'] + 0.1:
                X = WL if side < 0 else WR
                ew = paint_upper(5.0, b['roof'] + 0.3, 700 + int(b['z0']), 'siding', []).build()
                if side < 0:
                    sc['walls'].insert(0, dict(O=(X - 5.0, 0, b['z0']), U=(1, 0, 0), V=(0, 1, 0), wu=5.0, hv=b['roof'] + 0.3, N=(0, 0, -1), tex=ew))
                else:
                    sc['walls'].insert(0, dict(O=(X, 0, b['z0']), U=(1, 0, 0), V=(0, 1, 0), wu=5.0, hv=b['roof'] + 0.3, N=(0, 0, -1), tex=ew))

    # 灯笼
    lanterns = [
        (-1, 2.35, '焼', 0.44, 0.70), (-1, 3.55, '鳥', 0.44, 0.70), (-1, 6.5, '酒', 0.38, 0.62),
        (-1, 9.3, 'おでん', 0.36, 0.60), (-1, 11.9, '居酒屋', 0.36, 0.60), (-1, 17.6, '酒', 0.36, 0.6),
        (-1, 21.4, 'おでん', 0.36, 0.6), (-1, 23.3, 'BAR', 0.34, 0.55), (-1, 30.4, '鳥', 0.36, 0.6),
        (-1, 34.8, '酒', 0.36, 0.6), (-1, 38.5, '祭', 0.36, 0.6),
        (1, 5.7, '酒', 0.38, 0.62), (1, 9.0, '灯', 0.36, 0.6), (1, 10.5, 'やきとり', 0.36, 0.6),
        (1, 13.9, '串', 0.36, 0.6), (1, 15.2, '大衆酒場', 0.36, 0.6), (1, 19.2, '酒', 0.36, 0.6),
        (1, 26.8, '酒', 0.36, 0.6), (1, 31.0, '祭', 0.36, 0.6), (1, 34.0, '酒', 0.36, 0.6), (1, 39.6, '鳥', 0.36, 0.6),
    ]
    tcache = {}
    for i, (side, z, txt, w, h) in enumerate(lanterns):
        key = (txt, w, h)
        if key not in tcache:
            tcache[key] = paint_lantern(w, h, txt, 900 + i, hang=0.2).build()
        tex = tcache[key]
        X = side * 1.17
        yb = 2.58 - h
        q = dict(O=(X - w / 2, yb, z), U=(1, 0, 0), V=(0, 1, 0), wu=w, hv=h + 0.2, N=(0, 0, -1), tex=tex)
        sc['objects'].append(dict(z=z, kind='quad', q=q))
        sc['lights'].append(dict(pos=np.array([X, yb + h / 2, z]), col=np.array([1.0, 0.36, 0.12]), I=0.8 * (w / 0.38) ** 2,
                                 r=0.45, eave=side))

    # 立式招牌（与墙垂直，正对镜头）
    sgn = paint_sign(0.46, 1.5, 'スナック雨音', (0.85, 0.83, 0.8), (0.95, 0.88, 0.78), (0.05, 0.02, 0.05), (0.05, 0.01, 0.03),
                     mark=(2.2, 0.15, 0.45)).build()
    edge = Tex(0.12, 1.5, 0.01, alb=(0.7, 0.7, 0.7))
    edge.emi[:] = (0.6, 0.55, 0.5)
    edge.build()
    sc['objects'].append(dict(z=7.7, kind='box', b=(-1.48, -1.02, 2.95, 4.45, 7.7, 7.82),
                              mats=dict(front=dict(tex=sgn), px=dict(tex=edge), bot=dict(alb=(0.1, 0.1, 0.1)))))
    sc['lights'].append(dict(pos=np.array([-1.25, 3.7, 7.6]), col=np.array([1.0, 0.95, 0.9]), I=0.2, r=0.4))
    sgn2 = paint_sign(0.46, 1.5, '居酒屋', (0.75, 0.1, 0.06), (1.6, 0.14, 0.05), (0.95, 0.95, 0.9), (2.0, 1.9, 1.8)).build()
    edge2 = Tex(0.12, 1.5, 0.01, alb=(0.6, 0.1, 0.05))
    edge2.emi[:] = (1.0, 0.09, 0.04)
    edge2.build()
    sc['objects'].append(dict(z=12.1, kind='box', b=(1.02, 1.48, 2.95, 4.45, 12.1, 12.22),
                              mats=dict(front=dict(tex=sgn2), nx=dict(tex=edge2), bot=dict(alb=(0.1, 0.1, 0.1)))))
    sc['lights'].append(dict(pos=np.array([1.25, 3.7, 12.0]), col=np.array([1.0, 0.25, 0.1]), I=0.25, r=0.4))

    # 空调外机
    act = paint_ac(11).build()
    for (side, z0, y0) in [(-1, 5.0, 3.35), (1, 6.6, 3.55), (-1, 13.2, 3.4), (1, 21.0, 3.5)]:
        X = WL if side < 0 else WR
        if side < 0:
            b = (X, X + 0.3, y0, y0 + 0.6, z0, z0 + 0.8)
            mats = dict(px=dict(tex=act), front=dict(alb=(0.3, 0.3, 0.3)), bot=dict(alb=(0.2, 0.2, 0.2)))
        else:
            b = (X - 0.3, X, y0, y0 + 0.6, z0, z0 + 0.8)
            mats = dict(nx=dict(tex=act), front=dict(alb=(0.3, 0.3, 0.3)), bot=dict(alb=(0.2, 0.2, 0.2)))
        sc['objects'].append(dict(z=z0, kind='box', b=b, mats=mats))

    # 啤酒箱
    cs = paint_crate_side(0.45, 0.29, (0.75, 0.55, 0.05)).build()
    cs2 = paint_crate_side(0.42, 0.29, (0.75, 0.55, 0.05)).build()
    ct = paint_crate_top(0.42, 0.45, (0.75, 0.55, 0.05)).build()
    cr = paint_crate_side(0.45, 0.29, (0.6, 0.08, 0.05)).build()
    cr2 = paint_crate_side(0.42, 0.29, (0.6, 0.08, 0.05)).build()
    sc['objects'].append(dict(z=1.75, kind='box', b=(-1.5, -1.08, 0.0, 0.29, 1.75, 2.2),
                              mats=dict(front=dict(tex=cr2), px=dict(tex=cr))))
    sc['objects'].append(dict(z=1.749, kind='box', b=(-1.5, -1.08, 0.29, 0.58, 1.75, 2.2),
                              mats=dict(front=dict(tex=cs2), px=dict(tex=cs), top=dict(tex=ct))))
    # 盆栽
    for (X, z, seed) in [(-1.3, 4.45, 41), (1.3, 9.35, 42), (-1.3, 12.35, 43)]:
        pt = paint_plant(0.5, 0.95, seed).build()
        sc['objects'].append(dict(z=z, kind='quad', q=dict(O=(X - 0.25, 0, z), U=(1, 0, 0), V=(0, 1, 0), wu=0.5, hv=0.95, N=(0, 0, -1), tex=pt)))

    # 电线杆
    pole = paint_pole(5).build()
    PX, PZ = 1.22, 13.3
    sc['objects'].append(dict(z=PZ, kind='quad', q=dict(O=(PX - 0.17, 0, PZ), U=(1, 0, 0), V=(0, 1, 0), wu=0.34, hv=10.0, N=(0, 0, -1), tex=pole)))
    sc['objects'].append(dict(z=PZ - 0.2, kind='box', b=(PX - 0.9, PX + 0.3, 8.1, 8.22, PZ - 0.18, PZ - 0.06),
                              mats=dict(front=dict(alb=(0.2, 0.2, 0.2)), bot=dict(alb=(0.12, 0.12, 0.12)))))
    sc['objects'].append(dict(z=PZ - 0.25, kind='box', b=(PX - 0.55, PX - 0.15, 6.3, 7.1, PZ - 0.45, PZ - 0.1),
                              mats=dict(front=dict(alb=(0.3, 0.31, 0.32)), nx=dict(alb=(0.25, 0.26, 0.27)), bot=dict(alb=(0.2, 0.2, 0.2)))))
    lamp_em = (2.4, 2.25, 2.0)
    sc['objects'].append(dict(z=PZ - 0.3, kind='box', b=(PX - 0.75, PX - 0.15, 4.35, 4.45, PZ - 0.2, PZ - 0.05),
                              mats=dict(front=dict(alb=(0.25, 0.25, 0.25)), bot=dict(alb=(0.9, 0.9, 0.9), emi=lamp_em))))
    sc['lights'].append(dict(pos=np.array([PX - 0.45, 4.3, PZ - 0.12]), col=np.array([0.95, 0.9, 0.8]), I=1.1, r=0.3))

    # 自动售货机
    vf = paint_vending(7).build()
    vs = paint_vending_side(8).build()
    VX0, VX1, VZ0, VZ1 = 1.38, 2.28, 3.95, 4.75
    sc['objects'].append(dict(z=VZ0, kind='box', b=(VX0, VX1, 0.0, 1.83, VZ0, VZ1),
                              mats=dict(front=dict(tex=vf), nx=dict(tex=vs), top=dict(alb=(0.5, 0.5, 0.52)))))
    for iu in range(3):
        for iv in range(3):
            sc['lights'].append(dict(pos=np.array([VX0 + 0.2 + 0.25 * iu, 1.1 + 0.25 * iv, VZ0 - 0.04]),
                                     col=np.array([0.78, 0.9, 1.0]), I=0.6, r=0.25, dir=np.array([0.0, 0.0, -1.0])))
    sc['lights'].append(dict(pos=np.array([VX0 + 0.3, 0.7, VZ0 - 0.04]), col=np.array([0.3, 0.55, 1.0]), I=0.25, r=0.2, dir=np.array([0.0, 0.0, -1.0])))

    # 远处街口
    far = paint_far(12).build()
    sc['far'] = dict(O=(-12, 0, 52.0), U=(1, 0, 0), V=(0, 1, 0), wu=24, hv=16, N=(0, 0, -1), tex=far)
    sc['lights'].append(dict(pos=np.array([0.0, 5.0, 47.0]), col=np.array([1.0, 0.75, 0.5]), I=28.0, r=1.0))

    # 电线（悬链线）
    def cat(A, B, sag, n=40):
        A = np.asarray(A, float)
        B = np.asarray(B, float)
        tt = np.linspace(0, 1, n)[:, None]
        P = A + (B - A) * tt
        P[:, 1] -= sag * 4 * tt[:, 0] * (1 - tt[:, 0])
        return P
    top = np.array([PX, 8.2, PZ - 0.12])
    for dy in (0.0, -0.35, 0.3):
        sc['wires'].append(cat(top + [0.2, dy, 0], (-1.5, 6.3 + dy, 8.2), 0.5))
        sc['wires'].append(cat(top + [0.1, dy, 0], (0.4, 7.4 + dy, -1.0), 0.9))
        sc['wires'].append(cat(top + [0.2, dy, 0], (1.4, 7.8 + dy, 34.0), 1.2))
    sc['wires'].append(cat(top, (-1.5, 6.9, 18.5), 0.4))
    sc['wires'].append(cat(top + [0, -0.6, 0], (1.5, 6.0, 5.2), 0.35))
    sc['wires'].append(cat((-1.5, 6.1, 4.3), (1.5, 6.4, 6.0), 0.3))
    sc['wires'].append(cat((-1.5, 7.2, 22.6), (1.5, 6.6, 20.2), 0.4))
    sc['wires'].append(cat((-1.5, 6.8, 29.2), (1.5, 6.9, 26.2), 0.3))
    return sc


# ----------------------------------------------------------------------------- pass rendering
def draw_sky(ps):
    yy = (np.arange(H, dtype=np.float64) + 0.5)[:, None]
    xx = (np.arange(W, dtype=np.float64) + 0.5)[None, :]
    dx = (xx - CX) / F
    dy = (CY - yy) / F
    el = ps.s * dy / np.sqrt(dx * dx + dy * dy + 1)
    k = np.clip(el / 0.8, 0, 1)
    top = np.array([0.006, 0.010, 0.026])
    hor = np.array([0.05, 0.04, 0.065])
    col = hor + (top - hor) * (k ** 0.6)[..., None]
    n = fbm(dx * 2.5 / (np.abs(el) + 0.25), 1.5 / (np.abs(el) + 0.25), 4, 5)
    col = col * (0.7 + 0.7 * n)[..., None]
    m = (el > 0)
    ps.emi[:] = (col * m[..., None]).astype(f32)


ROWS_RNG = np.random.default_rng(101)
ROWB = np.concatenate([[0.0], np.cumsum(ROWS_RNG.uniform(0.22, 0.42, 500))])
ROWL = ROWS_RNG.uniform(0.3, 0.62, 501)
ROWO = ROWS_RNG.uniform(0, 1, 501) * ROWL


RIPPLES = [(-1.02, 2.9, 0.1), (-1.0, 5.6, 0.18), (-0.98, 7.3, 0.07), (1.0, 6.3, 0.14), (1.02, 10.3, 0.1),
           (-1.0, 10.0, 0.16), (0.98, 8.1, 0.2), (-1.01, 3.6, 0.22), (0.99, 5.2, 0.09)]


def draw_ground(ps, zmax=52.0):
    y0 = int(np.floor(CY)) + 1
    ys = np.arange(y0, H) + 0.5
    xs = np.arange(W) + 0.5
    acc_alb = 0
    acc_k = 0
    acc_r = 0
    acc_oy = 0
    acc_ox = 0
    acc_cov = 0
    subs = [(-0.25, -0.25), (0.25, -0.25), (-0.25, 0.25), (0.25, 0.25)]
    for (ox, oy) in subs:
        DX = ((xs + ox - CX) / F)[None, :]
        DY = ((CY - (ys + oy)) / F)[:, None]
        t = CAM[1] / (-DY)
        Z = t + 0 * DX
        X = CAM[0] + t * DX
        fpX = (t / F) * 0.5 + 0 * DX
        fpZ = (t * t / (CAM[1] * F)) * 0.5 + 0 * DX
        ri = np.clip(np.searchsorted(ROWB, Z) - 1, 0, len(ROWB) - 2)
        z0 = ROWB[ri]
        z1 = ROWB[ri + 1]
        dz = np.minimum(Z - z0, z1 - Z)
        Lr = ROWL[ri]
        o = ROWO[ri]
        j0 = np.floor((X - o) / Lr)
        J0 = (_hash(ri, j0.astype(np.int64), 91) - 0.5) * 0.5 * Lr
        J1 = (_hash(ri, (j0 + 1).astype(np.int64), 91) - 0.5) * 0.5 * Lr
        b0 = o + j0 * Lr + J0
        b1 = o + (j0 + 1) * Lr + J1
        sj = j0 - (X < b0) + (X >= b1)
        dxx = np.minimum(np.abs(X - b0), np.abs(X - b1))
        g = 0.0075
        gx = np.clip((g - dxx) / np.maximum(fpX, 1e-5) + 0.5, 0, 1)
        gzs = np.clip((g - dz) / np.maximum(fpZ, 1e-5) + 0.5, 0, 1)
        wm = smoothstep(0.04, 0.2, fpZ)
        gz = gzs * (1 - wm) + (2 * g / 0.32) * wm
        grout = np.maximum(gx, gz)
        h1 = _hash(ri, sj.astype(np.int64), 77)
        h2 = _hash(ri, sj.astype(np.int64), 78)
        h3 = _hash(ri, sj.astype(np.int64), 79)
        h4 = _hash(ri, sj.astype(np.int64), 80)
        h5 = _hash(ri, sj.astype(np.int64), 81)
        famp = np.clip(1 - fpZ / 0.05, 0, 1)
        speck = vnoise(X / 0.012, Z / 0.012, 5)
        speck2 = vnoise(X / 0.05 + 7 * h2, Z / 0.05, 9)
        mott = fbm(X / 0.18 + 13 * h1, Z / 0.18, 3, 6)
        dedge = np.minimum(dxx, dz)
        bev = np.clip(1 - dedge / 0.03, 0, 1) * np.clip(1 - fpZ / 0.06, 0, 1)
        val = 0.07 * (0.45 + 1.1 * h1) * (0.7 + 0.6 * mott) * (1 + famp * (0.7 * (speck - 0.5) + 0.4 * (speck2 - 0.5)))
        tint = np.stack([1 + 0.12 * (h2 - 0.5), np.ones_like(h2), 1 - 0.12 * (h2 - 0.5)], -1)
        wet = np.clip(0.55 + 0.45 * h3 + 0.35 * (fbm(X / 0.6, Z / 0.9, 3, 33) - 0.5), 0, 1)
        alb = val[..., None] * tint * (1.25 - 0.5 * wet)[..., None] * (1 - 0.35 * bev)[..., None]
        alb = alb * (1 - grout[..., None]) + 0.01 * grout[..., None]
        pn = (fbm(X / 0.9 + 3.1, Z / 1.5, 4, 21) + 0.16 * (h2 - 0.5) + 0.06 * np.exp(-(X - 0.1) ** 2 / 0.6)
              + 0.05 * np.exp(-(np.abs(X) - 1.0) ** 2 / 0.012) * (fbm(X / 0.3, Z / 0.5, 2, 44) > 0.45))
        pth = 0.525 + 0.07 * smoothstep(4.5, 1.8, Z)
        puddle = smoothstep(pth, pth + 0.03, pn)
        alb = alb * (1 - 0.55 * puddle[..., None])
        dn = np.sqrt(DX * DX + DY * DY + 1)
        cosT = (-DY) / dn
        fres = 0.02 + 0.98 * (1 - cosT) ** 5
        k_st = (0.05 + 0.12 * wet + 0.6 * fres) * (1 - 0.5 * bev)
        k_pd = 0.25 + 0.72 * fres
        k = k_st * (1 - puddle) + k_pd * puddle
        k = np.maximum(k, grout * 0.8 * k_pd)
        rough = (1 - puddle) * (1 - 0.5 * grout) * (0.75 + 0.25 * (1 - wet))
        flat = (1 - puddle)
        wob = vnoise(X / 0.12, Z / 0.25, 55) - 0.5
        offy = (h4 - 0.5) * 16.0 / np.maximum(Z, 1.0) * flat
        offx = (h5 - 0.5) * 6.0 / np.maximum(Z, 1.0) * flat + 5.0 * wob / np.maximum(Z, 1.0) * puddle
        for (xc, zc, R0) in RIPPLES:
            dXr = X - xc
            dZr = Z - zc
            rr_ = np.sqrt(dXr * dXr + dZr * dZr) + 1e-6
            env = np.exp(-((rr_ - R0) / (0.3 * R0 + 0.015)) ** 2) * (rr_ < R0 + 0.08)
            wv = np.sin(2 * np.pi * (rr_ - R0) / 0.022) * env * np.clip(1 - fpZ / 0.03, 0, 1)
            offx = offx + 5.0 * wv * dXr / rr_
            offy = offy - 3.0 * wv * dZr / rr_
            k = k + 0.12 * env * np.clip(wv, 0, None)
        cov = (Z < zmax).astype(np.float64)
        acc_alb = acc_alb + alb * cov[..., None]
        acc_k = acc_k + k * cov
        acc_r = acc_r + rough * cov
        acc_oy = acc_oy + offy * cov
        acc_ox = acc_ox + offx * cov
        acc_cov = acc_cov + cov
    n = len(subs)
    cov = acc_cov / n
    alb = acc_alb / n
    kk = acc_k / np.maximum(acc_cov, 1e-9)
    rr = acc_r / np.maximum(acc_cov, 1e-9)
    ps.goy[y0:H] = acc_oy / np.maximum(acc_cov, 1e-9)
    ps.gox[y0:H] = acc_ox / np.maximum(acc_cov, 1e-9)
    DX = ((xs - CX) / F)[None, :]
    DY = ((CY - ys) / F)[:, None]
    t = CAM[1] / (-DY)
    Z = t + 0 * DX
    X = CAM[0] + t * DX
    wr = np.where(Z < 4.8, 2.3, 1.5)
    ao = (1 - 0.55 * np.exp(-np.maximum(X + 1.5, 0) / 0.3)) * (1 - 0.55 * np.exp(-np.maximum(wr - X, 0) / 0.3))
    P = np.stack([X, np.zeros_like(X), Z], -1)
    N = np.broadcast_to(np.array([0, 1, 0], f32), P.shape)
    dist = t * np.sqrt(DX * DX + DY * DY + 1)
    sl = (slice(y0, H), slice(0, W))
    ps.blend(sl, cov.astype(f32), alb.astype(f32), np.zeros(alb.shape, f32), P.astype(f32), N, dist.astype(f32), ao.astype(f32))
    ps.G[sl] = cov
    ps.gk[sl] = kk
    ps.grough[sl] = rr
    ps.gX[sl] = X
    ps.gZ[sl] = Z


def draw_wire(ps, P3, width=0.014):
    Pc = P3[P3[:, 2] > 0.3]
    if len(Pc) < 2:
        return
    xs = CX + F * (Pc[:, 0] - CAM[0]) / Pc[:, 2]
    ys = CY - F * (Pc[:, 1] - CAM[1]) / Pc[:, 2]
    wpx = np.maximum(F * width / Pc[:, 2], 0.9)
    for i in range(len(Pc) - 1):
        a = np.array([xs[i], ys[i]])
        b = np.array([xs[i + 1], ys[i + 1]])
        d = b - a
        ln = np.hypot(*d)
        if ln < 1e-6:
            continue
        nrm = np.array([-d[1], d[0]]) / ln
        ext = d / ln * 0.5
        w0 = wpx[i] / 2
        w1 = wpx[i + 1] / 2
        quad = np.array([a - ext + nrm * w0, b + ext + nrm * w1, b + ext - nrm * w1, a - ext - nrm * w0])
        r = poly_cov(quad[:, 0], quad[:, 1], 4)
        if r is None:
            continue
        m, y0, x0 = r
        h, w = m.shape
        sl = (slice(y0, y0 + h), slice(x0, x0 + w))
        ps.wire[sl] = np.maximum(ps.wire[sl], m)


def render_pass(ps, sc):
    draw_sky(ps)
    draw_quad(ps, **sc['far'])
    if not ps.mirror:
        draw_ground(ps)
    for q in sc['walls']:
        draw_quad(ps, **q)
    for e in sorted(sc['eaves'], key=lambda e: -e['z']):
        draw_quad(ps, **e['q'])
    for ob in sorted(sc['objects'], key=lambda o: -o['z']):
        if ob['kind'] == 'quad':
            draw_quad(ps, **ob['q'])
        else:
            x0, x1, y0, y1, z0, z1 = ob['b']
            draw_box(ps, x0, x1, y0, y1, z0, z1, ob['mats'])
    if not ps.mirror:
        for wp in sc['wires']:
            draw_wire(ps, wp)


def shade(ps, lights, amb=np.array([0.012, 0.016, 0.028], f32)):
    P = ps.P
    N = ps.N
    Lsum = np.zeros((H, W, 3), f32)
    up = np.clip(N[..., 1], -1, 1)
    Lsum += amb[None, None, :] * (0.55 + 0.45 * up)[..., None]
    for L in lights:
        v = L['pos'].astype(f32)[None, None, :] - P
        d2 = np.einsum('ijk,ijk->ij', v, v)
        inv = 1.0 / np.sqrt(d2 + 1e-6)
        ndl = np.clip(np.einsum('ijk,ijk->ij', N, v) * inv, 0, None)
        att = L['I'] / (d2 + L['r'] ** 2)
        if 'dir' in L:
            att = att * np.clip(-(v @ L['dir'].astype(f32)) * inv, 0, None)
        if 'eave' in L:
            side = L['eave']
            same = (np.sign(P[..., 0]) == side) & (np.abs(P[..., 0]) > 1.05) & (P[..., 1] > 2.95)
            att = np.where(same, att * 0.05, att)
        Lsum += (ndl * att)[..., None] * L['col'].astype(f32)[None, None, :]
    C = ps.alb * Lsum * ps.ao[..., None] + ps.emi
    # 高度雾（雨后湿气贴地更浓）
    dens = (1 / 32.0) * (1 + 1.3 * np.exp(-np.maximum(P[..., 1], 0) / 1.2))
    T = np.exp(-ps.dist * dens)
    fog = np.array([0.02, 0.022, 0.036], f32)
    C = C * T[..., None] + fog * (1 - T)[..., None]
    return C.astype(f32)


def aces(x):
    return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def main():
    sc = build_scene()
    log('normal pass')
    pn = Pass(False)
    render_pass(pn, sc)
    log('mirror pass')
    pm = Pass(True)
    render_pass(pm, sc)
    log('shading')
    Cn = shade(pn, sc['lights'])
    Cm = shade(pm, sc['lights'])
    log('reflections')
    Rs = ndimage.gaussian_filter(Cm, sigma=(1.3, 1.1, 0))
    R1 = ndimage.gaussian_filter(Cm, sigma=(10, 1.8, 0))
    R2 = ndimage.gaussian_filter(Cm, sigma=(34, 4.0, 0))
    rough = pn.grough[..., None]
    Rmix = Rs * (1 - rough) + (0.65 * R1 + 0.35 * R2) * rough
    yy, xx = np.mgrid[0:H, 0:W].astype(f32)
    cy_ = yy + pn.goy
    cx_ = xx + pn.gox
    Rmix = np.stack([ndimage.map_coordinates(Rmix[..., c], [cy_, cx_], order=1, mode='nearest') for c in range(3)], -1)
    k = (pn.G * pn.gk)[..., None]
    C = Cn * (1 - 0.5 * k) + k * Rmix
    # 电线
    wT = np.exp(-np.linalg.norm(pn.P, axis=-1) / 60.0)
    wcol = np.array([0.004, 0.004, 0.006], f32)
    C = C * (1 - pn.wire[..., None]) + pn.wire[..., None] * wcol
    log('bloom + tonemap')
    exposure = 1.25
    Ce = C * exposure
    lum = Ce @ np.array([0.2126, 0.7152, 0.0722], f32)
    bright = Ce * np.clip((lum - 0.3) / np.maximum(lum, 1e-6), 0, 1)[..., None]
    bloom = np.zeros_like(Ce)
    for sgm, wgt in [(2.0, 0.12), (6, 0.16), (16, 0.16), (42, 0.13), (100, 0.08)]:
        bloom += wgt * ndimage.gaussian_filter(bright, sigma=(sgm, sgm, 0))
    Ce = Ce + bloom
    lum = Ce @ np.array([0.2126, 0.7152, 0.0722], f32)
    Tl = aces(lum)
    C_hue = Ce * (Tl / np.maximum(lum, 1e-6))[..., None]
    Ct = 0.55 * np.clip(C_hue, 0, 1) + 0.45 * aces(Ce)
    yy, xx = np.mgrid[0:H, 0:W]
    r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    Ct = Ct * (1 - 0.28 * np.clip(r2 / 2, 0, 1))[..., None]
    srgb = np.clip(Ct, 0, 1) ** (1 / 2.2)
    rng = np.random.default_rng(2026)
    srgb = srgb + rng.normal(0, 0.012, srgb.shape)
    img = Image.fromarray((np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8))
    out = os.path.join(OUT, 'final.png')
    img.save(out)
    log('saved', out)


if __name__ == '__main__':
    main()
