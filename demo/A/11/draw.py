#!/usr/bin/env python3
"""A11 像素画：勇者站在城堡前。

纯代码逐像素绘制（numpy + Pillow），不读取任何图片文件：
- 256×160 的调色板索引画布，只用下面定义的有限调色板；
- 天空用 4×4 Bayer 有序抖动做色带过渡，云、远山、城堡、草地、小路都是逐像素规则生成；
- 勇者精灵按像素坐标一块块手工放置（披风、腿、裙甲、胸甲、护肩、手套、剑、头发、发带），最后自动描 1 像素外轮廓；
- 最近邻放大 6 倍到 1536×960。
运行：python3 draw.py → final.png
"""
import os
import numpy as np
from PIL import Image

OUT = os.path.dirname(os.path.abspath(__file__))
WL, HL = 256, 160
UP = 6

PAL = {
    'K': '#1a1626',
    'h': '#5a2e18', 'H': '#8f4a22', 'y': '#c8793a',
    's': '#c8845e', 'S': '#f2bf94', 'L': '#ffe0c0',
    'r': '#6e1a24', 'R': '#b52a36', 'P': '#e85a5a',
    'b': '#1c2a66', 'B': '#2f55b0', 'C': '#5b8ae6',
    'g': '#5b6380', 'G': '#a3adc6', 'W': '#eef2fa',
    'n': '#43261a', 'N': '#744326', 'O': '#a96d3a',
    'o': '#9b6214', 'Y': '#e3ac2c', 'Z': '#fff08a',
    'd': '#2a2a40', 'D': '#45455e',
    'w': '#ffffff',
    # sky
    's0': '#1d2b6b', 's1': '#2c4aa0', 's2': '#3f6fd0', 's3': '#6a9ee8', 's4': '#9cc6f2', 's5': '#cfe6f6', 's6': '#f6e7c4',
    # clouds
    'c0': '#ffffff', 'c1': '#e2ecf8', 'c2': '#b4c4e2', 'c3': '#8d9ccc',
    # mountains
    'm0': '#4d5596', 'm1': '#6f7abb', 'm2': '#e8eefc', 'm3': '#3a5486', 'm4': '#557aa6',
    # greens
    'g0': '#173a26', 'g1': '#245c32', 'g2': '#3d8a3e', 'g3': '#6bb84a', 'g4': '#aee070',
    # dirt
    'e0': '#5e3f26', 'e1': '#9a7044', 'e2': '#caa06a', 'e3': '#e6c890',
    # stone
    't0': '#3e3a4e', 't1': '#6c6680', 't2': '#9c95ac', 't3': '#cbc3d4', 't4': '#ece6f0',
    # roof
    'f0': '#1c2862', 'f1': '#2f4696', 'f2': '#5270cc', 'f3': '#86a2ec',
    # window glow / misc
    'x0': '#0e0c18',
}
KEYS = list(PAL.keys())
IDX = {k: i for i, k in enumerate(KEYS)}
RGB = np.array([[int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16)] for v in PAL.values()], np.uint8)

BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16.0

CAN = np.full((HL, WL), IDX['s3'], np.int32)


def px(x, y, c, can=None):
    can = CAN if can is None else can
    if 0 <= x < can.shape[1] and 0 <= y < can.shape[0]:
        can[y, x] = IDX[c]


def hl(x0, x1, y, c, can=None):
    for x in range(min(x0, x1), max(x0, x1) + 1):
        px(x, y, c, can)


def vl(x, y0, y1, c, can=None):
    for y in range(min(y0, y1), max(y0, y1) + 1):
        px(x, y, c, can)


def rect(x0, y0, x1, y1, c, can=None):
    for y in range(y0, y1 + 1):
        hl(x0, x1, y, c, can)


def hash01(x, y, s=0):
    h = (x * 374761393 + y * 668265263 + s * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0


def vnoise(x, y, s=0):
    ix, iy = int(np.floor(x)), int(np.floor(y))
    fx, fy = x - ix, y - iy
    u, v = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = hash01(ix, iy, s), hash01(ix + 1, iy, s)
    c, d = hash01(ix, iy + 1, s), hash01(ix + 1, iy + 1, s)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm(x, y, s=0, o=3):
    t, a, n = 0.0, 1.0, 0.0
    for i in range(o):
        t += a * vnoise(x, y, s + i * 17)
        n += a
        a *= 0.5
        x, y = x * 2.03 + 3.1, y * 2.03 + 1.3
    return t / n


def dith(x, y, t):
    """t in [0,1]：有序抖动阈值判断。"""
    return t > BAYER[y % 4, x % 4]


# ----------------------------------------------------------------------------- sky & clouds
def draw_sky():
    bands = ['s0', 's1', 's2', 's3', 's4', 's5', 's6']
    edges = [0, 14, 30, 46, 62, 76, 86, 100]
    for y in range(HL):
        yy = min(y, 99)
        for i in range(len(bands)):
            if edges[i] <= yy < edges[i + 1]:
                t = (yy - edges[i]) / (edges[i + 1] - edges[i])
                for x in range(WL):
                    c = bands[i]
                    if i + 1 < len(bands) and dith(x, y, (t - 0.6) / 0.4):
                        c = bands[i + 1]
                    px(x, y, c)
                break


def draw_cloud(cx, cy, blobs, seed):
    """像素积云：若干圆叠加，平底；左上高光、右下阴影。"""
    cells = {}
    for (dx, dy, r) in blobs:
        for y in range(int(cy + dy - r - 1), int(cy + dy + r + 2)):
            for x in range(int(cx + dx - r - 1), int(cx + dx + r + 2)):
                d = ((x - cx - dx) ** 2 + (y - cy - dy) ** 2) ** 0.5
                if d <= r and y <= cy + 2:
                    # 法线方向估计：与圆心的偏移
                    nx, ny = (x - cx - dx) / r, (y - cy - dy) / r
                    lit = -0.7 * nx - 0.7 * ny
                    cells[(x, y)] = max(cells.get((x, y), -9), lit)
    for (x, y), lit in cells.items():
        bottom = y >= cy
        if lit > 0.35:
            c = 'c0'
        elif lit > -0.1:
            c = 'c1'
        elif lit > -0.55:
            c = 'c2'
        else:
            c = 'c3'
        if bottom and c in ('c0', 'c1'):
            c = 'c2'
        if y == cy + 2:
            c = 'c3' if dith(x, y, 0.6) else 'c2'
        px(x, y, c)


# ----------------------------------------------------------------------------- mountains & hills
def draw_mountains():
    peaks = [(8, 70, 0.9), (52, 58, 0.8), (96, 66, 0.85), (132, 52, 0.75), (178, 62, 0.8), (222, 50, 0.7), (262, 64, 0.9)]
    for x in range(WL):
        best, pk = 999, None
        for (p, h, sl) in peaks:
            yy = h + abs(x - p) * sl + 3 * (vnoise(x / 5.0, 0.5, 3) - 0.5)
            if yy < best:
                best, pk = yy, (p, h)
        top = int(round(best))
        for y in range(top, 112):
            depth = y - top
            lit = x < pk[0]
            c = 'm1' if lit else 'm0'
            snow_line = pk[1] + 7 + int(3 * vnoise(x / 4.0, 7.7, 9))
            if y < snow_line and pk[1] < 62:
                c = 'm2' if lit else 'c2'
            px(x, y, c)
    # 近处蓝绿色山丘
    for x in range(WL):
        top = int(round(94 + 4 * np.sin(x / 23.0) + 3 * np.sin(x / 9.0 + 1.3) + 2 * vnoise(x / 6.0, 1.1, 5)))
        for y in range(top, 118):
            c = 'm4'
            if y - top > 5:
                c = 'm3'
            if y == top:
                c = 'm1'
            px(x, y, c)


def draw_fields():
    # 城堡所在的草坡 + 中景田野：干净的色块，只在带边缘处少量抖动
    for x in range(WL):
        hill = 110 - 7 * np.exp(-((x - 170) / 48.0) ** 2) + 2 * np.sin(x / 17.0)
        top = int(round(hill))
        for y in range(top, HL):
            depth = y - top
            n = fbm(x / 16.0, y / 7.0, 21)
            c = 'g3'
            if depth < 1:
                c = 'g4'
            elif y > 142 or (y > 136 and dith(x, y, (y - 136) / 6.0)):
                c = 'g2'
            if n > 0.64 and c == 'g3':
                c = 'g4'
            elif n < 0.34 and c == 'g3':
                c = 'g2'
            elif n > 0.66 and c == 'g2':
                c = 'g3'
            px(x, y, c)


def draw_trees(cx, base, n, seed, spread=14):
    rng = np.random.default_rng(seed)
    for i in range(n):
        tx = cx + rng.integers(-spread, spread + 1)
        ty = base + rng.integers(-3, 4)
        r = rng.integers(4, 7)
        for y in range(ty - 2 * r, ty + 1):
            for x in range(tx - r, tx + r + 1):
                dx, dy = (x - tx) / r, (y - (ty - r)) / r
                if dx * dx + dy * dy <= 1.0 + 0.25 * (vnoise(x / 1.5, y / 1.5, seed + i) - 0.5):
                    lit = -dx * 0.8 - dy * 0.6
                    c = 'g2' if lit > 0.3 else ('g1' if lit > -0.4 else 'g0')
                    if lit > 0.6 and dith(x, y, 0.5):
                        c = 'g3'
                    px(x, y, c)
        vl(tx, ty - 1, ty + 2, 'e0')


# ----------------------------------------------------------------------------- castle
def stone(x, y, x0, x1, lit_frac=0.35, round_tower=False, brick=True):
    """城墙石块：光从左上来。"""
    u = (x - x0) / max(1, (x1 - x0))
    if round_tower:
        c = 't4' if u < 0.18 else ('t3' if u < 0.45 else ('t2' if u < 0.78 else 't1'))
        if 0.16 <= u < 0.2 and dith(x, y, 0.5):
            c = 't3'
    else:
        c = 't3' if u < lit_frac * 0.3 else 't3'
    if brick:
        row = y // 4
        off = 4 if row % 2 else 0
        if y % 4 == 0 or (x + off) % 8 == 0:
            c = {'t4': 't3', 't3': 't2', 't2': 't1', 't1': 't0'}[c]
    return c


def draw_tower(x0, x1, ytop, ybot, roof_h, seed, windows=True, flag=True, flagc='R'):
    for y in range(ytop, ybot + 1):
        for x in range(x0, x1 + 1):
            px(x, y, stone(x, y, x0, x1, round_tower=True))
    # 塔顶挑檐
    hl(x0 - 1, x1 + 1, ytop, 't1')
    hl(x0 - 1, x1 + 1, ytop - 1, 't2')
    # 锥形屋顶
    cxr = (x0 + x1) / 2.0
    hw = (x1 - x0) / 2.0 + 2.5
    for y in range(ytop - 1 - roof_h, ytop - 1):
        t = (y - (ytop - 1 - roof_h)) / roof_h
        w = hw * t
        for x in range(int(np.floor(cxr - w)), int(np.ceil(cxr + w)) + 1):
            if abs(x + 0.5 - cxr - 0.5) <= w + 0.3:
                u = (x - (cxr - w)) / max(2 * w, 1)
                c = 'f3' if u < 0.2 else ('f2' if u < 0.5 else ('f1' if u < 0.82 else 'f0'))
                if (y - ytop) % 3 == 0 and dith(x, y, 0.5):
                    c = {'f3': 'f2', 'f2': 'f1', 'f1': 'f0', 'f0': 'f0'}[c]
                px(x, y, c)
    tipy = ytop - 1 - roof_h
    if flag:
        vl(int(cxr), tipy - 9, tipy, 't0')
        fl = [(1, 0), (2, 0), (3, 0), (4, 0), (5, 1), (6, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (1, 2), (2, 2), (3, 2), (4, 3)]
        for (dx, dy) in fl:
            px(int(cxr) + dx, tipy - 9 + dy, flagc if dy < 2 else ('r' if flagc == 'R' else 'o'))
        px(int(cxr) + 2, tipy - 9, 'P' if flagc == 'R' else 'Z')
    if windows:
        for wy in range(ytop + 6, ybot - 12, 14):
            wx = int(cxr) - 1
            rect(wx, wy + 1, wx + 1, wy + 4, 'x0')
            px(wx, wy, 'x0')
            px(wx + 1, wy, 'x0')
            px(wx - 1, wy + 4, 't4')
            hl(wx - 1, wx + 2, wy + 5, 't1')


def crenel(x0, x1, y, h=3, merlon=3, gap=2, c_face=None):
    x = x0
    while x <= x1:
        for xx in range(x, min(x + merlon, x1 + 1)):
            for yy in range(y - h, y):
                u = (xx - x) / merlon
                px(xx, yy, 't4' if u < 0.34 else ('t3' if u < 0.67 else 't2'))
            px(xx, y - h, 't4')
        x += merlon + gap


def draw_castle():
    # 后方主塔（keep）
    kx0, kx1 = 158, 182
    for y in range(40, 96):
        for x in range(kx0, kx1 + 1):
            px(x, y, stone(x, y, kx0, kx1, round_tower=False))
            if x == kx0:
                px(x, y, 't4')
            if x >= kx1 - 2:
                px(x, y, 't2' if x < kx1 else 't1')
    crenel(kx0 - 1, kx1 + 1, 40, 3, 3, 2)
    # 主塔尖顶
    cxr, hw, top, h = 170.0, 10.5, 12, 26
    for y in range(top, top + h):
        t = (y - top) / h
        w = hw * t
        for x in range(int(cxr - w) - 1, int(cxr + w) + 2):
            if abs(x + 0.5 - cxr) <= w + 0.3:
                u = (x + 0.5 - (cxr - w)) / max(2 * w, 1)
                c = 'f3' if u < 0.22 else ('f2' if u < 0.52 else ('f1' if u < 0.82 else 'f0'))
                if (y - top) % 3 == 2 and dith(x, y, 0.5):
                    c = {'f3': 'f2', 'f2': 'f1', 'f1': 'f0', 'f0': 'f0'}[c]
                px(x, y, c)
    hl(int(cxr - hw) - 1, int(cxr + hw) + 1, top + h, 't1')
    vl(170, 1, top, 't0')
    for (dx, dy) in [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 1), (7, 1), (1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (6, 2),
                     (1, 2), (2, 2), (3, 2), (4, 2), (5, 3), (1, 3), (2, 3), (3, 4)]:
        px(170 + dx, 1 + dy, 'R' if dy < 3 else 'r')
    px(172, 1, 'P')
    px(173, 1, 'P')
    # 主塔窗
    for (wx, wy) in [(165, 50), (174, 50), (169, 63)]:
        rect(wx, wy + 1, wx + 1, wy + 5, 'x0')
        hl(wx, wx + 1, wy, 'x0')
        px(wx, wy + 2, 'Y')
        hl(wx - 1, wx + 2, wy + 6, 't1')
    # 左右小角楼
    draw_tower(146, 155, 62, 100, 13, 3, windows=False, flag=False)
    draw_tower(185, 194, 60, 100, 13, 4, windows=False, flag=False)
    # 城墙
    for y in range(84, 113):
        for x in range(124, 217):
            px(x, y, stone(x, y, 124, 216))
    crenel(124, 216, 84, 3, 3, 2)
    hl(124, 216, 84, 't2')
    # 城墙底部阴影和苔藓
    for x in range(124, 217):
        hh = int(2 + 5 * vnoise(x / 5.0, 0.3, 7))
        for y in range(112 - hh, 113):
            if not (163 <= x <= 177):
                px(x, y, 'g1' if y > 112 - hh + 1 else 'g2')
    # 门楼
    gx0, gx1 = 156, 184
    for y in range(66, 113):
        for x in range(gx0, gx1 + 1):
            c = stone(x, y, gx0, gx1)
            if x <= gx0 + 1:
                c = 't4'
            elif x >= gx1 - 1:
                c = 't1'
            px(x, y, c)
    crenel(gx0 - 1, gx1 + 1, 66, 4, 3, 2)
    # 拱门 + 铁闸门
    ax0, ax1, ay = 163, 177, 92
    for y in range(ay, 113):
        for x in range(ax0, ax1 + 1):
            cxa = (ax0 + ax1) / 2.0
            r = (ax1 - ax0) / 2.0
            if y < ay + r and ((x + 0.5 - cxa - 0.5) ** 2 + (y - (ay + r)) ** 2) ** 0.5 > r + 0.2:
                continue
            c = 'x0'
            if (x - ax0) % 3 == 1 or (y - ay) % 4 == 2:
                c = 't0'
            if y > 108:
                c = 'e0' if (x + y) % 2 else 'x0'
            px(x, y, c)
    for y in range(ay - 2, 113):
        for x in (ax0 - 1, ax1 + 1):
            px(x, y, 't4' if x == ax0 - 1 else 't1')
    for x in range(ax0, ax1 + 1):
        cxa = (ax0 + ax1) / 2.0
        r = (ax1 - ax0) / 2.0
        yy = int(round(ay + r - (max(r * r - (x + 0.5 - cxa - 0.5) ** 2, 0)) ** 0.5)) - 1
        px(x, yy, 't4')
    # 门楼两侧的红色旗帜
    for bx in (158, 180):
        for y in range(70, 90):
            for x in range(bx, bx + 3):
                c = 'R' if x == bx + 1 else ('P' if x == bx else 'r')
                if y == 89 and x == bx + 1:
                    c = 'r'
                px(x, y, c)
        px(bx + 1, 76, 'Y')
        px(bx + 1, 77, 'Z')
        px(bx + 1, 78, 'Y')
        px(bx, 77, 'Y')
        px(bx + 2, 77, 'o')
        hl(bx - 1, bx + 3, 69, 'o')
    # 门楼窗
    for (wx, wy) in [(161, 74), (178, 74)]:
        pass
    rect(168, 72, 172, 78, 'x0')
    px(168, 72, 't2')
    px(172, 72, 't2')
    vl(170, 72, 78, 't0')
    hl(167, 173, 79, 't1')
    # 左右圆塔
    draw_tower(114, 132, 58, 112, 22, 1, flagc='R')
    draw_tower(208, 226, 54, 112, 24, 2, flagc='Y')
    # 城墙上的箭窗
    for x in list(range(136, 152, 7)) + list(range(190, 206, 7)):
        vl(x, 92, 96, 'x0')
        px(x - 1, 94, 'x0')
        px(x + 1, 94, 'x0')


def draw_path():
    for y in range(110, HL):
        t = (y - 110) / 50.0
        cxp = 170 - (y - 110) * 0.95 - 6 * np.sin((y - 110) / 9.0)
        w = 3.5 + (y - 110) * 0.34
        for x in range(int(cxp - w) - 2, int(cxp + w) + 3):
            d = abs(x + 0.5 - cxp) - w + 1.2 * (vnoise(x / 2.0, y / 2.0, 31) - 0.5)
            if d < 0:
                n = fbm(x / 3.0, y / 2.0, 33)
                c = 'e2'
                if d > -1.2:
                    c = 'e1'
                elif n > 0.66 and dith(x, y, 0.6):
                    c = 'e3'
                elif n < 0.38 and dith(x, y, 0.6):
                    c = 'e1'
                if hash01(x, y, 5) < 0.04:
                    c = 'e0'
                px(x, y, c)
            elif d < 1.0 and dith(x, y, 0.5):
                px(x, y, 'g2')


def on_path(x, y):
    cxp = 170 - (y - 110) * 0.95 - 6 * np.sin((y - 110) / 9.0)
    w = 3.5 + (y - 110) * 0.34
    return abs(x + 0.5 - cxp) < w + 2


def draw_foreground():
    rng = np.random.default_rng(11)
    # 草丛
    for i in range(110):
        x = int(rng.integers(0, WL))
        y = int(rng.integers(118, HL))
        if on_path(x, y):
            continue
        c1 = 'g4' if y < 140 else 'g3'
        px(x, y, c1)
        px(x - 1, y - 1, 'g3')
        px(x + 1, y - 1, 'g3')
        if y > 135:
            px(x, y - 1, c1)
            px(x, y - 2, 'g4')
    # 小花
    for i in range(70):
        x = int(rng.integers(0, WL))
        y = int(rng.integers(122, HL - 1))
        if on_path(x, y):
            continue
        c = ['w', 'Z', 'P', 'C'][int(rng.integers(4))]
        px(x, y, c)
        if y > 138:
            px(x - 1, y, c)
            px(x + 1, y, c)
            px(x, y - 1, c)
            px(x, y + 1, c)
            px(x, y, 'Y')
    # 石头
    for (sx, sy, r) in [(12, 150, 4), (232, 146, 5), (122, 130, 2), (244, 128, 2)]:
        for y in range(sy - r, sy + 1):
            for x in range(sx - r - 1, sx + r + 2):
                dx, dy = (x - sx) / (r + 1), (y - sy) / r
                if dx * dx + dy * dy <= 1:
                    lit = -dx - dy
                    px(x, y, 't3' if lit > 0.6 else ('t2' if lit > -0.2 else 't1'))
        hl(sx - r, sx + r, sy + 1, 'g1')


def draw_tall_grass():
    rng = np.random.default_rng(23)
    for (x0, x1) in [(0, 46), (206, 256)]:
        for i in range(34):
            bx = int(rng.integers(x0, x1))
            hgt = int(rng.integers(5, 12))
            lean = rng.choice([-1, 0, 1])
            for k in range(hgt):
                x = bx + (lean * k) // 4
                y = HL - 1 - k
                c = 'g0' if k < hgt * 0.4 else ('g1' if k < hgt * 0.8 else 'g2')
                px(x, y, c)
                if k < 2:
                    px(x + 1, y, 'g0')


def castle_shadow():
    for x in range(216, 240):
        for y in range(111, 116):
            if (x - 216) < (116 - y) * 5 and CAN[y, x] in (IDX['g3'], IDX['g4']):
                px(x, y, 'g2')


def draw_moat():
    """城墙前的护城河 + 放下的木吊桥。"""
    for x in range(116, 226):
        e = min(x - 116, 225 - x)
        y0, y1 = 113, 117 if e > 3 else 116
        for y in range(y0, y1 + 1):
            c = 's3'
            if y == y0:
                c = 't0' if not (163 <= x <= 177) else 's2'
            elif y == y0 + 1:
                c = 's2'
            if (x * 3 + y * 7) % 11 == 0 and y > y0 + 1:
                c = 'c1'
            elif (x + y * 5) % 13 == 0 and y > y0:
                c = 's4'
            px(x, y, c)
        px(x, y1 + 1, 'e1' if e > 1 else 'g2')
        if e > 2:
            px(x, y1 + 2, 'g2')
    # 吊桥
    for y in range(111, 120):
        for x in range(163, 178):
            c = 'O' if (x - 163) % 3 == 0 else 'N'
            if y == 119 or x in (163, 177):
                c = 'n'
            px(x, y, c)
    for y in range(104, 112):
        px(162, y - (y - 104) // 3, 't0')
        px(178, y - (y - 104) // 3, 't0')


def draw_birds():
    for (x, y) in [(96, 38), (103, 34), (109, 40), (236, 70)]:
        for (dx, dy) in [(-2, -1), (-1, 0), (0, 1), (1, 0), (2, -1)]:
            px(x + dx, y + dy, 'm0')


# ----------------------------------------------------------------------------- hero sprite
def hero_sprite():
    """勇者精灵（约 58×80 像素），光从左上来。"""
    S = np.full((82, 60), -1, np.int32)

    def p(x, y, c):
        if 0 <= y < S.shape[0] and 0 <= x < S.shape[1]:
            S[y, x] = IDX[c]

    def h(x0, x1, y, c):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            p(x, y, c)

    def r_(x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            h(x0, x1, y, c)

    # ---- 披风（身后，向右飘）
    for y in range(21, 74):
        xr = 34 + int((y - 21) * 0.40) + int(round(1.8 * np.sin((y - 21) / 4.0)))
        for x in range(27, xr + 1):
            yb = 72 - int((x - 27) * 0.30 + 1.5 * np.sin(x / 2.0))
            if y > yb:
                continue
            f = (x - 27 + (y // 6)) % 6
            c = 'R'
            if f == 0 or f == 1 and y > 40:
                c = 'r'
            elif f == 2:
                c = 'P' if y < 50 else 'R'
            if x >= xr - 1 or y >= yb - 1:
                c = 'r'
            p(x, y, c)
    for y in range(26, 64):
        x_left = 6 + max(0, (40 - y) // 6)
        for x in range(x_left, 11):
            c = 'r'
            if x == x_left + 1 and y < 58:
                c = 'R'
            if x == x_left + 2 and y < 44:
                c = 'P'
            p(x, y, c)
    # ---- 腿、靴子
    for (lx0, lx1) in [(14, 19), (25, 30)]:
        r_(lx0, 52, lx1, 61, 'd')
        for y in range(52, 62):
            p(lx0, y, 'D')
        p(lx0 + 1, 58, 'D')
    for (bx0, bx1) in [(13, 19), (25, 31)]:
        r_(bx0, 61, bx1, 74, 'N')
        h(bx0, bx1, 61, 'O')
        h(bx0, bx1, 62, 'O')
        h(bx0, bx1, 63, 'n')
        for y in range(64, 75):
            p(bx0, y, 'O')
            p(bx1, y, 'n')
        h(bx0, bx1, 68, 'n')
        p(bx0 + 3, 68, 'Y')
    r_(9, 73, 19, 76, 'N')
    h(9, 19, 73, 'O')
    h(9, 19, 77, 'n')
    p(9, 76, 'n')
    r_(25, 73, 35, 76, 'N')
    h(25, 35, 73, 'O')
    h(25, 35, 77, 'n')
    p(35, 76, 'n')
    # ---- 裙甲
    for y in range(41, 53):
        w0 = 14 - (y - 41) // 4
        w1 = 30 + (y - 41) // 4
        for x in range(w0, w1 + 1):
            u = (x - w0) / max(1, (w1 - w0))
            c = 'C' if u < 0.18 else ('B' if u < 0.74 else 'b')
            if (x - 22) % 5 == 0 and y > 43 and 0.18 < u < 0.95:
                c = 'b'
            if y == 51:
                c = 'Y' if u < 0.72 else 'o'
            if y == 52:
                c = 'o'
            p(x, y, c)
    # ---- 躯干
    r_(15, 20, 29, 40, 'B')
    for y in range(20, 41):
        p(15, y, 'C')
        p(29, y, 'b')
    h(17, 27, 20, 'b')
    h(17, 27, 21, 'B')
    for y in range(22, 38):
        w0, w1 = 16, 28
        if y > 33:
            w0, w1 = 16 + (y - 33), 28 - (y - 33)
        for x in range(w0, w1 + 1):
            u = (x - w0) / max(1, (w1 - w0))
            c = 'G'
            if u < 0.25 and y < 29:
                c = 'W'
            elif u > 0.78:
                c = 'g'
            if y == 31:
                c = 'g'
            p(x, y, c)
    for (x, y, c) in [(22, 25, 'Y'), (21, 26, 'Y'), (22, 26, 'Z'), (23, 26, 'Y'), (20, 27, 'Y'), (21, 27, 'Y'),
                      (22, 27, 'R'), (23, 27, 'Y'), (24, 27, 'o'), (21, 28, 'Y'), (22, 28, 'Y'), (23, 28, 'o'), (22, 29, 'o')]:
        p(x, y, c)
    # 脖子
    r_(19, 17, 25, 19, 'S')
    for y in range(17, 20):
        p(25, y, 's')
    h(19, 25, 17, 's')
    # 腰带
    h(14, 30, 39, 'N')
    h(14, 30, 40, 'n')
    p(15, 39, 'Y')
    p(29, 39, 'Y')
    # ---- 护肩
    rows = [(19, 2, 6), (20, 1, 7), (21, 0, 7), (22, 0, 7), (23, 0, 7), (24, 0, 7), (25, 1, 6), (26, 2, 5)]
    for (y, a, b) in rows:
        for x in range(8 + a, 8 + b + 1):
            u = (x - 8) / 7.0
            c = 'G'
            if u < 0.45 and y < 23:
                c = 'W'
            elif y >= 25 or u > 0.8:
                c = 'g'
            p(x, y, c)
        for x in range(29 + (7 - b), 29 + (7 - a) + 1):
            u = (x - 29) / 7.0
            c = 'g'
            if u < 0.35 and y < 23:
                c = 'G'
            p(x, y, c)
    # ---- 手臂
    r_(8, 27, 12, 32, 'B')
    for y in range(27, 33):
        p(8, y, 'C')
        p(12, y, 'b')
        p(13, y, 'b')
    r_(32, 27, 36, 32, 'b')
    for y in range(27, 33):
        p(32, y, 'B')
        p(31, y, 'b')
    for (y, a, b_) in [(33, 9, 13), (34, 10, 14), (35, 11, 15), (36, 12, 16), (37, 13, 17), (38, 14, 18)]:
        h(a, b_, y, 'G')
        p(a, y, 'W')
        p(b_ + 1, y, 'g')
    for (y, a, b_) in [(33, 31, 35), (34, 30, 34), (35, 29, 33), (36, 28, 32), (37, 27, 31), (38, 26, 30)]:
        h(a, b_, y, 'G')
        p(b_, y, 'g')
        p(a - 1, y, 'g')
    p(9, 33, 'W')
    p(10, 33, 'W')
    p(34, 33, 'g')
    # 剑柄头（红宝石）
    p(22, 32, 'Y')
    h(21, 23, 33, 'Y')
    p(21, 33, 'Z')
    h(21, 23, 34, 'Y')
    p(22, 34, 'R')
    p(23, 34, 'o')
    h(21, 23, 35, 'o')
    h(21, 23, 36, 'N')
    # 双拳
    r_(17, 36, 27, 41, 'G')
    h(17, 26, 36, 'W')
    for y in range(37, 41):
        p(19, y, 'g')
        p(21, y, 'g')
        p(22, y, 'g')
        p(24, y, 'g')
        p(26, y, 'g')
        p(27, y, 'g')
    h(17, 27, 41, 'g')
    p(17, 37, 'W')
    p(17, 38, 'W')
    # ---- 剑：护手 + 剑刃
    h(14, 30, 42, 'Y')
    h(15, 18, 42, 'Z')
    h(14, 30, 43, 'o')
    h(20, 24, 43, 'Y')
    p(22, 43, 'R')
    p(13, 41, 'Y')
    p(13, 42, 'o')
    p(31, 41, 'o')
    p(31, 42, 'o')
    for y in range(44, 73):
        p(20, y, 'W')
        p(21, y, 'w' if y < 62 else 'W')
        p(22, y, 'G')
        p(23, y, 'g')
    h(20, 23, 73, 'G')
    h(21, 23, 74, 'G')
    p(23, 74, 'g')
    h(21, 22, 75, 'G')
    p(22, 76, 'g')
    p(21, 76, 'G')
    # ---- 头
    tops = [10, 8, 5, 3, 6, 8, 4, 1, 4, 7, 3, 0, 3, 6, 5, 2, 5, 8, 10]
    for i, t in enumerate(tops):
        x = 13 + i
        for y in range(t, 10):
            p(x, y, 'H')
    for i, t in enumerate(tops):
        x = 13 + i
        lt = tops[i - 1] if i > 0 else 99
        rt = tops[i + 1] if i + 1 < len(tops) else 99
        if t < lt and t <= rt:
            p(x, t, 'y')
            p(x, t + 1, 'y')
            p(x + 1, t + 1, 'H')
        elif t < lt:
            p(x, t, 'y')
        elif t > rt:
            p(x, t, 'h')
    for x in range(14, 31):
        if x < 22:
            p(x, 7, 'y' if (x % 3) else 'H')
        else:
            p(x, 7, 'H' if (x % 3) else 'h')
    # 发带
    h(13, 31, 8, 'R')
    h(14, 20, 8, 'P')
    h(13, 31, 9, 'R')
    h(24, 31, 9, 'r')
    for (x, y, c) in [(32, 8, 'R'), (32, 9, 'r'), (33, 7, 'R'), (34, 7, 'P'), (35, 6, 'R'), (36, 6, 'R'), (37, 5, 'P'), (38, 5, 'R'),
                      (33, 8, 'r'), (34, 8, 'R'), (35, 7, 'r'), (36, 7, 'r'), (37, 6, 'r'),
                      (33, 10, 'R'), (34, 10, 'R'), (35, 11, 'R'), (36, 11, 'P'), (37, 12, 'R'), (38, 12, 'r'), (39, 13, 'R'),
                      (33, 11, 'r'), (34, 11, 'r'), (35, 12, 'r'), (36, 12, 'r')]:
        p(x, y, c)
    # 脸
    r_(15, 10, 29, 16, 'S')
    h(16, 28, 17, 'S')
    h(18, 26, 18, 'S')
    for y in range(10, 18):
        p(28, y, 's')
        p(29, y, 's')
    h(16, 28, 17, 's')
    h(18, 26, 18, 's')
    h(19, 25, 17, 'S')
    p(16, 12, 'L')
    p(16, 13, 'L')
    p(17, 12, 'L')
    p(16, 14, 'L')
    # 刘海与两侧头发
    for x in (15, 17, 18, 20, 23, 24, 26, 28):
        p(x, 10, 'H')
    for x in (15, 18, 24, 28):
        p(x, 11, 'H')
    p(16, 10, 'h')
    p(27, 10, 'h')
    for y in range(10, 17):
        p(13, y, 'H')
        p(14, y, 'H' if y < 12 else ('h' if y > 15 else 'S'))
        p(30, y, 'h' if y < 12 else ('s' if y < 16 else 'h'))
        p(31, y, 'h')
    p(14, 13, 's')
    p(30, 14, 'h')
    # 眉、眼、鼻、嘴
    h(17, 19, 11, 'h')
    h(25, 27, 11, 'h')
    p(20, 12, 'h')
    p(24, 12, 'h')
    h(18, 19, 12, 'K')
    h(25, 26, 12, 'K')
    p(18, 13, 'w')
    p(19, 13, 'K')
    p(18, 14, 'b')
    p(19, 14, 'K')
    p(25, 13, 'w')
    p(26, 13, 'K')
    p(25, 14, 'b')
    p(26, 14, 'K')
    p(23, 15, 's')
    h(21, 23, 17, 's')
    p(20, 17, 'S')
    return S


def outline(S):
    op = S >= 0
    out = S.copy()
    k = IDX['K']
    Hh, Ww = S.shape
    for y in range(Hh):
        for x in range(Ww):
            if not op[y, x]:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < Ww and 0 <= yy < Hh and op[yy, xx]:
                        out[y, x] = k
                        break
    return out


def blit(S, x0, y0):
    for y in range(S.shape[0]):
        for x in range(S.shape[1]):
            if S[y, x] >= 0:
                xx, yy = x0 + x, y0 + y
                if 0 <= xx < WL and 0 <= yy < HL:
                    CAN[yy, xx] = S[y, x]


def main():
    draw_sky()
    draw_cloud(40, 30, [(-10, 0, 6), (-3, -3, 8), (6, -1, 7), (13, 1, 5)], 1)
    draw_cloud(118, 16, [(-8, 0, 5), (0, -3, 7), (8, 0, 5)], 2)
    draw_cloud(246, 36, [(-12, 0, 6), (-4, -2, 7), (5, 0, 6)], 3)
    draw_cloud(78, 58, [(-6, 0, 4), (0, -1, 5), (6, 0, 4)], 4)
    draw_mountains()
    draw_fields()
    draw_trees(100, 116, 7, 5, 12)
    draw_trees(238, 114, 7, 6, 16)
    draw_trees(12, 118, 5, 7, 12)
    draw_castle()
    castle_shadow()
    draw_path()
    draw_moat()
    draw_foreground()
    draw_tall_grass()
    draw_birds()
    # 勇者脚下阴影
    hx, hy = 52, 79
    for y in range(hy + 74, hy + 81):
        for x in range(hx + 2, hx + 44):
            dx = (x - (hx + 23)) / 20.0
            dy = (y - (hy + 77)) / 2.8
            if dx * dx + dy * dy <= 1 and dith(x, y, 0.75):
                px(x, y, 'g1')
    blit(outline(hero_sprite()), hx, hy)
    # 剑刃上的闪光
    sx, sy = hx + 13, hy + 41
    for (dx, dy, c) in [(0, 0, 'w'), (-1, 0, 'Z'), (1, 0, 'Z'), (0, -1, 'Z'), (0, 1, 'Z'), (-2, 0, 'w'), (2, 0, 'w'), (0, -2, 'w'), (0, 2, 'w')]:
        px(sx + dx, sy + dy, c)
    # 剑尖附近再加一个小闪光
    tx, ty = hx + 23, hy + 66
    for (dx, dy, c) in [(0, 0, 'w'), (-1, 0, 'Z'), (1, 0, 'Z'), (0, -1, 'Z'), (0, 1, 'Z')]:
        px(tx + dx, ty + dy, c)
    img = Image.fromarray(RGB[CAN])
    img = img.resize((WL * UP, HL * UP), Image.NEAREST)
    img.save(os.path.join(OUT, 'final.png'))
    print('saved', img.size)


if __name__ == '__main__':
    main()
