#!/usr/bin/env python3
"""A07 海边放风筝的小女孩。

纯代码绘制（numpy + Pillow + scipy），不读取任何图片文件：
- 针孔相机几何：地平线、海面、湿沙、干沙都按透视算出世界坐标 (X, Z)，再做程序化着色；
- 天空、云、太阳、远山、海鸥画成一张天空层，湿沙和海面按镜面关系翻转它得到倒影；
- 小女孩用 Catmull-Rom 样条轮廓的多边形逐个部件画（腿、裙子、手臂、头发、草帽），
  用“模糊遮罩的梯度”当法线做体积明暗，用“朝太阳方向平移遮罩再相减”做逆光轮廓光；
- 她的倒影、投在沙上的长影子、风筝（及其倒影）、风筝线都按同一相机几何计算。
运行：python3 draw.py → final.png（固定随机种子）
"""
import os
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

OUT = os.path.dirname(os.path.abspath(__file__))
W, H = 1536, 1024
HOR = 540.0            # 地平线（相机水平，视高 EYE）
F = 1400.0
EYE = 1.1
CXI = W / 2
SUNX, SUNY = 1262.0, 468.0
f32 = np.float32


# ----------------------------------------------------------------------------- utils
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


def ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def lin(c):
    return np.asarray(c, np.float64) ** 2.2


def mix(a, b, t):
    t = np.asarray(t, float)
    return np.asarray(a) * (1 - t[..., None]) + np.asarray(b) * t[..., None]


YY, XX = np.mgrid[0:H, 0:W].astype(np.float64) + 0.5


def poly_mask(pts, ss_=4):
    pts = np.asarray(pts, float)
    x0 = int(max(np.floor(pts[:, 0].min()) - 2, 0))
    x1 = int(min(np.ceil(pts[:, 0].max()) + 2, W))
    y0 = int(max(np.floor(pts[:, 1].min()) - 2, 0))
    y1 = int(min(np.ceil(pts[:, 1].max()) + 2, H))
    M = np.zeros((H, W), np.float64)
    if x1 <= x0 or y1 <= y0:
        return M
    img = Image.new('L', ((x1 - x0) * ss_, (y1 - y0) * ss_), 0)
    ImageDraw.Draw(img).polygon([((x - x0) * ss_ - 0.5, (y - y0) * ss_ - 0.5) for x, y in pts], fill=255)
    m = np.asarray(img, np.float64).reshape(y1 - y0, ss_, x1 - x0, ss_).mean((1, 3)) / 255.0
    M[y0:y1, x0:x1] = m
    return M


def ellipse_pts(cx, cy, rx, ry, ang=0.0, n=64):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = rx * np.cos(t)
    y = ry * np.sin(t)
    ca, sa = np.cos(ang), np.sin(ang)
    return np.stack([cx + x * ca - y * sa, cy + x * sa + y * ca], 1)


def catmull(P, closed=True, n=10):
    P = np.asarray(P, float)
    if closed:
        E = np.vstack([P[-1], P, P[0], P[1]])
    else:
        E = np.vstack([P[0], P, P[-1]])
    out = []
    for i in range(1, len(E) - 2):
        p0, p1, p2, p3 = E[i - 1], E[i], E[i + 1], E[i + 2]
        for t in np.linspace(0, 1, n, endpoint=False):
            t2 = t * t
            t3 = t2 * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1])
    return np.array(out)


def tube(C, hw, n=8):
    """沿中心线（样条）按半宽生成带圆头的多边形。"""
    C = np.asarray(C, float)
    hw = np.asarray(hw, float)
    P = catmull(C, closed=False, n=n)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(C, axis=0).T))]
    segP = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    r = np.interp(segP / segP[-1] * seg[-1], seg, hw)
    T = np.gradient(P, axis=0)
    T /= np.hypot(T[:, 0], T[:, 1])[:, None] + 1e-9
    Nn = np.stack([-T[:, 1], T[:, 0]], 1)
    L = P + Nn * r[:, None]
    R = P - Nn * r[:, None]
    a_end = np.arctan2(T[-1, 1], T[-1, 0])
    a_st = np.arctan2(T[0, 1], T[0, 0])
    cap_e = [P[-1] + r[-1] * np.array([np.cos(a_end + a), np.sin(a_end + a)]) for a in np.linspace(np.pi / 2, -np.pi / 2, 9)]
    cap_s = [P[0] + r[0] * np.array([np.cos(a_st + a), np.sin(a_st + a)]) for a in np.linspace(-np.pi / 2, -3 * np.pi / 2, 9)]
    return np.vstack([L, cap_e, R[::-1], cap_s])


# ----------------------------------------------------------------------------- sky layer
def sky_layer():
    t = np.clip(YY / HOR, 0, 1.0)
    stops = [(0.0, (0.26, 0.40, 0.69)), (0.42, (0.52, 0.58, 0.80)), (0.72, (0.86, 0.73, 0.76)),
             (0.9, (1.0, 0.80, 0.64)), (1.0, (1.0, 0.87, 0.68))]
    S = np.zeros((H, W, 3))
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        m = (t >= t0) & (t <= t1)
        u = ((t - t0) / (t1 - t0))[m][:, None]
        S[m] = lin(c0) * (1 - u) + lin(c1) * u
    d = np.hypot(XX - SUNX, (YY - SUNY) * 1.25)
    glow = 0.55 * np.exp(-(d / 70) ** 2) + 0.4 * np.exp(-(d / 240) ** 2) + 0.18 * np.exp(-(d / 620) ** 2)
    S += glow[..., None] * lin((1.0, 0.8, 0.52))
    # 云：低层长条云 + 中层积云，按朝太阳方向的密度差打光
    lx, ly = SUNX - XX, SUNY - YY
    ln = np.hypot(lx, ly) + 1e-6
    lx, ly = lx / ln, ly / ln
    D1 = fbm(XX / 330, YY / 26, 5, 11)
    D1s = fbm((XX + 16 * lx) / 330, (YY + 16 * ly) / 26, 5, 11)
    c1 = ss(0.53, 0.68, D1) * ss(405, 440, YY) * ss(528, 492, YY) * 0.85
    D2 = fbm(XX / 240, YY / 90, 5, 12) + 0.05 * np.sin(XX / 300)
    D2s = fbm((XX + 22 * lx) / 240, (YY + 22 * ly) / 90, 5, 12) + 0.05 * np.sin((XX + 22 * lx) / 300)
    c2 = ss(0.57, 0.72, D2) * ss(70, 150, YY) * ss(370, 290, YY)
    for c, D, Ds in [(c2, D2, D2s), (c1, D1, D1s)]:
        lit = np.clip(0.45 + 7.0 * (D - Ds), 0, 1)
        near = np.exp(-(d / 420) ** 2)
        shadow = lin((0.70, 0.64, 0.76))
        litc = lin((1.0, 0.80, 0.66)) * (1 + 0.8 * near)[..., None]
        col = shadow * (1 - lit[..., None]) + litc * lit[..., None]
        edge = np.clip(c * (1 - c) * 4, 0, 1) * near
        col = col + edge[..., None] * lin((1.0, 0.85, 0.6)) * 0.8
        S = S * (1 - c[..., None]) + col * c[..., None]
    # 太阳
    ds = np.hypot(XX - SUNX, YY - SUNY)
    disc = ss(27.0, 23.5, ds)
    S = S * (1 - disc[..., None]) + disc[..., None] * np.array([3.2, 2.9, 2.3])
    # 远处岬角与帆船
    xs = np.arange(W) + 0.5
    hump = 34 * np.exp(-((xs - 150) / 190) ** 2) + 16 * np.exp(-((xs - 360) / 90) ** 2)
    top = HOR - hump - 5 * (fbm(xs / 25, np.zeros_like(xs), 3, 5) - 0.5) * (hump > 3)
    head = (YY < HOR + 0.5) & (YY >= top[None, :]) & (hump[None, :] > 1.5)
    hc = lin((0.58, 0.57, 0.70)) * (1 - 0.15 * ss(HOR - 40, HOR, YY))[..., None] + lin((0.85, 0.75, 0.72)) * 0.15 * ss(HOR - 40, HOR, YY)[..., None]
    edgeAA = np.clip(YY - top[None, :] + 0.5, 0, 1) * head
    S = S * (1 - edgeAA[..., None]) + hc * edgeAA[..., None]
    sail = poly_mask([(702, 519), (702, 536), (712, 536)])
    hull = poly_mask([(696, 536.5), (714, 536.5), (711, 539.5), (699, 539.5)])
    S = S * (1 - sail[..., None]) + sail[..., None] * lin((0.98, 0.9, 0.85)) * 1.1
    S = S * (1 - hull[..., None]) + hull[..., None] * lin((0.35, 0.3, 0.38))
    # 海鸥
    img = Image.new('L', (W * 4, H * 4), 0)
    dr = ImageDraw.Draw(img)
    for (gx, gy, s, flap) in [(236, 180, 17, 0.35), (284, 214, 12, 0.5), (905, 128, 10, 0.3), (330, 162, 8, 0.45)]:
        for sgn in (-1, 1):
            pts = []
            for u in np.linspace(0, 1, 16):
                x = gx + sgn * u * s
                y = gy - np.sin(u * np.pi) * s * flap + u * u * s * 0.12
                pts.append((x * 4, y * 4))
            dr.line(pts, fill=255, width=int(max(3, s * 0.35)), joint='curve')
    gm = np.asarray(img, np.float64).reshape(H, 4, W, 4).mean((1, 3)) / 255
    S = S * (1 - gm[..., None]) + gm[..., None] * lin((0.24, 0.22, 0.3))
    return S


# ----------------------------------------------------------------------------- girl
FX, FY = 470.0, 862.0
ZG = EYE * F / (FY - HOR)
SCALE = (1.13 * F / ZG) / 380.0
XG = (FX - CXI) * ZG / F


def T(pts):
    pts = np.asarray(pts, float)
    return np.stack([FX + SCALE * pts[:, 0], FY - SCALE * pts[:, 1]], 1)


def TH(pts, k=1.16, pivot=(2.0, 300.0)):
    """头部（头发、草帽）整体放大，让比例更像幼儿。"""
    pts = np.asarray(pts, float)
    q = np.stack([pivot[0] + (pts[:, 0] - pivot[0]) * k, pivot[1] + (pts[:, 1] - pivot[1]) * k], 1)
    return T(q)


LSUN = np.array([0.95, -0.31])


def shade_part(M, base, sigma, fill=(0.47, 0.43, 0.52), key=(1.05, 0.82, 0.55), rim=(2.9, 1.95, 1.05), rim_w=3.0,
               tex=None):
    base = lin(base)
    if tex is not None:
        base = base * tex[..., None]
    Mb = ndimage.gaussian_filter(M, sigma)
    gy, gx = np.gradient(Mb)
    gn = np.hypot(gx, gy) + 1e-9
    strength = np.clip(gn * sigma * 2.2, 0, 1)
    ndl = (-gx / gn * LSUN[0] - gy / gn * LSUN[1]) * strength
    lam = np.clip(ndl, 0, 1) ** 0.8
    col = base * (np.array(fill) + np.array(key) * lam[..., None])
    sx = int(round(rim_w))
    Ms = np.roll(np.roll(M, -sx, axis=1), max(1, sx // 3), axis=0)
    rm = ndimage.gaussian_filter(np.clip(M - Ms, 0, 1), 0.9)
    Ms2 = np.roll(np.roll(M, -2 * sx, axis=1), max(1, sx // 2), axis=0)
    rm2 = ndimage.gaussian_filter(np.clip(M - Ms2, 0, 1), 1.5) * 0.35
    col = col + (rm + rm2)[..., None] * np.array(rim) * 1.15 * (0.35 + 0.65 * base)
    return col


def girl_layer():
    rgb = np.zeros((H, W, 3))
    A = np.zeros((H, W))

    def put(M, col):
        nonlocal rgb, A
        rgb = rgb * (1 - M[..., None]) + col * M[..., None]
        A = A * (1 - M) + M

    SKIN = (0.93, 0.73, 0.61)
    DRESS = (0.92, 0.40, 0.36)
    HAIR = (0.30, 0.19, 0.12)
    STRAW = (0.93, 0.80, 0.55)
    RIB = (0.80, 0.16, 0.18)
    # 腿（略内收的膝盖、小腿肚），脚跟没在浅水里
    for C, hw in [([(-20, 152), (-19, 124), (-17, 100), (-19, 74), (-21, 44), (-21, 14)], [17.5, 15.5, 12.8, 14.6, 11.2, 9.0]),
                  ([(21, 152), (21, 124), (20, 100), (23, 74), (27, 44), (30, 14)], [17.5, 15.5, 12.8, 14.6, 11.2, 9.0])]:
        M = poly_mask(T(tube(C, hw)))
        put(M, shade_part(M, SKIN, 4, rim_w=2.5))
    for (hx, sg) in [(-21, -1), (30, 1)]:
        Mh = poly_mask(T(ellipse_pts(hx, 7, 9.5, 7)))
        Mh = ndimage.gaussian_filter(Mh, 1.0) * 0.55
        put(Mh, shade_part(Mh, (0.8, 0.6, 0.5), 2) * 0.8)
    for (kx0, sgn) in [(-18, -1), (20, 1)]:
        Mk = poly_mask(T(tube([(kx0 - 6, 102), (kx0, 100.0), (kx0 + 6, 102)], [0.9, 1.1, 0.9])))
        Mk = ndimage.gaussian_filter(Mk, 1.2)
        rgb = rgb * (1 - 0.18 * Mk[..., None])
    # 肩背皮肤
    M = poly_mask(T(catmull([(-45, 286), (-44, 298), (-36, 304), (-24, 307), (-14, 314), (-12, 326), (12, 326), (14, 314),
                             (24, 307), (36, 304), (44, 298), (45, 286), (30, 279), (0, 276), (-30, 279)])))
    put(M, shade_part(M, SKIN, 5))
    # 左臂（微微张开保持平衡）
    M = poly_mask(T(tube([(-38, 286), (-46, 262), (-54, 236), (-60, 212), (-65, 192), (-68, 180)], [10.5, 10, 9, 8.2, 7.3, 7])))
    M = np.maximum(M, poly_mask(T(ellipse_pts(-70, 171, 7.8, 10.5, 0.35))))
    M = np.maximum(M, poly_mask(T(ellipse_pts(-64, 175, 3.5, 5.5, 0.1))))
    put(M, shade_part(M, SKIN, 3, rim_w=2.5))
    # 连衣裙（背面、下摆被风吹向右）
    dress_pts = [(-29, 297), (-35, 284), (-37, 262), (-35, 238), (-42, 210), (-52, 180), (-62, 156), (-68, 136),
                 (-56, 129), (-40, 135), (-24, 127), (-6, 134), (12, 125), (30, 133), (48, 123), (66, 131), (84, 122),
                 (99, 133), (87, 155), (71, 180), (55, 210), (38, 238), (39, 262), (38, 284), (31, 297),
                 (22, 290), (11, 283), (0, 281), (-11, 283), (-22, 290)]
    M = poly_mask(T(catmull(dress_pts)))
    lx_ = (XX - FX) / SCALE
    lY = (FY - YY) / SCALE
    th = np.arctan2(lx_ - 6, 330 - lY)
    folds = 0.8 + 0.2 * np.cos(th * 26 + 2.5 * fbm(lx_ / 20, lY / 40, 2, 3)) * ss(235, 150, lY)
    put(M, shade_part(M, DRESS, 5, tex=folds))
    # 腰带与背后的蝴蝶结
    M = poly_mask(T([(-36, 244), (37, 244), (37.5, 233), (-35.5, 233)]))
    put(M, shade_part(M, (0.97, 0.95, 0.9), 2))
    for (ex, ey, rx, ry, a) in [(-10, 241, 10, 6.5, -0.35), (10, 241, 10, 6.5, 0.35)]:
        M = poly_mask(T(ellipse_pts(ex, ey, rx, ry, a)))
        put(M, shade_part(M, (0.97, 0.95, 0.9), 2))
    for C in [[(-1, 236), (3, 222), (9, 205)], [(3, 236), (11, 223), (20, 209)]]:
        M = poly_mask(T(tube(C, [3.2, 3.0, 2.6])))
        put(M, shade_part(M, (0.97, 0.95, 0.9), 2))
    M = poly_mask(T(ellipse_pts(0, 238, 4.5, 4.5)))
    put(M, shade_part(M, (0.92, 0.9, 0.85), 2))
    # 右臂（举起拉着风筝线）
    M = poly_mask(T(tube([(41, 290), (54, 305), (68, 322), (80, 340), (92, 362), (102, 386), (108, 400)],
                         [10.5, 10, 9.3, 8.4, 7.6, 7, 6.5])))
    M = np.maximum(M, poly_mask(T(ellipse_pts(109, 406, 8.6, 11.0, -0.5))))
    M = np.maximum(M, poly_mask(T(ellipse_pts(102, 404, 3.8, 5.5, -0.1))))
    put(M, shade_part(M, SKIN, 3, rim_w=2.5))
    # 头发（向右飘）
    hair_pts = [(-27, 356), (-30, 338), (-31, 320), (-30, 304), (-25, 292), (-16, 287), (-6, 292), (5, 285), (16, 291),
                (27, 283), (40, 289), (52, 283), (64, 290), (78, 287), (88, 294), (76, 301), (62, 308), (50, 316),
                (40, 327), (33, 340), (29, 356)]
    M = poly_mask(TH(catmull(hair_pts)))
    strands = 0.78 + 0.22 * np.sin((0.55 * lx_ + lY) * 0.9 + 4 * fbm(lx_ / 12, lY / 12, 2, 9))
    put(M, shade_part(M, HAIR, 4, tex=strands, rim=(2.3, 1.6, 0.95), rim_w=3.5))
    for C, w in [([(40, 300), (62, 298), (82, 300), (100, 296)], 1.4), ([(48, 310), (70, 307), (90, 309), (104, 305)], 1.2),
                 ([(30, 292), (50, 290), (70, 294), (92, 289)], 1.3), ([(56, 318), (76, 316), (94, 318)], 1.1)]:
        M = poly_mask(TH(tube(C, np.linspace(w * 1.6, w * 0.6, len(C)))))
        put(M, shade_part(M, HAIR, 1.5, rim=(2.4, 1.7, 1.0), rim_w=2))
    # 草帽：帽顶 → 帽檐 → 缎带
    straw = 0.86 + 0.14 * np.sin(lx_ * 1.6) * np.sin(lY * 1.6)
    M = poly_mask(TH(catmull([(-30, 356), (-29, 372), (-22, 386), (-10, 393), (4, 395), (18, 391), (27, 382), (31, 368),
                             (31, 356), (0, 352)])))
    put(M, shade_part(M, STRAW, 4, tex=straw))
    band = poly_mask(TH(catmull([(-30.5, 358), (-30, 368), (0, 366), (31, 369), (31.5, 359), (0, 356)])))
    put(band, shade_part(band, RIB, 2))
    M = poly_mask(TH(ellipse_pts(2, 355, 66, 10.5, -0.07)))
    brim_tex = straw * (0.85 + 0.15 * ss(-60, 60, lx_))
    put(M, shade_part(M, STRAW, 3, tex=brim_tex))
    for C, w in [([(22, 362), (38, 367), (54, 361), (70, 366), (86, 359), (98, 363)], 3.6),
                 ([(22, 359), (36, 355), (50, 350), (63, 354), (76, 348), (86, 351)], 3.0)]:
        M = poly_mask(TH(tube(C, [w, w, w * 0.95, w * 0.9, w * 0.85, w * 0.6])))
        put(M, shade_part(M, RIB, 1.5))
    return rgb, A


# ----------------------------------------------------------------------------- kite
KX, KY, KZ = 4.9, 6.3, 26.0          # 风筝在世界中的位置（米）
KS = 1.6                               # 风筝高度（米）


def proj(X, Y, Z):
    return CXI + F * X / Z, HOR - F * (Y - EYE) / Z


def draw_kite(canvas_rgb, canvas_a, cx, cy, s, ang, flip=False, alpha=1.0, glow=1.0):
    """在给定画布上画菱形风筝和尾巴（像素坐标，s = 风筝高度像素）。"""
    def R(p):
        p = np.asarray(p, float)
        y = -p[:, 1] if flip else p[:, 1]
        ca, sa = np.cos(ang), np.sin(ang)
        return np.stack([cx + s * (p[:, 0] * ca - y * sa), cy + s * (p[:, 0] * sa + y * ca)], 1)
    top, right, bot, left, ctr = (0, -0.47), (0.33, -0.14), (0, 0.53), (-0.33, -0.14), (0, -0.14)
    panels = [((top, right, ctr), (1.0, 0.82, 0.18)), ((right, bot, ctr), (0.95, 0.30, 0.22)),
              ((bot, left, ctr), (0.20, 0.45, 0.85)), ((left, top, ctr), (0.12, 0.70, 0.65))]
    for pts, col in panels:
        M = poly_mask(R(pts)) * alpha
        c = lin(col) * 1.25 * glow
        canvas_rgb[:] = canvas_rgb * (1 - M[..., None]) + c * M[..., None]
        canvas_a[:] = canvas_a * (1 - M) + M
    for a, b, wd in [(top, bot, 0.012), (left, right, 0.012)]:
        a = np.array(a, float)
        b = np.array(b, float)
        d = b - a
        nrm = np.array([-d[1], d[0]]) / np.hypot(*d) * wd
        M = poly_mask(R([a + nrm, b + nrm, b - nrm, a - nrm])) * alpha
        canvas_rgb[:] = canvas_rgb * (1 - M[..., None]) + lin((0.25, 0.16, 0.1)) * M[..., None]
    # 尾巴
    tail = []
    for u in np.linspace(0, 1, 60):
        tail.append((0.9 * u * 1.3 + 0.12 * np.sin(u * 9.0), 0.53 + 1.25 * u + 0.05 * np.sin(u * 6)))
    tail = np.array(tail)
    tp = R(tail)
    img = Image.new('L', (W * 4, H * 4), 0)
    ImageDraw.Draw(img).line([(x * 4, y * 4) for x, y in tp], fill=255, width=max(2, int(s * 0.02 * 4)), joint='curve')
    M = np.asarray(img, np.float64).reshape(H, 4, W, 4).mean((1, 3)) / 255 * alpha
    canvas_rgb[:] = canvas_rgb * (1 - M[..., None]) + lin((0.9, 0.85, 0.8)) * M[..., None]
    canvas_a[:] = canvas_a * (1 - M) + M
    bow_cols = [(0.95, 0.30, 0.22), (1.0, 0.82, 0.18), (0.20, 0.45, 0.85), (0.12, 0.70, 0.65)]
    for i, u in enumerate(np.linspace(0.12, 0.95, 6)):
        j = int(u * 59)
        c = tail[j]
        dvec = tail[min(j + 1, 59)] - tail[max(j - 1, 0)]
        dvec /= np.hypot(*dvec)
        nv = np.array([-dvec[1], dvec[0]])
        bw = 0.075
        for sg in (-1, 1):
            tri = [c, c + nv * bw * sg + dvec * 0.03, c + nv * bw * sg - dvec * 0.03]
            M = poly_mask(R(tri)) * alpha
            canvas_rgb[:] = canvas_rgb * (1 - M[..., None]) + lin(bow_cols[i % 4]) * 1.2 * glow * M[..., None]
            canvas_a[:] = canvas_a * (1 - M) + M
    return R([(0, -0.05)])[0]


def draw_string(canvas_rgb, p0, p1, sag, color, width=1.3, alpha=0.9):
    p0 = np.asarray(p0, float)
    p1 = np.asarray(p1, float)
    mid = (p0 + p1) / 2 + np.array([0, sag])
    pts = [(1 - t) ** 2 * p0 + 2 * (1 - t) * t * mid + t * t * p1 for t in np.linspace(0, 1, 80)]
    img = Image.new('L', (W * 4, H * 4), 0)
    ImageDraw.Draw(img).line([(x * 4, y * 4) for x, y in pts], fill=255, width=max(2, int(width * 4)), joint='curve')
    M = np.asarray(img, np.float64).reshape(H, 4, W, 4).mean((1, 3)) / 255 * alpha
    canvas_rgb[:] = canvas_rgb * (1 - M[..., None]) + np.asarray(color) * M[..., None]


# ----------------------------------------------------------------------------- scene
def main():
    S = sky_layer()
    # ---- 地面坐标
    g = YY > HOR
    Z = np.where(g, EYE * F / np.maximum(YY - HOR, 1e-3), 1e4)
    X = (XX - CXI) * Z / F
    Zc = np.minimum(Z, 400)
    # 镜像天空（远处物体按地平线翻转）
    ry = np.clip(2 * HOR - YY, 0, HOR - 1).astype(int)
    Rsky = S[ry, XX.astype(int)]
    # ---- 海
    Zsh = 12.0 + 0.9 * np.sin(X / 2.7 + 0.5) + 1.4 * (fbm(X / 3.5, np.zeros_like(X), 2, 3) - 0.5)
    sea = g & (Z > Zsh)
    wv = fbm(X / 5.0, Zc / 1.3, 4, 21)
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * Zc / 3.4 + 5 * fbm(X / 9, Zc / 6, 2, 22))
    fres = np.clip(0.14 + 0.8 * ss(10, 120, Z), 0, 1)
    seabase = mix(lin((0.03, 0.33, 0.40)), lin((0.26, 0.45, 0.58)), ss(12, 150, Z)) * (0.75 + 0.5 * swell)[..., None]
    dy = (22 * (wv - 0.5) * (1 - ss(40, 200, Z))).astype(int)
    Rsea = S[np.clip(ry + dy, 0, HOR - 1).astype(int), XX.astype(int)]
    Rsea = ndimage.gaussian_filter(Rsea, sigma=(1.5, 4, 0))
    seacol = seabase * (1 - fres[..., None]) + Rsea * fres[..., None]
    # 碎浪白沫
    foam = np.zeros_like(Z)
    for dz, wdt in [(0.9, 0.55), (3.3, 0.6), (6.5, 0.8)]:
        band = np.exp(-((Z - Zsh - dz - 0.4 * (fbm(X / 2, np.zeros_like(X) + dz, 2, 7) - 0.5)) / wdt) ** 2)
        lace = ss(0.42, 0.62, fbm(X / 0.55, Zc / 0.18, 4, int(30 + dz * 10)))
        lace = ss(0.36, 0.56, fbm(X / 0.55, Zc / 0.18, 4, int(30 + dz * 10))) if dz < 2 else lace
        foam = np.maximum(foam, band * lace * (1.0 if dz < 2 else 0.7))
    seacol = seacol * (1 - foam[..., None]) + lin((1.0, 0.95, 0.88)) * 0.95 * foam[..., None]
    # 太阳在海面上的碎金
    wband = 30 + 2600 / np.maximum(Z, 1)
    glit = ss(0.64, 0.8, vnoise(X / 0.3, Zc / 0.06, 40)) * np.exp(-((XX - SUNX) / wband) ** 2)
    seacol = seacol + glit[..., None] * np.array([2.6, 2.1, 1.4]) * (0.4 + 0.6 * ss(12, 60, Z))[..., None]
    # ---- 冲上沙滩的薄水膜 + 湿沙 + 干沙
    kx, ky = proj(KX, KY, KZ)
    ks = F * KS / KZ
    krx, kry = proj(KX, -KY, KZ)
    kZg = EYE * F / (kry - HOR)
    kXg = (krx - CXI) * kZg / F
    Zedge = Zsh - 2.6 + 0.9 * (fbm(X / 1.6, np.ones_like(X), 3, 4) - 0.5)
    film = g & (Z > Zedge) & ~sea
    Xb = -0.79 - 1.25 * (Z - 3.18) + 0.55 * (fbm(Zc / 0.9, X / 0.9, 4, 8) - 0.5) + 0.12 * np.sin(Z / 0.35)
    dryness = ss(-0.02, 0.22, Xb - X) * g
    damp = ss(-0.4, -0.02, Xb - X) * (1 - dryness) * g
    Rbl = ndimage.gaussian_filter(Rsky, sigma=(6, 1.5, 0))
    Rfilm = ndimage.gaussian_filter(Rsky, sigma=(2, 0.8, 0))
    # 退潮沙纹：波谷积水反光、波峰露出湿沙
    fpz = Zc * Zc / (EYE * F)
    ang = 0.32
    ph = 2 * np.pi * (X * np.cos(ang) + Zc * np.sin(ang)) / 0.11 + 7.0 * fbm(X / 0.6, Zc / 0.6, 3, 19) + 1.5 * np.sin(X / 0.25)
    ramp = np.clip(1 - fpz / 0.07, 0, 1)
    patch = ss(0.38, 0.6, fbm(X / 1.4, Zc / 1.4, 3, 23))
    trough = (ss(0.25, 0.95, -np.sin(ph)) * ramp + 0.3 * (1 - ramp)) * patch
    pool = ss(0.57, 0.63, fbm(X / 1.1, Zc / 1.1, 4, 18))
    pool = np.maximum(pool, ss(1.0, 0.6, ((X - XG - 0.2) / 1.0) ** 2 + ((Z - ZG + 0.3) / 0.7) ** 2))
    pool = np.maximum(pool, ss(1.0, 0.6, ((X - kXg) / 0.75) ** 2 + ((Z - kZg) / 0.5) ** 2))
    fine = fbm(X / 0.05, Zc / 0.05, 3, 17)
    wetbase = mix(lin((0.56, 0.45, 0.34)), lin((0.43, 0.34, 0.26)), trough) * (0.88 + 0.24 * fine * ramp)[..., None]
    wetbase = wetbase * (1 - 0.45 * pool)[..., None]
    kwet = (0.12 + 0.3 * trough) * (1 - pool) + 0.72 * pool + 0.1 * ss(5, 11, Z)
    Rwet = mix(Rbl, Rfilm, pool)
    edge_line = np.exp(-((Z - Zedge) / (0.05 + 0.004 * Z)) ** 2) * ss(0.35, 0.55, fbm(X / 0.4, np.zeros_like(X), 3, 12))
    # 干沙：风纹 + 颗粒；过渡带是半干的深色沙
    rip = np.sin(2 * np.pi * (X * 0.8 + Zc * 0.6) / 0.09 + 9 * fbm(X / 0.4, Zc / 0.4, 3, 13))
    grainn = fbm(X / 0.015, Zc / 0.015, 2, 14)
    drybase = lin((0.95, 0.82, 0.64)) * (0.9 + 0.07 * rip * (1 - ss(4, 9, Z)) + 0.12 * (grainn - 0.5))[..., None]
    dampbase = lin((0.70, 0.56, 0.42)) * (0.9 + 0.2 * fine)[..., None]
    # ---- 小女孩：倒影、影子
    grgb, ga = girl_layer()
    rrow = np.clip(2 * FY - YY, 0, H - 1)
    Rg = np.stack([ndimage.map_coordinates(grgb[..., c], [rrow, XX - 0.5], order=1) for c in range(3)], -1)
    Ra = ndimage.map_coordinates(ga, [rrow, XX - 0.5], order=1) * (YY > FY)
    Rg = ndimage.gaussian_filter(Rg, sigma=(2.5, 0.8, 0))
    Ra = ndimage.gaussian_filter(Ra, sigma=(2.5, 0.8))
    # 风筝倒影（按真实几何：倒影点在 (X,-Y,Z)）
    Kr_rgb = np.zeros((H, W, 3))
    Kr_a = np.zeros((H, W))
    draw_kite(Kr_rgb, Kr_a, krx, kry, ks, -0.28, flip=True, alpha=1.0, glow=0.9)
    Kr_rgb = ndimage.gaussian_filter(Kr_rgb, sigma=(2, 0.7, 0))
    Kr_a = ndimage.gaussian_filter(Kr_a, sigma=(2, 0.7))
    # 组合地面反射图
    Rground = Rwet.copy()
    Rground[film] = Rfilm[film]
    Rground = Rground * (1 - Kr_a[..., None]) + Kr_rgb * 0.85 * Kr_a[..., None]
    Rground = Rground * (1 - Ra[..., None]) + Rg * 0.8 * Ra[..., None]
    # 影子：把女孩剪影投到沙面（太阳在右前方，影子伸向左下）
    sdir = np.array([-0.33, -0.94])
    sdir /= np.hypot(*sdir)
    lat = np.array([-sdir[1], sdir[0]])
    relX = X - XG
    relZ = Z - ZG
    Ym = (relX * sdir[0] + relZ * sdir[1]) / 1.45
    xm = relX * lat[0] + relZ * lat[1]
    lxs = xm * 380 / 1.13
    lYs = Ym * 380 / 1.13
    sh = ndimage.map_coordinates(ga, [FY - SCALE * lYs, FX + SCALE * lxs], order=1) * (Ym > -0.01) * g
    sh = ndimage.gaussian_filter(sh, 1.5)
    # 脚印（从左下的干沙一路走到她脚下）
    fp = np.zeros_like(Z)
    fprim = np.zeros_like(Z)
    for i, (px_, pz_) in enumerate([(-1.62, 3.05), (-1.43, 3.37), (-1.44, 3.72), (-1.26, 4.05), (-1.27, 4.4)]):
        d = np.array([0.28, 0.96])
        for (ox, oz, tgt) in [(0.0, 0.0, 'fp'), (0.012, -0.012, 'rim')]:
            dxp = X - px_ - ox
            dzp = Z - pz_ - oz
            a_ = dxp * d[0] + dzp * d[1]
            b_ = -dxp * d[1] + dzp * d[0]
            m_ = ss(1.0, 0.7, (a_ / 0.08) ** 2 + (b_ / 0.035) ** 2)
            if tgt == 'fp':
                fp = np.maximum(fp, m_)
            else:
                fprim = np.maximum(fprim, m_)
    fprim = np.clip(fprim - fp, 0, 1)
    # ---- 合成地面
    C = S.copy()
    kk = np.clip(kwet + 0.3 * fp, 0, 0.9)
    wetcol = wetbase * (1 - 0.5 * sh[..., None]) * (1 - 0.3 * fp[..., None])
    wetcol = wetcol * (1 - kk[..., None]) + Rground * kk[..., None]
    dampcol = dampbase * (1 - 0.5 * sh[..., None]) * (1 - 0.35 * fp[..., None]) * 0.9 + Rbl * 0.1
    drycol = drybase * (1 - 0.55 * sh[..., None]) * (1 - 0.35 * fp[..., None]) * (1 + 0.25 * fprim[..., None])
    land = wetcol * (1 - dryness - damp)[..., None] + dampcol * damp[..., None] + drycol * dryness[..., None]
    filmcol = lin((0.5, 0.41, 0.33)) * (1 - 0.4 * sh[..., None]) * 0.35 + Rground * 0.72
    C[g] = land[g]
    C[film] = filmcol[film]
    C[sea] = seacol[sea]
    C = C + (edge_line * film)[..., None] * lin((1.0, 0.96, 0.9)) * 0.9
    # 脚踝周围的小涟漪
    img = Image.new('L', (W * 4, H * 4), 0)
    dr = ImageDraw.Draw(img)
    for lx0 in (-21, 30):
        cxr = FX + SCALE * lx0
        for rr_m in (0.05, 0.09, 0.14):
            rx_ = F * rr_m / ZG
            ry_ = rx_ * EYE / ZG
            dr.ellipse([(cxr - rx_) * 4, (FY - 2 - ry_) * 4, (cxr + rx_) * 4, (FY - 2 + ry_) * 4], outline=255, width=5)
    rings = np.asarray(img, np.float64).reshape(H, 4, W, 4).mean((1, 3)) / 255
    rings = ndimage.gaussian_filter(rings, 0.8) * (0.6 + 0.4 * fbm(XX / 6, YY / 3, 2, 77))
    C = C + rings[..., None] * lin((1.0, 0.92, 0.82)) * 0.3
    # ---- 沙滩小桶和小铲子（干沙上）
    bx, by, bw_, bh_ = 138.0, 978.0, 50.0, 46.0
    body = poly_mask([(bx - bw_ / 2, by - bh_), (bx + bw_ / 2, by - bh_), (bx + bw_ * 0.4, by), (bx - bw_ * 0.4, by)])
    body = np.maximum(body, poly_mask(ellipse_pts(bx, by, bw_ * 0.4, 6)))
    u_ = np.clip((XX - (bx - bw_ / 2)) / bw_, 0, 1)
    bcol = lin((0.98, 0.78, 0.12)) * (0.45 + 0.75 * u_ ** 1.5)[..., None]
    bcol = bcol + (np.clip(u_ - 0.8, 0, 1) * 5)[..., None] * lin((1.0, 0.8, 0.5)) * 0.8
    shd = poly_mask(ellipse_pts(bx - 40, by + 4, 55, 9, 0.12))
    C = C * (1 - 0.45 * ndimage.gaussian_filter(shd, 3)[..., None])
    C = C * (1 - body[..., None]) + bcol * body[..., None]
    rim_ = poly_mask(ellipse_pts(bx, by - bh_, bw_ / 2, 7))
    inner = poly_mask(ellipse_pts(bx, by - bh_ + 1, bw_ / 2 - 3.5, 5))
    C = C * (1 - rim_[..., None]) + lin((1.0, 0.86, 0.3)) * rim_[..., None]
    C = C * (1 - inner[..., None]) + lin((0.72, 0.58, 0.40)) * inner[..., None]
    img = Image.new('L', (W * 4, H * 4), 0)
    ImageDraw.Draw(img).arc([(bx - bw_ / 2 + 2) * 4, (by - bh_ - 26) * 4, (bx + bw_ / 2 - 2) * 4, (by - bh_ + 14) * 4], 195, 345, fill=255, width=9)
    hm = np.asarray(img, np.float64).reshape(H, 4, W, 4).mean((1, 3)) / 255
    C = C * (1 - hm[..., None]) + lin((0.25, 0.22, 0.2)) * hm[..., None]
    sp = poly_mask(tube([(40, 1012), (66, 1004), (90, 997)], [2.8, 2.5, 2.3]))
    sp = np.maximum(sp, poly_mask(ellipse_pts(103, 993, 15, 8, -0.28)))
    C = C * (1 - 0.3 * ndimage.gaussian_filter(poly_mask(ellipse_pts(72, 1008, 40, 5, -0.28)), 2.5)[..., None])
    spc = lin((0.86, 0.2, 0.17)) * (0.55 + 0.6 * ss(990, 1012, YY))[..., None]
    C = C * (1 - sp[..., None]) + spc * sp[..., None]
    # ---- 风筝与风筝线（天空里）
    krgb = np.zeros((H, W, 3))
    ka = np.zeros((H, W))
    bridle = draw_kite(krgb, ka, kx, ky, ks, -0.28, glow=1.15)
    C = C * (1 - ka[..., None]) + krgb * ka[..., None]
    hand = T([(110, 409)])[0]
    draw_string(C, hand, bridle, 26, lin((1.0, 0.96, 0.88)) * 1.2, width=1.2, alpha=0.85)
    # 风筝线的倒影（从风筝倒影往画面下方延伸）
    hr = np.array([hand[0], 2 * FY - hand[1]])
    brr = np.array([bridle[0], kry + (kry - ky) * 0 + (bridle[1] - ky) * -1])
    draw_string(C, brr, hr, -20, lin((0.9, 0.85, 0.8)) * 0.7, width=1.0, alpha=0.45)
    # ---- 女孩本体
    C = C * (1 - ga[..., None]) + grgb * ga[..., None]
    # ---- 泛光、色调映射
    lum = C @ np.array([0.2126, 0.7152, 0.0722])
    bright = C * np.clip((lum - 0.85) / np.maximum(lum, 1e-6), 0, 1)[..., None]
    bloom = np.zeros_like(C)
    for sg, wt in [(4, 0.3), (16, 0.3), (50, 0.25), (140, 0.15)]:
        bloom += wt * ndimage.gaussian_filter(bright, sigma=(sg, sg, 0))
    C = C + 0.55 * bloom
    C = C * 1.05
    Ct = C * (1 + C / 6.0) / (1 + C)
    r2 = ((XX - W / 2) / (W / 2)) ** 2 + ((YY - H / 2) / (H / 2)) ** 2
    Ct = Ct * (1 - 0.18 * np.clip(r2 / 2, 0, 1))[..., None]
    out = np.clip(Ct, 0, 1) ** (1 / 2.2)
    gray = out.mean(-1, keepdims=True)
    out = np.clip(gray + (out - gray) * 1.12, 0, 1)
    out = out + 0.06 * (out - 0.5) * (1 - np.abs(2 * out - 1))
    rng = np.random.default_rng(7)
    out = out + rng.normal(0, 0.008, out.shape)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, 'final.png'))
    print('saved')


if __name__ == '__main__':
    main()
