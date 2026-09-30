#!/usr/bin/env python3
"""B12：日系动画背景——夏日乡间小路和积雨云。

素材（refs/，Wikimedia Commons 照片）：
  - Aomori_countryside,...(21).jpg：青森郊外一条笔直的乡间公路，两边是草地和田 → 地面部分
  - 2016_Chmura_Cumulus_congestus_01.jpg：一座浓积云塔 → 云的形状和细部
动画画风全部由代码做：天空渐变重画、远山用代码画、云按形状算光照后分成几档色阶、地面做 L0 平涂 + 调成动画的饱和配色、
电线杆和电线按照片的透视用代码画。只读 refs/，不联网，固定种子。用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF_ROAD = os.path.join(HERE, "refs", "Aomori_countryside,_Aomori_Prefecture;_June_2010_(21).jpg")
REF_CLOUD = os.path.join(HERE, "refs", "2016_Chmura_Cumulus_congestus_01.jpg")
W, H = 1600, 900
SEED = 12
VP = (745.0, 598.0)          # 照片里公路的消失点（也是地平线高度）
FOCAL = 1070.0               # 由路中间虚线的间距估出来的焦距（像素）
CAM_H = 1.5                  # 相机高度（米）


def sstep(a, b, x):
    return stylize.smoothstep(a, b, x)


def rgb2hsv(c):
    mx, mn = c.max(-1), c.min(-1)
    d = mx - mn + 1e-8
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    h = np.where(mx - mn < 1e-6, 0, h)
    return np.stack([h, (mx - mn) / (mx + 1e-8), mx], -1)


def hsv2rgb(hsv):
    h, s, v = hsv[..., 0] * 6, hsv[..., 1], hsv[..., 2]
    i = np.floor(h) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    conds = [i == k for k in range(6)]
    r = np.select(conds, [v, q, p, p, t, v])
    g = np.select(conds, [t, v, v, q, p, p])
    b = np.select(conds, [p, p, t, v, v, q])
    return np.stack([r, g, b], -1)


def horizon_line(g):
    """每一列里天空和地面（树林、田、远处）的分界：从上往下找第一段连续变暗的地方；再用横向中值滤波去掉铁塔之类的细刺。"""
    V = ndi.gaussian_filter(g.max(2), 1.0)
    dark = V < 0.42
    run = dark & np.roll(dark, -1, 0) & np.roll(dark, -2, 0)
    y0 = 520
    first = np.argmax(run[y0:640], axis=0) + y0
    first = np.where(run[y0:640].any(0), first, 600)
    first = ndi.median_filter(first, 25, mode="nearest")
    return ndi.gaussian_filter1d(first.astype(np.float32), 2.0)


def anime_cloud(ph, box, k, main=True, sun=(-0.55, -0.75, 0.45), shares=(0.24, 0.47, 0.70), stretch=1.0):
    """照片里的一块云 → 动画式的云：不偏蓝的地方当云，边缘收干净；明暗 = 照片亮度 + 局部对比（鼓包）+ 按外形算的穹顶光照
    + 越往下越暗，再按分位数分成四档（阴影、亮阴影、中间、受光白），每档之间留很窄的过渡。返回 (颜色, alpha)。"""
    PW, PH = ph.size
    crop = (int(box[0] * PW), int(box[1] * PH), int(box[2] * PW), int(box[3] * PH))
    cw, ch = int((crop[2] - crop[0]) * k), int((crop[3] - crop[1]) * k * stretch)   # stretch>1：往高里拉，更像“塔”
    c = np.asarray(ph.crop(crop).resize((cw, ch), Image.LANCZOS), np.float32) / 255
    cs = ndi.gaussian_filter(c, (1.2, 1.2, 0))
    V = cs.max(2)
    blue = cs[..., 2] - cs[..., 0]
    a_col = sstep(0.20, 0.07, blue)                                   # 不偏蓝的就是云
    py = np.arange(ch)[:, None] * np.ones((1, cw))
    px_ = np.ones((ch, 1)) * np.arange(cw)[None, :]
    if main:
        dense = (V > 0.84) & (blue < 0.10)
        dense = ndi.binary_opening(dense, iterations=2)
        lab, n = ndi.label(dense)
        dense = lab == (np.argmax(ndi.sum(dense, lab, range(1, n + 1))) + 1)
        base = (py > 0.55 * ch) & (px_ > 0.08 * cw) & (px_ < 0.80 * cw)
        keep = ndi.binary_dilation(dense, iterations=18) | base        # 云塔 + 塔下的云底；左上的薄卷云、右边的灰云不要
        win = ndi.gaussian_filter(keep.astype(np.float32), 10)
    else:
        win = np.ones_like(V)
    alpha = a_col * sstep(0.55, 0.72, V) * win
    alpha = sstep(0.35, 0.7, ndi.gaussian_filter(alpha, 1.0))        # 动画式的干净边缘
    alpha = np.maximum(alpha, ndi.binary_fill_holes(alpha > 0.5).astype(np.float32))

    L = cs @ stylize.LUMA
    inside = alpha > 0.5
    lo, hi = np.percentile(L[inside], [4, 97])
    Ln = np.clip((L - lo) / (hi - lo), 0, 1)
    mu = ndi.gaussian_filter(L, 14 * k / 0.34)
    sd = np.sqrt(np.maximum(ndi.gaussian_filter(L * L, 14 * k / 0.34) - mu * mu, 0)) + 0.012
    local = np.clip(0.5 + 0.22 * (L - mu) / sd, 0, 1)                 # 菜花状的鼓包（局部对比归一化）
    dome = ndi.gaussian_filter(alpha, 28 * k / 0.34)                  # 用外形做一个穹顶高度场，算大的明暗
    gy, gx = np.gradient(dome)
    nx, ny, nz = -gx * 60, -gy * 60, np.ones_like(gx)
    nn = np.sqrt(nx * nx + ny * ny + nz * nz)
    sv = np.array(sun) / np.linalg.norm(sun)
    lam = (nx * sv[0] + ny * sv[1] + nz * sv[2]) / nn
    vert = 1 - sstep(0.25 * ch, 0.80 * ch, py)                        # 越往下越背光
    T = 0.28 * Ln + 0.22 * local + 0.22 * lam + 0.28 * vert
    T = ndi.gaussian_filter(T, 2.2 * k / 0.34)                        # 色块成片，不要碎斑
    rank = stylize.rank01(T, inside)
    Tq = np.interp(rank, [0.0, shares[0], shares[1], shares[2], 1.0], [0.0, 0.15, 0.425, 0.675, 0.8])
    levels = [0.0, 0.30, 0.55, 0.80]
    q = stylize.soft_quantize(Tq, levels, soft=0.18)
    pal = np.array([[0.50, 0.55, 0.83], [0.66, 0.72, 0.93], [0.85, 0.89, 0.99], [1.0, 0.99, 0.95]])
    idx = np.interp(q, levels, np.arange(4))
    i0 = np.clip(np.floor(idx).astype(int), 0, 2)
    f = (idx - i0)[..., None]
    col = pal[i0] * (1 - f) + pal[i0 + 1] * f
    # 受光一侧的边缘再提亮一圈（动画里云的亮边）
    edge = np.clip(alpha - ndi.gaussian_filter(alpha, 3), 0, 1) * np.clip(lam * 1.6 - 0.4, 0, 1)
    col = col + (sstep(0.02, 0.12, edge))[..., None] * (np.array([1.0, 1.0, 0.98]) - col) * 0.9
    return col, alpha


def puff_cloud(w, h, seed):
    """代码画的小积云：沿顶部撒一串大小不一的圆形鼓包（高斯），底部削平；按外形算穹顶光照，分四档上色。"""
    r = np.random.default_rng(seed)
    cw, ch = w + 20, h + 20
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    field = np.zeros((ch, cw), np.float32)
    n = max(5, w // 28)
    for i in range(n):
        u = (i + 0.5) / n
        cx = 10 + u * w
        rad = (0.35 + 0.65 * np.sin(np.pi * u) ** 0.8) * h * r.uniform(0.45, 0.62)
        cy = 10 + h - rad * r.uniform(0.9, 1.25)
        field = np.maximum(field, 1 - ((xx - cx) ** 2 + (yy - cy) ** 2) / rad ** 2)
    flat_bottom = 1 - sstep(10 + h - 6, 10 + h, yy)
    alpha = sstep(0.0, 0.08, field) * flat_bottom
    dome = ndi.gaussian_filter(alpha, 6)
    gy, gx = np.gradient(dome)
    nx, ny, nz = -gx * 30, -gy * 30, np.ones_like(gx)
    sv = np.array([-0.55, -0.75, 0.45]) / np.linalg.norm([-0.55, -0.75, 0.45])
    lam = (nx * sv[0] + ny * sv[1] + nz * sv[2]) / np.sqrt(nx * nx + ny * ny + nz * nz)
    T = 0.5 * lam + 0.5 * (1 - sstep(10 + 0.2 * h, 10 + h, yy)) + 0.1 * np.clip(field, 0, 1)
    rank = stylize.rank01(T, alpha > 0.5)
    Tq = np.interp(rank, [0.0, 0.22, 0.45, 0.62, 1.0], [0.0, 0.15, 0.425, 0.675, 0.8])
    levels = [0.0, 0.30, 0.55, 0.80]
    q = stylize.soft_quantize(Tq, levels, soft=0.2)
    pal = np.array([[0.62, 0.70, 0.88], [0.75, 0.82, 0.95], [0.88, 0.92, 0.99], [1.0, 0.995, 0.97]])
    idx = np.interp(q, levels, np.arange(4))
    i0 = np.clip(np.floor(idx).astype(int), 0, 2)
    f = (idx - i0)[..., None]
    return pal[i0] * (1 - f) + pal[i0 + 1] * f, alpha


def put(canvas, col, alpha, ox, oy):
    ch, cw = alpha.shape
    ys, xs = slice(max(0, oy), min(H, oy + ch)), slice(max(0, ox), min(W, ox + cw))
    a = alpha[ys.start - oy:ys.stop - oy, xs.start - ox:xs.stop - ox, None]
    canvas[ys, xs] = canvas[ys, xs] * (1 - a) + col[ys.start - oy:ys.stop - oy, xs.start - ox:xs.stop - ox] * a


def sky_and_clouds(rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = np.clip(yy / VP[1], 0, 1) ** 1.35
    top, hor = np.array([0.10, 0.36, 0.84]), np.array([0.66, 0.85, 0.97])
    sky = top * (1 - t[..., None]) + hor * t[..., None]
    sky = sky + 0.03 * (1 - t[..., None]) * (xx / W - 0.5)[..., None] * np.array([-1, -0.3, 0.5])  # 右上略深
    ph = Image.open(REF_CLOUD).convert("RGB")
    # 左边远处两小团积云：代码生成（一串高斯鼓包叠成的高度场，平底），和主云用同一套色阶
    for (cx_, by_, w_, h_, sd_) in ((215, 548, 250, 95, 1), (430, 300, 150, 52, 2)):
        col2, a2 = puff_cloud(w_, h_, SEED + 20 + sd_)
        put(sky, col2, a2, cx_ - w_ // 2 - 10, by_ - a2.shape[0] + 10)
    # 主角：积雨云塔，中心在消失点右边
    col, alpha = anime_cloud(ph, (0.22, 0.13, 0.90, 1.0), 0.34, stretch=1.2)
    put(sky, col, alpha, 905 - int(0.48 * alpha.shape[1]), 8)
    # 地平线附近的空气透视：云底融进薄雾
    haze = sstep(VP[1] - 130, VP[1], yy)[..., None]
    sky = sky * (1 - 0.55 * haze) + hor * 0.55 * haze
    return sky


def mountains(canvas, rng):
    """远山：两层，用分形噪声做山脊线，平涂 + 一点上下渐变。"""
    xs = np.arange(W, dtype=np.float32)
    n1 = stylize.fbm(1, W, 260, 4, SEED + 1)[0]
    n2 = stylize.fbm(1, W, 140, 4, SEED + 2)[0]
    env = np.exp(-((xs - 380) / 330) ** 2)
    n3 = stylize.fbm(1, W, 40, 3, SEED + 3)[0]
    ridge_far = VP[1] - 12 - 44 * env * (0.45 + 0.9 * n1) - 10 * env * n3
    env2 = np.exp(-((xs - 180) / 260) ** 2) + 0.6 * np.exp(-((xs - 560) / 150) ** 2)
    ridge_near = VP[1] - 6 - 24 * env2 * (0.4 + 1.0 * n2) - 5 * n3
    yy = np.arange(H, dtype=np.float32)[:, None]
    for ridge, col, fade in ((ridge_far, np.array([0.56, 0.71, 0.84]), 0.25), (ridge_near, np.array([0.38, 0.58, 0.64]), 0.15)):
        m = sstep(ridge[None, :] - 0.8, ridge[None, :] + 0.8, yy)
        grad = 1 - fade * sstep(ridge[None, :], VP[1], yy)
        canvas[:] = canvas * (1 - m[..., None]) + (col * (0.92 + 0.08 * grad[..., None])) * m[..., None]
    return canvas


def ground_anime(g, hline):
    """地面：L0 平涂概括 + 动画配色（草更黄绿更饱和、暗部不死黑偏青）+ 近处保留一点草的笔触。"""
    flat = stylize.l0_smooth(g, lam=0.008)
    hsv = rgb2hsv(np.clip(flat, 0, 1))
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = sstep(0.12, 0.17, h) * (1 - sstep(0.45, 0.52, h)) * sstep(0.12, 0.25, s)
    h = h + green * 0.35 * (0.235 - h)
    s = np.clip(s * (1 + 0.55 * green), 0, 1)
    v = 0.07 + 0.93 * np.clip(v, 0, 1) ** 0.78
    out = hsv2rgb(np.stack([h, s, v], -1))
    # 路面：按照片的透视取路面楔形（左右边缘离相机 -3.2 m / +5.6 m），再要求原照片里不偏绿；统一成偏蓝的灰，远处更淡
    yy_, xx_ = np.mgrid[0:H, 0:W].astype(np.float32)
    dy = np.maximum(yy_ - VP[1], 0.5)
    Xm = (xx_ - VP[0]) * CAM_H / dy                                    # 每个地面像素的横向位置（米）
    wedge = sstep(-3.4, -3.1, Xm) * (1 - sstep(5.5, 5.8, Xm)) * sstep(VP[1] + 1, VP[1] + 4, yy_)
    gb = ndi.gaussian_filter(g, (3, 3, 0))
    greenish = sstep(0.03, 0.07, gb[..., 1] - np.maximum(gb[..., 0], gb[..., 2]))
    greenish = ndi.gaussian_filter(ndi.binary_opening(greenish > 0.5, iterations=3).astype(np.float32), 1.0)
    road = wedge * (1 - greenish)
    Lr = ndi.gaussian_filter(flat.mean(-1), 1.0)
    dist = 1 - sstep(VP[1] + 5, VP[1] + 300, yy_)
    asphalt = np.array([0.35, 0.37, 0.44]) * (1 - dist[..., None]) + np.array([0.56, 0.60, 0.68]) * dist[..., None]
    tex = stylize.fbm(H, W, 60, 4, SEED + 5)
    road_col = asphalt * (0.95 + 0.08 * tex[..., None])                # 路面的白线由代码重画（见 road_marks）
    out = out * (1 - road[..., None]) + road_col * road[..., None]
    # 暗部偏青
    out = out + ((1 - v) ** 2)[..., None] * np.array([-0.03, 0.0, 0.05])
    # 近处的草：把照片的细节按亮暗分档后加回来（像手绘的草叶笔触）
    det = (g - ndi.gaussian_filter(g, (1.6, 1.6, 0))).mean(-1)
    det = np.tanh(det * 12) * 0.06
    yy = np.arange(H, dtype=np.float32)[:, None]
    near = sstep(hline[None, :] + 20, hline[None, :] + 200, yy)
    out = out + (det * near * green)[..., None]
    # 空气透视：越靠地平线越淡、越偏蓝
    far = 1 - sstep(hline[None, :], hline[None, :] + 60, yy)
    out = out * (1 - 0.35 * far[..., None]) + np.array([0.60, 0.75, 0.85]) * 0.35 * far[..., None]
    return np.clip(out, 0, 1)


def poles_and_wires():
    """电线杆沿路右侧排向消失点，电线按悬链线在三维里取点再投影。2 倍超采样画，缩小抗锯齿。"""
    S = 2
    layer = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)

    def proj(X, Yh, Z):                       # X 右，Yh 离地高度，Z 深度（米）
        return (VP[0] + FOCAL * X / Z) * S, (VP[1] + FOCAL * (CAM_H - Yh) / Z) * S

    Xp, Hp = 6.0, 11.0
    Zs = [9.0 + 32.0 * i for i in range(12)]
    pole_col, lit_col = (70, 74, 86, 255), (150, 150, 158, 255)
    arm_h = [Hp - 0.6, Hp - 2.2]
    wire_pts = {}
    for Z in Zs:
        xb, yb = proj(Xp, 0, Z)
        xt, yt = proj(Xp, Hp, Z)
        wpx = max(1.0, FOCAL * 0.32 / Z * S)
        if wpx < 6:
            dr.polygon([(xb - wpx / 2, yb), (xb + wpx / 2, yb), (xt + wpx * 0.35, yt), (xt - wpx * 0.35, yt)],
                       fill=pole_col)
        else:                                                               # 近处的杆：分几条竖带画出圆柱的明暗
            bands = [(0.00, (178, 178, 182)), (0.18, (150, 151, 158)), (0.42, (118, 120, 132)), (0.70, (88, 90, 104)),
                     (0.88, (70, 72, 88))]
            for (f0, colb), f1 in zip(bands, [b[0] for b in bands[1:]] + [1.0]):
                pb0, pb1 = xb - wpx / 2 + f0 * wpx, xb - wpx / 2 + f1 * wpx
                tt0, tt1 = xt - wpx * 0.35 + f0 * wpx * 0.7, xt - wpx * 0.35 + f1 * wpx * 0.7
                dr.polygon([(pb0, yb), (pb1, yb), (tt1, yt), (tt0, yt)], fill=colb + (255,))
            # 路边电线杆下部的黄黑斜纹护套
            xg0, yg0 = proj(Xp, 1.1, Z)
            xg1, yg1 = proj(Xp, 1.8, Z)
            nst = 5 if Z < 20 else 0
            for k_ in range(nst):
                y_a = yg0 + (yg1 - yg0) * k_ / nst
                y_b = yg0 + (yg1 - yg0) * (k_ + 1) / nst
                sk = (yg1 - yg0) / nst * 0.6
                colg = (238, 196, 30, 255) if k_ % 2 == 0 else (35, 35, 40, 255)
                dr.polygon([(xb - wpx * 0.52, y_a), (xb + wpx * 0.52, y_a + sk), (xb + wpx * 0.52, y_b + sk),
                            (xb - wpx * 0.52, y_b)], fill=colg)
            for i_, hh in enumerate(np.arange(2.4, Hp, 0.45)):              # 脚钉，左右交替
                sd_ = 1 if i_ % 2 == 0 else -1
                xs_, ys_ = proj(Xp + 0.15 * sd_, hh, Z)
                dr.line([(xs_, ys_), (xs_ + sd_ * wpx * 0.22, ys_)], fill=(70, 72, 84, 255), width=max(1, int(wpx * 0.07)))
        for j, ah in enumerate(arm_h):                                   # 横担
            xa0, ya = proj(Xp - 1.1, ah, Z)
            xa1, _ = proj(Xp + 1.1, ah, Z)
            dr.line([(xa0, ya), (xa1, ya)], fill=pole_col, width=max(1, int(wpx * 0.35)))
        for dx in (-0.95, 0.0, 0.95):
            wire_pts.setdefault(("hi", dx), []).append((Xp + dx, arm_h[0] + 0.25, Z))
        for dx in (-0.9, 0.9):
            wire_pts.setdefault(("lo", dx), []).append((Xp + dx, arm_h[1] + 0.2, Z))
    wire_col = (40, 44, 58, 235)
    for key, pts in wire_pts.items():
        # 最近那根杆之前的一段：往相机方向伸出画面
        seq = [(pts[0][0], pts[0][1] + 0.8, 1.2)] + pts
        for (x0, y0, z0), (x1, y1, z1) in zip(seq[:-1], seq[1:]):
            tt = np.linspace(0, 1, 60)
            X = x0 + (x1 - x0) * tt
            Z = z0 + (z1 - z0) * tt
            sag = 0.9 * (4 * tt * (1 - tt)) * min(1.0, abs(z1 - z0) / 32)
            Yh = y0 + (y1 - y0) * tt - sag
            P = [proj(a, b, c) for a, b, c in zip(X, Yh, Z)]
            wdt = max(1, int(round(2.2 * S * min(1.0, 14.0 / max(z0, 1)))))
            dr.line(P, fill=wire_col, width=wdt)
    # 左边路肩那根红白标杆（照片里有，重画成动画的样子）
    x, y0, y1 = 587 * S, 568 * S, 655 * S
    for i, yb in enumerate(np.linspace(y0, y1, 9)[:-1]):
        dr.rectangle([x - 3 * S, yb, x + 3 * S, yb + (y1 - y0) / 8], fill=(222, 50, 48, 255) if i % 2 == 0 else (245, 245, 240, 255))
    return layer.resize((W, H), Image.LANCZOS)


def road_marks():
    """路面白线：按照片的透视重画——左右边线（离相机 -2.48 m、+4.92 m）实线，中线（+1.22 m）5 m 一段、间隔 5 m。"""
    S = 3
    layer = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    white = (236, 238, 240, 255)

    def quad(X0, X1, Z0, Z1):
        pts = []
        for X, Z in ((X0, Z0), (X1, Z0), (X1, Z1), (X0, Z1)):
            pts.append(((VP[0] + FOCAL * X / Z) * S, (VP[1] + FOCAL * CAM_H / Z) * S))
        dr.polygon(pts, fill=white)

    for Xc in (-2.48, 4.92):
        quad(Xc - 0.08, Xc + 0.08, 2.5, 900.0)
    z = 4.6
    while z < 700:
        quad(1.22 - 0.08, 1.22 + 0.08, z, z + 5.0)
        z += 10.0
    return layer.resize((W, H), Image.LANCZOS)


def build():
    rng = np.random.default_rng(SEED)
    g = np.asarray(Image.open(REF_ROAD).convert("RGB").resize((W, H), Image.LANCZOS), np.float32) / 255
    hline = horizon_line(g)
    sky = sky_and_clouds(rng)
    sky = mountains(sky, rng)
    ground = ground_anime(g, hline)
    yy = np.arange(H, dtype=np.float32)[:, None]
    gm = sstep(hline[None, :] - 1.0, hline[None, :] + 1.0, yy)[..., None]
    img = sky * (1 - gm) + ground * gm
    # 泛光：亮处（云、白线）往外晕一点，夏天强光的感觉
    Lb = img @ stylize.LUMA
    bright = sstep(0.80, 0.98, Lb)
    glow = ndi.gaussian_filter(img * bright[..., None], (20, 20, 0))
    img = 1 - (1 - img) * (1 - 0.22 * glow * (1 - 0.7 * ndi.gaussian_filter(bright, 3))[..., None])  # 主要晕到云外面，云里的阴影不冲淡
    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).convert("RGBA")
    out = Image.alpha_composite(out, road_marks())
    out = Image.alpha_composite(out, poles_and_wires()).convert("RGB")
    return out


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    build().save(dst)
    print(dst)
