#!/usr/bin/env python3
"""A10 中国水墨画：月下孤舟。

纯代码：numpy 画布记录“墨量”，用自写的毛笔笔触（沿路径的距离场：起笔收笔粗细、墨色由浓到淡、
飞白、湿边积墨、毛边）和大面积渲染（烘云托月、远山淡墨、雾）逐层落墨，最后按墨量在程序生成的
宣纸（纤维 + 斑驳旧色）上显色。题字用系统自带的行楷字体渲染成字形再加墨迹质感，印章也是代码画的。
不读任何图片文件，随机种子固定。用法：python3 draw.py [输出路径]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
W, H = 1536, 1024
SEED = 10
rng = np.random.default_rng(SEED)
F32 = np.float32
FONT_XK = "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/13b8ce423f920875b28b551f9406bf1014e0a656.asset/AssetData/Xingkai.ttc"
FONT_ST = "/System/Library/Fonts/Supplemental/Songti.ttc"


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def vnoise(h, w, scale, octaves, seed, aniso=(1.0, 1.0)):
    """值噪声分形（双三次插值放大随机网格），值域约 [0,1]。aniso 可把纹理拉长。"""
    r = np.random.default_rng(seed)
    out = np.zeros((h, w), F32)
    amp, tot = 1.0, 0.0
    for _ in range(octaves):
        sy, sx = scale * aniso[0], scale * aniso[1]
        g = r.random((int(h / sy) + 3, int(w / sx) + 3)).astype(F32)
        big = Image.fromarray(g, mode="F").resize((int(g.shape[1] * sx), int(g.shape[0] * sy)), Image.BICUBIC)
        out += amp * np.asarray(big, F32)[:h, :w]
        tot += amp
        amp *= 0.5
        scale = max(1.0, scale / 2)
    return np.clip(out / tot, 0, 1)


YY, XX = np.mgrid[0:H, 0:W].astype(F32)
N_FINE = vnoise(H, W, 3, 2, SEED + 1)
N_MID = vnoise(H, W, 18, 3, SEED + 2)
N_LOW = vnoise(H, W, 160, 4, SEED + 3)
D = np.zeros((H, W), F32)          # 墨量


# ---------------- 笔触 ----------------
def catmull(pts, step=2.0):
    P = np.asarray(pts, np.float64)
    if len(P) == 2:
        n = max(2, int(np.hypot(*(P[1] - P[0])) / step))
        t = np.linspace(0, 1, n)[:, None]
        return P[0] + (P[1] - P[0]) * t
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int(np.hypot(*(p2 - p1)) / step))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2][None])
    return np.vstack(out)


def stroke(pts, w0, ink=1.0, tin=0.12, tout=0.35, dry=0.0, wet=0.0, rough=0.3, deplete=0.3, press=None, seed=None,
           target=None, soft=0.22):
    """一笔：沿路径算每个像素到中线的距离 u 和弧长 s，按笔形给墨。"""
    tgt = D if target is None else target
    r = np.random.default_rng(seed if seed is not None else rng.integers(1 << 30))
    C = catmull(pts, 2.0)
    seg = np.diff(C, axis=0)
    sl = np.hypot(seg[:, 0], seg[:, 1])
    keep = sl > 1e-6
    A, seg, sl = C[:-1][keep], seg[keep], sl[keep]
    s0 = np.concatenate([[0], np.cumsum(sl)])[:-1]
    L = float(sl.sum()) + 1e-6
    wmax = w0 * 1.25 + 3
    x0, y0 = int(max(0, np.floor(C[:, 0].min() - wmax))), int(max(0, np.floor(C[:, 1].min() - wmax)))
    x1, y1 = int(min(W, np.ceil(C[:, 0].max() + wmax))), int(min(H, np.ceil(C[:, 1].max() + wmax)))
    if x1 <= x0 or y1 <= y0:
        return
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).line([(float(p[0] - x0), float(p[1] - y0)) for p in C], fill=255, width=int(2 * wmax) + 2, joint="curve")
    ys, xs = np.nonzero(np.asarray(m))
    if len(ys) == 0:
        return
    px, py = xs + x0 + 0.5, ys + y0 + 0.5
    best = np.full(len(px), np.inf)
    s_near = np.zeros(len(px))
    side = np.zeros(len(px))
    ab2 = (seg ** 2).sum(1)
    for k in range(0, len(A), 64):
        a, ab, l2 = A[k:k + 64], seg[k:k + 64], ab2[k:k + 64]
        apx = px[:, None] - a[None, :, 0]
        apy = py[:, None] - a[None, :, 1]
        t = np.clip((apx * ab[None, :, 0] + apy * ab[None, :, 1]) / l2[None], 0, 1)
        dx, dy = apx - t * ab[None, :, 0], apy - t * ab[None, :, 1]
        d2 = dx * dx + dy * dy
        j = d2.argmin(1)
        dj = d2[np.arange(len(px)), j]
        upd = dj < best
        best[upd] = dj[upd]
        tj = t[np.arange(len(px)), j]
        s_near[upd] = (s0[k:k + 64][j] + tj * sl[k:k + 64][j])[upd]
        cr = ab[j, 0] * apy[np.arange(len(px)), j] - ab[j, 1] * apx[np.arange(len(px)), j]
        side[upd] = np.sign(cr)[upd]
    tt = s_near / L
    wa = smoothstep(0, tin, tt) ** 0.6 if tin > 0 else 1.0
    wb = smoothstep(1, 1 - tout, tt) ** 0.7 if tout > 0 else 1.0
    wid = w0 * (0.12 + 0.88 * wa) * (0.04 + 0.96 * wb)
    if press is not None:
        wid = wid * np.interp(tt, np.linspace(0, 1, len(press)), press)
    u = side * np.sqrt(best) / np.maximum(wid, 0.35)
    iy, ix = ys + y0, xs + x0
    edge = np.abs(u) + rough * (N_FINE[iy, ix] - 0.5) * 2 + 0.5 * rough * (N_MID[iy, ix] - 0.5)
    body = smoothstep(1.0, 1.0 - soft - 0.12 / np.maximum(wid, 1), edge)
    c = ink * (1 - deplete * tt) * (0.85 + 0.3 * N_MID[iy, ix])
    if dry > 0:                                  # 飞白：沿笔毛方向的断续白线，越到笔尾越干
        nb = 26
        bv = r.random(nb + 1)
        uu = np.clip((u + 1) / 2, 0, 1) * nb + 0.4 * np.sin(s_near / 13 + r.random() * 6)
        br = np.interp(uu, np.arange(nb + 1), bv)
        along = np.interp(s_near / 9.0, np.arange(int(L / 9) + 3), r.random(int(L / 9) + 3))
        thr = dry * (0.15 + 0.85 * tt ** 1.3) * (0.7 + 0.6 * along)
        body = body * smoothstep(thr - 0.12, thr + 0.12, br)
    if wet > 0:                                  # 湿笔：边缘积墨
        c = c + wet * ink * smoothstep(0.55, 0.95, np.abs(u))
    tgt[iy, ix] += (body * c).astype(F32)


def dab(cx, cy, rx, ry, ink, ang=0.0, soft=0.5, target=None):
    """一个湿墨点（米点、苔点、芦花）。"""
    tgt = D if target is None else target
    R = int(max(rx, ry) * 1.6 + 3)
    x0, x1, y0, y1 = int(max(0, cx - R)), int(min(W, cx + R)), int(max(0, cy - R)), int(min(H, cy + R))
    if x1 <= x0 or y1 <= y0:
        return
    xx, yy = XX[y0:y1, x0:x1] - cx, YY[y0:y1, x0:x1] - cy
    c, s = np.cos(ang), np.sin(ang)
    u, v = (c * xx + s * yy) / rx, (-s * xx + c * yy) / ry
    r_ = np.sqrt(u * u + v * v) + 0.35 * (N_FINE[y0:y1, x0:x1] - 0.5)
    body = smoothstep(1.0, 1.0 - soft, r_)
    tgt[y0:y1, x0:x1] += (ink * body * (0.8 + 0.4 * N_MID[y0:y1, x0:x1]) + 0.35 * ink * smoothstep(0.6, 0.95, r_) * body).astype(F32)


# ---------------- 各部分 ----------------
MOON = (1140.0, 225.0, 64.0)


def sky():
    mx, my, mr = MOON
    dist = np.hypot(XX - mx, YY - my)
    vert = smoothstep(620, 60, YY)
    clouds = 0.75 + 0.25 * smoothstep(0.3, 0.8, vnoise(H, W, 150, 3, SEED + 4, aniso=(0.5, 1.8)))
    around = 0.45 + 1.5 * np.exp(-dist / 300)                                 # 月亮周围的云烘得重一些
    halo = 0.42 + 0.58 * smoothstep(mr, mr + 90, dist)                        # 近月处有一圈光晕，但月轮边界仍清楚
    left = 0.45 + 0.55 * smoothstep(250, 900, XX)                             # 左上题字处少着墨
    wash = 0.12 * vert * clouds * around * halo * left
    rim = 0.012 * np.exp(-((dist - mr - 1.5) / 2.5) ** 2)
    # 一缕薄云横过月亮下缘
    band = np.exp(-((YY - (my + 40 + 0.08 * (XX - mx)) - 14 * (N_LOW - 0.5)) / 11) ** 2)
    band *= smoothstep(760, 960, XX) * smoothstep(1500, 1300, XX) * (0.4 + 0.8 * N_MID)
    wash = wash + rim + 0.05 * band
    inside = smoothstep(mr + 0.8, mr - 0.8, dist)
    wash *= 1 - 0.85 * inside
    D[:] += wash.astype(F32)


def mountains():
    # 远山：极淡，脚下化进雾里
    def ridge_line(x, base, bumps, amp_n, seed):
        y = np.full_like(x, base, dtype=F32)
        for cx, h, wdt in bumps:
            y -= h * np.exp(-((x - cx) / wdt) ** 2)
        n = vnoise(1, len(x) + 8, 40, 4, seed)[0, :len(x)]
        n2 = vnoise(1, len(x) + 8, 7, 2, seed + 50)[0, :len(x)]
        return y - amp_n * (n - 0.5) - 5 * (n2 - 0.5)

    x = np.arange(W, dtype=F32)
    for base, bumps, amp, fall, ink, seed, xfade, soft_e, rim in [
        (598, [(980, 40, 110), (1180, 55, 140), (1380, 35, 120), (1520, 50, 90)], 12, 40, 0.05, 23, (860, 1000), 4.0, 0.2),
        (560, [(120, 110, 90), (300, 150, 120), (470, 90, 80), (650, 60, 90), (820, 30, 80)], 26, 70, 0.12, 21, (1000, 780), 3.0, 0.45),
        (600, [(40, 120, 80), (190, 170, 90), (330, 110, 70), (470, 70, 60), (590, 40, 60)], 22, 55, 0.2, 22, (760, 560), 1.5, 0.9),
    ]:
        yr = ridge_line(x, base, bumps, amp, seed)[None, :]
        below = YY - yr
        body = smoothstep(-soft_e, soft_e, below)
        dens = ink * body * (0.45 + 0.55 * np.exp(-np.maximum(below, 0) / fall))
        dens += ink * rim * np.exp(-np.maximum(below, 0) / 5) * body * (0.4 + 0.9 * N_MID)   # 山脊线积墨，时断时续
        mist = smoothstep(base + 25, base - 45, YY)                           # 山脚入雾
        if xfade[0] < xfade[1]:
            fade_x = smoothstep(xfade[0], xfade[1], XX)
        else:
            fade_x = smoothstep(xfade[0], xfade[1], XX)
        dens *= mist * fade_x * (0.7 + 0.6 * N_LOW)
        D[:] += dens.astype(F32)
    yr = ridge_line(x, 600, [(40, 120, 80), (190, 170, 90), (330, 110, 70), (470, 70, 60), (590, 40, 60)], 22, 22)
    # 近山沟壑：从山脊往下的几道柔和淡墨晕染
    gul = np.zeros((H, W), F32)
    for _ in range(26):
        cx = rng.uniform(10, 600)
        top = yr[int(cx)] + rng.uniform(4, 12)
        if top > 540:
            continue
        ln = rng.uniform(30, 70)
        dx = rng.uniform(-10, 10) + (8 if cx > 190 else -8)
        stroke([(cx, top), (cx + dx * 0.5, top + ln * 0.5), (cx + dx, top + ln)], rng.uniform(3.0, 5.5),
               ink=rng.uniform(0.05, 0.1), tin=0.15, tout=0.6, dry=0.3, rough=0.4, soft=0.6, target=gul)
    D[:] += ndi.gaussian_filter(gul, 1.8)
    for _ in range(9):                                  # 苔点
        cx = rng.uniform(30, 560)
        top = yr[int(cx)]
        for _ in range(rng.integers(2, 5)):
            dab(cx + rng.normal(0, 6), top + rng.uniform(-1, 5), rng.uniform(2.0, 3.5), rng.uniform(1.4, 2.4),
                rng.uniform(0.25, 0.45), ang=rng.uniform(-0.3, 0.3), soft=0.6)
    # 近山米点皴：沿山脊和山坡的横向湿墨点
    for _ in range(170):
        cx = rng.uniform(0, 620)
        top = yr[int(cx)]
        cy = top + abs(rng.normal(0, 22)) + 3
        if cy > 575:
            continue
        dab(cx, cy, rng.uniform(5, 10), rng.uniform(2.2, 3.8), rng.uniform(0.08, 0.2) * smoothstep(600, 420, cx + 0.0),
            ang=rng.uniform(-0.15, 0.15), soft=0.7)


def water():
    bx, by = 640, 712
    for _ in range(26):
        cy = 700 + abs(rng.normal(0, 90))
        cx = bx + 40 + rng.normal(0, 150 + (cy - 700) * 0.9)
        if abs(cx - MOON[0]) < 70 or cy > 990:
            continue
        near = np.exp(-((cx - bx) ** 2 / 260 ** 2 + (cy - by) ** 2 / 110 ** 2))
        ln = rng.uniform(40, 90) * (1 + (cy - 700) / 250)
        xs = np.linspace(cx - ln / 2, cx + ln / 2, 9)
        ph, fr = rng.uniform(0, 6), rng.uniform(1.5, 3.0)
        pts = [(x, cy + 1.3 * np.sin((x - cx) / ln * 2 * np.pi * fr + ph)) for x in xs]
        stroke(pts, 0.9 + 0.5 * (cy - 700) / 300, ink=rng.uniform(0.14, 0.26) * (0.55 + 0.9 * near),
               tin=0.35, tout=0.45, rough=0.12, dry=0.35)
    # 月影：月下水面几笔断续的淡墨，中间留一道亮
    for i in range(9):
        cy = 634 + i * 15 + rng.uniform(-4, 4)
        ln = rng.uniform(10, 30) * (1 + i * 0.08)
        side = rng.choice([-1, 1])
        cx = MOON[0] + side * rng.uniform(8, 26 + i * 3) + rng.normal(0, 4)
        pts = [(cx - ln / 2, cy), (cx, cy + rng.uniform(-1.2, 1.2)), (cx + ln / 2, cy + rng.uniform(-1, 1))]
        stroke(pts, 0.8 + i * 0.05, ink=rng.uniform(0.1, 0.17), tin=0.4, tout=0.5, rough=0.15, dry=0.45)


def boat():
    bx, by = 640.0, 712.0            # 船中部水线
    L = 200.0
    # 船身：一弯月牙，船头（右）翘起
    top = [(bx - L / 2, by - 18), (bx - L / 4, by - 4), (bx + L / 6, by - 3), (bx + L / 2 - 10, by - 14), (bx + L / 2 + 6, by - 30)]
    bot = [(bx - L / 2 + 8, by - 14), (bx - L / 4, by + 6), (bx + L / 6, by + 7), (bx + L / 2 - 8, by - 6), (bx + L / 2 + 4, by - 27)]
    hull = Image.new("L", (W, H), 0)
    ctop, cbot = catmull(top, 1.5), catmull(bot, 1.5)
    ImageDraw.Draw(hull).polygon([tuple(p) for p in ctop] + [tuple(p) for p in cbot[::-1]], fill=255)
    hm = ndi.gaussian_filter(np.asarray(hull, F32) / 255, 1.0)
    D[:] += (0.42 * hm * (0.65 + 0.7 * N_MID)).astype(F32)
    stroke(top, 3.2, ink=1.3, tin=0.05, tout=0.1, dry=0.25, rough=0.25, seed=101)
    stroke(bot, 2.4, ink=1.0, tin=0.1, tout=0.15, dry=0.4, rough=0.3, seed=102)
    for k in range(3):                                   # 船舷木纹
        stroke([(bx - L / 3 + k * 8, by - 2 + k * 2.5), (bx + L / 3, by + k * 2.5)], 0.8, ink=0.4, dry=0.5, seed=110 + k)
    # 船篷：竹编拱篷
    cx0 = bx + 10
    arch = [(cx0 - 36, by - 6), (cx0 - 31, by - 24), (cx0 - 10, by - 33), (cx0 + 18, by - 31), (cx0 + 33, by - 19), (cx0 + 37, by - 6)]
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in catmull(arch, 1.5)], fill=255)
    am = ndi.gaussian_filter(np.asarray(m, F32) / 255, 1.2)
    D[:] += (0.09 * am * (0.6 + 0.8 * N_FINE)).astype(F32)
    stroke(arch, 1.7, ink=1.0, tin=0.1, tout=0.2, dry=0.5, seed=103)
    for k in range(8):
        t = (k + 1) / 9
        x = cx0 - 36 + 73 * t
        stroke([(x, by - 6), (x + 1.5, by - 10 - 20 * np.sin(np.pi * t))], 0.7, ink=0.38, dry=0.55, seed=120 + k)
    for k in range(3):
        y = by - 12 - k * 6
        stroke([(cx0 - 30 + k * 4, y), (cx0 + 31 - k * 4, y - 1)], 0.6, ink=0.25, dry=0.6, seed=127 + k)
    # 渔翁：斗笠 + 蓑衣，坐在船尾
    fx, fy = bx - 58, by - 10
    stroke([(fx - 24, fy - 34), (fx - 2, fy - 52), (fx + 22, fy - 35)], 3.8, ink=1.35, tin=0.05, tout=0.15, seed=130)   # 斗笠
    stroke([(fx - 30, fy - 33), (fx + 26, fy - 33)], 2.0, ink=1.2, tin=0.05, tout=0.1, seed=131)
    cape = [(fx - 13, fy - 32), (fx - 23, fy - 16), (fx - 19, fy - 1), (fx + 14, fy - 1), (fx + 16, fy - 20), (fx + 9, fy - 32)]
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in catmull(cape, 1.5)], fill=255)
    D[:] += (0.7 * ndi.gaussian_filter(np.asarray(m, F32) / 255, 0.8) * (0.55 + 0.9 * N_FINE)).astype(F32)
    for k in range(9):                                   # 蓑衣的草茎
        x = fx - 16 + k * 3.6
        stroke([(x, fy - 30 + abs(k - 4)), (x - 2 + rng.uniform(-1, 1), fy)], 0.9, ink=1.1, dry=0.3, seed=140 + k)
    # 钓竿和钓丝
    stroke([(fx + 10, fy - 16), (fx + 90, fy - 70), (fx + 190, fy - 112)], 1.4, ink=1.1, tin=0.02, tout=0.6, dry=0.15, seed=150)
    stroke([(fx + 190, fy - 112), (fx + 196, fy - 40), (fx + 199, fy + 18)], 0.45, ink=0.5, tin=0.0, tout=0.3, rough=0.05, seed=151)
    # 倒影：船下几道断续的横笔
    for k in range(6):
        y = by + 12 + k * 5
        ln = (L * 0.8) * (1 - k * 0.12)
        stroke([(bx - ln / 2 + rng.uniform(-8, 8), y), (bx + ln / 2 + rng.uniform(-8, 8), y + rng.uniform(-1, 1))],
               1.2 + 0.3 * (k < 2), ink=0.45 * (1 - k * 0.13), tin=0.2, tout=0.3, dry=0.55, seed=160 + k)


def reeds():
    for i in range(15):
        near = i >= 5
        x0 = rng.uniform(1300, 1550) if near else rng.uniform(1230, 1500)
        top_y = rng.uniform(610, 720) if not near else rng.uniform(640, 800)
        lean = rng.uniform(25, 80)
        ink = rng.uniform(1.0, 1.4) if near else rng.uniform(0.25, 0.42)
        w = rng.uniform(1.4, 2.1) if near else rng.uniform(0.9, 1.4)
        stem = [(x0, 1040), (x0 - lean * 0.25, (1040 + top_y) / 2 + 20), (x0 - lean, top_y)]
        stroke(stem, w, ink=ink, tin=0.02, tout=0.12, dry=0.3, rough=0.2)
        p = catmull(stem, 4.0)
        for k in range(3):                         # 茎节
            q = p[int((0.35 + 0.18 * k + rng.uniform(-0.04, 0.04)) * (len(p) - 1))]
            stroke([(q[0] - w * 1.6, q[1] + 1), (q[0] + w * 1.6, q[1] - 1)], 0.9, ink=ink * 1.1, tin=0.2, tout=0.2, rough=0.1)
        for _ in range(rng.integers(2, 4) + near):  # 叶：三种姿态交替——斜挺、折垂、贴茎短叶
            t = rng.uniform(0.3, 0.82)
            q = p[int(t * (len(p) - 1))]
            q0, q1 = float(q[0]), float(q[1])
            dirx = rng.choice([-1, -1, 1])
            ln = rng.uniform(60, 150)
            kind = rng.random()
            if kind < 0.4:
                pts = [(q0, q1), (q0 + dirx * ln * 0.35, q1 - ln * 0.5), (q0 + dirx * ln * 0.7, q1 - ln * 0.72),
                       (q0 + dirx * ln * 0.95, q1 - ln * 0.66)]
            elif kind < 0.8:
                ap = rng.uniform(0.35, 0.55)
                pts = [(q0, q1), (q0 + dirx * ln * ap * 0.6, q1 - ln * 0.42), (q0 + dirx * ln * ap, q1 - ln * 0.52),
                       (q0 + dirx * ln * (ap + 0.28), q1 - ln * 0.36), (q0 + dirx * ln * (ap + 0.42), q1 - ln * 0.06)]
            else:
                pts = [(q0, q1), (q0 + dirx * ln * 0.12, q1 - ln * 0.5), (q0 + dirx * ln * 0.3, q1 - ln * 0.9)]
            stroke(pts, w * rng.uniform(1.8, 2.6), ink=ink * rng.uniform(0.75, 1.0), tin=0.08, tout=0.6, dry=0.45, rough=0.3,
                   press=[0.4, 1.0, 0.8, 0.3])
        if rng.random() < 0.85:                    # 芦花：顶上一蓬被风吹向左下的淡墨细笔
            tx, ty = x0 - lean, top_y
            ang = rng.uniform(2.1, 2.6)
            for k in range(12):
                r_ = rng.uniform(0, 36)
                bx_, by_ = tx + r_ * np.cos(ang), ty + r_ * np.sin(ang) * 0.9
                a = ang + rng.normal(0, 0.45)
                ln_ = rng.uniform(7, 15) * (1 - r_ / 60)
                stroke([(bx_, by_), (bx_ + ln_ * np.cos(a), by_ + ln_ * np.sin(a))], rng.uniform(1.0, 1.7),
                       ink=ink * rng.uniform(0.15, 0.3), tin=0.2, tout=0.6, dry=0.5, rough=0.3)
            for _ in range(16):
                r_ = rng.uniform(0, 40)
                a = ang + rng.normal(0, 0.2)
                dab(tx + r_ * np.cos(a), ty + r_ * np.sin(a) * 0.9, rng.uniform(2.5, 5.0), rng.uniform(1.0, 1.8),
                    ink * rng.uniform(0.06, 0.12) * (1 - r_ / 60), ang=a + rng.normal(0, 0.3), soft=0.9)


def inscription(canvas):
    """左上角题诗（行楷），末尾落款、钤印。直接在颜色画布上操作。"""
    col_text = ["野曠天低樹", "江清月近人"]
    size = 46
    font = ImageFont.truetype(FONT_XK, size, index=1)
    small = ImageFont.truetype(FONT_XK, 30, index=3)
    m = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(m)
    x = 250
    for col in col_text:
        y = 70
        for ch in col:
            dr.text((x, y), ch, font=font, fill=255)
            y += size * 1.12
        x -= size * 1.35
    xs_ = x + 8
    y = 90
    for ch in "代碼寫意":
        dr.text((xs_, y), ch, font=small, fill=255)
        y += 34
    a = np.asarray(m, F32) / 255
    a = ndi.gaussian_filter(a, 0.6)
    a = a * (0.75 + 0.35 * N_MID) * smoothstep(0.1, 0.4, a + 0.3 * (N_FINE - 0.5))
    D_txt = 1.35 * a
    # 印章（白文）
    seal_y = int(y + 14)
    stamp(canvas, int(xs_ - 2), seal_y, 44, "孤舟", white=True)
    return D_txt


def stamp(canvas, x0, y0, S, text, white=True, rot=0.0):
    font = ImageFont.truetype(FONT_ST, int(S * 0.42), index=1)
    m = Image.new("L", (S, S), 255 if white else 0)
    dr = ImageDraw.Draw(m)
    if not white:
        dr.rectangle([1, 1, S - 2, S - 2], outline=255, width=max(2, S // 14))
    cs = int(S * 0.42)
    # 印文从右往左、从上往下读：两字竖排
    for i, ch in enumerate(text[:2]):
        dr.text((S // 2 - cs // 2, int(S * 0.06) + i * int(S * 0.46)), ch, font=font, fill=0 if white else 255)
    a = np.asarray(m, F32) / 255
    r = np.random.default_rng(int(x0 * 7 + y0))
    a *= (r.random(a.shape) > 0.05) * (vnoise(S, S, S / 6, 3, int(x0 + y0)) > 0.25)
    a = ndi.gaussian_filter(a, 0.5)
    red = np.array([0.70, 0.15, 0.10], F32)
    reg = canvas[y0:y0 + S, x0:x0 + S]
    k = 0.88 * a[..., None]
    canvas[y0:y0 + S, x0:x0 + S] = reg * (1 - k) + (red * (0.85 + 0.25 * reg)) * k


def paper():
    base = np.array([0.918, 0.878, 0.792], F32)
    fib = np.random.default_rng(SEED + 7).random((H, W)).astype(F32)
    fib = ndi.gaussian_filter(fib, (0.6, 4)) + ndi.gaussian_filter(fib, (4, 0.6))
    fib = (fib - fib.mean()) / (fib.std() + 1e-6)
    mottle = vnoise(H, W, 220, 4, SEED + 8) - 0.5
    grain = N_FINE - 0.5
    edge = np.minimum(np.minimum(XX, W - XX), np.minimum(YY, H - YY))
    aged = 1 - 0.07 * smoothstep(120, 0, edge)
    t = (1 + 0.012 * fib + 0.06 * mottle + 0.025 * grain) * aged
    return np.clip(base[None, None] * t[..., None], 0, 1)


def main():
    sky()
    mountains()
    water()
    boat()
    reeds()
    pap = paper()
    # 洇：墨沿纸纤维向外渗一点
    fib = np.random.default_rng(SEED + 9).random((H, W)).astype(F32)
    fib = ndi.gaussian_filter(fib, (0.5, 2.5)) + ndi.gaussian_filter(fib, (2.5, 0.5))
    fib = smoothstep(0.95, 1.05, fib / fib.mean())
    Dd = np.maximum(D, 0.9 * ndi.gaussian_filter(D, 1.6) * fib)
    canvas = pap.copy()
    D_txt = inscription(canvas)
    Dall = Dd + D_txt
    k = np.array([2.15, 2.2, 2.3], F32)
    canvas = canvas * np.exp(-Dall[..., None] * k[None, None])
    mx, my, mr = MOON
    dist = np.hypot(XX - mx, YY - my)
    lift = (0.55 * smoothstep(mr + 0.8, mr - 1.5, dist) * (0.85 + 0.3 * N_MID))[..., None]   # 月轮点一层白粉
    canvas = canvas * (1 - lift) + np.array([0.975, 0.965, 0.93], F32) * lift
    stamp(canvas, 36, H - 100, 58, "墨戲", white=False)
    Image.fromarray((np.clip(canvas, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
