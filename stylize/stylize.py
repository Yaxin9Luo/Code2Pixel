"""照片风格化：不调用任何模型，只用图像处理和计算机图形学的方法把照片变成某种画风。

风格：
  ink         水墨：墨色浓淡、留白、积墨、晕染、轮廓线、宣纸纹理
  watercolor  水彩：透明薄涂、边缘积色、颜料颗粒、纸白、边界晃动
  lowpoly     低多边形：按边缘撒点做 Delaunay 三角剖分，输出 SVG

用法:
  python3 stylize.py input.jpg --style ink --out out.png
  python3 stylize.py input.jpg --style lowpoly --out out.svg
函数接口: stylize(PIL.Image, style, strength=1.0, seed=0, size=1600) -> PIL.Image 或 SVG 文本
依赖: numpy、scipy、Pillow
"""
import argparse
import ctypes
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

LUMA = np.array([0.299, 0.587, 0.114])


# ---------------- 基础工具 ----------------
def box(x, r):
    """半径 r 的均值滤波（对每个通道）。"""
    size = [2 * r + 1, 2 * r + 1] + [1] * (x.ndim - 2)
    return ndi.uniform_filter(x, size=size, mode="reflect")


def guided(I, p, r, eps):
    """引导滤波（He et al.）：用灰度图 I 引导，对 p（灰度或彩色）做保边平滑。"""
    if p.ndim == 3:
        return np.stack([guided(I, p[..., c], r, eps) for c in range(p.shape[2])], -1)
    mI, mp = box(I, r), box(p, r)
    cov = box(I * p, r) - mI * mp
    var = box(I * I, r) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return box(a, r) * I + box(b, r)


def kuwahara(img, r):
    """Kuwahara 滤波：每个像素取四个象限里亮度方差最小的那个的平均色，得到笔触感的简化。"""
    g = img @ LUMA
    k = r + 1
    m = ndi.uniform_filter(img, size=(k, k, 1), mode="reflect")
    mg = ndi.uniform_filter(g, size=k, mode="reflect")
    vg = ndi.uniform_filter(g * g, size=k, mode="reflect") - mg * mg
    best_v = np.full(g.shape, np.inf)
    out = np.zeros_like(img)
    h = r // 2
    for dy in (-h, h - (r % 2 == 0)):
        for dx in (-h, h - (r % 2 == 0)):
            v = np.roll(vg, (dy, dx), axis=(0, 1))
            mm = np.roll(m, (dy, dx), axis=(0, 1))
            sel = v < best_v
            best_v = np.where(sel, v, best_v)
            out[sel] = mm[sel]
    return out


def fbm(h, w, scale, octaves=4, seed=0):
    """分形噪声，值域约 [0, 1]。scale 为最大一层的格子大小（像素）。"""
    r = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for _ in range(octaves):
        gh, gw = max(2, int(h / scale) + 2), max(2, int(w / scale) + 2)
        grid = r.random((gh, gw)).astype(np.float32)
        out += amp * np.asarray(Image.fromarray(grid, mode="F").resize((w, h), Image.BICUBIC))
        tot += amp
        amp *= 0.5
        scale = max(1.0, scale / 2)
    return np.clip(out / tot, 0, 1)


def warp(x, amp, scale, seed):
    """用低频噪声位移场把图像扭一扭，让边界不那么规整。"""
    h, w = x.shape[:2]
    dy = (fbm(h, w, scale, 3, seed) - 0.5) * 2 * amp
    dx = (fbm(h, w, scale, 3, seed + 1) - 0.5) * 2 * amp
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    coords = [yy + dy, xx + dx]
    if x.ndim == 2:
        return ndi.map_coordinates(x, coords, order=1, mode="reflect")
    return np.stack([ndi.map_coordinates(x[..., c], coords, order=1, mode="reflect") for c in range(x.shape[2])], -1)


def xdog(L, sigma, k=1.6, p=20.0, eps=0.6, phi=10.0):
    """XDoG 线稿（Winnemöller 2012）：1 为纸，接近 0 为线。"""
    g1, g2 = ndi.gaussian_filter(L, sigma), ndi.gaussian_filter(L, sigma * k)
    S = (1 + p) * g1 - p * g2
    return np.where(S >= eps, 1.0, 1.0 + np.tanh(phi * (S - eps)))


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def paper_texture(h, w, s, seed, base, fiber=0.5):
    """纸：底色 + 细颗粒 + 纤维（沿随机方向拉长的噪声）。返回 (h, w, 3)。"""
    grain = fbm(h, w, 3 * s, 3, seed) - 0.5
    fib = np.random.default_rng(seed + 7).random((h, w)).astype(np.float32)
    fib = ndi.gaussian_filter(fib, (0.6 * s, 4 * s)) + ndi.gaussian_filter(fib, (4 * s, 0.6 * s))
    fib = (fib - fib.mean()) / (fib.std() + 1e-6)
    blot = fbm(h, w, 200 * s, 3, seed + 3) - 0.5
    t = 1 + 0.035 * grain + 0.012 * fiber * fib + 0.04 * blot
    return np.clip(np.asarray(base, np.float32)[None, None, :] * t[..., None], 0, 1)


def rgb2lab(rgb):
    c = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab2rgb(lab):
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = np.clip(xyz @ Mi.T, 0, 1)
    return np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)



# ---------------- 流场与笔触工具 ----------------
def flow_field(L, s, sigma=1.5, rho=5.0):
    """结构张量求每个像素的"笔势"方向（沿边缘的切向，单位向量）和一致性（0–1）。"""
    gy = ndi.gaussian_filter(L, sigma * s, order=(1, 0))
    gx = ndi.gaussian_filter(L, sigma * s, order=(0, 1))
    E = ndi.gaussian_filter(gx * gx, rho * s)
    F = ndi.gaussian_filter(gx * gy, rho * s)
    G = ndi.gaussian_filter(gy * gy, rho * s)
    root = np.sqrt((E - G) ** 2 + 4 * F * F)
    l1, l2 = (E + G + root) / 2, (E + G - root) / 2
    tx, ty = E - l1, F
    n = np.hypot(tx, ty)
    flat = n < 1e-12
    tx = np.where(flat, 1.0, tx / np.maximum(n, 1e-12))
    ty = np.where(flat, 0.0, ty / np.maximum(n, 1e-12))
    coh = (l1 - l2) / (l1 + l2 + 1e-12)
    return tx.astype(np.float32), ty.astype(np.float32), coh.astype(np.float32)


def lic(src, tx, ty, length, step=1.0, sigma=None):
    """线积分卷积（C 实现）：沿流场方向对 src 做（高斯加权的）一维平均，噪声进去出来就是顺着笔势的笔触纹理。"""
    h, w = src.shape
    out = np.empty((h, w), np.float32)
    f = lambda a: np.ascontiguousarray(a, np.float32)  # noqa: E731
    _lib().lic_c(f(src), f(tx), f(ty), h, w, int(length), float(step), float(sigma or length / 2.0), out)
    return out


def fdog(L, tx, ty, s, sigma_c=1.0, rho=0.99, sigma_m=3.0, tau=0.5):
    """流线 DoG（Kang et al. 2007）：先沿梯度方向做一维 DoG，再沿切向平滑，得到连贯的线稿。1 为纸，0 为线。"""
    h, w = L.shape
    sc, ss = sigma_c * s, 1.6 * sigma_c * s
    T = int(np.ceil(3 * ss))
    t = np.arange(-T, T + 1, dtype=np.float64)
    wts = ((np.exp(-0.5 * (t / sc) ** 2) / sc - rho * np.exp(-0.5 * (t / ss) ** 2) / ss) / np.sqrt(2 * np.pi))
    H = np.empty((h, w), np.float32)
    f = lambda a: np.ascontiguousarray(a, np.float32)  # noqa: E731
    _lib().dog_line(f(L), f(-ty), f(tx), h, w, T, f(wts), H)
    H = lic(H, tx, ty, int(np.ceil(2 * sigma_m * s)), sigma=sigma_m * s)
    return np.where((H < 0) & (1 + np.tanh(40 * H) < tau), 1 + np.tanh(40 * H), 1.0).astype(np.float32)


def sky_mask(rgb, s):
    """从顶边出发、穿过平滑区域漫水填充得到的天空（要求颜色偏蓝或是亮灰），返回 0–1 软掩码。"""
    lab = rgb2lab(ndi.gaussian_filter(rgb, (1.5 * s, 1.5 * s, 0)))
    g = sum(ndi.gaussian_gradient_magnitude(lab[..., c], 1.5 * s) for c in range(3))
    smooth = g < 2.2
    smooth = ndi.binary_opening(smooth, iterations=max(1, int(2 * s)))
    lbl, n = ndi.label(smooth)
    h, w = smooth.shape
    sky = np.zeros_like(smooth)
    for k in set(np.unique(lbl[0])) - {0}:
        comp = lbl == k
        if comp.sum() < 0.02 * h * w:
            continue
        L, a, b = [lab[..., c][comp].mean() for c in range(3)]
        chroma = np.hypot(a, b)
        if b < -4 or (L > 75 and chroma < 15):
            sky |= comp
    sky = ndi.binary_closing(sky, iterations=max(1, int(4 * s)))
    sky = ndi.binary_fill_holes(sky) & (ndi.binary_dilation(sky, iterations=max(1, int(6 * s))))
    return ndi.gaussian_filter(sky.astype(np.float32), 2 * s)


def l0_smooth(I, lam=0.02, kappa=2.0, beta_max=1e5):
    """L0 梯度最小化（Xu et al. 2011）：把图像压成边缘清楚的平涂色块。I: (h, w) 或 (h, w, C)，0–1。
    每步的梯度阈值和散度在 C 里算（l0_step），FFT 求解用 scipy.fft 多线程。"""
    from scipy import fft as sfft
    X = I[..., None] if I.ndim == 2 else I
    h, w, C = X.shape
    fx = np.zeros((h, w), np.float32); fx[0, 0], fx[0, -1] = -1, 1
    fy = np.zeros((h, w), np.float32); fy[0, 0], fy[-1, 0] = -1, 1
    den = (np.abs(sfft.rfft2(fx)) ** 2 + np.abs(sfft.rfft2(fy)) ** 2).astype(np.float32)
    FI = sfft.rfft2(X.astype(np.float32), axes=(0, 1), workers=-1)
    S = np.ascontiguousarray(X, np.float32)
    div, hb, vb = np.empty_like(S), np.empty_like(S), np.empty_like(S)
    lib = _lib()
    beta = 2 * lam
    while beta < beta_max:
        lib.l0_step(S, div, hb, vb, h, w, C, float(lam / beta))
        FS = (FI + np.float32(beta) * sfft.rfft2(div, axes=(0, 1), workers=-1)) / (1 + np.float32(beta) * den)[..., None]
        S = np.ascontiguousarray(sfft.irfft2(FS, s=(h, w), axes=(0, 1), workers=-1), np.float32)
        beta *= kappa
    return S[..., 0] if I.ndim == 2 else S


def aniso_kuwahara(rgb, s, radius=6.0, q=8.0, alpha=1.0, zeta=0.1, passes=1):
    """各向异性 Kuwahara 滤波（C 实现）：沿结构方向拉长的扇区里取方差最小的均值，得到顺着形体的"笔刷"式概括。"""
    L = rgb @ LUMA
    gy = ndi.gaussian_filter(L, 1.0 * s, order=(1, 0))
    gx = ndi.gaussian_filter(L, 1.0 * s, order=(0, 1))
    E = ndi.gaussian_filter(gx * gx, 2.0 * s)
    F = ndi.gaussian_filter(gx * gy, 2.0 * s)
    G = ndi.gaussian_filter(gy * gy, 2.0 * s)
    root = np.sqrt((E - G) ** 2 + 4 * F * F)
    l1, l2 = (E + G + root) / 2, (E + G - root) / 2
    phi = np.arctan2(-F, l1 - G).astype(np.float32)       # 切向的角度（与 flow_field 相同的方向）
    phi = np.arctan2(F, l1 - E).astype(np.float32)
    A = ((l1 - l2) / (l1 + l2 + 1e-12)).astype(np.float32)
    out = np.ascontiguousarray(rgb, np.float32)
    h, w = rgb.shape[:2]
    for _ in range(passes):
        dst = np.empty_like(out)
        _lib().akf(out, dst, h, w, np.ascontiguousarray(phi), np.ascontiguousarray(A), float(radius * s), float(q),
                   float(alpha), float(zeta))
        out = dst
    return out


def rank01(x, mask=None):
    """每个像素在 mask 内的分位数（0–1）。"""
    flat = x.ravel()
    sel = np.ones(flat.shape, bool) if mask is None else mask.ravel()
    r = np.zeros(flat.shape, np.float32)
    vals = flat[sel]
    order = np.argsort(vals, kind="stable")
    rr = np.empty(len(vals), np.float32)
    rr[order] = np.linspace(0, 1, len(vals), dtype=np.float32)
    r[sel] = rr
    return r.reshape(x.shape)


def soft_quantize(x, levels, soft=0.3):
    """把 x 软量化到给定的几个色阶上（台阶之间用 smoothstep 过渡，soft 越大越柔）。"""
    levels = np.asarray(levels, np.float32)
    i = np.clip(np.searchsorted(levels, x, side="right") - 1, 0, len(levels) - 2)
    lo, hi = levels[i], levels[i + 1]
    f = np.clip((x - lo) / (hi - lo), 0, 1)
    return lo + (hi - lo) * smoothstep(0.5 - soft, 0.5 + soft, f)



# ---------------- C 内核（笔触） ----------------
HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = None
NSP = 8                                   # 每笔参数个数，与 npr.c 一致
_f32p = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
_i32p = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")


LP = ["R", "step", "grid", "T", "min_len", "max_len", "fc", "stop", "rj_lo", "rj_hi", "tin", "tout", "op",
      "grad", "dry_p", "dry", "soft", "bristle", "deplete", "rim", "rim_w", "thick", "jit", "mix", "ridge"]   # 与 npr.c 一致


def _lib():
    """首次调用时把 npr.c 编译成 npr.so（需要系统 C 编译器）。"""
    global _LIB
    if _LIB is None:
        src, so = os.path.join(HERE, "npr.c"), os.path.join(HERE, "npr.so")
        if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
            fd, tmp = tempfile.mkstemp(suffix=".so", dir=HERE)
            os.close(fd)
            subprocess.check_call(["cc", "-O3", "-shared", "-fPIC", "-o", tmp, src, "-lm"])
            os.replace(tmp, so)
        lib = ctypes.CDLL(so)
        lib.paint_layer.restype = ctypes.c_int
        lib.paint_layer.argtypes = [_f32p, _f32p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    _f32p, _f32p, _f32p, ctypes.c_int, ctypes.c_uint64, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        lib.mesh_optimize.restype = ctypes.c_double
        lib.mesh_optimize.argtypes = [_f32p, ctypes.c_int, ctypes.c_int, _f32p, ctypes.c_int, _i32p, _i32p, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
                                      ctypes.c_uint64, ctypes.c_int,
                                      np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS")]
        lib.l0_step.restype = None
        lib.l0_step.argtypes = [_f32p, _f32p, _f32p, _f32p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_float]
        lib.regions_c.restype = ctypes.c_int
        lib.regions_c.argtypes = [_f32p, ctypes.c_int, ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_int,
                                  _i32p]
        lib.lic_c.restype = None
        lib.lic_c.argtypes = [_f32p, _f32p, _f32p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_float,
                              ctypes.c_float, _f32p]
        lib.dog_line.restype = None
        lib.dog_line.argtypes = [_f32p, _f32p, _f32p, ctypes.c_int, ctypes.c_int, ctypes.c_int, _f32p, _f32p]
        lib.akf.restype = None
        lib.akf.argtypes = [_f32p, _f32p, ctypes.c_int, ctypes.c_int, _f32p, _f32p, ctypes.c_float, ctypes.c_float,
                            ctypes.c_float, ctypes.c_float]
        lib.mesh_colors.restype = None
        lib.mesh_colors.argtypes = [_f32p, ctypes.c_int, ctypes.c_int, _f32p, _i32p, ctypes.c_int, _f32p, _f32p]
        _LIB = lib
    return _LIB


def paint_layer(ref, canvas, tx, ty, mode, seed=0, height=None, record=False, max_pts=24, **kw):
    """画一层笔触（原地修改 canvas / height）。kw 是层参数（名字见 LP）。
    record=True 时返回每笔的 (控制点, 点数, 颜色, 半径)，否则返回笔数。"""
    lp = np.zeros(len(LP), np.float32)
    for k, v in kw.items():
        lp[LP.index(k)] = v
    h, w = canvas.shape[:2]
    C = 1 if canvas.ndim == 2 else canvas.shape[2]
    assert canvas.dtype == np.float32 and canvas.flags.c_contiguous
    ref = np.ascontiguousarray(ref, np.float32)
    hp = height.ctypes.data if height is not None else None
    args = [ref, canvas, hp, h, w, C, np.ascontiguousarray(tx, np.float32), np.ascontiguousarray(ty, np.float32),
            lp, int(mode), int(seed)]
    if not record:
        return _lib().paint_layer(*args, 0, max_pts, None, None, None, None)
    ms = (h // max(1, int(kw.get("grid", 1))) + 2) * (w // max(1, int(kw.get("grid", 1))) + 2)
    pts = np.zeros((ms, max_pts, 2), np.float32)
    npts = np.zeros(ms, np.int32)
    cols = np.zeros((ms, C), np.float32)
    rad = np.zeros(ms, np.float32)
    n = _lib().paint_layer(*args, ms, max_pts, pts.ctypes.data, npts.ctypes.data, cols.ctypes.data, rad.ctypes.data)
    return pts[:n], npts[:n], cols[:n], rad[:n]


def prep(img, size):
    img = img.convert("RGB")
    k = size / max(img.size)
    if k < 1:
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    rgb = np.asarray(img, dtype=np.float32) / 255
    return rgb, max(rgb.shape[:2]) / 1600.0


# ---------------- 水墨 ----------------
INK_LEVELS = [0.0, 0.10, 0.24, 0.45, 0.70, 0.92]      # 清、淡、重、浓、焦


def ink_target(rgb, s, contrast=0.3):
    """照片 → 目标墨浓度（0 纸白 .. 1 焦墨）和笔势方向场。"""
    L = rgb @ LUMA
    lo, hi = np.percentile(L, [1, 99])
    L = np.clip((L - lo) / (hi - lo + 1e-6), 0, 1)
    A = guided(L, L, max(2, int(6 * s)), 0.004)
    A = guided(A, A, max(3, int(14 * s)), 0.01)
    tx, ty, coh = flow_field(A, s, sigma=2.0, rho=6.0)
    sky = sky_mask(rgb, s)
    D0 = 1 - A
    r = rank01(D0, sky < 0.5)
    F = np.interp(r, [0, 0.25, 0.55, 0.8, 0.94, 1.0], [0, 0.03, 0.16, 0.36, 0.62, 0.88])
    d_abs = 0.9 * np.clip((D0 - 0.2) / 0.8, 0, 1) ** 1.3
    d = (0.6 * F + 0.4 * d_abs) * (1 - sky)
    d = np.clip(d + contrast * (d - ndi.gaussian_filter(d, 25 * s)), 0, 1)
    return d.astype(np.float32), tx, ty, sky, A


INK = dict(radii=(36, 18, 9, 4.5), T=(0.04, 0.07, 0.12, 0.18), max_len=14, fc=0.55, stop=0.08,
           soft=(0.8, 0.6, 0.35, 0.2), dry_p=0.6, dry=(0.1, 0.3, 0.5, 0.5), grad=0.8, bristle=0.35, deplete=0.35,
           bleed=1.2, lines=0.6, line_w=1.3, line_sigma=1.2, line_T=0.08, vignette=0.8,
           paper=(0.95, 0.925, 0.87), contrast=0.6)


def ink(img, strength=1.0, seed=0, size=1600, seal=True, params=None):
    P = dict(INK, **(params or {}))
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    target, tx, ty, sky, A = ink_target(rgb, s, P["contrast"])
    if P["vignette"] > 0:                        # 四周渐渐留白（写意画常见的构图）
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        r = r + 0.25 * (fbm(h, w, 120 * s, 3, seed + 12) - 0.5)
        target = target * (1 - P["vignette"] * smoothstep(0.55, 0.95, r))
    target = np.clip(target * strength, 0, 1)
    canvas = np.zeros((h, w), np.float32)
    for li, r0 in enumerate(P["radii"]):
        R = max(1.2, r0 * s)
        ref = np.ascontiguousarray(ndi.gaussian_filter(target, 0.5 * R), np.float32)
        paint_layer(ref, canvas, tx, ty, 1, seed * 31 + li, R=R, step=0.9 * R, grid=max(2, int(R)), T=P["T"][li],
                    min_len=2, max_len=P["max_len"], fc=P["fc"], stop=P["stop"], rj_lo=0.8, rj_hi=1.25,
                    tin=0.15, tout=0.3, op=1.0, grad=P["grad"], dry_p=P["dry_p"], dry=P["dry"][li],
                    soft=P["soft"][li], bristle=P["bristle"], deplete=P["deplete"])
    # 洇：墨沿纸的纤维向外渗一点，边缘毛糙；墨色低频不匀
    fib = np.random.default_rng(seed + 9).random((h, w)).astype(np.float32)
    fib = ndi.gaussian_filter(fib, (0.5 * s, 3 * s)) + ndi.gaussian_filter(fib, (3 * s, 0.5 * s))
    fib = smoothstep(0.95, 1.05, fib / fib.mean())
    wash = np.maximum(canvas, P["bleed"] * ndi.gaussian_filter(canvas, 2.5 * s) * fib)
    wash = wash * (0.9 + 0.2 * fbm(h, w, 40 * s, 4, seed + 2))
    # 勾勒：流线 DoG 找轮廓，再沿轮廓一笔笔勾（起笔收笔、粗细变化、偶有飞白）
    if P["lines"] > 0:
        E = fdog(A, tx, ty, s, sigma_c=P["line_sigma"], sigma_m=3.0, tau=0.55)
        gm = ndi.gaussian_gradient_magnitude(A, 2.0 * s)
        lref = (1 - E) * smoothstep(0.02, 0.06, gm) * (1 - sky)
        if P["vignette"] > 0:
            lref = lref * (1 - P["vignette"] * smoothstep(0.55, 0.95, r))
        lref = np.clip(ndi.gaussian_filter(lref, 0.6 * s) * 1.3, 0, 0.92).astype(np.float32)
        lines = np.zeros((h, w), np.float32)
        Rl = max(0.8, P["line_w"] * s)
        paint_layer(lref, lines, tx, ty, 1, seed * 31 + 7, R=Rl, step=max(1.5, 2.5 * s), grid=max(2, int(3 * s)),
                    T=P["line_T"], min_len=3, max_len=24, fc=0.8, stop=0.3, rj_lo=0.7, rj_hi=1.5, tin=0.2,
                    tout=0.35, op=1.0, grad=0.3, dry_p=0.3, dry=0.4, soft=0.15, bristle=0.3, deplete=0.25)
        wash = 1 - (1 - wash) * (1 - P["lines"] * lines)
    alpha = np.clip(wash, 0, 0.96)
    paper = paper_texture(h, w, s, seed + 10, P["paper"])
    ink_col = np.array([0.08, 0.075, 0.07], np.float32)
    out = paper * (1 - alpha[..., None]) + ink_col * alpha[..., None]
    out = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))
    if seal:
        out = add_seal(out, seed)
    return out


def add_seal(img, seed=0, text="墨戲"):
    """右下角盖一方朱文印（红底白字），边缘做些残破。"""
    w, h = img.size
    S = max(24, int(0.07 * min(w, h)))
    if S > min(w, h) // 2:                                  # 图太小（或太扁）就不盖了
        return img
    font = None
    for path, idx in (("/System/Library/Fonts/Supplemental/Songti.ttc", 7), ("/System/Library/Fonts/Songti.ttc", 7),
                      ("/System/Library/Fonts/STHeiti Medium.ttc", 0)):
        try:
            font = __import__("PIL.ImageFont", fromlist=["x"]).truetype(path, int(S * 0.44), index=idx)
            break
        except OSError:
            continue
    m = Image.new("L", (S, S), 0)
    dr = ImageDraw.Draw(m)
    dr.rectangle([0, 0, S - 1, S - 1], fill=255)
    if font is not None:
        cs = int(S * 0.44)
        for i, ch in enumerate(text[:2]):                   # 竖排两字，从右往左读就放一列
            dr.text((S // 2 - cs // 2, int(S * 0.06) + i * int(S * 0.46)), ch, fill=0, font=font)
    a = np.asarray(m, np.float32) / 255
    rng = np.random.default_rng(seed + 99)
    a *= (rng.random(a.shape) > 0.06) * (fbm(S, S, S / 6, 3, seed + 98) > 0.28)
    a = ndi.gaussian_filter(a, 0.6)
    arr = np.asarray(img, np.float32) / 255
    x0, y0 = w - S - int(0.04 * w), h - S - int(0.05 * h)
    red = np.array([0.72, 0.16, 0.12], np.float32)
    reg = arr[y0:y0 + S, x0:x0 + S]
    arr[y0:y0 + S, x0:x0 + S] = reg * (1 - 0.9 * a[..., None]) + red * reg * 1.05 * (0.9 * a[..., None])
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


# ---------------- 水彩 ----------------
def nc_blur(x, m, sigma):
    """归一化卷积：只在掩码 m 内做高斯平均（区域内抹平，区域外不串色）。"""
    if x.ndim == 3:
        num = ndi.gaussian_filter(x * m[..., None], (sigma, sigma, 0))
        den = ndi.gaussian_filter(m, sigma)[..., None]
    else:
        num, den = ndi.gaussian_filter(x * m, sigma), ndi.gaussian_filter(m, sigma)
    return num / np.maximum(den, 1e-4)


WATER = dict(lam=0.02, work=4096, edge_de=8.0, min_area=100, lighten=0.75, chroma=1.1, flat=6.0, wobble=4.0,
             gap=0.7, gap_w=1.8, rim=0.7, rim_w=2.0, slope=0.2, turb=0.3, gran=0.5, vignette=0.7, pencil=0.0,
             detail=0.8, detail_t=0.35, paper=(0.975, 0.965, 0.935))


def regions(lab, de, min_area, qstep=2.5):
    """区域划分：先按精细量化后的同色连通块切小块，再在区域邻接图上按色差从小到大合并（并查集，C 实现），
    合并后的区域平均色差不超过 de；面积小于 min_area 的块并入色差最小的邻居。返回从 0 开始的区域编号。"""
    h, w = lab.shape[:2]
    out = np.empty((h, w), np.int32)
    _lib().regions_c(np.ascontiguousarray(lab, np.float32), h, w, float(qstep), float(de), int(min_area), out)
    return out


def smooth_labels(L, sigma):
    """把区域编号图的边界磨圆：每个区域的掩码做高斯模糊，像素归给模糊后值最大的区域（只在区域外框附近算）。"""
    if sigma <= 0:
        return L
    h, w = L.shape
    n = L.max() + 1
    best = np.full((h, w), -1.0, np.float32)
    out = L.copy()
    objs = ndi.find_objects(L + 1)
    m = int(np.ceil(3 * sigma))
    for k, sl in enumerate(objs):
        if sl is None:
            continue
        y0, y1 = max(0, sl[0].start - m), min(h, sl[0].stop + m)
        x0, x1 = max(0, sl[1].start - m), min(w, sl[1].stop + m)
        sub = ndi.gaussian_filter((L[y0:y1, x0:x1] == k).astype(np.float32), sigma)
        bsub = best[y0:y1, x0:x1]
        upd = sub > bsub
        bsub[upd] = sub[upd]
        out[y0:y1, x0:x1][upd] = k
    return out


def watercolor(img, strength=1.0, seed=0, size=1600, params=None):
    """水彩：先用 L0 把画面概括成平涂色块，按颜色突变切成区域，每个区域当成一片洗染——
    区域内颜色抹匀（保留大尺度冷暖变化）；边界扭动；色差大的边界上有的留一条断续的白缝、边缘积色；
    块内颜料往一侧沉淀；纸纹颗粒；四周留白；铅笔底稿。"""
    P = dict(WATER, **(params or {}))
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    rng = np.random.default_rng(seed)
    k = min(1.0, P["work"] / max(h, w))
    small = np.asarray(Image.fromarray((rgb * 255).astype(np.uint8)).resize((max(8, round(w * k)), max(8, round(h * k))),
                                                                            Image.LANCZOS), np.float32) / 255
    S = l0_smooth(small, P["lam"])
    lab = rgb2lab(np.clip(S, 0, 1)).astype(np.float32)
    lbl = regions(lab, P["edge_de"], P["min_area"])
    nl = lbl.max() + 1
    # 放大到原尺寸（边界扭动），区域内把颜色抹匀
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dy = (fbm(h, w, 20 * s, 3, seed) - 0.5) * 2 * P["wobble"] * s
    dx = (fbm(h, w, 20 * s, 3, seed + 1) - 0.5) * 2 * P["wobble"] * s
    sy = np.clip(((yy + dy) * k).astype(np.int32), 0, lbl.shape[0] - 1)
    sx = np.clip(((xx + dx) * k).astype(np.int32), 0, lbl.shape[1] - 1)
    L = lbl[sy, sx]
    labu = lab[sy, sx]
    flat = np.zeros_like(labu)
    for c in range(3):                                        # 区域内的归一化卷积（按区域分组做）
        num = ndi.gaussian_filter(labu[..., c], P["flat"] * s)
        flat[..., c] = num
    # 区域均值兜底：避免跨区域串色——与区域均值差太多的地方回退到均值
    cnt = np.bincount(L.ravel(), minlength=nl).astype(np.float32)
    mean = np.stack([np.bincount(L.ravel(), weights=labu[..., c].ravel(), minlength=nl) / np.maximum(cnt, 1)
                     for c in range(3)], -1)
    mL = mean[L]
    dev = np.sqrt(((flat - mL) ** 2).sum(-1, keepdims=True))
    wmix = np.clip(1 - dev / 10.0, 0, 1)
    lab2 = wmix * flat + (1 - wmix) * mL
    lab2[..., 0] = 100 - (100 - lab2[..., 0]) * P["lighten"]
    lab2[..., 1:] *= P["chroma"]
    C = lab2rgb(lab2).astype(np.float32)
    paper = np.asarray(P["paper"], np.float32)
    a = -np.log(np.clip(C / paper, 0.02, 1.0))
    # 块内颜料往一侧沉淀
    ang = rng.uniform(0, 2 * np.pi, nl)
    proj = xx * np.cos(ang)[L] + yy * np.sin(ang)[L]
    pm = np.bincount(L.ravel(), weights=proj.ravel(), minlength=nl) / np.maximum(cnt, 1)
    sd = np.sqrt(np.bincount(L.ravel(), weights=(proj - pm[L]).ravel() ** 2, minlength=nl) / np.maximum(cnt, 1))
    a *= (1 + P["slope"] * np.clip((proj - pm[L]) / (sd[L] + 1e-3), -1.5, 1.5) / 1.5)[..., None]
    # 边界（都是色差大的地方）：积色 + 断续白缝（只在较亮一侧）
    bnd = np.zeros((h, w), bool)
    bnd[:, 1:] |= L[:, 1:] != L[:, :-1]
    bnd[1:, :] |= L[1:, :] != L[:-1, :]
    dist = ndi.distance_transform_edt(~bnd).astype(np.float32)
    a *= (1 + P["rim"] * np.exp(-dist / (P["rim_w"] * s)))[..., None]
    lum = mean[..., 0][L]
    brighter = lum >= ndi.maximum_filter(lum, size=3) - 1e-3
    gw = P["gap_w"] * s * smoothstep(0.35, 0.75, fbm(h, w, 12 * s, 3, seed + 6))
    gapm = (fbm(h, w, 60 * s, 3, seed + 5) < P["gap"]) & (dist < gw) & brighter
    a[gapm] *= 0.1
    # 第二遍：暗部细节（窗、船、人影）——照片比第一遍洗染暗得多的地方再罩一遍小块深色
    if P["detail"] > 0:
        D = guided(rgb @ LUMA, rgb, max(1, int(2 * s)), 0.002)
        labd = rgb2lab(np.clip(D, 0, 1))
        labd[..., 0] = 100 - (100 - labd[..., 0]) * P["lighten"]
        labd[..., 1:] *= P["chroma"]
        ad = -np.log(np.clip(lab2rgb(labd).astype(np.float32) / paper, 0.02, 1.0))
        res = warp((ad - a).mean(-1), 1.5 * s, 12 * s, seed + 30)
        m = smoothstep(P["detail_t"], P["detail_t"] + 0.12, ndi.gaussian_filter(res, 0.8 * s))
        rim2 = np.clip(m - ndi.gaussian_filter(m, 1.5 * s), 0, None)
        a += P["detail"] * np.clip(ad - a, 0, None) * (m * (1 + 1.2 * rim2))[..., None]
    # 大尺度颜料不匀 + 纸纹颗粒
    a *= (1 + P["turb"] * 2 * (fbm(h, w, 50 * s, 4, seed + 3) - 0.5))[..., None]
    paper_h = fbm(h, w, 3 * s, 3, seed + 20)
    a *= (1 + P["gran"] * 2 * (0.5 - paper_h))[..., None]
    a = ndi.gaussian_filter(a, (0.6 * s, 0.6 * s, 0))
    if P["vignette"] > 0:                                                 # 四周没画完、露出纸
        r = np.maximum(np.abs(xx - w / 2) / (w / 2), np.abs(yy - h / 2) / (h / 2))
        r = r + 0.3 * (fbm(h, w, 90 * s, 4, seed + 12) - 0.5)
        a *= (1 - P["vignette"] * smoothstep(0.78, 1.02, r))[..., None]
    a *= strength
    pap = paper_texture(h, w, s, seed + 10, P["paper"], fiber=0.2)
    out = pap * np.exp(-a)
    if P["pencil"] > 0:                                                   # 淡淡的铅笔底稿
        E = xdog(rgb @ LUMA, 1.0 * s, p=20, eps=0.62, phi=10)
        out *= (1 - P["pencil"] * (1 - E))[..., None]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


# ---------------- 铅笔素描 ----------------
PENCIL = dict(line_frac=1 / 40, line_w=1.0, line_gamma=1.0, line_k=0.6, w_bright=52, w_mid=37, w_dark=11,
              hatch_angle=45.0, hatch_len=8, cross=0.5, grain=0.5, tone_k=1.0, color=False, color_sat=0.7,
              sky=0.7, vignette=0.9, angle_var=0.12, flow=0.0, paper=(0.97, 0.965, 0.95))


def _line_kernels(n, size, width=1.0):
    ks = []
    c = (size - 1) / 2
    for i in range(n):
        th = np.pi * i / n
        im = Image.new("F", (size * 4, size * 4), 0)
        dr = ImageDraw.Draw(im)
        dx, dy = np.cos(th) * c * 4, np.sin(th) * c * 4
        dr.line([(c * 4 + 2 - dx, c * 4 + 2 - dy), (c * 4 + 2 + dx, c * 4 + 2 + dy)], fill=1.0, width=max(1, int(4 * width)))
        k = np.asarray(im.resize((size, size), Image.BOX), np.float32)
        ks.append(k / k.sum())
    return ks


def _fft_conv_same(shape, kernels):
    """返回一个函数 conv(x, only=None)：x 与每个核（或第 only 个核）做 'same' 模式的线性卷积（FFT，核的频谱只算一次）。"""
    from scipy import fft as sfft
    h, w = shape
    kh, kw = kernels[0].shape
    fh, fw = sfft.next_fast_len(h + kh - 1), sfft.next_fast_len(w + kw - 1)
    KF = [sfft.rfft2(k, s=(fh, fw)) for k in kernels]
    oy, ox = (kh - 1) // 2, (kw - 1) // 2

    def conv(x, only=None):
        XF = sfft.rfft2(x, s=(fh, fw), workers=-1)
        ks = KF if only is None else [KF[only]]
        return [sfft.irfft2(XF * k, s=(fh, fw), workers=-1)[oy:oy + h, ox:ox + w].astype(np.float32) for k in ks]
    return conv


def _tone_target():
    """Lu et al. 2012 的铅笔画色调分布（亮部拉普拉斯 + 中间调均匀 + 暗部高斯），返回 256 级的 CDF。"""
    v = np.arange(256, dtype=np.float64)
    p1 = np.exp(-(255 - v) / 9.0) / 9.0
    p2 = ((v >= 105) & (v <= 225)).astype(np.float64) / (225 - 105)
    p3 = np.exp(-((v - 90) ** 2) / (2 * 11.0 ** 2)) / np.sqrt(2 * np.pi * 11.0 ** 2)
    return p1, p2, p3


def hist_match(x, pdf):
    """把 x（0–1）的直方图匹配到给定的 256 级分布。"""
    cdf_t = np.cumsum(pdf) / pdf.sum()
    r = rank01(x)
    return (np.interp(r, cdf_t, np.arange(256)) / 255.0).astype(np.float32)


def hatch_texture(h, w, angle, length, seed, s, angle_var=0.12, flow=None):
    """程序生成的铅笔排线纹理：白噪声沿某个方向拉成短线。方向 = 固定角度 + 大块区域各自的偏转（angle_var 弧度），
    flow=(tx, ty, 权重) 时再往物体的走向偏。"""
    rng = np.random.default_rng(seed)
    n = rng.random((h, w)).astype(np.float32)
    n = (n > 0.72).astype(np.float32) * rng.random((h, w)).astype(np.float32)
    th = np.deg2rad(angle) + angle_var * 2 * (fbm(h, w, 150 * s, 2, seed + 1) - 0.5)
    tx, ty = np.cos(th).astype(np.float32), np.sin(th).astype(np.float32)
    if flow is not None and flow[2] > 0:
        fx, fy, k = flow
        fx, fy = np.where(fx * tx + fy * ty < 0, -fx, fx), np.where(fx * tx + fy * ty < 0, -fy, fy)
        tx, ty = (1 - k) * tx + k * fx, (1 - k) * ty + k * fy
        nn = np.hypot(tx, ty) + 1e-6
        tx, ty = (tx / nn).astype(np.float32), (ty / nn).astype(np.float32)
    st = lic(n, tx, ty, max(3, int(length * s)), sigma=length * s)
    st = (st - st.min()) / (st.max() - st.min() + 1e-6)
    return np.clip(1 - 0.9 * st, 0.02, 1)


def pencil(img, strength=1.0, seed=0, size=1600, params=None, color=None):
    """铅笔素描（Lu, Xu, Jia 2012）：方向分类的线条 × 排线纹理渲染的色调；color=True 为彩色铅笔。"""
    P = dict(PENCIL, **(params or {}))
    if color is not None:
        P["color"] = color
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    I = rgb @ LUMA
    # 1. 线条：梯度按 8 个方向分类，再用对应方向的短线核把每一类"画"出来
    Ib = ndi.gaussian_filter(I, 0.7 * s)
    gx = np.zeros_like(Ib); gy = np.zeros_like(Ib)
    gx[:, :-1] = Ib[:, 1:] - Ib[:, :-1]
    gy[:-1] = Ib[1:] - Ib[:-1]
    G = np.hypot(gx, gy)
    size_k = max(5, int(P["line_frac"] * max(h, w)) | 1)
    ks = _line_kernels(8, size_k, P["line_w"])
    conv = _fft_conv_same(G.shape, ks)
    resp = np.stack(conv(G))
    cls = resp.argmax(0)
    Sp = sum(conv(np.where(cls == i, G, 0), only=i)[0] for i in range(len(ks)))
    Sp = Sp / (np.percentile(Sp, 99.5) + 1e-6)
    S = np.clip(1 - P["line_k"] * Sp, 0, 1) ** P["line_gamma"]
    if P["vignette"] > 0:
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        r = r + 0.25 * (fbm(h, w, 120 * s, 3, seed + 12) - 0.5)
        S = 1 - (1 - S) * (1 - P["vignette"] * smoothstep(0.65, 1.05, r))
    # 2. 色调：直方图匹配到铅笔画的色调分布，再用排线纹理画出来（暗处叠交叉排线）
    p1, p2, p3 = _tone_target()
    pdf = P["w_bright"] * p1 + P["w_mid"] * p2 + P["w_dark"] * p3
    J = hist_match(ndi.gaussian_filter(I, 1.0 * s), pdf)
    J = 1 - (1 - J) * P["tone_k"] * strength
    fade = np.zeros((h, w), np.float32)
    if P["sky"] > 0:                                           # 天空基本留白
        fade = np.maximum(fade, P["sky"] * sky_mask(rgb, s))
    if P["vignette"] > 0:                                      # 四周渐渐淡出
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        r = r + 0.25 * (fbm(h, w, 120 * s, 3, seed + 12) - 0.5)
        fade = np.maximum(fade, P["vignette"] * smoothstep(0.6, 1.0, r))
    J = 1 - (1 - J) * (1 - fade)
    flow = None
    if P["flow"] > 0:
        ftx, fty, _ = flow_field(ndi.gaussian_filter(I, 2 * s), s, sigma=2.0, rho=10.0)
        flow = (ftx, fty, P["flow"])
    H1 = hatch_texture(h, w, P["hatch_angle"], P["hatch_len"], seed, s, P["angle_var"], flow)
    Hm = np.clip(ndi.gaussian_filter(H1, 6 * s), 0.05, 0.98)
    beta = np.log(np.clip(J, 0.02, 1)) / np.log(Hm)
    T = H1 ** beta
    if P["cross"] > 0:
        H2 = hatch_texture(h, w, P["hatch_angle"] - 90, P["hatch_len"], seed + 50, s, P["angle_var"])
        dark = smoothstep(0.55, 0.25, J) * P["cross"]
        T = T * (1 - dark * (1 - H2))
    grain = fbm(h, w, 1.5 * s, 2, seed + 7)
    T = T * (1 - 0.08 * P["grain"] * (grain - 0.5) * 2)
    R = np.clip(S * T, 0, 1)
    paper = np.asarray(P["paper"], np.float32)
    if P["color"]:
        ycc = rgb @ np.array([[0.299, -0.168736, 0.5], [0.587, -0.331264, -0.418688], [0.114, 0.5, -0.081312]], np.float32)
        ycc[..., 0] = R
        ycc[..., 1:] *= P["color_sat"]
        M = np.array([[1, 1, 1], [0, -0.344136, 1.772], [1.402, -0.714136, 0]], np.float32)
        out = np.clip(ycc @ M, 0, 1) * paper
    else:
        graphite = np.array([0.20, 0.21, 0.23], np.float32)
        out = paper * R[..., None] + graphite * (1 - R[..., None]) * (1 - paper) * 0 + 0
        out = paper * (1 - (1 - R[..., None]) * (1 - graphite))
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


# ---------------- 油画 ----------------
OIL = dict(radii=(40, 20, 10), T=(0.06, 0.10, 0.14), max_len=16, min_len=3, fc=0.6, stop=0.18,
           op=0.95, bristle=0.5, jit=0.05, thick=1.0, impasto=0.6, light=(-0.6, -0.8), spec=0.12, canvas=0.06,
           sat=1.12, contrast=1.05, ground=(0.55, 0.45, 0.35), abstract=0.05, mix=0.6, ridge=0.5, dry_p=0.3, dry=0.35,
           lift=0.0, warm=0.6, rho=5.0, step=0.8, focus=0.0, tempo=0.6, flat_dir=0.0, palette=0, pal_mix=0.6,
           ref_blur=0.5, akf=0.0, strokes=True, streak=0.0)


def canvas_texture(h, w, s, seed):
    """亚麻画布的纹理：横竖两组细纹 + 一点随机。返回 0 附近的起伏。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    per = max(2.5, 4.0 * s)
    weave = np.sin(2 * np.pi * xx / per) * np.sin(2 * np.pi * yy / per)
    n = fbm(h, w, 2 * s, 2, seed) - 0.5
    return (0.6 * weave + 0.8 * n).astype(np.float32)


def oil(img, strength=1.0, seed=0, size=1600, params=None):
    """油画（Hertzmann 1998 的多尺度曲线笔触 + 鬃毛条纹 + 颜料厚度打光的厚涂效果）。"""
    P = dict(OIL, **(params or {}))
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    lab = rgb2lab(rgb)
    lab[..., 1:] *= P["sat"]
    lab[..., 0] = 50 + (lab[..., 0] - 50) * P["contrast"]
    if P["tempo"] > 0:                                             # 亮部偏暖、暗部偏冷
        t = np.clip((lab[..., 0] - 50) / 40, -1, 1)
        lab[..., 2] += P["tempo"] * 14 * t
        lab[..., 1] += P["tempo"] * 4 * t
    src = lab2rgb(lab).astype(np.float32)
    if P["abstract"] > 0:                                          # 先概括（去掉照片的细碎纹理）
        src = l0_smooth(src, P["abstract"])
    if P["akf"] > 0:                                               # 或者用各向异性 Kuwahara 概括（顺着形体的笔刷感）
        src = aniso_kuwahara(src, s, radius=P["akf"])
    if P["palette"] > 0:                                           # 有限调色板：颜色往 K 个主色靠
        from scipy.cluster.vq import kmeans2
        lab2 = rgb2lab(np.clip(src, 0, 1)).astype(np.float32)
        cent, _ = kmeans2(lab2[::4, ::4].reshape(-1, 3), int(P["palette"]), seed=seed, minit="++", iter=15)
        d2 = ((lab2[..., None, :] - cent[None, None]) ** 2).sum(-1)
        q = cent[d2.argmin(-1)]
        src = lab2rgb(P["pal_mix"] * q + (1 - P["pal_mix"]) * lab2).astype(np.float32)
    L = src @ LUMA
    tx, ty, coh = flow_field(ndi.gaussian_filter(L, 1.0 * s), s, sigma=2.0, rho=P["rho"])
    if P["flat_dir"] > 0:                                          # 平坦处（天空、水面）横着刷
        k = 1 - P["flat_dir"] * (1 - smoothstep(0.1, 0.5, coh))
        tx, ty = k * tx + (1 - k) * np.where(tx < 0, -1.0, 1.0), k * ty
        nn = np.hypot(tx, ty) + 1e-6
        tx, ty = (tx / nn).astype(np.float32), (ty / nn).astype(np.float32)
    canvas = np.ascontiguousarray(np.broadcast_to(np.asarray(P["ground"], np.float32), (h, w, 3)).copy())
    height = np.zeros((h, w), np.float32)
    if P["focus"] > 0:                                             # 焦点：中心保留细节，四周只用大笔
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        fm = (P["focus"] * smoothstep(0.3, 0.9, r + 0.2 * (fbm(h, w, 100 * s, 3, seed + 13) - 0.5)))[..., None]
        src = src * (1 - fm) + ndi.gaussian_filter(src, (12 * s, 12 * s, 0)) * fm
    if not P["strokes"]:                                           # 不画笔触：直接用概括后的颜色，笔纹另加
        canvas[:] = src
    for li, r0 in enumerate(P["radii"] if P["strokes"] else ()):
        R = max(1.2, r0 * s)
        ref = np.ascontiguousarray(ndi.gaussian_filter(src, (P["ref_blur"] * R, P["ref_blur"] * R, 0)), np.float32)
        T = P["T"][li] if li > 0 else 0.0                        # 第一层铺满（不留底色）
        paint_layer(ref, canvas, tx, ty, 0, seed * 41 + li, height=height, R=R, step=P["step"] * R, grid=max(2, int(R)),
                    T=T, min_len=P["min_len"], max_len=P["max_len"], fc=P["fc"], stop=P["stop"], rj_lo=0.85,
                    rj_hi=1.15, tin=0.05, tout=0.15, op=P["op"], soft=0.12, bristle=P["bristle"], thick=P["thick"],
                    jit=P["jit"] * strength, mix=P["mix"], ridge=P["ridge"], dry_p=P["dry_p"], dry=P["dry"])
    if P["streak"] > 0:                                            # 顺着笔势的鬃毛纹（噪声沿流场做线积分）
        nz = np.random.default_rng(seed + 21).random((h, w)).astype(np.float32)
        st = lic(nz, tx, ty, max(4, int(8 * s)))
        st = (st - st.mean()) / (st.std() + 1e-6)
        height = height + P["streak"] * 0.3 * st
        canvas = np.ascontiguousarray(canvas * (1 + 0.04 * P["streak"] * st)[..., None])
    # 厚涂：颜料厚度 → 法线 → 漫反射 + 高光；再叠画布纹理
    hgt = ndi.gaussian_filter(height, 0.7 * s) + P["canvas"] * canvas_texture(h, w, s, seed + 3)
    gy, gx = np.gradient(hgt)
    k = P["impasto"] * 6.0 / max(s, 0.3)
    nx, ny, nz = -k * gx, -k * gy, np.ones_like(gx)
    nn = np.sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly = P["light"]
    lz = 1.0
    ln = np.sqrt(lx * lx + ly * ly + lz * lz)
    diff = (nx * lx + ny * ly + nz * lz) / (nn * ln)
    spec = np.clip(diff, 0, 1) ** 24
    out = canvas * (0.55 + 0.45 * diff / (lz / ln))[..., None] + P["spec"] * spec[..., None]
    if P["lift"] > 0:                                              # 颜料的明暗范围比照片窄：黑不死、白不爆
        out = P["lift"] + (1 - 1.6 * P["lift"]) * out
    if P["warm"] > 0:                                              # 旧光油的暖色罩光
        out = out * (1 - P["warm"] * np.array([0.0, 0.06, 0.2], np.float32))
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


# ---------------- 卡通平涂 ----------------
CARTOON = dict(lam=0.03, edge_de=14.0, min_area=150, sat=1.5, bright=1.06, gamma=0.8, shade_levels=0, line_w=4.0,
               line_de=12.0, line_col=(0.12, 0.10, 0.10), detail=0.0, detail_sigma=1.2, detail_min=0, round=4.0,
               tempo=0.0)


def cartoon(img, strength=1.0, seed=0, size=1600, params=None):
    """卡通平涂：L0 概括 + 区域合并成平涂色块（提亮、加饱和）+ 色块边界描粗线 + 细节细线。"""
    P = dict(CARTOON, **(params or {}))
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    S = l0_smooth(rgb, P["lam"])
    lab = rgb2lab(np.clip(S, 0, 1)).astype(np.float32)
    L = regions(lab, P["edge_de"], P["min_area"])
    n = L.max() + 1
    cnt = np.bincount(L.ravel(), minlength=n).astype(np.float32)
    mean = np.stack([np.bincount(L.ravel(), weights=lab[..., c].ravel(), minlength=n) / np.maximum(cnt, 1)
                     for c in range(3)], -1)
    L = smooth_labels(L, P["round"] * s)
    flat = mean[L]
    if P["shade_levels"] > 0:                                        # 区域内再按明暗分几档（赛璐璐阴影）
        q = np.round((lab[..., 0] - flat[..., 0]) / 12.0).clip(-P["shade_levels"], P["shade_levels"])
        flat[..., 0] += q * 8.0
    flat[..., 1:] *= P["sat"] * strength + (1 - strength)
    flat[..., 0] = np.clip(100 * (flat[..., 0] / 100) ** P["gamma"] * P["bright"], 0, 100)
    if P["tempo"] > 0:                                               # 亮部偏暖、暗部偏冷
        t = np.clip((flat[..., 0] - 50) / 40, -1, 1)
        flat[..., 2] += P["tempo"] * 14 * t
        flat[..., 1] += P["tempo"] * 4 * t
    out = lab2rgb(flat).astype(np.float32)
    # 轮廓线：相邻区域平均色差大于 line_de 的边界
    de = np.zeros((h, w), np.float32)
    dx = np.sqrt(((mean[L[:, 1:]] - mean[L[:, :-1]]) ** 2).sum(-1))
    dy = np.sqrt(((mean[L[1:]] - mean[L[:-1]]) ** 2).sum(-1))
    de[:, 1:] = np.maximum(de[:, 1:], dx)
    de[1:] = np.maximum(de[1:], dy)
    edge = (de > P["line_de"]).astype(np.float32)
    r = max(1, int(round(P["line_w"] * s)))
    edge = ndi.grey_dilation(edge, footprint=np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r)
    edge = ndi.gaussian_filter(edge, 0.5 * s)
    # 细节线：XDoG（比轮廓淡）
    if P["detail"] > 0:
        E = xdog(ndi.gaussian_filter(rgb @ LUMA, 0.5 * s), P["detail_sigma"] * s, p=20, eps=0.55, phi=12)
        D = 1 - E
        if P["detail_min"] > 0:                                     # 去掉零碎的小线头（纹理噪点）
            lb, nn = ndi.label(D > 0.5)
            sz = np.bincount(lb.ravel(), minlength=nn + 1)
            D = D * (sz[lb] >= P["detail_min"] * s * s) * (lb > 0)
        edge = np.maximum(edge, P["detail"] * D)
    lc = np.asarray(P["line_col"], np.float32)
    out = out * (1 - edge[..., None]) + lc * edge[..., None]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


# ---------------- 低多边形 ----------------
LOWPOLY = dict(n=1500, init_frac=0.45, rounds=5, iters=6, final_iters=14, min_angle=14.0, min_area=2.0, stroke=0.6,
               sat=1.0, grad_pow=0.5)


def _ccw(pts, tris):
    """保证每个三角形的 orient > 0（与 npr.c 的约定一致）。"""
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    o = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    t = tris.copy()
    t[o < 0, 1], t[o < 0, 2] = tris[o < 0, 2], tris[o < 0, 1]
    return t


def _border_flags(pts, w, h):
    eps = 1e-3
    onx = (np.abs(pts[:, 0]) < eps) | (np.abs(pts[:, 0] - w) < eps)
    ony = (np.abs(pts[:, 1]) < eps) | (np.abs(pts[:, 1] - h) < eps)
    return np.where(onx & ony, 3, np.where(onx, 1, np.where(ony, 2, 0))).astype(np.int32)


def lowpoly_mesh(rgb, n_tri, seed=0, P=None):
    """优化后的三角网：返回 (顶点, 三角形, 每个三角形的颜色)。"""
    from scipy.spatial import Delaunay
    P = dict(LOWPOLY, **(P or {}))
    h, w = rgb.shape[:2]
    rng = np.random.default_rng(seed)
    d = np.sqrt(2.0 * w * h / n_tri) * 1.2                     # 期望边长
    # 边界点（四角固定，边上的点只能沿边移动）
    xs = np.linspace(0, w, max(2, int(round(w / d)) + 1))
    ys = np.linspace(0, h, max(2, int(round(h / d)) + 1))
    border = np.unique(np.concatenate([np.stack([xs, np.zeros_like(xs)], 1), np.stack([xs, np.full_like(xs, h)], 1),
                                       np.stack([np.zeros_like(ys), ys], 1), np.stack([np.full_like(ys, w), ys], 1)]), axis=0)
    nb = len(border)
    nv_target = int((n_tri + nb + 2) / 2)
    # 内部初始点：按边缘强度撒（边缘多撒）
    L = rgb @ LUMA
    g = ndi.gaussian_gradient_magnitude(ndi.gaussian_filter(L, 1.0), 1.0)
    p = (g / (g.max() + 1e-9)) ** P["grad_pow"] + 0.15
    p = (p / p.sum()).ravel()
    n0 = max(8, int(P["init_frac"] * (nv_target - nb)))
    idx = rng.choice(h * w, size=n0, replace=False, p=p)
    inner = np.stack([idx % w, idx // w], 1).astype(np.float32) + rng.random((n0, 2)).astype(np.float32)
    inner = np.clip(inner, 1, [w - 1, h - 1])
    pts = np.vstack([border, inner]).astype(np.float32)
    img = np.ascontiguousarray(rgb, np.float32)
    lib = _lib()
    for r in range(P["rounds"] + 1):
        tris = _ccw(pts, Delaunay(pts).simplices.astype(np.int32))
        flags = _border_flags(pts, w, h)
        verts = np.ascontiguousarray(pts, np.float32)
        tris = np.ascontiguousarray(tris, np.int32)
        err = np.zeros(len(tris), np.float64)
        last = r == P["rounds"] or len(pts) >= nv_target
        it = P["final_iters"] if last else P["iters"]
        lib.mesh_optimize(img, h, w, verts, len(verts), flags, tris, len(tris), it, float(d / (8 if last else 4)),
                          0.5, float(P["min_angle"]), float(P["min_area"]), int(seed * 7 + r), 1, err)
        pts = verts
        if last:
            break
        # 在误差最大的三角形里加点（重心）
        k = int(min(nv_target - len(pts), max(8, 0.6 * len(pts))))
        top = np.argsort(-err)[:k]
        cen = pts[tris[top]].mean(1)
        pts = np.vstack([pts, cen]).astype(np.float32)
    cols = np.zeros((len(tris), 3), np.float32)
    cnt = np.zeros(len(tris), np.float32)
    lib.mesh_colors(img, h, w, verts, tris, len(tris), cols, cnt)
    return verts, tris, cols


def lowpoly(img, strength=1.0, seed=0, size=1600, n=None, params=None, raster=False):
    """低多边形：优化顶点位置并按误差翻边的三角网，每个三角形填平均色。默认返回 SVG 文本；raster=True 返回 PIL 图。"""
    P = dict(LOWPOLY, **(params or {}))
    rgb, s = prep(img, size)
    h, w = rgb.shape[:2]
    n_tri = int((n or P["n"]) * strength)
    verts, tris, cols = lowpoly_mesh(rgb, n_tri, seed, P)
    if P["sat"] != 1.0:
        lab = rgb2lab(np.clip(cols[None], 0, 1))
        lab[..., 1:] *= P["sat"]
        cols = lab2rgb(lab)[0]
    c8 = np.clip(np.round(cols * 255), 0, 255).astype(int)
    if raster:
        k = 2
        im = Image.new("RGB", (w * k, h * k))
        dr = ImageDraw.Draw(im)
        for t, c in zip(tris, c8):
            dr.polygon([(float(verts[v, 0]) * k, float(verts[v, 1]) * k) for v in t], fill=tuple(int(x) for x in c))
        return im.resize((w, h), Image.LANCZOS)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
             f'<g stroke-width="{P["stroke"]}" stroke-linejoin="round">']
    for t, c in zip(tris, c8):
        q = verts[t]
        col = "#%02x%02x%02x" % tuple(int(x) for x in c)
        lines.append(f'<path fill="{col}" stroke="{col}" d="M{q[0,0]:.1f} {q[0,1]:.1f}L{q[1,0]:.1f} {q[1,1]:.1f} '
                     f'{q[2,0]:.1f} {q[2,1]:.1f}z"/>')
    lines.append("</g></svg>")
    return "\n".join(lines)


# ---------------- 几何抽象（半透明三角形拟合） ----------------
GEOM = dict(work=800, budget=3000, time=25.0, effort=0.3)


def geometric(img, strength=1.0, seed=0, size=1600, params=None):
    """几何抽象：用 ../autoresearch/best_solver.py 的半透明三角形贪心拟合，输出 gzip 后不超过 budget 字节的 SVG。
    strength 放大预算（越大越细）。返回 SVG 文本（viewBox 是工作尺寸，width/height 按 size 缩放）。"""
    import sys
    P = dict(GEOM, **(params or {}))
    rgb, _ = prep(img, min(size, P["work"]))
    h, w = rgb.shape[:2]
    solver = os.path.join(os.path.dirname(HERE), "autoresearch", "best_solver.py")
    budget = int(P["budget"] * strength)
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "in.png")
        Image.fromarray((rgb * 255).astype(np.uint8)).save(src)
        subprocess.run([sys.executable, solver, src, td, "--time", str(P["time"]), "--budgets", str(budget),
                        "--seed", str(seed), "--effort", str(P["effort"]), "--tiles", str(max(4, w // 100))],
                       check=True, capture_output=True)
        svg = open(os.path.join(td, f"b{budget}.svg")).read()
    k = min(size, max(img.size)) / max(w, h)
    return svg.replace(f'width="{w}" height="{h}"', f'width="{round(w * k)}" height="{round(h * k)}"', 1)


# ---------------- 没有参考图时：从 Wikimedia Commons 找一张可用的照片 ----------------
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "stylize.py/1.0 (procedural image stylization; no generative models)"}
FREE = ("public domain", "cc0", "pd", "cc by", "cc-by", "cc by-sa", "cc-by-sa")


def search_commons(query, n=8, min_width=1000):
    """按关键词在 Wikimedia Commons 搜照片，只返回公有领域 / CC0 / CC BY / CC BY-SA 授权的。
    返回 [dict(title, url, width, height, license, artist, page)]，url 是长边约 1600 的缩略图。"""
    import json
    import re
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                                "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": max(n * 3, 20),
                                "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1600})
    with urllib.request.urlopen(urllib.request.Request(f"{COMMONS_API}?{q}", headers=UA), timeout=30) as r:
        data = json.load(r)
    pages = sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if ii.get("mime") not in ("image/jpeg", "image/png") or ii.get("width", 0) < min_width:
            continue
        if not lic.lower().startswith(FREE):
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
        out.append(dict(title=p["title"], url=ii.get("thumburl") or ii["url"], width=ii["width"], height=ii["height"],
                        license=lic, artist=artist, page=ii.get("descriptionurl", "")))
        if len(out) >= n:
            break
    return out


def fetch_reference(query, pick=0):
    """搜一张参考照片并下载。返回 (PIL.Image, 署名文本)。署名需要随成品一起保留（CC BY / BY-SA 要求署名）。"""
    import io
    import urllib.request
    hits = search_commons(query)
    if not hits:
        raise RuntimeError(f"Wikimedia Commons 上没找到可用授权的照片：{query!r}")
    h = hits[min(pick, len(hits) - 1)]
    with urllib.request.urlopen(urllib.request.Request(h["url"], headers=UA), timeout=60) as r:
        img = Image.open(io.BytesIO(r.read())).convert("RGB")
    credit = f"{h['title']} — {h['artist'] or '作者不详'} — {h['license']} — {h['page']}"
    return img, credit


STYLES = {"ink": ink, "watercolor": watercolor, "lowpoly": lowpoly, "pencil": pencil, "oil": oil, "cartoon": cartoon,
          "geometric": geometric}


def stylize(img, style, strength=1.0, seed=0, size=1600, **kw):
    """img: PIL.Image；style: STYLES 里的名字。返回 PIL.Image，lowpoly / geometric 返回 SVG 文本。"""
    return STYLES[style](img, strength=strength, seed=seed, size=size, **kw)


def svg_to_image(svg):
    """把 lowpoly / geometric 的 SVG 栅格化（只认本工具输出的 path 三角形，不需要浏览器）。"""
    import re
    w = int(float(re.search(r'width="([0-9.]+)"', svg).group(1)))
    h = int(float(re.search(r'height="([0-9.]+)"', svg).group(1)))
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    k = 2                                                         # 2 倍超采样再缩小，边缘抗锯齿
    sx, sy = w * k / vb[2], h * k / vb[3]
    bg = re.search(r'<rect[^>]*fill="#([0-9a-f]{6})"', svg)
    im = Image.new("RGB", (w * k, h * k), "#" + bg.group(1) if bg else "white")
    op = re.search(r'fill-opacity="([0-9.]+)"', svg)
    alpha = float(op.group(1)) if op else 1.0
    for col, d in re.findall(r'<path fill="#([0-9a-f]{6})"[^>]*? d="([^"]+)"', svg):
        nums = [float(v) for v in re.findall(r"-?[0-9.]+", d)]
        if d.startswith("M") and "l" in d:                         # 相对坐标：M x y l dx dy dx dy
            x0, y0, dx1, dy1, dx2, dy2 = nums[:6]
            pts = [(x0, y0), (x0 + dx1, y0 + dy1), (x0 + dx1 + dx2, y0 + dy1 + dy2)]
        else:
            pts = [(nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5])]
        pts = [(x * sx, y * sy) for x, y in pts]
        c = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
        if alpha >= 1:
            ImageDraw.Draw(im).polygon(pts, fill=c)
        else:
            x0, y0 = int(min(p[0] for p in pts)), int(min(p[1] for p in pts))
            x1, y1 = int(max(p[0] for p in pts)) + 2, int(max(p[1] for p in pts)) + 2
            m = Image.new("L", (x1 - x0, y1 - y0), 0)
            ImageDraw.Draw(m).polygon([(x - x0, y - y0) for x, y in pts], fill=int(255 * alpha))
            im.paste(Image.new("RGB", m.size, c), (x0, y0), m)
    return im.resize((w, h), Image.LANCZOS)


STYLE_NOTES = {
    "ink": "水墨：宣纸、墨色浓淡、飞白、勾勒、留白构图、印章（--no-seal 关掉）。适合山水、风景、动物、静物",
    "watercolor": "水彩：色块概括、透明罩染、留白缝、边缘积色、颜料颗粒、四周留白。适合风景、建筑、街景",
    "lowpoly": "低多边形：优化过的三角网，每块平均色。输出 SVG（可无限放大），写 .png 则栅格化。适合动物、人像、产品",
    "pencil": "铅笔素描：方向线条 + 排线色调，四周淡出、天空留白。适合建筑、人像、室内",
    "oil": "油画：多层曲线笔触、双色混笔、厚涂光照、画布纹理、亮暖暗冷。适合人像、静物、风景",
    "cartoon": "卡通平涂：色块边界磨圆、加粗描线、提亮加饱和。适合人像、简单场景、图标式插画",
    "geometric": "几何抽象：约 200 个半透明三角形拟合（SVG，约 3KB）。适合海报、封面、抽象背景",
}


def main():
    ap = argparse.ArgumentParser(description="照片风格化（不用任何生成模型）")
    ap.add_argument("input", nargs="?", help="输入图片路径（或用 --search 按关键词找一张）")
    ap.add_argument("--search", help="没有参考图时：按关键词从 Wikimedia Commons 找一张公有领域/CC 授权的照片")
    ap.add_argument("--pick", type=int, default=0, help="--search 时用第几个结果（0 起）")
    ap.add_argument("--style", choices=sorted(STYLES) + ["all"], help="风格；all = 每种都出一张，另存一张总览图")
    ap.add_argument("--out", help="输出路径：.png/.jpg；lowpoly、geometric 写 .svg 得到矢量图，写 .png 则栅格化")
    ap.add_argument("--strength", type=float, default=1.0, help="风格强度（各风格含义见 README）")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--size", type=int, default=1600, help="输出的长边像素（输入更大时缩小）")
    ap.add_argument("--no-seal", action="store_true", help="水墨不盖印章")
    ap.add_argument("--list", action="store_true", help="列出所有风格和适用场景")
    a = ap.parse_args()
    if a.list:
        for k, v in STYLE_NOTES.items():
            print(f"{k:11s}{v}")
        return
    if not a.style or not a.out:
        ap.error("需要 --style 和 --out")
    if bool(a.input) == bool(a.search):
        ap.error("给一个输入图片路径，或者用 --search 关键词（二选一）")
    credit = None
    if a.search:
        img, credit = fetch_reference(a.search, a.pick)
    else:
        img = Image.open(a.input)
    styles = list(STYLES) if a.style == "all" else [a.style]
    base, ext = os.path.splitext(a.out)
    outs = []
    for st in styles:
        path = a.out if len(styles) == 1 else f"{base}_{st}{ext}"
        kw = {}
        if st == "ink":
            kw["seal"] = not a.no_seal
        if st == "lowpoly" and not path.lower().endswith(".svg"):
            kw["raster"] = True
        res = stylize(img, st, a.strength, a.seed, a.size, **kw)
        if isinstance(res, str):
            if path.lower().endswith(".svg"):
                open(path, "w").write(res)
            else:
                res = svg_to_image(res)
        if not isinstance(res, str):
            res.convert("RGB").save(path)
        outs.append((st, path, res))
        print(path)
    if len(styles) > 1:                                             # 总览图：每种风格一格，带名字
        from PIL import ImageFont
        tiles = [(st, r if not isinstance(r, str) else svg_to_image(r)) for st, _, r in outs]
        H = 360
        tiles = [(st, im.convert("RGB").resize((max(1, round(im.width * H / im.height)), H))) for st, im in tiles]
        cols = 4
        cw = max(im.width for _, im in tiles)
        sheet = Image.new("RGB", (cols * (cw + 10) + 10, ((len(tiles) + cols - 1) // cols) * (H + 40) + 10), "white")
        dr = ImageDraw.Draw(sheet)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
        for i, (st, im) in enumerate(tiles):
            x, y = 10 + (i % cols) * (cw + 10), 10 + (i // cols) * (H + 40)
            dr.text((x, y), st, fill="black", font=font)
            sheet.paste(im, (x, y + 28))
        sheet.save(f"{base}_all.png")
        print(f"{base}_all.png")
    if credit:
        open(base + ".credit.txt", "w").write(credit + "\n")
        print("参考照片：" + credit)


if __name__ == "__main__":
    main()
