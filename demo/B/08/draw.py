#!/usr/bin/env python3
"""B08：木桌上的一碗水果和一个陶罐，侧光。

素材（refs/，Wikimedia Commons）：
  - Stillleben_mit-Obst(Kiel)-msu-1181.jpg：黑丝绒前、左侧光照亮的一盘水果 → 抠出水果堆
  - Fruit_bowl_on_woode_table.jpg：俯拍的松木桌面 → 只取左边干净的木纹，变换成低视角的桌面和桌沿
代码画的部分：陶罐和碗体（旋转体光线求交 + 与照片一致的左侧光）、背景、桌面光照、投影和接触阴影、调色。
只读 refs/，不联网，固定种子。用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.interpolate import PchipInterpolator

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402  只用它的 fbm / smoothstep

HERE = os.path.dirname(os.path.abspath(__file__))
REF_FRUIT = os.path.join(HERE, "refs", "Stillleben_mit-Obst(Kiel)-msu-1181.jpg")
REF_WOOD = os.path.join(HERE, "refs", "Fruit_bowl_on_woode_table.jpg")
W, H = 1600, 1200
SEED = 8

TH = np.deg2rad(4.3)                       # 相机俯角（和水果照片里盘沿椭圆的扁度一致）
SN, CS = np.sin(TH), np.cos(TH)
LDIR = np.array([-0.72, -0.30, 0.62])
LDIR = LDIR / np.linalg.norm(LDIR)         # 光从左边、略靠前、偏上照过来
VDIR = np.array([0.0, -CS, SN])            # 指向相机
HALF = (LDIR + VDIR) / np.linalg.norm(LDIR + VDIR)
LIGHT = 1.9 * np.array([1.0, 0.88, 0.72])  # 暖色主光（线性空间强度）

Y_BACK, Y_FRONT = 880, 1050                # 桌面后沿 / 前沿的屏幕 y；前沿以下是桌子的立面
P0 = Y_FRONT                               # 世界坐标：桌面前沿 Y=0，屏幕 y = P0 - Y*SN - Z*CS
JAR = dict(cx=495.0, by=930.0)
BOWL = dict(cx=985.0, by=1015.0)


def lin(x):
    return np.power(np.clip(x, 0, 1), 2.2)


def srgb(x):
    return np.power(np.clip(x, 0, 1), 1 / 2.2)


# ---------------- 旋转体：光线求交 ----------------
class Solid:
    def __init__(self, zr, r_in_top):
        z = np.array([p[0] for p in zr], float)
        r = np.array([p[1] for p in zr], float)
        f = PchipInterpolator(z, r)
        self.Hh, self.R = z[-1], r.max()
        self.zg = np.linspace(0, self.Hh, int(self.Hh * 8) + 1)
        self.rg = f(self.zg)
        self.drg = f.derivative()(self.zg)
        self.r_in = r_in_top

    def r(self, Z):
        return np.interp(Z, self.zg, self.rg, left=-1.0, right=-1.0)

    def dr(self, Z):
        return np.interp(Z, self.zg, self.drg)


def raycast(S, cx, by, ss=2, n_t=260):
    """正交相机、俯角 TH。返回 bbox 左上角 (x0, y0)，以及超采样 ss 倍网格上的命中掩码和命中点局部坐标。"""
    R, Hh = S.R, S.Hh
    x0, x1 = int(np.floor(cx - R - 3)), int(np.ceil(cx + R + 3))
    y0, y1 = int(np.floor(by - Hh * CS - R * SN - 3)), int(np.ceil(by + R * SN + 3))
    xs = x0 + (np.arange((x1 - x0) * ss) + 0.5) / ss
    ys = y0 + (np.arange((y1 - y0) * ss) + 0.5) / ss
    U, Wv = np.meshgrid(xs - cx, by - ys)
    tmax = (R + (Hh + R) * SN) / CS + 3
    ts = np.linspace(-tmax, tmax, n_t)
    th = np.full(U.shape, np.nan)
    for a in range(0, U.shape[0], 16):
        u, w = U[a:a + 16], Wv[a:a + 16]
        Y = w[..., None] * SN + ts * CS
        Z = w[..., None] * CS - ts * SN
        rr = S.r(Z)
        ins = (rr >= 0) & (u[..., None] ** 2 + Y ** 2 <= rr ** 2)
        anyh = ins.any(-1)
        i = ins.argmax(-1)
        lo, hi = ts[np.maximum(i - 1, 0)], ts[i]
        for _ in range(14):
            m = 0.5 * (lo + hi)
            rm = S.r(w * CS - m * SN)
            inside = (rm >= 0) & (u ** 2 + (w * SN + m * CS) ** 2 <= rm ** 2)
            hi, lo = np.where(inside, m, hi), np.where(inside, lo, m)
        th[a:a + 16] = np.where(anyh, hi, np.nan)
    hit = ~np.isnan(th)
    t = np.where(hit, th, 0.0)
    X, Y, Z = U, Wv * SN + t * CS, Wv * CS - t * SN
    return (x0, y0), hit, X, Y, Z


def normals(S, X, Y, Z):
    rr, d = S.r(Z), S.dr(Z)
    N = np.stack([X, Y, -rr * d], -1)
    return N / (np.linalg.norm(N, axis=-1, keepdims=True) + 1e-9)


def self_shadow(S, X, Y, Z, sel, N, n_s=40):
    """从表面点朝光源走，碰到物体自身就算在影子里（例如碗身挡住碗脚）。光源当成有一定大小（5 个方向平均），
    只对朝光的点算，背光一侧交给漫反射的柔和明暗交界，免得出现生硬的交界线。返回 0..1 的受光系数。"""
    lit = np.ones(X.shape, np.float32)
    idx = sel & ((N @ LDIR) > 0.0)
    P = np.stack([X[idx], Y[idx], Z[idx]], -1)
    e1 = np.cross(LDIR, [0, 0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(LDIR, e1)
    dirs = [LDIR] + [LDIR + 0.09 * e for e in (e1, -e1, e2, -e2)]
    acc = np.zeros(len(P), np.float32)
    smax = S.Hh / LDIR[2] + S.R
    for d in dirs:
        d = d / np.linalg.norm(d)
        ok = np.ones(len(P), bool)
        for s_ in np.geomspace(4.0, smax, n_s):
            Q = P + s_ * d
            rq = S.r(Q[:, 2])
            ok &= ~((rq >= 0) & (Q[:, 0] ** 2 + Q[:, 1] ** 2 < (rq - 3.0) ** 2))
        acc += ok
    lit[idx] = acc / len(dirs)
    return ndi.gaussian_filter(lit, 1.5)


def shade(N, alb, ks, shin, wrap=0.12, amb=0.012, bounce=0.07, bounce_col=(0.45, 0.22, 0.10), Z=None, lit=None):
    """alb 为线性空间的反照率。左侧暖光的漫反射（带 wrap 的柔和明暗交界）+ Blinn 高光 + 桌面反光 + 很弱的环境光。"""
    ndl = N @ LDIR
    diff = np.clip((ndl + wrap) / (1 + wrap), 0, 1) ** 1.3
    spec = ks * np.clip(N @ HALF, 0, 1) ** shin * (ndl > 0)
    if lit is not None:                                                          # 自身投影（碗身挡住碗脚等）
        diff, spec = diff * lit, spec * lit
    bnc = bounce * np.clip(-N[..., 2] * 0.8 + 0.2 * N[..., 0], 0, 1)[..., None] * np.array(bounce_col)
    fill = 0.025 * np.clip(N @ np.array([0.7, -0.6, 0.3]) / 1.0, 0, 1)[..., None]
    fill = fill + 0.045 * np.clip(N @ np.array([0.88, 0.40, 0.25]), 0, 1)[..., None] * np.array([1.0, 0.8, 0.6])
    occl = 1.0 if Z is None else (1 - 0.55 * np.exp(-Z / 22.0))[..., None]      # 贴近桌面处的遮蔽
    return alb * (amb + diff[..., None] * LIGHT + bnc + fill) * occl + spec[..., None] * LIGHT


def downsample(img, ss):
    if ss == 1:
        return img
    h, w = img.shape[0] // ss, img.shape[1] // ss
    return img[:h * ss, :w * ss].reshape(h, ss, w, ss, *img.shape[2:]).mean((1, 3))


def paste(canvas, rgb, alpha, x0, y0):
    h, w = alpha.shape
    ys, xs = slice(max(0, y0), min(H, y0 + h)), slice(max(0, x0), min(W, x0 + w))
    a = alpha[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0, None]
    c = rgb[ys.start - y0:ys.stop - y0, xs.start - x0:xs.stop - x0]
    canvas[ys, xs] = canvas[ys, xs] * (1 - a) + c * a


# ---------------- 物体形状 ----------------
JAR_R, JAR_K = 205.0, 600 / 560
jar = Solid([(z * JAR_K, r * JAR_R) for z, r in [(0, .50), (8, .53), (40, .70), (120, .92), (220, 1.0), (320, .95),
                                          (400, .76), (450, .55), (480, .44), (520, .41), (545, .45), (556, .48),
                                          (560, .47)]], 0.40 * JAR_R)

SF = 0.285                                  # 水果照片的缩放
BOWL_R = 1250 * SF * 1.03                   # 碗口半径略大于照片里的盘子
bowl = Solid([(z * BOWL_R / 340, r * BOWL_R) for z, r in [(0, .30), (6, .31), (11, .28), (24, .40), (60, .66), (105, .86),
                                           (145, .97), (165, 1.0)]], BOWL_R - 11)


def build():
    rng = np.random.default_rng(SEED)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # ---------- 背景：暗暖色，左上方被光扫到的地方稍亮 ----------
    g = np.exp(-(((xx - 520) / 700) ** 2 + ((yy - 480) / 520) ** 2))
    n = stylize.fbm(H, W, 260, 4, SEED + 1)
    bgv = 0.0011 + 0.0075 * g * (0.7 + 0.6 * n)
    canvas = bgv[..., None] * np.array([1.0, 0.72, 0.45])[None, None]

    # ---------- 桌面：木纹照片 → 低视角桌面 ----------
    wood = Image.open(REF_WOOD).convert("RGB")
    top_src = wood.crop((0, 200, 1400, 1915))
    rows = Y_FRONT - Y_BACK
    top = lin(np.asarray(top_src.resize((1400, rows), Image.LANCZOS), np.float32) / 255)
    face_src = wood.crop((0, 1960, 1400, 1960 + int((H - Y_FRONT) * 0.875)))
    face = lin(np.asarray(face_src.resize((W, H - Y_FRONT), Image.LANCZOS), np.float32) / 255)
    # 每行按深度做一点透视收缩，横向重采样
    Yw = (P0 - (np.arange(Y_BACK, Y_FRONT) + 0.5)) / SN          # 每行的世界深度
    k = 0.875 * (1 + Yw / 5200.0)                                 # 越远，一个屏幕像素覆盖越多木纹
    top_img = np.zeros((rows, W, 3), np.float32)
    for i in range(rows):
        sx = 700 + (np.arange(W) - W / 2 + 0.5) * k[i]
        for c in range(3):
            top_img[i, :, c] = np.interp(np.clip(sx, 0, 1399), np.arange(1400), top[i, :, c])
    # 木色：压暗、略去饱和、偏棕
    def grade(t):
        g_ = t.mean(-1, keepdims=True)
        t = g_ + 0.78 * (t - g_)
        return t * np.array([0.86, 0.70, 0.52])
    top_img, face = grade(top_img), grade(face)

    # 桌面光照：直射光 N·L，加上画家式的聚光（左中亮、右边和后面暗）
    ty, tx = np.mgrid[Y_BACK:Y_FRONT, 0:W].astype(np.float32)
    spot = 0.12 + 0.88 * np.exp(-(((tx - 640) / 600) ** 2))
    depth_fade = 0.45 + 0.55 * stylize.smoothstep(Y_BACK - 10, Y_BACK + 110, ty)
    shadow = np.ones((rows, W), np.float32)

    # 投影：陶罐、碗（旋转体精确求交），水果堆（剪影分层投到桌面）
    Xt, Yt = tx + 0.5, (P0 - (ty + 0.5)) / SN

    def solid_shadow(S, o):
        Xo, Yo = o["cx"], (P0 - o["by"]) / SN
        zs = np.linspace(0.5, S.Hh, 160)
        s = zs / LDIR[2]
        occ = np.zeros(Xt.shape, bool)
        for z_, s_ in zip(zs, s):
            dx = Xt - Xo + s_ * LDIR[0]
            dy = Yt - Yo + s_ * LDIR[1]
            occ |= dx * dx + dy * dy <= S.r(np.array(z_)) ** 2
        return occ

    occ = solid_shadow(jar, JAR) | solid_shadow(bowl, BOWL)

    # ---------- 陶罐 ----------
    ss = 2
    (jx0, jy0), hit, X, Y, Z = raycast(jar, JAR["cx"], JAR["by"], ss)
    N = normals(jar, X, Y, Z)
    rho = np.hypot(X, Y)
    cap = hit & (Z > jar.Hh - 0.05) & (rho < jar.r(np.array(jar.Hh)) - 0.3)
    mouth = cap & (rho < jar.r_in)
    N[cap] = [0, 0, 1]
    phi = np.arctan2(Y, X)
    # 反照率：赤陶色 + 斑驳 + 拉坯纹 + 口沿和底部颜色深一点
    tex = stylize.fbm(512, 1024, 90, 5, SEED + 3)
    tex2 = stylize.fbm(512, 1024, 18, 3, SEED + 4)
    tu = ((phi + np.pi) / (2 * np.pi) * 1023).clip(0, 1023)
    tv = (Z / jar.Hh * 511).clip(0, 511)
    m1 = ndi.map_coordinates(tex, [tv, tu], order=1)
    m2 = ndi.map_coordinates(tex2, [tv, tu], order=1)
    rings = np.sin(2 * np.pi * Z / 11.0 + 9 * m1 + 4 * m2) * 0.5 + 0.5
    base = np.array([0.66, 0.37, 0.22])
    grain = ndi.map_coordinates(stylize.fbm(512, 1024, 3, 2, SEED + 5), [tv, tu], order=1)
    alb_s = base * (0.92 + 0.12 * m1[..., None]) * (0.94 + 0.10 * m2[..., None]) * (0.985 + 0.025 * rings[..., None])
    alb_s = alb_s * (0.94 + 0.12 * grain[..., None])
    alb_s = alb_s * (1 - 0.18 * stylize.smoothstep(40, 0, Z))[..., None]           # 底部沾灰
    alb_s = alb_s * (1 - 0.12 * stylize.smoothstep(520 * JAR_K, 556 * JAR_K, Z))[..., None]  # 口沿深一点
    alb = lin(alb_s)
    col = shade(N, alb, ks=0.07, shin=12, Z=Z)                                   # 罐身是凸的，不需要自身投影
    col[mouth] = lin(np.array([0.10, 0.05, 0.03])) * 1.0
    col[~hit] = 0
    jar_rgb = downsample(col, ss)
    jar_a = downsample(hit.astype(np.float32), ss)
    jar_rgb = jar_rgb / np.maximum(jar_a, 1e-6)[..., None]

    # ---------- 碗 ----------
    (bx0, by0), bhit, BX, BY, BZ = raycast(bowl, BOWL["cx"], BOWL["by"], ss)
    BN = normals(bowl, BX, BY, BZ)
    brho = np.hypot(BX, BY)
    bcap = bhit & (BZ > bowl.Hh - 0.05) & (brho < bowl.R - 0.3)
    inner = bcap & (brho < bowl.r_in)
    rim = bcap & ~inner
    BN[bcap] = [0, 0, 1]
    bphi = np.arctan2(BY, BX)
    bt = ndi.map_coordinates(tex, [(BZ / bowl.Hh * 300).clip(0, 511), ((bphi + np.pi) / (2 * np.pi) * 1023)], order=1)
    spk = ndi.map_coordinates(stylize.fbm(512, 1024, 2, 1, SEED + 6), [(BZ / bowl.Hh * 511).clip(0, 511),
                              ((bphi + np.pi) / (2 * np.pi) * 1023)], order=1)
    speck = 1 - 0.35 * stylize.smoothstep(0.80, 0.9, spk)                              # 粗陶釉面上的小黑点
    balb = lin(np.array([0.74, 0.63, 0.45]) * (0.88 + 0.20 * bt[..., None]) * speck[..., None])  # 奶油色釉
    blit = self_shadow(bowl, BX, BY, BZ, bhit & ~bcap & (BZ < 0.3 * bowl.Hh), BN)   # 只有碗脚会被碗身挡住
    bcol = shade(BN, balb, ks=0.45, shin=90, Z=BZ, lit=blit, bounce=0.16)
    bcol += 0.10 * (np.clip(BN @ HALF, 0, 1) ** 14 * blit)[..., None] * LIGHT          # 釉面的宽泛光泽（左前方一道亮）
    # 碗内壁：左侧光照进来，右边内壁亮，左边内壁暗
    bcol[inner] = (balb[inner] * (0.01 + 0.18 * stylize.smoothstep(-0.2, 1.0, BX[inner] / bowl.r_in))[:, None]
                   * LIGHT)
    front_layer = bhit & ~inner & ~(rim & (BY > 0))                                    # 外壁 + 前半圈碗沿
    back_layer = inner | (rim & (BY > 0))
    bcol[~bhit] = 0
    bowl_rgb = downsample(bcol, ss)
    bf_a = downsample(front_layer.astype(np.float32), ss)
    bb_a = downsample(back_layer.astype(np.float32), ss)
    ball = np.maximum(bf_a + bb_a, 1e-6)
    bowl_rgb = bowl_rgb / ball[..., None]

    # ---------- 水果：从照片抠出来 ----------
    ph = Image.open(REF_FRUIT).convert("RGB")
    CX0, CY0, CW, CH = 850, 1000, 2800, 1500
    crop = ph.crop((CX0, CY0, CX0 + CW, CY0 + CH))
    fw, fh = int(round(CW * SF)), int(round(CH * SF))
    fr = np.asarray(crop.resize((fw, fh), Image.LANCZOS), np.float32) / 255
    small = np.asarray(crop.reduce(2), np.float32) / 255                     # 在 1/2 分辨率上做掩码
    sm = ndi.gaussian_filter(small, (3, 3, 0))
    V = sm.max(2)
    m = (V > 0.06) & (V - sm.min(2) > 0.06)                                  # 丝绒是灰的，水果即使在暗部也有颜色
    m = ndi.binary_opening(m, iterations=2)
    lab, nl = ndi.label(m)
    m = lab == (np.argmax(ndi.sum(m, lab, range(1, nl + 1))) + 1)
    m = ndi.binary_fill_holes(ndi.binary_closing(m, iterations=4))
    m = ndi.binary_erosion(m, iterations=1)                                  # 去掉边上一圈黑丝绒
    # 切掉盘子：盘沿上缘以下（照片坐标：盘心 x=1430，上缘中间 y=1260、两端 y=1166，半径 1250）
    hy, hx = np.mgrid[0:m.shape[0], 0:m.shape[1]] * 2.0
    q = np.clip(1 - ((hx - 1430) / 1250) ** 2, 0, 1)
    plate_top = 1166 + 94 * np.sqrt(q)
    m &= hy < plate_top + 6
    ma = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((fw, fh), Image.LANCZOS), np.float32) / 255
    ma = ndi.gaussian_filter(ma, 0.6)
    # 边缘去污：半透明边上的颜色换成最近的内部颜色，免得带出黑边
    core = ndi.binary_erosion(ma > 0.5, iterations=2)
    _, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
    fr = np.where((ma < 0.999)[..., None] | ~core[..., None], fr[iy, ix], fr)
    gray = fr.mean(-1, keepdims=True)
    fr = gray + 0.86 * (fr - gray)                                           # 照片的饱和度收一点
    fruit = lin(fr)
    # 放到碗里：照片盘心对准碗心，盘沿上缘略低于碗沿（水果底部被碗沿挡住）
    fox = int(round(BOWL["cx"] - 1430 * SF))
    rim_front_y = BOWL["by"] - (bowl.Hh * CS - bowl.R * SN)
    foy = int(round(rim_front_y - 1260 * SF + 7))
    # 碗沿附近的水果压暗一点（接触处的遮蔽）
    fy_c = np.arange(fh)[:, None] + foy
    fx_c = np.arange(fw)[None, :] + fox
    uu = np.clip(1 - ((fx_c - BOWL["cx"]) / bowl.R) ** 2, 0, 1)
    rim_y = BOWL["by"] - (bowl.Hh * CS - np.sqrt(uu) * bowl.R * SN)
    ao = 1 - 0.45 * np.exp(-np.clip(rim_y - fy_c, 0, None) / 14.0)
    fruit = fruit * ao[..., None]

    # 水果堆的投影：按剪影每一行的左右端点，把水果堆当成一叠椭圆截面（前后厚度取宽度的一部分），沿光线投到桌面
    Xo_b, Yo_b = BOWL["cx"], (P0 - BOWL["by"]) / SN
    for row in range(0, fh, 2):
        xsr = np.nonzero(ma[row] > 0.5)[0]
        if len(xsr) < 4:
            continue
        z_ = (BOWL["by"] - (row + foy)) / CS
        if z_ < bowl.Hh * 0.8:
            continue
        c_ = 0.5 * (xsr[0] + xsr[-1]) + fox
        a_ = 0.5 * (xsr[-1] - xsr[0])
        b_ = min(a_, 0.8 * bowl.R)
        s_ = z_ / LDIR[2]
        dx = Xt - c_ + s_ * LDIR[0]
        dy = Yt - Yo_b + s_ * LDIR[1]
        occ |= (dx / a_) ** 2 + (dy / b_) ** 2 <= 1
    occf = ndi.gaussian_filter(occ.astype(np.float32), (1.5, 7))
    shadow = 1 - 0.9 * occf

    # 接触阴影
    def contact(o, r_foot):
        return np.exp(-(((tx - o["cx"]) / (r_foot * 1.15)) ** 2 + ((ty - o["by"]) / (r_foot * 1.15 * SN + 5)) ** 2))
    ao_t = 1 - 0.75 * np.maximum(contact(JAR, jar.r(np.array(0.0))), contact(BOWL, bowl.r(np.array(0.0))))

    ndl_top = LDIR[2]
    top_lit = top_img * (0.01 + ndl_top * LIGHT * spot[..., None] * depth_fade[..., None] * shadow[..., None]) \
        * ao_t[..., None]
    canvas[Y_BACK:Y_FRONT] = top_lit
    # 桌沿立面：受光比桌面少，越往下越暗；前沿一道亮边
    fy, fx = np.mgrid[Y_FRONT:H, 0:W].astype(np.float32)
    fspot = 0.12 + 0.88 * np.exp(-(((fx - 640) / 600) ** 2))
    fdown = 1 - 0.7 * stylize.smoothstep(Y_FRONT, H, fy)
    canvas[Y_FRONT:] = face * (0.006 + 0.55 * (-LDIR[1]) * LIGHT * fspot[..., None] * fdown[..., None])
    edge = np.exp(-((fy - Y_FRONT - 1.5) / 1.6) ** 2) * fspot
    canvas[Y_FRONT:] += (0.06 * edge)[..., None] * LIGHT * np.array([0.9, 0.7, 0.5])
    # 桌面后沿：一条很淡的亮线把桌子和背景分开
    back_edge = np.exp(-((yy - Y_BACK) / 1.2) ** 2) * (0.3 + 0.7 * np.exp(-(((xx - 600) / 700) ** 2)))
    canvas += (0.006 * back_edge)[..., None] * LIGHT

    # ---------- 合成 ----------
    paste(canvas, jar_rgb, jar_a, jx0, jy0)
    paste(canvas, bowl_rgb, bb_a, bx0, by0)
    paste(canvas, fruit, ma, fox, foy)
    paste(canvas, bowl_rgb, bf_a, bx0, by0)

    # ---------- 收尾：暗角、颗粒 ----------
    r = np.hypot((xx - W * 0.46) / (W * 0.62), (yy - H * 0.56) / (H * 0.62))
    canvas *= (1 - 0.45 * stylize.smoothstep(0.55, 1.25, r))[..., None]
    out = srgb(canvas).astype(np.float32)
    # 统一成油画质感：各向异性 Kuwahara 概括（照片和代码画的部分一起变成“笔触”）
    # + 顺着笔势的鬃毛纹（噪声沿流场做线积分）+ 画布纹理的起伏打光 + 旧光油的暖色
    paint = stylize.aniso_kuwahara(out, 1.0, radius=4.5, q=8.0)
    Lp = paint @ stylize.LUMA
    tx_, ty_, coh = stylize.flow_field(ndi.gaussian_filter(Lp, 1.0), 1.0, sigma=2.0, rho=8.0)
    wf = stylize.smoothstep(0.15, 0.5, coh)                                     # 平坦处方向乱，改成横向运笔，免得出现蚯蚓纹
    sg = np.where(tx_ < 0, -1.0, 1.0)
    tx_, ty_ = wf * tx_ * sg + (1 - wf), wf * ty_ * sg
    nn = np.hypot(tx_, ty_) + 1e-6
    tx_, ty_ = (tx_ / nn).astype(np.float32), (ty_ / nn).astype(np.float32)
    st = stylize.lic(rng.random((H, W)).astype(np.float32), tx_, ty_, 14)
    st = (st - st.mean()) / (st.std() + 1e-6)
    hgt = ndi.gaussian_filter(0.6 * st + 0.5 * stylize.canvas_texture(H, W, 1.0, SEED + 9), 0.8)
    gy_, gx_ = np.gradient(hgt)
    relief = 0.6 * gx_ + 0.8 * gy_                                              # 左上方来的光照在颜料起伏上
    paint = paint * (1 + 0.025 * st + 0.07 * relief)[..., None]
    out = paint * np.array([1.0, 0.975, 0.92], np.float32)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    build().save(dst)
    print(dst)
