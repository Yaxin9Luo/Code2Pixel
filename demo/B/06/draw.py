#!/usr/bin/env python3
"""B06 窗边看书的老人。

素材：一张授权照片（Shixart1985 拍的老人在窗前沙发上叼着烟斗看书，CC BY 2.0），存在 refs/。
画法（自己写的钢笔淡彩渲染，只借用 stylize 里的 L0 平滑、引导滤波、分形噪声、纸纹、流场、线积分这些底层函数）：
  1. 把窗子画回来：照片里窗子被纱帘挡着又过曝，从亮度剖面量出两扇窗格的位置，在窗帘区域用代码画出
     窗格（留白、一点不匀的暖光）、窗框和墙（淡灰紫、冷暖不匀）、窗台横影、纱帘竖褶；
  2. 概括：脸、烟斗和左手、书和右手三处用引导滤波（保边、渐变柔和），其余用 L0 压成平涂色块；
  3. 水彩颜料模型（Bousseau 2006）：色块边界积色、大尺度浓淡不匀、颜料颗粒；边界随噪声扭动；
  4. 透明罩染：颜色换成吸光度叠在纸上，最亮处就是纸白；四周不规则留白，留白边上一道积色；
  5. 墨线：DoG 取边缘暗侧，沿边缘方向做线积分，深褐色，中心重、四周轻。
用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys
import time

sys.dont_write_bytecode = True                      # 不在 stylize/ 下写 __pycache__
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
from scipy import ndimage as ndi                    # noqa: E402
import stylize as S                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "refs", "elderly_man_reading_pipe_window_shixart1985.jpg")
W = 1500
SEED = 3
PAPER = np.array([0.975, 0.962, 0.930], np.float32)


def load():
    im = Image.open(REF).convert("RGB")
    im = im.resize((W, round(W * im.height / im.width)), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def background_mask(rgb):
    """窗帘（窗子）区域：上半部分、很亮、和画面上边连通的一片。"""
    h, w = rgb.shape[:2]
    yy = np.mgrid[0:h, 0:w][0]
    Ls = ndi.gaussian_filter(rgb @ S.LUMA, 2)
    cand = (Ls > 0.82) & (yy < 540)
    lbl, _ = ndi.label(cand)
    keep = [k for k in np.unique(lbl[0]) if k != 0]
    bg = np.pad(np.isin(lbl, keep), 4, mode="edge")                 # 先补边，形态学运算才不会吃掉画面上沿
    bg = ndi.binary_opening(ndi.binary_closing(bg, iterations=2), iterations=1)[4:-4, 4:-4]
    return ndi.gaussian_filter(bg.astype(np.float32), 1.5)


def draw_window(rgb, bg, seed):
    """把窗子画清楚。照片里窗子被纱帘挡着、又过曝，只剩一片白；从亮度剖面量出窗子的位置：
    左右两扇窗格（x 150–630、830–1270，下沿 y≈300/290），中间是窗间墙，下面是窗台和窗下墙。
    窗格留白（一点暖光），窗框、窗间墙、窗下墙是淡灰紫，窗台一道稍深的横线，外面罩一层纱帘的竖褶；
    纱帘花边用照片自己的高频细节淡淡叠上。只画在窗帘区域（bg），人和沙发不动。"""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    def box(x0, x1, y0, y1, soft=1.5):
        return (S.smoothstep(x0 - soft, x0 + soft, xx) * S.smoothstep(x1 + soft, x1 - soft, xx) *
                S.smoothstep(y0 - soft, y0 + soft, yy) * S.smoothstep(y1 + soft, y1 - soft, yy))

    panes = np.maximum(box(150, 630, -10, 298), box(830, 1270, -10, 288))
    wall = np.array([0.80, 0.805, 0.86], np.float32)
    img = np.broadcast_to(wall, (h, w, 3)).copy()
    img *= (1 - 0.07 * S.smoothstep(310, 490, yy))[..., None]              # 窗下墙越往下越暗（沙发的影子）
    sill = box(110, 1320, 296, 312)
    img *= (1 - 0.10 * sill)[..., None]
    img *= (1 - 0.12 * box(110, 1320, 312, 318))[..., None]                # 窗台下的一道影
    n1 = S.fbm(h, w, 120, 3, seed + 41) - 0.5
    n2 = S.fbm(h, w, 90, 3, seed + 42) - 0.5
    img *= (1 + 0.10 * n1)[..., None]
    img += (np.array([0.03, 0.0, -0.03], np.float32) * n2[..., None])            # 墙面冷暖不匀
    warm = 0.5 + 0.5 * S.smoothstep(-0.2, 0.3, S.fbm(h, w, 70, 3, seed + 43) - 0.5)
    pane_col = 1 - np.array([0.0, 0.03, 0.10], np.float32) * warm[..., None]     # 窗格：不匀的淡暖光
    img = img * (1 - panes[..., None]) + pane_col * panes[..., None]
    # 纱帘：竖向的褶（沿 x 的平滑随机起伏）+ 照片里的花边细节
    rng = np.random.default_rng(seed + 40)
    fold = ndi.gaussian_filter1d(rng.random(w).astype(np.float32), 7)
    fold = (fold - fold.mean()) / (fold.std() + 1e-6)
    img *= (1 + 0.025 * fold)[None, :, None]
    L = rgb @ S.LUMA
    hp = L - ndi.gaussian_filter(L, 3)
    img = img + 0.9 * hp[..., None]
    img = np.clip(img, 0, 1)
    return rgb * (1 - bg[..., None]) + img * bg[..., None]


def focus_map(h, w):
    """细节留在脸、烟斗和左手、书和右手三处，其余（格子衬衫、靠垫、毯子）概括。"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    f = np.zeros((h, w), np.float32)
    for cx, cy, rx, ry in ((740, 310, 170, 220), (630, 520, 140, 130), (930, 590, 240, 170)):
        f = np.maximum(f, np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)))
    return np.clip(1.4 * f, 0, 1)


def abstract(rgb, focus, bg):
    """概括：中心（脸、手、书）用引导滤波——保边、渐变柔和，像湿画法；四周用 L0 压成平涂色块；
    窗帘区域 L0 轻一些，保留窗框。"""
    L = rgb @ S.LUMA
    fine = S.guided(L, rgb, 5, 0.003)
    mid = S.l0_smooth(rgb, 0.012)
    coarse = S.l0_smooth(rgb, 0.04)
    kb = np.clip(bg, 0, 1)[..., None]
    per = coarse * (1 - kb) + mid * kb
    k = np.clip(focus, 0, 1)[..., None]
    return np.clip(fine * k + per * (1 - k), 0, 1)


def face_map(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.exp(-(((xx - 740) / 140) ** 2 + ((yy - 320) / 200) ** 2))


def watercolor(A, rgb, focus, bg, seed):
    h, w = A.shape[:2]
    face = face_map(h, w)
    # 边界扭动：用低频噪声位移场重采样（窗帘区域、脸上扭得少）
    amp = 2.4 * (1 - 0.8 * face)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dy = (S.fbm(h, w, 24, 3, seed) - 0.5) * 2 * amp
    dx = (S.fbm(h, w, 24, 3, seed + 1) - 0.5) * 2 * amp
    A = np.stack([ndi.map_coordinates(A[..., c], [yy + dy, xx + dx], order=1, mode="reflect") for c in range(3)], -1)
    # 透明颜料：颜色 → 相对纸的吸光度；水彩比照片浅，离中心越远越淡
    a = -np.log(np.clip(A / PAPER, 0.03, 1.0))
    a *= 0.75 * (0.55 + 0.45 * np.clip(focus * 1.3, 0, 1))[..., None]
    a *= (1 - 0.45 * S.smoothstep(700, 870, yy))[..., None]          # 书下面失焦的毯子一带淡下去，不发脏
    # 颜料密度：色块边界积色（脸上少）+ 大尺度浓淡 + 颗粒
    Lg = A @ S.LUMA
    g = ndi.gaussian_gradient_magnitude(Lg, 1.2)
    edge = np.clip(g / 0.06, 0, 1) * (1 - 0.8 * face)
    d = 1 + 0.6 * edge
    d *= 1 + (0.25 + 0.2 * bg) * (S.fbm(h, w, 70, 4, seed + 2) - 0.5) * 2
    d *= 1 + 0.20 * (S.fbm(h, w, 2.5, 2, seed + 3) - 0.5) * 2
    a *= d[..., None]
    # 纸白：窗格最亮的地方不上色
    a *= S.smoothstep(0.985, 0.94, Lg)[..., None] * 0.92 + 0.08
    # 不规则留白边：下方和两侧收进来，边缘是干了的水痕（清楚的边 + 一道积色）
    rx = (xx - 790) / 820
    ry = np.where(yy > 450, (yy - 450) / 410, (yy - 450) / 900)
    r = np.hypot(rx, ry) + 0.10 * (S.fbm(h, w, 60, 4, seed + 12) - 0.5) + 0.05 * (S.fbm(h, w, 12, 2, seed + 13) - 0.5)
    inside = S.smoothstep(1.0, 0.985, r)
    rim = np.exp(-((r - 0.99) / 0.012) ** 2) * inside
    a *= (inside * (1 + 0.6 * rim))[..., None]
    paper = S.paper_texture(h, w, 1.0, seed + 10, PAPER, fiber=0.25)
    out = paper * np.exp(-a)
    # 墨线：DoG 取边缘的暗侧，再沿边缘方向做线积分让线连贯；勾出眼镜、五官、手、书、窗框；中心重、四周轻
    Lsm = A @ S.LUMA
    D = ndi.gaussian_filter(Lsm, 1.0) - ndi.gaussian_filter(Lsm, 1.8)
    line = S.smoothstep(0.004, 0.018, -D).astype(np.float32)
    tx, ty, _ = S.flow_field(ndi.gaussian_filter(Lsm, 1.0), 1.0, sigma=2.0, rho=5.0)
    line = np.clip(1.3 * S.lic(line, tx, ty, 5), 0, 1)
    wline = np.clip(0.3 + 0.6 * focus, 0, 0.85) * inside
    line = line * wline
    sepia = np.array([0.24, 0.17, 0.12], np.float32)
    k = np.clip(0.9 * line, 0, 0.8)[..., None]
    out = out * (1 - k) + sepia * k
    return np.clip(out, 0, 1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    t0 = time.time()
    rgb = load()
    h, w = rgb.shape[:2]
    bg = background_mask(rgb)
    rgb = draw_window(rgb, bg, SEED)
    focus = focus_map(h, w)
    A = abstract(rgb, focus, bg)
    out = watercolor(A, rgb, focus, bg, SEED)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(out_path)
    print(out_path, (w, h), "bg frac = %.3f" % float(bg.mean()), "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
