"""程序化绘制《千里江山图》风格青绿山水长卷。"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 6400, 1100
S = 3  # 笔触层超采样倍数
OUT = sys.argv[1] if len(sys.argv) > 1 else "qianli.png"
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"
TC_REG, TC_BOLD = 7, 2


def c(*v):
    return np.array(v, dtype=np.float32) / 255


SILK = c(198, 174, 126)
MIST = c(206, 192, 150)
canvas = np.empty((H, W, 3), np.float32)


# ---------------- 噪声 ----------------
def noise1d(n, scale, octaves=4, seed=0):
    r = np.random.default_rng(seed)
    out = np.zeros(n, np.float32)
    amp, tot = 1.0, 0.0
    for _ in range(octaves):
        k = max(3, int(n / max(scale, 1)) + 3)
        pts = r.standard_normal(k).astype(np.float32)
        xs = np.linspace(0, k - 2, n)
        i = np.floor(xs).astype(int)
        f = xs - i
        f = (1 - np.cos(f * np.pi)) / 2
        out += amp * (pts[i] * (1 - f) + pts[i + 1] * f)
        tot += amp
        amp *= 0.5
        scale /= 2
    return out / tot


def noise2d(w, h, cx, cy, seed):
    r = np.random.default_rng(seed)
    gw, gh = max(2, int(w / cx) + 2), max(2, int(h / cy) + 2)
    a = r.random((gh, gw)).astype(np.float32)
    return np.asarray(Image.fromarray(a, mode="F").resize((w, h), Image.BICUBIC))


# ---------------- 笔触层（局部超采样后合成） ----------------
class Layer:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = int(max(0, x0)), int(max(0, y0))
        self.x1, self.y1 = int(min(W, x1)), int(min(H, y1))
        self.img = Image.new("RGBA", ((self.x1 - self.x0) * S, (self.y1 - self.y0) * S), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return ((x - self.x0) * S, (y - self.y0) * S)

    def line(self, pts, col, w=1.0):
        self.d.line([self.p(x, y) for x, y in pts], fill=col, width=max(1, int(round(w * S))), joint="curve")

    def poly(self, pts, col):
        self.d.polygon([self.p(x, y) for x, y in pts], fill=col)

    def ellipse(self, x, y, rx, ry, col):
        a, b = self.p(x - rx, y - ry)
        c_, d = self.p(x + rx, y + ry)
        self.d.ellipse([a, b, c_, d], fill=col)

    def rect(self, x0, y0, x1, y1, col):
        a, b = self.p(x0, y0)
        c_, d = self.p(x1, y1)
        self.d.rectangle([a, b, c_, d], fill=col)

    def flush(self):
        w, h = self.x1 - self.x0, self.y1 - self.y0
        if w <= 0 or h <= 0:
            return
        im = np.asarray(self.img.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255
        a = im[..., 3:4]
        reg = canvas[self.y0:self.y1, self.x0:self.x1]
        reg[:] = reg * (1 - a) + im[..., :3] * a


def blend(y0, x0, alpha, col):
    h, w = alpha.shape
    reg = canvas[y0:y0 + h, x0:x0 + w]
    a = alpha[..., None]
    reg[:] = reg * (1 - a) + col * a


# ---------------- 背景：天与水 ----------------
HORIZON = 520
yy = np.arange(H, dtype=np.float32)[:, None]
g = np.clip((yy - HORIZON) / (H - HORIZON), 0, 1)
sky = SILK * 1.0 + (MIST - SILK) * np.clip(1 - np.abs(yy - HORIZON) / 260, 0, 1)
water = MIST + (c(186, 172, 128) - MIST) * g
canvas[:] = np.where((yy < HORIZON)[..., None], sky[:, None, :], water[:, None, :])


# ---------------- 山 ----------------
STOPS = np.array([0.00, 0.05, 0.22, 0.42, 0.60, 0.78, 1.00])
COLS = np.array([
    (20, 58, 74),     # 石青深色山脊
    (34, 92, 110),    # 石青
    (48, 118, 108),   # 青绿
    (76, 136, 94),    # 石绿
    (120, 130, 80),   # 绿赭过渡
    (158, 114, 66),   # 赭石
    (170, 130, 84),
], dtype=np.float32) / 255


def ramp(dd):
    return np.stack([np.interp(dd, STOPS, COLS[:, k]) for k in range(3)], axis=-1).astype(np.float32)


def tree(L, x, y, s, rng, fade=0.0):
    a = int(230 * (1 - fade))
    trunk = (58, 42, 30, a)
    kind = rng.random()
    L.line([(x, y), (x + rng.uniform(-0.3, 0.3) * s, y - s)], trunk, 0.35 * max(1, s / 6))
    if kind < 0.45:  # 松：层叠横笔
        for k in range(4):
            yy_ = y - s * (0.45 + 0.17 * k)
            ww = s * (0.45 - 0.08 * k)
            L.line([(x - ww, yy_ + 0.12 * s), (x, yy_), (x + ww, yy_ + 0.12 * s)], (26, 52, 40, a), 0.45 * max(1, s / 7))
    else:  # 点叶树
        col = (30, 62, 44, a) if kind < 0.8 else (48, 82, 56, a)
        for k in range(5):
            L.ellipse(x + rng.uniform(-0.35, 0.35) * s, y - s * rng.uniform(0.6, 1.05),
                      s * 0.28, s * 0.22, col)


def peak(cx, base, h, w, seed, fade=0.0, p=2.1, trees=True, folds=True, flat=False):
    r = np.random.default_rng(seed)
    x0, x1 = max(0, int(cx - 1.7 * w)), min(W, int(cx + 1.7 * w))
    if x1 - x0 < 4:
        return None
    xs = np.arange(x0, x1, dtype=np.float32)
    n = len(xs)
    t = (xs - cx) / w
    skew = r.uniform(-0.3, 0.3)
    t = t * (1 + skew * np.sign(t))
    s = np.exp(-np.abs(t) ** p * 2.6)
    if not flat:
        for _ in range(r.integers(1, 3)):
            sh = r.choice([-1, 1]) * r.uniform(0.35, 0.8)
            s = np.maximum(s, r.uniform(0.35, 0.7) * np.exp(-((t - sh) / r.uniform(0.2, 0.35)) ** 2))
    nz = noise1d(n, w * 0.6, 5, seed) * 0.16 + noise1d(n, w * 0.1, 3, seed + 1) * 0.05
    prof = s * (1 + nz) - 0.04
    top = base - h * prof
    valid = top < base - 1
    if not valid.any():
        return None
    y0 = max(0, int(top[valid].min()) - 2)
    y1 = min(H, int(base) + 1)
    ys = np.arange(y0, y1, dtype=np.float32)[:, None]
    alpha = np.clip(ys - top[None, :] + 0.5, 0, 1) * valid[None, :]
    alpha *= np.clip((base - ys) / (h * 0.14 + 10), 0, 1)
    hh, ww = y1 - y0, n
    streak = 0.6 * noise2d(ww, hh, 7, 90, seed + 2) + 0.4 * noise2d(ww, hh, 16, 40, seed + 5)
    big = noise2d(ww, hh, 60, 60, seed + 3)
    d = (ys - top[None, :]) / h
    if flat:
        d = d * 2.2 + 0.35
    dd = np.clip(d + (streak - 0.5) * 0.30 + (big - 0.5) * 0.18, 0, 1)
    col = ramp(dd)
    shade = 0.90 + 0.16 * noise2d(ww, hh, 5, 45, seed + 4)
    shade *= (1 - 0.10 * np.clip(t, 0, 1.5))[None, :]
    col *= shade[..., None]
    col = col * (1 - fade) + MIST * fade
    blend(y0, x0, alpha, col)

    L = Layer(x0 - 20, y0 - 30, x1 + 20, y1 + 5)
    ink = int(210 * (1 - fade * 0.9))
    idx = np.where(valid & (s > 0.08))[0]
    if len(idx) == 0:
        L.flush()
        return None
    segs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    for sg in segs:
        pts = [(xs[i], top[i]) for i in sg[::2]]
        if len(pts) > 1:
            L.line(pts, (30, 48, 46, ink), 0.9)
    if folds:
        nf = int(w / 18)
        for _ in range(nf):
            i = r.choice(idx)
            xa = xs[i]
            ya = top[i] + 1
            L_ = h * r.uniform(0.12, 0.55) * s[i] ** 0.3
            drift = (xa - cx) / w * 0.7 + r.uniform(-0.2, 0.2)
            pts = []
            for k in range(14):
                u = k / 13
                px, py = xa + drift * L_ * u + 3 * np.sin(u * 5 + i), ya + L_ * u
                j = int(px - x0)
                if not (0 <= j < n and valid[j] and py > top[j] + 1):
                    break  # 皴线不出山体轮廓
                pts.append((px, py))
            if len(pts) < 2:
                continue
            L.line(pts, (24, 58, 58, int(r.uniform(60, 120) * (1 - fade))), 0.7)
        # 苔点
        for _ in range(int(w / 6)):
            i = r.choice(idx)
            L.ellipse(xs[i] + r.uniform(-2, 2), top[i] + r.uniform(0, h * 0.25), 0.9, 0.6,
                      (22, 45, 40, int(150 * (1 - fade))))
    if trees:
        x = xs[idx[0]] + r.uniform(0, 12)
        while x < xs[idx[-1]]:
            i = int(x - x0)
            if valid[i] and 0.08 < s[i] < 0.93:
                tree(L, x, top[i] + 1.5, r.uniform(6, 12) * (1 - 0.5 * fade), r, fade)
            x += r.uniform(7, 22)
    L.flush()
    return xs, top, valid


def group(xa, xb, base, maxh, n, seed, fade=0.0, trees=True, zspread=90, wr=(0.34, 0.55)):
    r = np.random.default_rng(seed)
    peaks = []
    mid, half = (xa + xb) / 2, (xb - xa) / 2
    for _ in range(n):
        z = r.random()
        cx = r.uniform(xa, xb)
        center = 1 - abs((cx - mid) / half)
        h = maxh * (0.3 + 0.7 * center ** 0.8) * r.uniform(0.75, 1.05) * (1 - 0.5 * z)
        w = h * r.uniform(*wr)
        peaks.append((z, cx, base + z * zspread, h, w, int(r.integers(1 << 30))))
    peaks.sort()
    for z, cx, b, h, w, sd in peaks:
        peak(cx, b, h, w, sd, fade=fade * (1 - 0.3 * z), trees=trees)


def mist_band(y, thick, strength, seed):
    band = np.exp(-((yy - y) / thick) ** 2)
    nz = noise2d(W, H, 400, 80, seed)
    a = np.clip(band * strength * (0.5 + nz), 0, 0.9).astype(np.float32)
    blend(0, 0, a, MIST)


# ---------------- 水纹 ----------------
def ripples(seed):
    r = np.random.default_rng(seed)
    for cx0 in range(0, W, 800):
        L = Layer(cx0, HORIZON, cx0 + 800, H)
        y = HORIZON + 30.0
        while y < H:
            g_ = (y - HORIZON) / (H - HORIZON)
            A = 0.8 + 2.2 * g_
            lam = 8 + 12 * g_
            x = cx0 + r.uniform(-20, 0)
            while x < cx0 + 800:
                seg = r.uniform(40, 160)
                pts = []
                u = 0.0
                while u <= seg:
                    pts.append((x + u, y - A * abs(np.sin(np.pi * (x + u) / lam))))
                    u += 1.5
                L.line(pts, (92, 104, 96, int(35 + 45 * g_)), 0.45 + 0.35 * g_)
                x += seg + r.uniform(4, 40)
            y += 4 + 11 * g_ + r.uniform(-1, 1)
        L.flush()


# ---------------- 建筑、桥、舟 ----------------
def house(L, x, y, s, rng):
    wall = (214, 204, 178, 245)
    roof = (62, 66, 72, 250)
    w = s * rng.uniform(1.2, 2.0)
    L.rect(x - w / 2, y - s * 0.7, x + w / 2, y, wall)
    L.line([(x - w / 2, y - s * 0.7), (x - w / 2, y), (x + w / 2, y), (x + w / 2, y - s * 0.7)], (60, 50, 40, 200), 0.3)
    L.poly([(x - w / 2 - s * 0.35, y - s * 0.62), (x - w / 2 + s * 0.1, y - s * 1.15),
            (x + w / 2 - s * 0.1, y - s * 1.15), (x + w / 2 + s * 0.35, y - s * 0.62)], roof)


def village(x, y, n, s, seed, spread=60):
    r = np.random.default_rng(seed)
    L = Layer(x - spread - 40, y - spread - 40, x + spread + 40, y + 20)
    pts = sorted([(y - r.uniform(0, spread * 0.4), x + r.uniform(-spread, spread)) for _ in range(n)])
    for py, px in pts:
        house(L, px, py, s * r.uniform(0.8, 1.2), r)
    for _ in range(n * 2):
        tree(L, x + r.uniform(-spread, spread), y + r.uniform(-3, 4), r.uniform(8, 15), r)
    L.flush()


def bridge(xa, xb, y, seed):
    r = np.random.default_rng(seed)
    L = Layer(xa - 20, y - 90, xb + 20, y + 40)
    # 桥柱
    x = xa
    while x <= xb:
        L.line([(x, y), (x, y + 22)], (70, 52, 38, 220), 0.9)
        x += 14
    L.rect(xa, y - 3, xb, y + 2, (120, 86, 58, 255))
    L.line([(xa, y - 7), (xb, y - 7)], (70, 52, 38, 230), 0.6)
    x = xa
    while x <= xb:
        L.line([(x, y - 7), (x, y - 3)], (70, 52, 38, 200), 0.5)
        x += 7
    # 桥心楼阁（两层）
    m = (xa + xb) / 2
    for k, (bw, bh) in enumerate([(46, 20), (32, 18)]):
        yb = y - 3 - k * 26
        L.rect(m - bw / 2 + 4, yb - bh, m + bw / 2 - 4, yb, (208, 196, 170, 255))
        for px in np.linspace(m - bw / 2 + 4, m + bw / 2 - 4, 5):
            L.line([(px, yb - bh), (px, yb)], (140, 60, 40, 230), 0.8)
        L.poly([(m - bw / 2 - 10, yb - bh + 2), (m - bw / 2 + 2, yb - bh - 10),
                (m + bw / 2 - 2, yb - bh - 10), (m + bw / 2 + 10, yb - bh + 2)], (58, 62, 70, 255))
    L.line([(m, y - 72), (m, y - 80)], (58, 62, 70, 255), 1.2)
    # 倒影
    L.flush()


def boat(x, y, s, seed, sail=False):
    r = np.random.default_rng(seed)
    L = Layer(x - 3 * s, y - 5 * s, x + 3 * s, y + s)
    L.poly([(x - 2 * s, y - 0.4 * s), (x + 2 * s, y - 0.5 * s), (x + 1.4 * s, y + 0.25 * s), (x - 1.5 * s, y + 0.25 * s)],
           (96, 70, 48, 240))
    L.rect(x - 0.6 * s, y - 1.0 * s, x + 0.5 * s, y - 0.4 * s, (70, 66, 60, 230))
    L.ellipse(x + 1.3 * s, y - 0.9 * s, 0.22 * s, 0.22 * s, (40, 36, 34, 230))
    L.line([(x + 1.3 * s, y - 0.7 * s), (x + 1.35 * s, y - 0.3 * s)], (200, 190, 170, 230), 0.25 * s)
    if sail:
        L.line([(x, y - 0.4 * s), (x, y - 4 * s)], (60, 45, 35, 230), 0.25 * s)
        L.poly([(x + 0.1 * s, y - 3.8 * s), (x + 1.6 * s, y - 3.4 * s), (x + 1.4 * s, y - 1.2 * s), (x + 0.1 * s, y - 1.0 * s)],
               (212, 200, 172, 220))
    else:
        L.line([(x - 1.8 * s, y - 0.3 * s), (x - 3 * s, y + 0.8 * s)], (60, 45, 35, 220), 0.15 * s)
    L.flush()


def waterfall(x, ytop, ybot, wdt, seed):
    r = np.random.default_rng(seed)
    col = canvas[int(ytop):int(ybot), int(x)]
    on = np.where(col[:, 1] > col[:, 0] + 0.04)[0]  # 找到山体（偏青绿）起点，瀑布从山里流出
    if len(on) == 0:
        return
    ytop = ytop + on[0] + 35
    if ybot - ytop < 60:
        return
    ww = int(wdt * 3)
    xs_ = np.arange(-ww, ww + 1, dtype=np.float32)
    ys_ = np.arange(int(ytop), int(ybot), dtype=np.float32)[:, None]
    wig = noise1d(len(ys_), 40, 3, seed)[:, None] * wdt * 0.6
    a = np.exp(-((xs_[None, :] - wig) / wdt) ** 2) * 0.85
    a *= np.clip((ys_ - ytop) / 20, 0, 1) * np.clip((ybot - ys_) / 40, 0, 1)
    a *= 0.7 + 0.3 * noise2d(len(xs_), len(ys_), 2, 25, seed)
    blend(int(ytop), int(x - ww), a.astype(np.float32), c(228, 222, 204))


# ================= 构图 =================
print("far range")
far = np.random.default_rng(11)
for cx in np.arange(-100, W + 200, 140):
    peak(cx + far.uniform(-60, 60), HORIZON + far.uniform(20, 45), far.uniform(50, 170), far.uniform(70, 130),
         int(far.integers(1 << 30)), fade=0.62, trees=False, folds=False)
mist_band(HORIZON + 20, 28, 0.55, 5)

print("ripples")
ripples(3)

print("mid groups")
group(1450, 2450, 780, 430, 12, 101, fade=0.25)
group(4550, 5500, 800, 470, 9, 102, fade=0.25)
mist_band(790, 22, 0.3, 6)

print("main groups")
group(80, 1350, 940, 780, 18, 201)
group(2450, 4000, 990, 930, 22, 202)
group(5450, 6380, 960, 800, 17, 203)

waterfall(3040, 470, 780, 3.2, 1)
waterfall(3470, 560, 830, 2.6, 2)
waterfall(720, 520, 760, 2.4, 3)
waterfall(5880, 470, 760, 2.8, 4)
mist_band(960, 30, 0.35, 7)

print("foreground banks")
fg = np.random.default_rng(31)
for xa, xb in [(0, 700), (1300, 2350), (3700, 4100), (4900, 5600), (6000, 6400)]:
    for _ in range(int((xb - xa) / 150) + 1):
        peak(fg.uniform(xa, xb), H + 10, fg.uniform(60, 160), fg.uniform(120, 260), int(fg.integers(1 << 30)),
             p=3.2, flat=True, trees=True)

print("villages, bridge, boats")
bridge(4060, 4560, 878, 1)
for x, y, n, s in [(520, 905, 6, 11), (1180, 890, 4, 10), (1700, 765, 5, 8), (2200, 1060, 6, 13),
                   (2800, 960, 5, 12), (3600, 975, 7, 12), (4000, 1072, 4, 13), (4800, 800, 4, 8),
                   (5300, 1065, 5, 13), (5650, 945, 6, 12), (6200, 930, 4, 11)]:
    village(x, y, n, s, x)
bt = np.random.default_rng(41)
for x, y, s, sail in [(1350, 700, 5, True), (2420, 830, 6, False), (2380, 640, 4, True), (4300, 700, 4, True),
                      (4720, 960, 7, False), (4450, 1000, 7, False), (5150, 690, 4, False), (900, 1000, 7, False),
                      (1950, 880, 6, True), (5500, 820, 5, False), (3900, 760, 4, False)]:
    boat(x, y, s, int(bt.integers(1 << 30)), sail)

# ---------------- 做旧绢本 ----------------
print("aging")
xx = np.arange(W, dtype=np.float32)[None, :]
tex = (noise2d(W, H, 300, 300, 91) - 0.5) * 0.10 + (noise2d(W, H, 40, 40, 92) - 0.5) * 0.05
grain = (np.random.default_rng(93).random((H, W), dtype=np.float32) - 0.5) * 0.05
weave = 0.012 * np.sin(xx * 2.1) + 0.012 * np.sin(yy * 2.3)
vig = 1 - 0.18 * (np.abs(yy - H / 2) / (H / 2)) ** 3 - 0.10 * (np.abs(xx - W / 2) / (W / 2)) ** 4
canvas *= (1 + tex + grain + weave)[..., None] * vig[..., None]
# 整体压暗偏黄，模拟年久
canvas[:] = canvas * c(242, 232, 214) * 1.02
stain = noise2d(W, H, 700, 500, 94)
canvas *= (1 - 0.08 * np.clip(stain - 0.6, 0, 1) * 2.5)[..., None]
img = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))

# ---------------- 装裱、题签、印章 ----------------
BORDER = 60
full = Image.new("RGB", (W + 2 * BORDER, H + 2 * BORDER), (92, 64, 44))
fd = ImageDraw.Draw(full)
fd.rectangle([BORDER - 10, BORDER - 10, W + BORDER + 9, H + BORDER + 9], fill=(170, 150, 110))
full.paste(img, (BORDER, BORDER))
d = ImageDraw.Draw(full)

ft = ImageFont.truetype(FONT, 56, index=TC_REG)
title = "千里江山圖"
tx, ty = W + BORDER - 110, BORDER + 60
for i, ch in enumerate(title):
    d.text((tx, ty + i * 66), ch, font=ft, fill=(38, 30, 24))


def seal(x, y, size, text, white=True):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(im)
    red = (172, 40, 32, 225)
    f = ImageFont.truetype(FONT, int(size * 0.4), index=TC_BOLD)
    if white:  # 白文印
        sd.rectangle([0, 0, size - 1, size - 1], fill=red)
        tc = (0, 0, 0, 0)
    else:  # 朱文印
        sd.rectangle([2, 2, size - 3, size - 3], outline=red, width=max(2, size // 22))
        tc = red
    chars = list(text)
    order = [(1, 0), (1, 1), (0, 0), (0, 1)]  # 右起竖读
    for ch, (col, row) in zip(chars, order):
        cx_ = size * (0.27 + 0.46 * col)
        cy_ = size * (0.27 + 0.46 * row)
        sd.text((cx_, cy_), ch, font=f, fill=tc, anchor="mm")
    if white:
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.rectangle([0, 0, size - 1, size - 1], fill=225)
        for ch, (col, row) in zip(chars, order):
            md.text((size * (0.27 + 0.46 * col), size * (0.27 + 0.46 * row)), ch, font=f, fill=0, anchor="mm")
        im = Image.new("RGBA", (size, size), red[:3] + (0,))
        im.putalpha(mask)
    # 印泥斑驳
    a = np.asarray(im).copy()
    rr = np.random.default_rng(size + x)
    a[..., 3] = (a[..., 3] * (0.75 + 0.25 * rr.random((size, size)))).astype(np.uint8)
    im = Image.fromarray(a)
    full.alpha_composite(im, (x, y)) if full.mode == "RGBA" else full.paste(im, (x, y), im)


seal(tx - 4, ty + len(title) * 66 + 20, 64, "千里江山", white=True)
seal(BORDER + 40, BORDER + H - 150, 88, "宣和御覽", white=False)
seal(BORDER + W - 260, BORDER + H - 130, 76, "乾隆御覽", white=True)
seal(BORDER + 3200, BORDER + 40, 56, "緝熙殿寶", white=False)

full.save(OUT, optimize=True)
full.resize((full.width // 4, full.height // 4), Image.LANCZOS).save(OUT.replace(".png", "_preview.png"))
print("saved", OUT)
