#!/usr/bin/env python3
"""B09 书桌一角：台灯、打开的书、一杯咖啡、一盆绿植。

底图是一张窗边书桌照片（已有台灯和一小盆多肉），用代码把桌面往下补画延伸，
再从另外两张照片里抠出一本打开的书和一杯咖啡放到桌上，统一色调，加阴影和台灯的暖光。
只读 refs/ 里的照片，不联网。用法：python3 draw.py [--out final.png]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
from stylize import fbm, smoothstep  # noqa: E402  程序化噪声（只 import，不改）

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 9
W = 1600
EXT = 180                      # 桌面往下补画的高度（成图像素）
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def ref(name):
    return os.path.join(HERE, "refs", name)


def load(name):
    return np.asarray(Image.open(ref(name)).convert("RGB"), np.float32) / 255


def poly_mask(h, w, pts, ss=2):
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return np.asarray(im.resize((w, h), Image.BOX), np.float32) / 255


def place(canvas_hw, src, mask, sx0, sy0, scale, squash, dx, dy):
    """把 src 里以 (sx0, sy0) 为锚点的物体，缩放 scale（竖向再乘 squash）后，锚点放到成图 (dx, dy)。
    返回成图大小的 (rgb, alpha)。"""
    H, W_ = canvas_hw
    yy, xx = np.mgrid[0:H, 0:W_].astype(np.float32)
    sx = (xx - dx) / scale + sx0
    sy = (yy - dy) / (scale * squash) + sy0
    # 先把源图按缩放比例预模糊，避免缩小时混叠
    sig = max(0.0, 0.5 / scale - 0.5)
    s_rgb = ndi.gaussian_filter(src, (sig, sig, 0)) if sig > 0 else src
    s_m = ndi.gaussian_filter(mask, sig) if sig > 0 else mask
    rgb = np.stack([ndi.map_coordinates(s_rgb[..., c], [sy, sx], order=1, mode="constant") for c in range(3)], -1)
    a = ndi.map_coordinates(s_m, [sy, sx], order=1, mode="constant")
    return rgb, np.clip(a, 0, 1)


def match_tone(rgb, mask, target_white, target_black=(0.12, 0.10, 0.13), sat=0.7):
    """把抠出来的物体的色调拉到底图的调子：去掉原来的偏色，白点、黑点对齐底图，饱和度降一点。"""
    m = mask > 0.5
    Y = rgb @ LUMA
    lo, hi = np.percentile(Y[m], 2), np.percentile(Y[m], 99.5)
    t = np.clip((Y - lo) / max(hi - lo, 1e-3), 0, 1)
    chroma = (rgb - Y[..., None]) * sat
    # 每个通道各自按原图的白点做白平衡
    wb = np.array([np.percentile(rgb[..., c][m], 99) for c in range(3)], np.float32)
    rgb_wb = rgb / wb * wb.mean()
    Ywb = rgb_wb @ LUMA
    chroma = (rgb_wb - Ywb[..., None]) * sat
    base = np.asarray(target_black, np.float32) * (1 - t[..., None]) + np.asarray(target_white, np.float32) * t[..., None]
    return np.clip(base + chroma, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "final.png"))
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)

    # ---------- 底图：窗边书桌（原图 4288x2848）缩到 1600 宽，桌面往下补 EXT 像素 ----------
    src = Image.open(ref("Laptop_and_lamp_on_table_(Unsplash).jpg")).convert("RGB")
    S = W / src.width
    H0 = round(src.height * S)
    base = np.asarray(src.resize((W, H0), Image.LANCZOS), np.float32) / 255
    H = H0 + EXT
    img = np.zeros((H, W, 3), np.float32)
    img[:H0] = base
    # 补画桌面：桌上那道斜的窗框阴影向左下延伸，按它的方向把最底下几行的颜色斜着拉下来
    bottom = base[H0 - 6:H0 - 1].mean(0)                     # (W, 3)
    bottom = ndi.gaussian_filter1d(bottom, 2, axis=0)
    yy_e, xx_e = np.mgrid[0:EXT, 0:W].astype(np.float32)
    xs = np.clip(xx_e + 3.0 * (yy_e + 3), 0, W - 1)
    ext = np.stack([np.interp(xs.ravel(), np.arange(W), bottom[:, c]).reshape(EXT, W) for c in range(3)], -1)
    ext *= (1 - 0.10 * (yy_e / EXT))[..., None]            # 离窗越远越暗一点
    ext += ((fbm(EXT, W, 4, 2, SEED) - 0.5) * 0.012)[..., None]
    img[H0:] = ext
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # ---------- 书：从“阳光下打开的书”里抠出来（多边形蒙版，原图坐标） ----------
    bsrc = load("Open_book_in_sun_(Unsplash).jpg")
    book_poly = [(148, 3030), (246, 2784), (394, 2456), (574, 2194), (705, 2030), (787, 1980), (984, 1948),
                 (1312, 1915), (1640, 1892), (1968, 1931), (2165, 2030), (2230, 2095), (2296, 1997), (2493, 1948),
                 (2788, 1964), (3116, 2003), (3444, 2062), (3772, 2161), (3969, 2259), (4100, 2456), (4231, 2718),
                 (4362, 2948), (4460, 3079), (4477, 3128), (4264, 3161), (3608, 3128), (2952, 3086), (2493, 3046),
                 (2296, 2997), (2263, 2948), (2099, 3030), (1640, 3063), (984, 3063), (492, 3053)]
    bmask = poly_mask(bsrc.shape[0], bsrc.shape[1], book_poly)
    bmask = ndi.gaussian_filter(bmask, 3.0)
    desk_white = np.array([0.93, 0.90, 0.95], np.float32)       # 底图桌面亮处的淡紫白
    b_rgb = match_tone(bsrc, bmask, target_white=desk_white, target_black=(0.30, 0.28, 0.34), sat=0.35)
    # 书的锚点：左下角 (148, 3030)；成图里放在桌面前部
    book_rgb, book_a = place((H, W), b_rgb, bmask, 148, 3030, 0.19, 0.85, 205, 1190)

    # ---------- 咖啡：从“白杯和笔记本”里按颜色抠白杯+碟子 ----------
    csrc = load("White_cup_and_MacBook_(Unsplash).jpg")
    x0, x1, y0, y1 = 70, 860, 1225, 1660
    sub = csrc[y0:y1, x0:x1]
    mx, mn = sub.max(-1), sub.min(-1)
    white = (mn > 0.55) & ((mx - mn) < 0.22)                  # 白瓷：亮、低饱和
    coffee = (np.abs(np.arange(y1 - y0)[:, None] - 80) < 40) & (sub.mean(-1) < 0.5)   # 杯口里的咖啡
    cm = white | coffee
    cm = ndi.binary_closing(cm, iterations=4)
    cm = ndi.binary_fill_holes(cm)
    lab, n = ndi.label(cm)
    if n > 1:
        sizes = ndi.sum(cm, lab, range(1, n + 1))
        cm = lab == (1 + int(np.argmax(sizes)))
    cm = ndi.binary_opening(cm, iterations=2)
    cmask = np.zeros(csrc.shape[:2], np.float32)
    cmask[y0:y1, x0:x1] = ndi.gaussian_filter(cm.astype(np.float32), 1.2)
    # 杯碟上反射的橙色桌面：降饱和
    c_rgb = csrc.copy()
    Yc = c_rgb @ LUMA
    c_rgb = Yc[..., None] + (c_rgb - Yc[..., None]) * 0.35
    c_rgb = np.clip(c_rgb * np.array([0.98, 0.97, 1.02], np.float32), 0, 1)
    cup_rgb, cup_a = place((H, W), c_rgb, cmask, 460, 1640, 0.44, 1.0, 1290, 1228)

    # ---------- 阴影：书和杯子挡住窗光，影子落在靠近镜头的一侧（往下、略往左） ----------
    def shadow(alpha, off=(10, -6), blur=10, k=0.30):
        sh = ndi.shift(alpha, off, order=1)
        sh = ndi.gaussian_filter(sh, blur)
        return k * sh

    sh = shadow(book_a, (8, -10), 12, 0.28) + shadow(cup_a, (10, -12), 9, 0.32)
    contact = ndi.gaussian_filter(np.clip(ndi.shift(book_a, (3, 0), order=1) - book_a, 0, 1), 2) * 0.35 \
        + ndi.gaussian_filter(np.clip(ndi.shift(cup_a, (3, 0), order=1) - cup_a, 0, 1), 2) * 0.4
    img = img * (1 - np.clip(sh + contact, 0, 0.6))[..., None] * np.array([1.0, 0.98, 1.02], np.float32) + \
        img * np.clip(sh + contact, 0, 0.6)[..., None] * 0.0
    img = img * (1 - book_a[..., None]) + book_rgb * book_a[..., None]
    img = img * (1 - cup_a[..., None]) + cup_rgb * cup_a[..., None]

    # ---------- 台灯打开：灯罩口一团暖光，书页上一片暖色光斑 ----------
    lin = np.power(img, 2.2)
    gx, gy = 2300 * S, 1080 * S                               # 灯罩开口（原图坐标）
    glow = np.exp(-(((xx - gx) / 70) ** 2 + ((yy - gy) / 55) ** 2))
    pool = np.exp(-(((xx - 640) / 430) ** 2 + ((yy - 1060) / 150) ** 2))
    warm = np.array([1.0, 0.78, 0.48], np.float32)
    lin = lin + (0.35 * glow + 0.10 * pool)[..., None] * warm
    img = np.power(np.clip(lin, 0, 1), 1 / 2.2)

    # ---------- 统一：整体轻微的哑光和淡紫调（底图本来的调子），细颗粒 ----------
    img = 0.03 + img * 0.96
    img = img + rng.normal(0, 0.008, img.shape).astype(np.float32)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(a.out)
    print("saved", a.out, img.shape)


if __name__ == "__main__":
    main()
