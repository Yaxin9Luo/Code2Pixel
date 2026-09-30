#!/usr/bin/env python3
"""B02 日落时的雪山湖泊，湖面倒映着山影。

素材：一张授权照片（Giles Laurent 拍的 Stellisee 湖里的马特洪峰日落倒影，CC BY-SA 4.0），存在 refs/。
画法：代码分出天空 / 山 / 草坡 / 湖面，按日落调色（积雪加亮偏暖、亮部暖暗部冷、落日方向加一团暖光，
倒影里对应的位置同样处理），再用 stylize 的笔触内核按自定的笔势方向（湖面、天空横刷，山体顺着山势）
一层层画成油画，最后按颜料厚度打光、加画布纹理。
用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys

sys.dont_write_bytecode = True                      # 不在 stylize/ 下写 __pycache__
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
from scipy import ndimage as ndi                    # noqa: E402
import stylize as S                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "refs", "matterhorn_stellisee_sunset_giles_laurent.jpg")
W, H = 1500, 1000
SEED = 7
MIRROR_Y = 492          # 远山倒影的对称轴（照片里峰顶 y≈293，倒影峰尖 y≈691）


def load():
    im = Image.open(REF).convert("RGB").resize((W, H), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def shoreline():
    """湖岸线（从照片上量的折线）：这条线以下是水。"""
    xs = [0, 650, 950, 1000, 1100, 1200, 1300, 1400, 1500]
    ys = [510, 503, 500, 505, 518, 530, 542, 552, 560]
    return np.interp(np.arange(W), xs, ys).astype(np.float32)


def ridge_line(L):
    """天际线：动态规划找一条从左到右的路径，路径上方亮、下方暗的反差之和最大（同时略偏向靠上的边）。"""
    Lb = ndi.gaussian_filter(L, 1.5)
    d = 3
    D = np.zeros_like(Lb)
    D[d:-d] = Lb[:-2 * d] - Lb[2 * d:]
    y0, y1 = 200, 540
    cost = -np.clip(D[y0:y1], 0, None) + 0.0004 * np.arange(y1 - y0)[:, None]
    n = y1 - y0
    k = 6
    acc = cost[:, 0].copy()
    back = np.zeros((n, W), np.int16)
    for x in range(1, W):
        best = np.full(n, np.inf, np.float32)
        arg = np.zeros(n, np.int16)
        for dy in range(-k, k + 1):
            sh = np.full(n, np.inf, np.float32)
            if dy >= 0:
                sh[:n - dy] = acc[dy:]
            else:
                sh[-dy:] = acc[:n + dy]
            sh = sh + 0.004 * abs(dy)
            m = sh < best
            best[m] = sh[m]
            arg[m] = dy
        acc = cost[:, x] + best
        back[:, x] = arg
    y = int(np.argmin(acc))
    path = np.zeros(W, np.int32)
    for x in range(W - 1, -1, -1):
        path[x] = y
        y += back[y, x]
    return (path + y0).astype(np.float32)


def masks(rgb):
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32)
    L = rgb @ S.LUMA
    ridge = ridge_line(L)
    shore = shoreline()
    sky = S.smoothstep(2, -2, yy - ridge[None, :])
    water = S.smoothstep(-2, 3, yy - shore[None, :])
    land = np.clip(1 - sky - water, 0, 1)
    return sky, land, water, ridge, shore


def mirror(m, shore):
    """把山上的掩码按远山倒影的对称轴翻到湖面上（只留在水里）。"""
    yy = np.arange(H)[:, None]
    src = np.clip(2 * MIRROR_Y - yy, 0, H - 1)
    out = m[src, np.arange(W)[None, :]]
    return out * (yy > shore[None, :] + 2)


def grade(rgb, sky, land, water, ridge, shore):
    """日落调色。返回调好色的 rgb 和积雪掩码。"""
    lab = S.rgb2lab(rgb)
    Lc, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # 积雪：山体里偏亮、偏灰、比周围亮的地方
    # （照片里积雪 L≈47–61、岩石 L≈37–45、左侧山体 L≈26；草坡偏黄绿、彩度高）
    Lloc = ndi.gaussian_filter(Lc, 12)
    below_ridge = S.smoothstep(2, 6, yy - ridge[None, :])
    meadow = land * S.smoothstep(4, 14, b) * S.smoothstep(2, -6, a)
    snow = land * below_ridge * S.smoothstep(42, 52, Lc) * S.smoothstep(22, 10, chroma) * S.smoothstep(-3, 5, Lc - Lloc)
    snow = ndi.gaussian_filter(snow * (1 - meadow), 0.6)
    snow_w = mirror(snow, shore)
    rock = land * (1 - meadow) * (1 - snow) * S.smoothstep(shore[None, :] - 20, shore[None, :] - 60, yy)
    mount = land * (1 - meadow)
    mt = np.maximum(mount, 0.85 * mirror(mount, shore))
    near_top = mount * S.smoothstep(130, 15, yy - ridge[None, :])          # 离天际线近 = 山的高处
    warm = np.maximum(near_top, mirror(near_top, shore))
    L0 = Lc.copy()
    # 山体（和倒影里的山）局部反差加强：山脊、雪沟、岩带更清楚
    Lc = Lc + 0.9 * mt * (L0 - ndi.gaussian_filter(L0, 6))
    # 亮部偏暖、暗部偏冷
    t = np.clip((Lc - 55) / 35, -1, 1)
    b = b + 7 * t
    a = a + 2.5 * t
    # 天空加饱和，越靠近地平线越暖
    horizon = S.smoothstep(150, 480, yy)
    a = a * (1 + 0.25 * sky) + 4 * sky * horizon
    b = b * (1 + 0.30 * sky) + 6 * sky * horizon
    # 湖面（倒影）稍暗一点、同样加饱和
    a = a * (1 + 0.2 * water)
    b = b * (1 + 0.2 * water)
    Lc = Lc - 3 * water
    # 积雪：提亮、染上夕照的粉橙
    sn = np.maximum(snow, 0.8 * snow_w)
    det = L0 - ndi.gaussian_filter(L0, 3)                                   # 保留雪面自己的纹理
    Lc = Lc + sn * (18 + 1.2 * det)
    a = a + sn * (1 + 6 * warm)                                             # 高处的雪被夕照染成粉橙，低处偏冷
    b = b + sn * (-3 + 12 * warm)
    # 峰顶一带（岩石也算）再罩一层夕照的暖色
    gt = mt * warm * S.smoothstep(28, 48, L0)
    Lc = Lc + 5 * gt
    a = a + 6 * gt
    b = b + 6 * gt
    # 岩石稍压暗、偏冷，让雪跳出来（倒影里同样）
    rk = np.maximum(rock, 0.8 * mirror(rock, shore))
    Lc = Lc - 5 * rk
    b = b - 4 * rk
    out = S.lab2rgb(np.stack([Lc, a, b], -1)).astype(np.float32)
    # 落日方向（右侧山后）加一团暖光，倒影里对应位置弱一些
    for cx, cy, amp in ((1270, 425, 0.30), (1270, 2 * MIRROR_Y - 425, 0.16)):
        r2 = ((xx - cx) / 420) ** 2 + ((yy - cy) / 170) ** 2
        g = amp * np.exp(-r2)
        g = g * (sky + water) if cy < MIRROR_Y else g * water
        glow = np.array([1.0, 0.62, 0.30], np.float32)
        out = 1 - (1 - out) * (1 - g[..., None] * glow)          # 滤色叠加
    return np.clip(out, 0, 1), sn


def direction_field(src, sky, water):
    """笔势：山体顺着结构张量的方向；天空里平淡处横刷；湖面一律横刷（带一点起伏）。"""
    L = src @ S.LUMA
    tx, ty, coh = S.flow_field(ndi.gaussian_filter(L, 1.0), 1.0, sigma=2.0, rho=5.0)
    flip = tx < 0                                     # 统一朝右，才能和"横向"方向混合
    tx, ty = np.where(flip, -tx, tx), np.where(flip, -ty, ty)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    hx = np.ones_like(tx)
    hy = 0.06 * np.sin(xx / 37.0 + yy / 23.0).astype(np.float32)
    k_sky = sky * (1 - S.smoothstep(0.15, 0.6, coh)) * 0.8
    k = np.clip(np.maximum(k_sky, water), 0, 1)
    tx2 = (1 - k) * tx + k * hx
    ty2 = (1 - k) * ty + k * hy
    nn = np.hypot(tx2, ty2) + 1e-6
    return (tx2 / nn).astype(np.float32), (ty2 / nn).astype(np.float32)


def paint(src, tx, ty, seed):
    """多层曲线笔触（stylize 的 C 内核，mode 0 = 油画），大笔铺底、小笔收细节；返回画布与颜料厚度。"""
    canvas = np.ascontiguousarray(np.broadcast_to(np.array([0.42, 0.30, 0.22], np.float32), (H, W, 3)).copy())
    height = np.zeros((H, W), np.float32)
    radii = (26, 13, 6.5, 3.2)
    Ts = (0.0, 0.07, 0.09, 0.11)
    for li, (R, T) in enumerate(zip(radii, Ts)):
        rb = 0.5 if li < 2 else 0.35
        ref = np.ascontiguousarray(ndi.gaussian_filter(src, (rb * R, rb * R, 0)), np.float32)
        S.paint_layer(ref, canvas, tx, ty, 0, seed * 41 + li, height=height, R=R, step=0.8 * R,
                      grid=max(2, int(R)), T=T, min_len=3, max_len=16, fc=0.6, stop=0.18, rj_lo=0.85,
                      rj_hi=1.15, tin=0.05, tout=0.15, op=0.95, soft=0.12, bristle=0.5, thick=1.0, jit=0.04,
                      mix=0.5, ridge=0.2, dry_p=0.25, dry=0.3)
    # 焦点（马特洪峰和它的倒影）再用细笔收一遍：焦点外把目标设成画布本身，就不会落笔
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    fz = np.exp(-(((xx - 760) / 230) ** 2 + ((yy - 470) / 250) ** 2))[..., None]
    R = 2.2
    ref = ndi.gaussian_filter(src, (0.35 * R, 0.35 * R, 0))
    ref = np.ascontiguousarray(ref * fz + canvas * (1 - fz), np.float32)
    S.paint_layer(ref, canvas, tx, ty, 0, seed * 41 + 9, height=height, R=R, step=0.8 * R, grid=2, T=0.04,
                  min_len=3, max_len=12, fc=0.6, stop=0.15, rj_lo=0.85, rj_hi=1.15, tin=0.05, tout=0.15, op=0.95,
                  soft=0.12, bristle=0.4, thick=0.8, jit=0.03, mix=0.4, ridge=0.2, dry_p=0.2, dry=0.3)
    return canvas, height


def impasto(canvas, height, seed):
    """颜料厚度 → 法线 → 侧光（左上）打光 + 一点高光，再叠亚麻画布纹理。"""
    hgt = ndi.gaussian_filter(height, 0.7) + 0.05 * S.canvas_texture(H, W, 1.0, seed + 3)
    gy, gx = np.gradient(hgt)
    k = 1.3
    nx, ny, nz = -k * gx, -k * gy, np.ones_like(gx)
    nn = np.sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly, lz = -0.6, -0.8, 1.0
    ln = np.sqrt(lx * lx + ly * ly + lz * lz)
    diff = (nx * lx + ny * ly + nz * lz) / (nn * ln)
    spec = np.clip(diff, 0, 1) ** 24
    out = canvas * (0.55 + 0.45 * diff / (lz / ln))[..., None] + 0.05 * spec[..., None]
    return np.clip(out, 0, 1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    rgb = load()
    sky, land, water, ridge, shore = masks(rgb)
    src, snow = grade(rgb, sky, land, water, ridge, shore)
    # 画面中心（山峰和倒影）保留细节，四角先糊一点，只留大笔
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((xx - W * 0.5) / (W * 0.5), (yy - H * 0.52) / (H * 0.5)) / np.sqrt(2)
    fm = (0.45 * S.smoothstep(0.35, 0.95, r))[..., None]
    src = src * (1 - fm) + ndi.gaussian_filter(src, (6, 6, 0)) * fm
    tx, ty = direction_field(src, sky, water)
    canvas, height = paint(src, tx, ty, SEED)
    out = impasto(canvas, height, SEED)
    out = out * (1 - 0.18 * np.array([0.0, 0.05, 0.16], np.float32))          # 一点旧光油的暖色
    out = out * (1 - 0.10 * S.smoothstep(0.5, 1.0, r))[..., None]              # 四角略压暗，视线落在山和倒影上
    # 裁掉右缘那丛草（在画面里只是一块黑斑），保持 3:2
    out = out[16:976, 8:1448]
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out_path)
    print(out_path, "ridge@758 =", ridge[758], "ridge@0 =", ridge[0], "ridge@1450 =", ridge[1450],
          "snow px =", int((snow > 0.5).sum()))


if __name__ == "__main__":
    main()
