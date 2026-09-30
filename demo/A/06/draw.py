#!/usr/bin/env python3
"""A06 窗边看书的老人。

纯代码：Python 生成 SVG（所有造型都是手写坐标的贝塞尔曲线；明暗用渐变 + 剪裁 + 模糊叠色）→
headless Chrome 渲染成 PNG（demo/tools/render.py）→ numpy 加窗光泛光、暗角和颗粒。
不读任何现成图片，随机种子固定。用法：python3 draw.py [输出路径]
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
RENDER = os.path.join(HERE, "..", "..", "tools", "render.py")
W, H = 1536, 1024
rng = np.random.default_rng(6)
S = []          # SVG 元素
FIG = []        # 人物在椅子扶手前面的部分（给窗光叠加用的遮罩）
FIG_BACK = []   # 人物在椅子扶手后面的部分
CHAIR_SIDE = []
DEFS = []       # 渐变、滤镜、剪裁


def f(v):
    return f"{v:.1f}"


def smooth(pts, closed=True):
    """过点的 Catmull-Rom 平滑曲线 → SVG path。点写成 (x, y, 'c') 表示尖角。"""
    n = len(pts)
    P = [(float(p[0]), float(p[1])) for p in pts]
    corner = [len(p) > 2 for p in pts]

    def tan(i):
        if corner[i] or (not closed and i in (0, n - 1)):
            return (0.0, 0.0)
        a, b = P[(i - 1) % n], P[(i + 1) % n]
        return ((b[0] - a[0]) / 6, (b[1] - a[1]) / 6)

    d = f"M{f(P[0][0])},{f(P[0][1])}"
    for i in range(n if closed else n - 1):
        j = (i + 1) % n
        t1, t2 = tan(i), tan(j)
        d += (f" C{f(P[i][0] + t1[0])},{f(P[i][1] + t1[1])} {f(P[j][0] - t2[0])},{f(P[j][1] - t2[1])}"
              f" {f(P[j][0])},{f(P[j][1])}")
    return d + (" Z" if closed else "")


def lines(pts, closed=True):
    d = "M" + " L".join(f"{f(x)},{f(y)}" for x, y in pts)
    return d + (" Z" if closed else "")


def el(tag, **a):
    attrs = " ".join(f'{k.rstrip("_").replace("_", "-")}="{v}"' for k, v in a.items() if v is not None)
    return f"<{tag} {attrs}/>"


def add(tag, **a):
    S.append(el(tag, **a))


def P(d, fill="none", **a):
    add("path", d=d, fill=fill, **a)


def lin(id_, x1, y1, x2, y2, stops, units="userSpaceOnUse"):
    st = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>' for o, c, op in
                 [(s[0], s[1], s[2] if len(s) > 2 else 1) for s in stops])
    DEFS.append(f'<linearGradient id="{id_}" gradientUnits="{units}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{st}</linearGradient>')
    return f"url(#{id_})"


def rad(id_, cx, cy, r, stops, fx=None, fy=None):
    st = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>' for o, c, op in
                 [(s[0], s[1], s[2] if len(s) > 2 else 1) for s in stops])
    fxy = f' fx="{fx}" fy="{fy}"' if fx is not None else ""
    DEFS.append(f'<radialGradient id="{id_}" gradientUnits="userSpaceOnUse" cx="{cx}" cy="{cy}" r="{r}"{fxy}>{st}</radialGradient>')
    return f"url(#{id_})"


def clip(id_, d):
    DEFS.append(f'<clipPath id="{id_}"><path d="{d}"/></clipPath>')
    return f"url(#{id_})"


for s_ in (0.6, 1, 1.5, 2, 3, 4, 6, 8, 12, 18, 28, 40):
    DEFS.append(f'<filter id="b{str(s_).replace(".", "_")}" x="-50%" y="-50%" width="200%" height="200%">'
                f'<feGaussianBlur stdDeviation="{s_}"/></filter>')


def blur(s_):
    return f"url(#b{str(s_).replace('.', '_')})"


def group_start(**a):
    attrs = " ".join(f'{k.rstrip("_").replace("_", "-")}="{v}"' for k, v in a.items() if v is not None)
    S.append(f"<g {attrs}>")


def group_end():
    S.append("</g>")


# ================= 房间 =================
VP = (768, 354)          # 视平线（相机高约 1.2 m）
FLOOR_Y = 810            # 墙脚线


def room():
    # 墙：暗鼠尾草绿，窗边被光照亮
    add("rect", x=0, y=0, width=W, height=FLOOR_Y, fill="#3d4a3f")
    add("rect", x=0, y=0, width=W, height=FLOOR_Y,
        fill=rad("wallglow", 300, 330, 980, [(0, "#a8ad86", 0.95), (0.35, "#77866c", 0.75), (0.7, "#4c5b4c", 0.4), (1, "#3d4a3f", 0)]))
    # 墙纸竖条纹
    DEFS.append('<pattern id="stripe" width="54" height="54" patternUnits="userSpaceOnUse">'
                '<rect x="0" y="0" width="20" height="54" fill="#1e2a22" opacity="0.16"/>'
                '<rect x="27" y="0" width="3" height="54" fill="#e8e0c0" opacity="0.07"/></pattern>')
    add("rect", x=0, y=0, width=W, height=FLOOR_Y, fill="url(#stripe)")
    # 右侧和顶部更暗
    add("rect", x=0, y=0, width=W, height=FLOOR_Y,
        fill=lin("wallshade", 0, 0, W, 0, [(0, "#000", 0), (0.45, "#000", 0.05), (1, "#0b0f0c", 0.55)]))
    add("rect", x=0, y=0, width=W, height=FLOOR_Y,
        fill=lin("wallshade2", 0, 0, 0, FLOOR_Y, [(0, "#0b0f0c", 0.35), (0.35, "#000", 0), (1, "#000", 0.12)]))
    # 墙上挂一幅小画
    add("rect", x=640, y=150, width=150, height=118, fill="#6b5327")
    add("rect", x=648, y=158, width=134, height=102, fill=lin("frame", 648, 158, 782, 260, [(0, "#d6b369"), (1, "#7b5e2a")]))
    add("rect", x=660, y=170, width=110, height=78, fill=lin("pic", 0, 170, 0, 248, [(0, "#b7b99a"), (0.6, "#8c8f6a"), (1, "#5d6446")]))
    P(smooth([(660, 225), (690, 205), (712, 214), (738, 198), (770, 214), (770, 248, "c"), (660, 248, "c")]), fill="#4f5a3d", opacity=0.9)
    add("rect", x=660, y=170, width=110, height=78, fill="#000", opacity=0.12)
    # 踢脚线
    add("rect", x=0, y=FLOOR_Y - 26, width=W, height=28, fill=lin("base", 0, 0, W, 0, [(0, "#d9cfb6"), (0.4, "#a79f88"), (1, "#3f3c33")]))
    add("rect", x=0, y=FLOOR_Y - 28, width=W, height=4, fill="#f2ead2", opacity=0.5)
    # 地板：透视木条
    P(lines([(0, FLOOR_Y), (W, FLOOR_Y), (W, H), (0, H)]), fill=lin("floor", 0, FLOOR_Y, 0, H, [(0, "#4a3120"), (1, "#6e4b30")]))
    k = (H - VP[1]) / (FLOOR_Y - VP[1])
    xs = np.arange(-1400, 2900, 44)
    for i, x in enumerate(xs[:-1]):
        x2 = xs[i + 1]
        quad = [(x, FLOOR_Y), (x2, FLOOR_Y), (VP[0] + (x2 - VP[0]) * k, H), (VP[0] + (x - VP[0]) * k, H)]
        shade = rng.uniform(-0.07, 0.07)
        P(lines(quad), fill="#1c1008" if shade < 0 else "#c08a55", opacity=f"{abs(shade):.3f}")
        P(lines([quad[0], quad[3]], closed=False), stroke="#24160c", stroke_width=1.3, opacity=0.6)
    for j in range(40):                     # 木板接缝
        t = rng.random()
        y = FLOOR_Y + (H - FLOOR_Y) * t ** 1.3
        i = rng.integers(0, len(xs) - 1)
        kk = (y - VP[1]) / (FLOOR_Y - VP[1])
        xa, xb = VP[0] + (xs[i] - VP[0]) * kk, VP[0] + (xs[i + 1] - VP[0]) * kk
        P(lines([(xa, y), (xb, y)], closed=False), stroke="#24160c", stroke_width=1.2, opacity=0.5)
    # 地毯（椅子下）
    rug = [(760, 842), (W + 40, 842), (W + 40, H + 10), (560, H + 10)]
    P(lines(rug), fill="#5f2622")
    P(lines([(785, 850), (W + 40, 850), (W + 40, H + 10), (598, H + 10)]), fill="none", stroke="#c39a5a", stroke_width=5, opacity=0.8)
    P(lines([(805, 858), (W + 40, 858), (W + 40, H + 10), (628, H + 10)]), fill="none", stroke="#27344a", stroke_width=9, opacity=0.9)
    for j in range(9):
        y = 875 + j * 17 + j * j * 0.8
        kk = (y - VP[1]) / (842 - VP[1])
        xa = 760 + (560 - 760) * (y - 842) / (H + 10 - 842) + 50
        for m in range(int((W - xa) / 44) + 1):
            cx = xa + 20 + m * 46 * kk
            P(lines([(cx, y - 5 * kk), (cx + 9 * kk, y), (cx, y + 5 * kk), (cx - 9 * kk, y)]), fill="#b4843f", opacity=0.45)
    P(lines(rug), fill=lin("rugshade", 560, 0, W, 0, [(0, "#000", 0.0), (1, "#000", 0.45)]))


def window():
    # 窗外（虚焦）：天空、树冠、邻家屋顶
    ox0, oy0, ox1, oy1 = 78, 68, 482, 500
    cid = clip("winopen", lines([(ox0, oy0), (ox1, oy0), (ox1, oy1), (ox0, oy1)]))
    group_start(clip_path=cid)
    add("rect", x=ox0, y=oy0, width=ox1 - ox0, height=oy1 - oy0,
        fill=lin("sky", 0, oy0, 0, oy1, [(0, "#bcd6e6"), (0.45, "#e4ecdf"), (1, "#f8e3b6")]))
    group_start(filter=blur(5))
    P(smooth([(300, 500), (330, 330), (380, 300), (430, 318), (470, 290), (520, 320), (520, 520, "c"), (300, 520, "c")]),
      fill="#b98a6d", opacity=0.7)                                        # 邻家屋墙
    P(lines([(310, 345), (420, 262), (530, 330), (530, 360), (310, 372)]), fill="#9c5b43", opacity=0.75)  # 屋顶
    for cx, cy, r, c in [(70, 420, 120, "#6f8f55"), (170, 380, 95, "#86a562"), (120, 300, 80, "#9ab872"),
                         (250, 450, 90, "#5d7d49"), (40, 250, 90, "#7a9a5a"), (220, 330, 60, "#a9c47e"),
                         (430, 470, 80, "#6b8b50"), (500, 420, 70, "#809f5c")]:
        add("circle", cx=cx, cy=cy, r=r, fill=c, opacity=0.95)
        for _ in range(6):
            a = rng.uniform(0, 2 * np.pi)
            add("circle", cx=f(cx + 0.8 * r * np.cos(a)), cy=f(cy + 0.8 * r * np.sin(a)), r=f(r * rng.uniform(0.25, 0.45)),
                fill=c, opacity=0.9)
    for _ in range(60):                       # 叶间透光的亮斑
        add("circle", cx=f(rng.uniform(ox0, 300)), cy=f(rng.uniform(220, 500)), r=f(rng.uniform(4, 11)),
            fill="#f3f0c4", opacity=f"{rng.uniform(0.3, 0.8):.2f}")
    group_end()
    add("circle", cx=110, cy=90, r=260, fill=rad("sunglow", 110, 90, 260, [(0, "#fffbe8", 0.95), (0.4, "#fff3cf", 0.5), (1, "#fff3cf", 0)]))
    group_end()
    # 玻璃上的反光
    for x0, w_ in [(140, 26), (190, 10), (330, 30), (390, 12)]:
        P(lines([(x0, oy0), (x0 + w_, oy0), (x0 + w_ - 90, oy1), (x0 - 90, oy1)]), fill="#ffffff", opacity=0.06, clip_path=cid)
    # 窗框（逆光，偏暗）和窗棂
    trim = "#c9c0a8"
    P(lines([(48, 38), (512, 38), (512, 512), (48, 512)]) + " " + lines([(ox0, oy0), (ox1, oy0), (ox1, oy1), (ox0, oy1)]),
      fill=lin("trim", 48, 0, 512, 0, [(0, "#e9e2cc"), (1, "#b3ab94")]), fill_rule="evenodd")
    P(lines([(48, 38), (512, 38)], closed=False), stroke="#f6f0dd", stroke_width=2, opacity=0.8)
    bars = [(ox0, oy0, ox1, oy0 + 12), (ox0, oy1 - 12, ox1, oy1), (ox0, oy0, ox0 + 12, oy1), (ox1 - 12, oy0, ox1, oy1),
            (276, oy0, 284, oy1), (ox0, 278, ox1, 292), (ox0, 170, ox1, 176), (ox0, 394, ox1, 400)]
    for x0, y0, x1, y1 in bars:
        add("rect", x=x0, y=y0, width=x1 - x0, height=y1 - y0, fill=trim)
        add("rect", x=x0, y=y0, width=x1 - x0, height=min(2, y1 - y0), fill="#f5efdc", opacity=0.7)
    add("rect", x=ox0, y=292, width=ox1 - ox0, height=5, fill="#000", opacity=0.12)
    # 窗台（从上往下看得到台面）
    P(lines([(34, 500), (526, 500), (540, 522), (20, 522)]), fill=lin("sill", 0, 500, 0, 522, [(0, "#e7dfc8"), (1, "#f4ecd6")]))
    add("rect", x=20, y=522, width=520, height=14, fill="#b7ae96")
    add("rect", x=58, y=536, width=444, height=22, fill="#a8a08a")
    add("rect", x=58, y=536, width=444, height=6, fill="#000", opacity=0.15)


def sill_items():
    # 花盆（天竺葵），逆光，叶子半透明
    P(lines([(108, 446), (178, 446), (170, 504), (116, 504)]), fill=lin("pot", 108, 0, 178, 0, [(0, "#c7754b"), (1, "#7e3f25")]))
    add("rect", x=104, y=440, width=78, height=12, rx=2, fill="#b86a42")
    leaves = [(142, 420, 26, 16, -20), (118, 404, 22, 14, 30), (168, 398, 24, 15, -35), (140, 380, 20, 13, 10),
              (110, 372, 18, 12, 40), (176, 366, 19, 12, -25), (150, 352, 17, 11, 0), (126, 346, 15, 10, 25),
              (190, 424, 20, 12, -50), (96, 426, 18, 11, 55)]
    for cx, cy, rx, ry, a in leaves:
        add("ellipse", cx=cx, cy=cy, rx=rx, ry=ry, transform=f"rotate({a} {cx} {cy})", fill="#4d6b34")
        add("ellipse", cx=cx - 3, cy=cy - 2, rx=rx * 0.7, ry=ry * 0.6, transform=f"rotate({a} {cx} {cy})",
            fill="#9dbb5a", opacity=0.55, filter=blur(2))
        P(lines([(cx - rx * 0.8, cy), (cx + rx * 0.8, cy)], closed=False), stroke="#39522a", stroke_width=1,
          transform=f"rotate({a} {cx} {cy})", opacity=0.6)
    for cx, cy in [(132, 332), (160, 326), (184, 342), (112, 352)]:
        for _ in range(9):
            a, r_ = rng.uniform(0, 2 * np.pi), rng.uniform(0, 9)
            add("circle", cx=f(cx + r_ * np.cos(a)), cy=f(cy + r_ * np.sin(a)), r=f(rng.uniform(3, 5)),
                fill=rng.choice(["#d8453a", "#e8604a", "#b8302c"]))
        P(lines([(cx, cy + 6), (cx + rng.uniform(-6, 6), 400)], closed=False), stroke="#4d6b34", stroke_width=2)
    # 一摞书
    for i, (c, w0, dx) in enumerate([("#6b2b25", 104, 0), ("#2b3d57", 96, 6), ("#a07a36", 88, -2)]):
        y = 490 - i * 13
        add("rect", x=336 + dx, y=y, width=w0, height=13, fill=c)
        add("rect", x=336 + dx + 3, y=y + 3, width=w0 - 6, height=7, fill="#efe5cb", opacity=0.9 if i != 1 else 0)
        add("rect", x=336 + dx, y=y, width=w0, height=2, fill="#fff", opacity=0.15)
    # 茶杯
    add("ellipse", cx=480, cy=500, rx=26, ry=5, fill="#e9e4da")
    P(lines([(462, 474), (498, 474), (494, 496), (466, 496)]), fill=lin("cup", 462, 0, 498, 0, [(0, "#fbf8f1"), (1, "#bdb5a6")]))
    add("ellipse", cx=480, cy=474, rx=18, ry=4, fill="#8a5a2c")
    P("M497,479 C510,478 509,492 494,490", stroke="#d9d2c4", stroke_width=3.5)
    P("M478,468 C470,450 490,440 480,420 C472,404 486,396 482,384", stroke="#ffffff", stroke_width=3, opacity=0.25, filter=blur(2))


def curtains():
    # 左侧薄纱，逆光发亮
    for i in range(9):
        x0 = 40 + i * 15 + rng.uniform(-3, 3)
        w_ = rng.uniform(16, 30)
        pts = [(x0, 20), (x0 + w_, 20)] + [(x0 + w_ + 4 * np.sin(y / 60 + i), y) for y in range(60, 520, 60)] + \
              [(x0 + w_ + 3, 522), (x0 - 2, 526)] + [(x0 + 4 * np.sin(y / 55 + i * 2), y) for y in range(480, 40, -60)]
        P(smooth(pts), fill="#fbf6ea", opacity=f"{rng.uniform(0.18, 0.35):.2f}")
    # 右侧厚窗帘（铁锈红丝绒），在绑带处收拢
    pts = [(505, 0, "c"), (600, 0, "c"), (598, 200), (585, 420), (572, 560), (590, 700), (612, 800, "c"), (496, 800, "c"),
           (512, 690), (530, 560), (520, 420), (508, 200)]
    d = smooth(pts)
    cid = clip("drape", d)
    P(d, fill=lin("drapeg", 500, 0, 610, 0, [(0, "#a45a36"), (0.5, "#7c3f24"), (1, "#3f1c10")]))
    group_start(clip_path=cid)
    for x in [520, 540, 556, 574, 590]:
        P(smooth([(x, 0), (x - 4, 300), (x + 6, 560), (x + 12, 800)], closed=False), stroke="#2c120a", stroke_width=7,
          opacity=0.35, filter=blur(3))
        P(smooth([(x + 8, 0), (x + 4, 300), (x + 13, 560), (x + 20, 800)], closed=False), stroke="#d98a5c", stroke_width=4,
          opacity=0.25, filter=blur(3))
    group_end()
    P(smooth([(520, 548), (560, 556), (592, 552), (590, 570), (556, 575), (522, 568)]), fill="#c79a4e")


def bookshelf():
    x0, x1 = 1318, W + 10
    add("rect", x=x0, y=0, width=x1 - x0, height=FLOOR_Y, fill="#2e1d12")
    add("rect", x=x0 + 18, y=0, width=x1 - x0, height=FLOOR_Y, fill="#1a100a")
    cols = ["#6b2b25", "#2b3d57", "#a07a36", "#3f5a3a", "#7a5a3a", "#5a2f4a", "#8a8a78", "#2f2f35", "#9a4a2a", "#c2a86a"]
    for sy in [0, 170, 350, 530, 710]:
        base = sy + 160
        x = x0 + 22
        while x < W:
            if rng.random() < 0.08:          # 横放的一小摞
                for k_ in range(3):
                    add("rect", x=f(x), y=f(base - 14 * (k_ + 1)), width=70, height=13, fill=rng.choice(cols))
                x += 74
                continue
            w_ = rng.uniform(12, 28)
            h_ = rng.uniform(100, 145)
            c = rng.choice(cols)
            add("rect", x=f(x), y=f(base - h_), width=f(w_), height=f(h_), fill=c)
            add("rect", x=f(x), y=f(base - h_), width=f(w_ * 0.3), height=f(h_), fill="#fff", opacity=0.08)
            for yy in (base - h_ + 14, base - 20):
                add("rect", x=f(x + 2), y=f(yy), width=f(w_ - 4), height=3, fill="#d8b86a", opacity=0.5)
            x += w_ + rng.uniform(0.5, 2.5)
        add("rect", x=x0, y=base, width=x1 - x0, height=16, fill="#4a3020")
        add("rect", x=x0, y=base, width=x1 - x0, height=3, fill="#8a6040", opacity=0.6)
    add("rect", x=x0, y=0, width=20, height=FLOOR_Y, fill="#4a3020")
    add("rect", x=x0, y=0, width=x1 - x0, height=FLOOR_Y, fill=lin("shelfshade", x0, 0, W, 0, [(0, "#0a0604", 0.5), (1, "#0a0604", 0.8)]))


# ================= 光 =================
def floor_light():
    """窗光投在地板上的四块亮斑（被窗棂分开）。"""
    group_start(filter=blur(4), style="mix-blend-mode:screen")
    # 近墙边 (y=820) 的 x 区间 → 近处 (y=1024) 的 x 区间
    for (a0, a1), (b0, b1), (ya, yb) in [((330, 470), (640, 860), (822, 915)), ((480, 610), (870, 1080), (822, 915)),
                                          ((330, 470), (640, 860), (925, 1030)), ((480, 610), (870, 1080), (925, 1030))]:
        def xat(xw, xn, y):
            t = (y - 822) / (1024 - 822)
            return xw + (xn - xw) * t
        quad = [(xat(a0, b0, ya), ya), (xat(a1, b1, ya), ya), (xat(a1, b1, yb), yb), (xat(a0, b0, yb), yb)]
        P(lines(quad), fill="#ffcf8a", opacity=0.55)
    group_end()


def light_beams():
    group_start(style="mix-blend-mode:screen")
    for (p, op) in [([(90, 75), (270, 75), (1000, 1024), (520, 1024)], 0.2),
                    ([(290, 75), (475, 75), (1180, 1024), (760, 1024)], 0.16),
                    ([(90, 300), (475, 300), (1060, 900), (610, 1024)], 0.1),
                    ([(300, 90), (475, 90), (1010, 400), (990, 640), (470, 300)], 0.07)]:
        P(lines(p), fill=lin(f"beam{len(S)}", p[0][0], p[0][1], (p[2][0] + p[3][0]) / 2, (p[2][1] + p[3][1]) / 2,
                             [(0, "#fff0c8", op * 2.2), (0.55, "#ffd9a0", op), (1, "#ffd9a0", 0)]), filter=blur(18))
    for _ in range(140):                    # 光里的浮尘
        t = rng.random()
        x = 150 + 700 * t + rng.normal(0, 60)
        y = 120 + 700 * t + rng.normal(0, 70)
        add("circle", cx=f(x), cy=f(y), r=f(rng.uniform(0.7, 2.0)), fill="#fff6dc", opacity=f"{rng.uniform(0.25, 0.8):.2f}")
    group_end()


# ================= 椅子 =================
LEATHER = ("#8e4a30", "#5a2718", "#2c110a")


def chair_back():
    d = smooth([(1150, 890, "c"), (1150, 660), (1153, 520), (1160, 420), (1172, 372), (1200, 350), (1250, 343), (1292, 350),
                (1312, 378), (1316, 520), (1314, 700), (1310, 890, "c")])
    cid = clip("chairback", d)
    P(d, fill=lin("cb", 1150, 0, 1316, 0, [(0, LEATHER[0]), (0.35, LEATHER[1]), (1, LEATHER[2])]))
    group_start(clip_path=cid)
    P(smooth([(1175, 380), (1210, 356), (1260, 352)], closed=False), stroke="#d08a62", stroke_width=6, opacity=0.5, filter=blur(4))
    P(smooth([(1160, 430), (1158, 560), (1160, 700)], closed=False), stroke="#b8694a", stroke_width=8, opacity=0.35, filter=blur(6))
    # 头的影子落在椅背上
    add("ellipse", cx=1170, cy=425, rx=34, ry=62, fill="#140704", opacity=0.45, filter=blur(12))
    group_end()
    for i in range(14):                      # 铜钉
        t = i / 13
        x = 1172 + (1300 - 1172) * t
        y = 372 - 26 * np.sin(np.pi * t) + 8
        add("circle", cx=f(x), cy=f(y + 6), r=2.6, fill="#c9a55a", opacity=0.8)


def chair_front():
    # 近侧扶手（卷边）+ 侧板 + 木腿
    d = smooth([(905, 642), (1000, 638), (1100, 640), (1170, 646), (1312, 650, "c"), (1312, 892, "c"), (888, 892, "c"),
                (886, 760), (872, 712), (868, 676), (882, 650)])
    CHAIR_SIDE.append(d)
    cid = clip("chairside", d)
    P(d, fill=lin("cs", 0, 640, 0, 892, [(0, LEATHER[0]), (0.25, LEATHER[1]), (1, LEATHER[2])]))
    group_start(clip_path=cid)
    add("rect", x=860, y=630, width=460, height=270, fill=lin("cs2", 868, 0, 1312, 0, [(0, "#000", 0), (1, "#000", 0.45)]))
    P(smooth([(905, 648), (1000, 645), (1100, 648), (1300, 656)], closed=False), stroke="#e8a27a", stroke_width=5, opacity=0.55,
      filter=blur(3))
    P(smooth([(870, 700), (900, 688), (930, 700), (935, 740)], closed=False), stroke="#000", stroke_width=10, opacity=0.3, filter=blur(6))
    group_end()
    # 扶手正面的卷涡
    P(smooth([(868, 676), (876, 652), (902, 644), (928, 656), (934, 684), (920, 708), (896, 712), (882, 698), (886, 678),
              (902, 672), (914, 684)], closed=False), stroke="#2a0f08", stroke_width=2.2, opacity=0.4)
    for i in range(10):                      # 扶手下沿的铜钉
        x = 895 + i * 42
        add("circle", cx=x, cy=694 if i == 0 else 700, r=2.6, fill="#d8b46a", opacity=0.85)
    add("rect", x=886, y=876, width=426, height=18, fill="#3a1a10")
    for x0 in (892, 1276):                  # 旋木椅腿
        P(smooth([(x0, 892, "c"), (x0 + 24, 892, "c"), (x0 + 20, 930), (x0 + 22, 960), (x0 + 16, 996, "c"), (x0 + 8, 996, "c"),
                  (x0 + 2, 960), (x0 + 4, 930)]), fill=lin(f"leg{x0}", x0, 0, x0 + 24, 0, [(0, "#8a5a36"), (1, "#2c1a0e")]))


# ================= 人 =================
SKIN = ("#f2c6a2", "#d79c7b", "#9a604b")
HAIR = ("#f6f2ea", "#cfc8bc", "#8e877e")
KNIT = ("#dcc9a2", "#a8946f", "#5e503d")


def legs():
    # 远侧腿（大部分被挡住）
    far = smooth([(1000, 705), (900, 708), (872, 722), (860, 760), (858, 860), (862, 948), (900, 948), (905, 860), (912, 780),
                  (1000, 772)])
    P(far, fill=lin("farleg", 850, 0, 915, 0, [(0, "#4a484e"), (1, "#26252a")]))
    near = [(1000, 700), (900, 699), (848, 703), (814, 716), (798, 742), (790, 790), (782, 860), (776, 942, "c"), (824, 944, "c"),
            (834, 880), (848, 818), (866, 784), (884, 772), (1000, 770)]
    d = smooth(near)
    near_d = d
    FIG_BACK.append((d, None))
    cid = clip("nearleg", d)
    P(d, fill=lin("nl", 798, 0, 880, 0, [(0, "#8a8588"), (0.35, "#5a575c"), (1, "#2c2b30")]))
    group_start(clip_path=cid)
    P(smooth([(806, 730), (828, 710), (870, 704), (920, 705)], closed=False), stroke="#c8c0bc", stroke_width=7, opacity=0.5,
      filter=blur(4))
    add("ellipse", cx=818, cy=726, rx=16, ry=12, fill="#d8d0cc", opacity=0.35, filter=blur(4))          # 膝盖
    P(smooth([(846, 776), (832, 840), (818, 940)], closed=False), stroke="#1a1a1e", stroke_width=6, opacity=0.35, filter=blur(4))
    P(smooth([(794, 790), (790, 860), (788, 940)], closed=False), stroke="#e0d0c0", stroke_width=4, opacity=0.35, filter=blur(3))
    for y0 in (760, 776, 790):                                                                          # 膝弯的褶
        P(f"M{f(880 - (y0 - 760) * 0.6)},{y0} q-14,4 -26,14", stroke="#1e1d22", stroke_width=1.6, opacity=0.5)
    group_end()
    # 袜子和拖鞋
    add("rect", x=778, y=936, width=46, height=16, fill="#3a3035")
    add("rect", x=862, y=936, width=40, height=14, fill="#2a2226")
    P(smooth([(866, 948), (900, 944), (930, 960), (944, 986), (930, 1000), (880, 1002), (862, 990)]), fill="#3c2418")
    d = smooth([(780, 946), (826, 946), (834, 972), (830, 1004), (770, 1008), (726, 1004), (720, 990), (740, 966)])
    P(d, fill=lin("slip", 720, 0, 834, 0, [(0, "#a8764f"), (0.5, "#6e4630"), (1, "#3c2418")]))
    P(smooth([(730, 996), (780, 1000), (830, 996)], closed=False), stroke="#2a180e", stroke_width=3, opacity=0.7)
    P(smooth([(742, 968), (770, 952), (800, 950)], closed=False), stroke="#e2b48a", stroke_width=3, opacity=0.45, filter=blur(1.5))
    P(smooth([(724, 1000), (770, 1006), (832, 1002)], closed=False), stroke="#2a180e", stroke_width=5, opacity=0.8)
    P(smooth([(784, 950), (806, 958), (828, 952)], closed=False), stroke="#3a2418", stroke_width=2.5, opacity=0.7)
    # 窗光照在腿的前侧
    DEFS.append(f'<clipPath id="legsall"><path d="{near_d}"/><path d="{d}"/></clipPath>')
    add("rect", x=700, y=690, width=200, height=330, clip_path="url(#legsall)", style="mix-blend-mode:screen",
        fill=lin("leglight", 760, 0, 860, 0, [(0, "#ffcf8a", 0.4), (1, "#ffcf8a", 0)]))


def torso():
    # 衬衫领 + 开衫身体
    d = smooth([(1012, 462), (996, 490), (984, 540), (976, 600), (980, 660), (992, 710, "c"), (1170, 712, "c"), (1176, 640),
                (1168, 560), (1150, 505), (1128, 472), (1100, 452), (1070, 450), (1040, 456)])
    FIG_BACK.append((d, None))
    cid = clip("torso", d)
    P(d, fill=lin("tor", 976, 0, 1176, 0, [(0, KNIT[0]), (0.35, KNIT[1]), (1, KNIT[2])]))
    group_start(clip_path=cid)
    for x in range(960, 1180, 7):           # 针织罗纹
        P(lines([(x, 440), (x - 14, 720)], closed=False), stroke="#3a3024", stroke_width=1.2, opacity=0.12)
    # 书在胸口投下的影子
    P(smooth([(990, 520), (1010, 540), (1015, 620), (995, 660), (975, 640), (975, 560)]), fill="#241b12", opacity=0.45, filter=blur(10))
    # 衣褶：肚子上的横褶、腋下的斜褶
    for pts in ([(982, 640), (1010, 646), (1040, 644)], [(984, 668), (1016, 676), (1050, 672)], [(1040, 520), (1060, 560), (1070, 610)],
                [(1030, 600), (1052, 626), (1066, 660)]):
        P(smooth(pts, closed=False), stroke="#4a3d2c", stroke_width=4, opacity=0.35, filter=blur(2))
        P(smooth([(x - 3, y - 4) for x, y in pts], closed=False), stroke="#f0e2c0", stroke_width=2, opacity=0.25, filter=blur(1.5))
    # V 领里的衬衫
    P(smooth([(1008, 462, "c"), (1060, 458, "c"), (1030, 540, "c")]), fill=lin("shirt", 1000, 0, 1060, 0, [(0, "#c6d4e0"), (1, "#7c8c9c")]))
    P(smooth([(1010, 470), (1022, 520), (1030, 540)], closed=False), stroke="#8a7a5e", stroke_width=6, opacity=0.6)
    for y in (560, 610, 660):               # 纽扣
        x = 1004 - (y - 540) * 0.25
        add("circle", cx=f(x), cy=y, r=5, fill="#4a3322")
        add("circle", cx=f(x - 1.5), cy=y - 1.5, r=1.6, fill="#c8a47a", opacity=0.6)
    P(smooth([(1012, 470), (1002, 540), (992, 620), (990, 700)], closed=False), stroke="#f0e2c0", stroke_width=3, opacity=0.35)
    group_end()
    # 领子
    P(smooth([(1016, 450), (1046, 444), (1080, 440), (1104, 450), (1100, 466), (1062, 468), (1030, 470)]), fill="#aebfcf")
    P(smooth([(1016, 450), (1008, 468, "c"), (1030, 470)]), fill="#d4e0ea")


def neck():
    d = smooth([(1040, 420), (1064, 398), (1092, 386), (1100, 420), (1106, 456), (1040, 460)])
    P(d, fill=lin("neck", 1040, 0, 1106, 0, [(0, "#b27a62"), (1, "#6e4234")]))
    P(smooth([(1070, 408), (1082, 430), (1090, 452)], closed=False), stroke="#5a3226", stroke_width=2, opacity=0.4, filter=blur(1))


def upper_arm():
    d = smooth([(1100, 462), (1132, 468), (1148, 500), (1146, 555), (1128, 612), (1096, 656), (1062, 664), (1050, 642),
                (1066, 592), (1082, 532), (1090, 490)])
    FIG_BACK.append((d, None))
    cid = clip("uarm", d)
    P(d, fill=lin("ua", 1044, 0, 1156, 0, [(0, KNIT[0]), (0.45, KNIT[1]), (1, KNIT[2])]))
    group_start(clip_path=cid)
    for i in range(12):
        y = 480 + i * 16
        P(smooth([(1040, y), (1100, y + 10), (1160, y + 4)], closed=False), stroke="#3a3024", stroke_width=1.2, opacity=0.1)
    P(smooth([(1090, 480), (1070, 560), (1052, 640)], closed=False), stroke="#fff4dc", stroke_width=5, opacity=0.35, filter=blur(3))
    P(smooth([(1150, 500), (1150, 580), (1120, 640)], closed=False), stroke="#2a2218", stroke_width=10, opacity=0.35, filter=blur(5))
    for pts in ([(1062, 618), (1084, 630), (1100, 648)], [(1072, 600), (1096, 612), (1116, 630)], [(1058, 640), (1076, 650), (1090, 662)]):
        P(smooth(pts, closed=False), stroke="#3a3024", stroke_width=3.5, opacity=0.4, filter=blur(1.5))
    group_end()
    P(d, stroke="#4a3f30", stroke_width=1.6, opacity=0.55)


def book():
    G0, G1 = (915, 625), (935, 525)
    L0, L1 = (838, 613), (852, 513)
    R0, R1 = (975, 613), (990, 520)
    # 封面（深绿布面）+ 书页厚度
    P(smooth([(L0[0] - 6, L0[1] + 8, "c"), (L1[0] - 6, L1[1] - 4, "c"), (895, 505), (G1[0], G1[1] + 2, "c"), (965, 510),
              (R1[0] + 5, R1[1] - 2, "c"), (R0[0] + 5, R0[1] + 8, "c"), (G0[0], G0[1] + 12, "c")]), fill="#23392f")
    P(smooth([(L0[0], L0[1], "c"), (878, 622), (G0[0], G0[1], "c"), (948, 624), (R0[0], R0[1], "c"), (R0[0] + 2, R0[1] + 7, "c"),
              (948, 631), (G0[0], G0[1] + 8, "c"), (878, 629), (L0[0] - 1, L0[1] + 7, "c")]), fill="#e2d6bb")
    for k_ in range(3):
        P(smooth([(L0[0], L0[1] + 2 + 2 * k_), (878, 624 + 2 * k_), (G0[0], G0[1] + 2 + 2 * k_)], closed=False), stroke="#b9ab8c",
          stroke_width=0.8)
    # 左页（更朝向窗，更亮）
    lp = [(L0[0], L0[1], "c"), (L1[0], L1[1], "c"), (870, 505), (900, 508), (G1[0], G1[1], "c"), (G0[0], G0[1], "c"), (878, 620)]
    rp = [(G0[0], G0[1], "c"), (G1[0], G1[1], "c"), (955, 512), (R1[0], R1[1], "c"), (R0[0], R0[1], "c"), (948, 620)]
    FIG.append((smooth(lp), None))
    FIG.append((smooth(rp), None))
    P(smooth(lp), fill=lin("lpage", L1[0], 0, G1[0], 0, [(0, "#fffaf0"), (0.8, "#f4e9d2"), (1, "#c9b995")]))
    P(smooth(rp), fill=lin("rpage", G1[0], 0, R1[0], 0, [(0, "#b8a88a"), (0.25, "#e8dcc2"), (1, "#f3e9d3")]))
    # 文字行
    for i in range(13):
        t = (i + 1.3) / 15
        ya, yb = L1[1] + (L0[1] - L1[1]) * t, G1[1] + (G0[1] - G1[1]) * t
        xa, xb = L1[0] + (L0[0] - L1[0]) * t + 7, G1[0] + (G0[0] - G1[0]) * t - 8
        dip = -6 * (1 - t)
        e = 1.0 if (i % 5 != 4) else rng.uniform(0.4, 0.7)
        P(f"M{f(xa)},{f(ya - 3 + dip * 0.2)} Q{f((xa + xb) / 2)},{f((ya + yb) / 2 - 4 + dip)} {f(xa + (xb - xa) * e)},{f(ya + (yb - ya) * e - 1)}",
          stroke="#8e8574", stroke_width=1.3, opacity=0.75)
        ya2, yb2 = G1[1] + (G0[1] - G1[1]) * t, R1[1] + (R0[1] - R1[1]) * t
        xa2, xb2 = G1[0] + (G0[0] - G1[0]) * t + 6, R1[0] + (R0[0] - R1[0]) * t - 5
        e = 1.0 if (i % 6 != 3) else rng.uniform(0.4, 0.7)
        P(f"M{f(xa2)},{f(ya2)} Q{f((xa2 + xb2) / 2)},{f((ya2 + yb2) / 2 - 4 + dip)} {f(xa2 + (xb2 - xa2) * e)},{f(ya2 + (yb2 - ya2) * e - 1)}",
          stroke="#8e8574", stroke_width=1.1, opacity=0.6)
    P(lines([G0, G1], closed=False), stroke="#9c8b6c", stroke_width=2, opacity=0.8)
    # 书页被窗光照亮
    P(smooth(lp), fill="#fff3d6", opacity=0.25, style="mix-blend-mode:screen")


def far_hand():
    d = smooth([(998, 600), (986, 592), (976, 578), (967, 564), (963, 556), (968, 552), (978, 558), (990, 570), (1000, 582)])
    P(d, fill=lin("fthumb", 962, 0, 1000, 0, [(0, SKIN[0]), (1, SKIN[2])]))
    P(d, stroke="#8a5a46", stroke_width=1.1, opacity=0.55)
    P(smooth([(963, 556), (968, 552), (974, 556), (971, 561), (965, 561)]), fill="#f7e0cf", opacity=0.9)


def forearm():
    d = smooth([(1088, 628), (1050, 612), (990, 604), (910, 600), (882, 602, "c"), (877, 620), (880, 640, "c"), (920, 646),
                (1000, 654), (1062, 668), (1090, 662)])
    FIG.append((d, None))
    cid = clip("farm", d)
    P(d, fill=lin("fa", 0, 600, 0, 668, [(0, KNIT[0]), (0.5, KNIT[1]), (1, KNIT[2])]))
    group_start(clip_path=cid)
    for x in range(900, 1100, 9):
        P(lines([(x, 595), (x + 4, 675)], closed=False), stroke="#3a3024", stroke_width=1.1, opacity=0.1)
    P(smooth([(1080, 622), (1000, 608), (920, 606)], closed=False), stroke="#fff6de", stroke_width=5, opacity=0.4, filter=blur(3))
    for pts in ([(936, 604), (930, 624), (938, 646)], [(956, 606), (950, 628), (958, 650)], [(1040, 614), (1030, 638), (1036, 662)]):
        P(smooth(pts, closed=False), stroke="#3a3024", stroke_width=3, opacity=0.35, filter=blur(1.5))
    P(smooth([(900, 650), (1000, 656), (1080, 668)], closed=False), stroke="#2a2218", stroke_width=6, opacity=0.35, filter=blur(3))
    group_end()
    P(d, stroke="#4a3f30", stroke_width=1.4, opacity=0.5)
    # 袖口的罗纹
    P(smooth([(882, 602, "c"), (898, 601), (896, 621), (898, 644), (880, 640, "c"), (877, 620)]), fill="#b9a67f")
    for x in (884, 888, 892):
        P(f"M{x},603 L{x - 1},640", stroke="#6e604b", stroke_width=1, opacity=0.4)


def near_hand():
    d = smooth([(846, 598), (866, 600), (884, 604), (884, 634), (862, 638), (846, 630), (838, 614)])
    FIG.append((d, None))
    cid = clip("nhand", d)
    P(d, fill=lin("nh", 838, 598, 884, 638, [(0, SKIN[0]), (0.6, SKIN[1]), (1, SKIN[2])]))
    group_start(clip_path=cid)
    P(smooth([(840, 610), (860, 603), (884, 606)], closed=False), stroke="#fff0dc", stroke_width=4, opacity=0.5, filter=blur(2))
    P(smooth([(846, 634), (866, 638), (886, 634)], closed=False), stroke="#6a3a2c", stroke_width=5, opacity=0.35, filter=blur(3))
    P(smooth([(882, 614), (866, 620), (852, 626)], closed=False), stroke="#7a6a8a", stroke_width=1.2, opacity=0.35)
    group_end()
    P(d, stroke="#8a5a46", stroke_width=1.2, opacity=0.5)
    # 拇指：压在左页上，指向右上
    d = smooth([(844, 608), (847, 594), (856, 582), (867, 572), (877, 569), (882, 575), (876, 587), (866, 597), (860, 608)])
    P(d, fill=lin("thumb", 844, 0, 882, 0, [(0, SKIN[0]), (1, SKIN[1])]))
    P(d, stroke="#8a5a46", stroke_width=1.1, opacity=0.55)
    P(smooth([(870, 572), (877, 570), (881, 575), (876, 580), (869, 579)]), fill="#f7e0cf", opacity=0.95)   # 指甲
    P("M856,590 q5,-1 8,-5", stroke="#a06a55", stroke_width=1, opacity=0.6)
    # 书的左外沿后面露一点食指
    d = smooth([(838, 574), (831, 578), (829, 590), (833, 598), (839, 596)])
    P(d, fill=lin("idx", 829, 0, 839, 0, [(0, SKIN[0]), (1, SKIN[2])]))


HEAD_T = "translate(1045 372) rotate(-18)"


def head():
    group_start(transform=HEAD_T)
    skull = [(0, -70), (-30, -64), (-46, -46), (-53, -25), (-56, -12), (-52, -4, "c"), (-57, 6), (-64, 17), (-70, 25), (-69, 31),
             (-62, 35), (-54, 34, "c"), (-54, 41), (-52, 48), (-50, 56), (-44, 64), (-30, 66), (-10, 62), (10, 52), (25, 40), (40, 30),
             (52, 12), (57, -12), (52, -40), (35, -60), (15, -69)]
    d = smooth(skull)
    FIG.append((d, HEAD_T))
    cid = clip("skull", d)
    P(d, fill=lin("skin", -70, 0, 57, 0, [(0, SKIN[0]), (0.45, SKIN[1]), (1, SKIN[2])]))
    group_start(clip_path=cid)
    add("ellipse", cx=-58, cy=24, rx=14, ry=11, fill="#e0786a", opacity=0.35, filter=blur(4))     # 鼻头泛红
    add("ellipse", cx=-30, cy=18, rx=16, ry=12, fill="#d9776a", opacity=0.25, filter=blur(6))     # 面颊
    add("ellipse", cx=-8, cy=-60, rx=34, ry=14, fill="#fff2e2", opacity=0.45, filter=blur(6))     # 秃顶反光
    add("ellipse", cx=30, cy=0, rx=34, ry=60, fill="#5a3025", opacity=0.3, filter=blur(12))       # 后脑暗部
    add("ellipse", cx=-38, cy=-4, rx=10, ry=7, fill="#8a4a3a", opacity=0.3, filter=blur(3))       # 眼窝
    add("ellipse", cx=-47, cy=-22, rx=12, ry=28, fill="#ffe2c4", opacity=0.35, filter=blur(6))    # 额头和面颊前侧受光
    # 皱纹
    for y in (-44, -36, -28):
        P(f"M-48,{y} q10,-3 20,-1", stroke="#a0624c", stroke_width=1.1, opacity=0.55)
    for a in (-25, 0, 25):
        P(f"M-30,-2 l{f(9 * np.cos(np.radians(a)))},{f(9 * np.sin(np.radians(a)))}", stroke="#a0624c", stroke_width=1, opacity=0.5)
    P(smooth([(-55, 21), (-51, 28), (-47, 36)], closed=False), stroke="#9a5a46", stroke_width=1.4, opacity=0.6)
    P(smooth([(-38, 12), (-33, 22), (-30, 32)], closed=False), stroke="#b06a55", stroke_width=1, opacity=0.35)
    P(smooth([(-62, 28), (-56, 26), (-53, 30)], closed=False), stroke="#8a4a3a", stroke_width=1.4, opacity=0.7)     # 鼻翼
    add("ellipse", cx=-64, cy=22, rx=4, ry=3, fill="#fff4e8", opacity=0.55, filter=blur(1.5))       # 鼻头高光
    add("ellipse", cx=-36, cy=8, rx=7, ry=4, fill="#ffe8d4", opacity=0.35, filter=blur(2.5))        # 颧骨
    # 脸前缘的轮廓光
    P(smooth([(-30, -64), (-46, -46), (-53, -25), (-56, -12), (-52, -4), (-57, 6), (-64, 17), (-70, 25)], closed=False),
      stroke="#fff0dc", stroke_width=4, opacity=0.55, filter=blur(1.5))
    group_end()
    # 白发：两侧和后脑一圈，头顶几缕
    hair = [(-22, -44), (-6, -50), (18, -56), (40, -50), (55, -32), (61, -8), (60, 12), (55, 30), (46, 44), (34, 46), (27, 36),
            (28, 18), (30, 4), (26, -16), (8, -28), (-10, -30), (-20, -36)]
    d = smooth(hair)
    FIG.append((d, HEAD_T))
    P(d, fill=lin("hair", -20, 0, 62, 0, [(0, HAIR[0]), (0.5, HAIR[1]), (1, HAIR[2])]))
    group_start(clip_path=clip("hairc", d))
    for _ in range(70):
        x0, y0 = rng.uniform(-18, 58), rng.uniform(-52, 34)
        ln = rng.uniform(8, 16)
        a = np.radians(rng.uniform(55, 100))
        P(f"M{f(x0)},{f(y0)} q{f(ln * 0.5 * np.cos(a) + 2)},{f(ln * 0.5 * np.sin(a))} {f(ln * np.cos(a))},{f(ln * np.sin(a))}",
          stroke=rng.choice(["#9c958a", "#fbf8f2"]), stroke_width=0.9, opacity=0.3)
    group_end()
    P(d, fill="none", stroke="#f4f0e8", stroke_width=3, opacity=0.5, filter=blur(1.5))
    for _ in range(9):                       # 头顶稀疏的几缕，贴着头皮
        x0 = rng.uniform(-18, 30)
        P(f"M{f(x0)},{f(-62 + abs(x0) * 0.08)} q{f(rng.uniform(6, 10))},{f(-2)} {f(rng.uniform(14, 20))},{f(rng.uniform(1, 4))}",
          stroke="#f3eee6", stroke_width=0.9, opacity=0.45, filter=blur(0.6))
    # 耳朵
    add("ellipse", cx=14, cy=2, rx=11, ry=19, transform="rotate(12 14 2)", fill=lin("ear", 3, 0, 25, 0, [(0, SKIN[1]), (1, SKIN[2])]))
    P("M19,-10 C10,-12 8,4 12,12 C14,16 18,14 17,10", stroke="#8a4f3e", stroke_width=1.6, opacity=0.8)
    P("M8,-14 C4,-6 4,8 9,18", stroke="#f6d2b8", stroke_width=1.5, opacity=0.6)
    # 胡子：唇髭 + 短络腮胡
    beard = [(-54, 42), (-57, 52), (-54, 64), (-46, 75), (-32, 81), (-14, 77), (4, 67), (18, 54), (24, 38), (20, 22), (12, 24),
             (4, 36), (-8, 42), (-22, 44), (-38, 43)]
    d = smooth(beard)
    FIG.append((d, HEAD_T))
    P(d, fill=lin("beard", -57, 0, 16, 0, [(0, HAIR[0]), (0.55, HAIR[1]), (1, HAIR[2])]))
    group_start(clip_path=clip("beardc", d))
    for i in range(30):
        x0 = -52 + i * 2.4
        P(f"M{f(x0)},{f(40 + (i % 3) * 3)} q{f(-2)},{f(14)} {f(2 - i * 0.1)},{f(34 - abs(i - 12) * 0.9)}", stroke="#a39c90",
          stroke_width=0.9, opacity=0.45)
    group_end()
    must = [(-55, 33), (-61, 38), (-60, 45), (-52, 48), (-42, 46), (-36, 40), (-44, 34)]
    P(smooth(must), fill=lin("must", -61, 0, -36, 0, [(0, "#fbf8f2"), (1, "#bdb6aa")]))
    for i in range(6):
        P(f"M{-58 + i * 3},{36} q-2,6 -3,{9 - abs(i - 2)}", stroke="#9d968a", stroke_width=0.8, opacity=0.6)
    # 眉毛、下垂的眼睑（看书）
    P(smooth([(-54, -16), (-46, -19), (-36, -18), (-28, -15), (-34, -12), (-46, -12)]), fill="#e9e3d8")
    for i in range(7):
        P(f"M{-52 + i * 3.5},-16 q-3,3 -6,4", stroke="#b8b0a4", stroke_width=1, opacity=0.8)
    P("M-47,-3 C-43,-6 -37,-5 -33,-2", stroke="#4a2a20", stroke_width=2.2)
    P("M-46,-2 C-42,0 -38,0 -34,-1", stroke="#6a3a2c", stroke_width=1, opacity=0.6)
    P("M-45,4 C-41,6 -37,6 -33,4", stroke="#a0624c", stroke_width=1, opacity=0.5)
    # 老花镜：侧面看是一片窄椭圆 + 镜腿
    P("M-56,-2 L10,-12", stroke="#3b2a1c", stroke_width=2.2)
    add("ellipse", cx=-60, cy=7, rx=4, ry=11, transform="rotate(-12 -60 7)", fill="#ffffff", fill_opacity=0.18,
        stroke="#3b2a1c", stroke_width=2)
    P("M-62,0 l1,8", stroke="#ffffff", stroke_width=1.2, opacity=0.7)
    group_end()


# ================= 组装 =================
def figure_light():
    """窗光落在人物朝窗的一侧：书、手、脸、胡子最亮。"""
    def paths(lst, col):
        return "".join(f'<path d="{d}" fill="{col}"' + (f' transform="{t}"' if t else "") + "/>" for d, t in lst)
    DEFS.append(f'<mask id="figall" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">'
                f'{paths(FIG_BACK, "#fff")}{paths([(d, None) for d in CHAIR_SIDE], "#000")}{paths(FIG, "#fff")}</mask>')
    group_start(mask="url(#figall)", style="mix-blend-mode:screen")
    add("rect", x=700, y=250, width=560, height=800,
        fill=rad("figglow", 900, 540, 330, [(0, "#ffd9a2", 0.42), (0.55, "#ffcf8e", 0.16), (1, "#ffcf8e", 0)]))
    add("rect", x=700, y=250, width=560, height=800,
        fill=rad("faceglow", 975, 385, 95, [(0, "#ffd9b0", 0.32), (1, "#ffd9b0", 0)]))
    group_end()


def build():
    room()
    window()
    curtains()
    sill_items()
    bookshelf()
    floor_light()
    # 椅子和人在地上的影子（朝右）
    P(smooth([(880, 996), (1320, 990), (1536, 1010), (1536, 1024), (840, 1024)]), fill="#120804", opacity=0.55, filter=blur(12))
    chair_back()
    legs()
    torso()
    neck()
    head()
    upper_arm()
    chair_front()
    book()
    far_hand()
    forearm()
    near_hand()
    figure_light()
    light_beams()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f'<defs>{"".join(DEFS)}</defs>{"".join(S)}</svg>')
    return svg


def post(png_in, png_out):
    """窗光泛光 + 暗角 + 细颗粒。"""
    from scipy import ndimage as ndi
    img = np.asarray(Image.open(png_in).convert("RGB"), np.float32) / 255
    lum = img @ np.array([0.3, 0.59, 0.11], np.float32)
    glow = ndi.gaussian_filter(img * (lum > 0.8)[..., None], (22, 22, 0))
    img = 1 - (1 - img) * (1 - 0.45 * glow)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot((xx - 640) / W, (yy - 520) / H) * 1.6
    img = img * (1 - 0.42 * np.clip(r - 0.35, 0, 1) ** 1.4)[..., None]
    img = img * np.array([1.025, 1.0, 0.965], np.float32)
    r_ = np.random.default_rng(67)
    low = sum(np.asarray(Image.fromarray(r_.random((H // s_ + 2, W // s_ + 2)).astype(np.float32), mode="F")
                         .resize((W, H), Image.BICUBIC)) * (0.5 ** i) for i, s_ in enumerate((160, 64, 24, 8)))
    low = (low - low.mean()) / (low.std() + 1e-6)
    img = img * (1 + 0.025 * low)[..., None]
    img = img + np.random.default_rng(66).normal(0, 0.012, (H, W, 1)).astype(np.float32)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(png_out)


def main():
    svg = build()
    svg_path = os.path.join(HERE, "scene.svg")
    open(svg_path, "w").write(svg)
    raw = os.path.join(HERE, "scene_raw.png")
    subprocess.run([sys.executable, RENDER, svg_path, raw], check=True, stdout=subprocess.DEVNULL)
    post(raw, OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
