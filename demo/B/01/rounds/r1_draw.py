#!/usr/bin/env python3
"""B01 雨后江南水乡：南浔运河照片做底，抠一条绍兴乌篷船贴到河上，再用代码加倒影、雨后涟漪、阴天调色和远处薄雾。

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
SEED = 7
W = 1600
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def ref(name):
    return os.path.join(HERE, "refs", name)


def to_lin(x):
    return np.power(np.clip(x, 0, 1), 2.2)


def to_srgb(x):
    return np.power(np.clip(x, 0, 1), 1 / 2.2)


def poly_mask(h, w, pts, ss=4):
    """多边形蒙版，ss 倍超采样抗锯齿。pts 为 (x, y) 像素坐标。"""
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return np.asarray(im.resize((w, h), Image.BOX), np.float32) / 255


def grade(rgb, sat=0.45, tint=(-0.035, -0.004, 0.03)):
    """日出暖调 → 雨后阴天冷灰：降饱和，高光偏青灰，暗部略提。输入输出 sRGB。"""
    Y = rgb @ LUMA
    out = Y[..., None] + (rgb - Y[..., None]) * sat
    out = out + np.asarray(tint, np.float32) * smoothstep(0.05, 0.9, Y)[..., None]
    return np.clip(0.035 + out * 0.965, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "final.png"))
    a = ap.parse_args()
    rng = np.random.default_rng(SEED)

    # ---------- 底图：南浔运河（原图 5002x3193，缩到 1600 宽） ----------
    src = Image.open(ref("Nanxun_-_Ancient_water_town_-_0100.jpg")).convert("RGB")
    S = W / src.width
    H = round(src.height * S)
    base = np.asarray(src.resize((W, H), Image.LANCZOS), np.float32) / 255
    lum0 = base @ LUMA
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # 水面：两岸石驳岸的水线以下（坐标按原图量，再乘 S）
    water_pts = [(0, 1995), (1000, 1905), (2000, 1810), (2760, 1752), (3150, 1722), (3450, 1655),
                 (3800, 1765), (4300, 1832), (5002, 1905), (5002, 3193), (0, 3193)]
    water = poly_mask(H, W, [(x * S, y * S) for x, y in water_pts])
    water = ndi.gaussian_filter(water, 1.0)

    # 天空：亮、在水线以上、和上边缘连通
    sky = (lum0 > 0.72) & (water < 0.5)
    lab, _ = ndi.label(sky)
    top = np.unique(lab[0][lab[0] > 0])
    sky = np.isin(lab, top).astype(np.float32)
    sky = ndi.gaussian_filter(sky, 1.2)

    # 桥身（拱桥剪影）：给它一个固定深度，免得拱顶按"走廊"模型算成无穷远
    bridge_box = poly_mask(H, W, [(x * S, y * S) for x, y in
                                  [(2740, 1040), (3900, 1040), (3900, 1760), (2740, 1760)]])
    bridge = bridge_box * (lum0 < 0.45)
    bridge = ndi.gaussian_filter(bridge, 1.0)

    # ---------- 调色：暖日出 → 冷灰阴天 ----------
    img = to_lin(grade(base))

    # ---------- 深度（米）：简单的"走廊"模型：左右两排房子 + 水面 ----------
    f = 1256.0                       # 等效焦距（像素），按约 65° 水平视角估的
    vpx, vpy = 3450 * S, 1640 * S    # 河道灭点
    u = (xx - vpx) / f
    v = (yy - vpy) / f
    XL, XR, HC = 7.0, 4.5, 2.5       # 左岸、右岸离视线的横向距离，相机离水面高度
    wall = np.where(u < 0, np.abs(u) / XL, np.abs(u) / XR)
    z = 1.0 / np.maximum(np.maximum(wall, np.where(v > 0, v / HC, 0)), 1e-4)
    z = np.minimum(z, 400.0)
    z = z * (1 - bridge) + 45.0 * bridge   # 拱桥约 45 米
    z = z * (1 - sky) + 400.0 * sky

    # ---------- 船：从绍兴乌篷船照片里抠出最前面那条（船尾被画框切掉） ----------
    bsrc = np.asarray(Image.open(ref("乌篷船_-_panoramio.jpg")).convert("RGB"), np.float32) / 255
    boat_poly = [(100, 1158), (170, 1150), (173, 1095), (180, 1088), (360, 1079), (366, 1073), (450, 1064),
                 (550, 1056), (615, 1047), (630, 1046), (641, 1056), (646, 1085), (660, 1086), (700, 1082),
                 (745, 1080), (765, 1100), (780, 1148), (776, 1165), (770, 1180),
                 (740, 1203), (650, 1237), (500, 1280), (300, 1329), (150, 1355), (100, 1365)]
    waterline_src = [(100, 1365), (150, 1355), (300, 1329), (500, 1280), (650, 1237), (740, 1203), (770, 1180)]
    bmask = poly_mask(bsrc.shape[0], bsrc.shape[1], boat_poly)
    bmask = ndi.gaussian_filter(bmask, 0.7)
    sc = 0.66                                    # 源图 → 成图的缩放
    ox, oy = -4.0, 985.0                         # 源图 (100, 1365) 放到成图的位置
    to_dst = lambda x, y: ((x - 100) * sc + ox, (y - 1365) * sc + oy)
    # 反向映射：成图像素 → 源图像素
    sx = (xx - ox) / sc + 100
    sy = (yy - oy) / sc + 1365
    boat_rgb = np.stack([ndi.map_coordinates(bsrc[..., c], [sy, sx], order=1, mode="constant") for c in range(3)], -1)
    boat_a = ndi.map_coordinates(bmask, [sy, sx], order=1, mode="constant")
    boat_rgb = to_lin(grade(boat_rgb, sat=0.55, tint=(-0.02, 0.0, 0.02)) * 0.92)

    # 水线（成图坐标），逐列插值
    wl = np.array([to_dst(x, y) for x, y in waterline_src])
    cols = np.arange(W, dtype=np.float32)
    yw = np.interp(cols, wl[:, 0], wl[:, 1], left=np.nan, right=np.nan)
    has = ~np.isnan(yw)
    yw_f = np.where(has, yw, 0)

    # 倒影：沿水线逐列上下翻转，压暗、略糊
    ry = 2 * yw_f[None, :] - yy
    refl_rgb = np.stack([ndi.map_coordinates(boat_rgb[..., c], [ry, xx], order=1, mode="constant") for c in range(3)], -1)
    refl_a = ndi.map_coordinates(boat_a, [ry, xx], order=1, mode="constant")
    below = (yy > yw_f[None, :]) & has[None, :]
    refl_a = refl_a * below * np.exp(-np.clip(yy - yw_f[None, :], 0, None) / 160.0)
    refl_rgb = ndi.gaussian_filter(refl_rgb, (1.2, 0.6, 0))
    refl_a = ndi.gaussian_filter(refl_a, (1.2, 0.6))
    img = img * (1 - 0.85 * refl_a[..., None]) + 0.85 * refl_a[..., None] * refl_rgb * 0.75

    # ---------- 雨后涟漪：屋檐滴水打出的几圈水纹（透视压扁的同心圆） ----------
    hgt = np.zeros((H, W), np.float32)
    n_ok = 0
    while n_ok < 16:
        cx = rng.uniform(0, W)
        cy = vpy + (H - vpy) * rng.uniform(0.12, 0.98) ** 0.8
        if water[int(cy), int(cx)] < 0.9:
            continue
        n_ok += 1
        d = cy - vpy
        asp = d / np.hypot(f, d)                 # 水面透视压扁比
        r_img = rng.uniform(0.12, 0.35) * d / HC  # 半径 0.12–0.35 米换成像素
        lam = max(2.5, 0.35 * r_img)
        x0, x1 = int(max(0, cx - 2 * r_img - 20)), int(min(W, cx + 2 * r_img + 20))
        y0, y1 = int(max(0, cy - 2 * r_img * asp - 10)), int(min(H, cy + 2 * r_img * asp + 10))
        rho = np.hypot(xx[y0:y1, x0:x1] - cx, (yy[y0:y1, x0:x1] - cy) / asp)
        wave = np.sin(2 * np.pi * (rho - r_img) / lam) * np.exp(-((rho - r_img) / (1.6 * lam)) ** 2)
        hgt[y0:y1, x0:x1] += rng.uniform(0.5, 1.0) * wave * (1 - 0.5 * (rho < r_img))
    # 船边的细浪：顺着水线的几道平行纹
    dyw = yy - yw_f[None, :]
    near_hull = has[None, :] & (dyw > 0) & (dyw < 60)
    hgt += near_hull * 0.6 * np.sin(2 * np.pi * dyw / 9.0) * np.exp(-dyw / 22.0)
    gy, gx = np.gradient(ndi.gaussian_filter(hgt, 0.8))
    k_disp = 4.0
    wy = yy + k_disp * gy * water * 6
    wx = xx + k_disp * gx * water * 2
    rip = np.stack([ndi.map_coordinates(img[..., c], [wy, wx], order=1, mode="nearest") for c in range(3)], -1)
    shade = np.clip(1 + 1.6 * gy * water, 0.7, 1.5)
    img = img * (1 - water[..., None]) + rip * shade[..., None] * water[..., None]

    # 船贴上去（贴在涟漪之后，船身本身不受水纹影响）
    contact = has[None, :] & (dyw > -1) & (dyw < 6)
    img = img * (1 - 0.35 * contact[..., None] * np.exp(-np.clip(dyw, 0, None) / 3.0)[..., None])
    img = img * (1 - boat_a[..., None]) + boat_rgb * boat_a[..., None]
    z = z * (1 - boat_a) + 6.5 * boat_a

    # ---------- 薄雾：按深度的大气透过率，远处更白；再加一点成团的起伏 ----------
    patch = fbm(H, W, 220, 4, SEED + 11)
    vis = 120.0 * (0.75 + 0.5 * patch)          # 能见距离（米），成团变化
    T = np.exp(-z / vis)
    # 贴水面的一层低雾：远处水面上方更浓
    low = np.exp(-((yy - (vpy + 8)) / 38.0) ** 2) * np.exp(-((xx - vpx) / 420.0) ** 2)
    T = T * (1 - 0.35 * low * (0.6 + 0.8 * patch))
    fog_top = np.array([0.80, 0.83, 0.86], np.float32)
    fog_hor = np.array([0.89, 0.91, 0.92], np.float32)
    g = smoothstep(0.0, 0.55, yy / H)[..., None]
    fog = to_lin(fog_top * (1 - g) + fog_hor * g)
    img = img * T[..., None] + fog * (1 - T[..., None])

    # ---------- 收尾：轻微暗角 + 胶片颗粒 ----------
    out = to_srgb(img)
    r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    out = out * (1 - 0.07 * np.clip(r2 - 0.3, 0, None))[..., None]
    out = out + rng.normal(0, 0.006, out.shape).astype(np.float32)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(a.out)
    print("saved", a.out, out.shape)


if __name__ == "__main__":
    main()
