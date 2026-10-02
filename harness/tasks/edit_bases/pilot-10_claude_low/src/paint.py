"""中国水墨画：月下孤舟 —— 纯代码程序化绘制 (numpy + scipy + pillow)。"""
import os
import numpy as np
from scipy import ndimage as ndi
from PIL import Image, ImageDraw, ImageFont

W, H = 1536, 1024
rng = np.random.default_rng(20261001)
YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "out", "final.png")


# ---------------------------------------------------------------- 噪声工具
def value_noise(h, w, cell, seed):
    r = np.random.default_rng(seed)
    gh, gw = h // cell + 3, w // cell + 3
    g = r.random((gh, gw)).astype(np.float32)
    ys = np.arange(h, dtype=np.float32) / cell
    xs = np.arange(w, dtype=np.float32) / cell
    return ndi.map_coordinates(g, np.meshgrid(ys, xs, indexing="ij"), order=3, mode="reflect")


def fbm(h, w, base, octaves, seed, gain=0.5):
    out = np.zeros((h, w), np.float32)
    amp, tot, cell = 1.0, 0.0, base
    for i in range(octaves):
        out += amp * value_noise(h, w, max(2, int(cell)), seed + i * 17)
        tot += amp
        amp *= gain
        cell /= 2
    return out / tot


def fbm1d(n, base, octaves, seed, gain=0.55):
    r = np.random.default_rng(seed)
    out = np.zeros(n, np.float32)
    amp, tot, cell = 1.0, 0.0, base
    x = np.arange(n, dtype=np.float32)
    for i in range(octaves):
        k = int(n / cell) + 4
        g = r.random(k).astype(np.float32)
        out += amp * np.interp(x / cell, np.arange(k), g)
        tot += amp
        amp *= gain
        cell /= 2
    out /= tot
    return ndi.gaussian_filter1d(out, 1.5)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- 宣纸
paper_noise = fbm(H, W, 256, 6, 1)
fiber = ndi.gaussian_filter(rng.random((H, W)).astype(np.float32), (0.6, 3.0))
fiber2 = ndi.gaussian_filter(rng.random((H, W)).astype(np.float32), (3.0, 0.6))
fib = (fiber - fiber.mean()) * 6 + (fiber2 - fiber2.mean()) * 5
paper = np.zeros((H, W, 3), np.float32)
base_col = np.array([236, 226, 204], np.float32) / 255
for c in range(3):
    paper[..., c] = base_col[c] + (paper_noise - 0.5) * 0.05 + fib * 0.02
# 旧纸边缘泛黄
dx = (XX - W / 2) / (W / 2)
dy = (YY - H / 2) / (H / 2)
vig = np.clip(dx**2 * 0.6 + dy**2 * 0.8, 0, 1.5)
paper[..., 0] -= vig * 0.045
paper[..., 1] -= vig * 0.065
paper[..., 2] -= vig * 0.10

# ink: 墨量 0..1 累积（以吸收率叠加）
ink = np.zeros((H, W), np.float32)


def lay(alpha):
    """把一层墨叠加到画面（多次叠加类似积墨）。"""
    global ink
    alpha = np.clip(alpha, 0, 1)
    ink = 1 - (1 - ink) * (1 - alpha)


def bleed(mask, sigma, seed, amt=0.5):
    """墨在宣纸上的晕染：模糊 + 纸纹扰动边缘。"""
    n = fbm(H, W, 48, 4, seed)
    b = ndi.gaussian_filter(mask, sigma)
    return np.clip(b * (1 + (n - 0.5) * amt * 2), 0, 1)


# ---------------------------------------------------------------- 月亮与夜空淡墨
MX, MY, MR = 1090, 230, 92
dist = np.hypot(XX - MX, YY - MY)
sky_wash = fbm(H, W, 420, 3, 7)
# 天空：上部淡墨渲染，月亮周围留白（烘云托月）
sky = 0.34 * smooth(0.0, 1.0, 1 - YY / (H * 0.6)) ** 1.3 + 0.06
sky *= 0.82 + 0.36 * sky_wash
halo = smooth(MR * 0.98, MR * 3.2, dist)
sky *= halo
sky *= smooth(H * 0.62, H * 0.30, YY)  # 渐隐入水雾
lay(bleed(sky, 8, 11, 0.12))
# 月轮轻微的边线淡墨环（留白的月）
ring = np.exp(-((dist - MR) / 3.0) ** 2) * 0.10
lay(ring * (0.6 + 0.8 * fbm(H, W, 30, 3, 13)))
# 云带掠过月下
for i, (cy, cx, sx, sy, a) in enumerate([(300, 1010, 300, 14, 0.18), (178, 1230, 220, 10, 0.12), (340, 820, 260, 9, 0.09)]):
    e = np.exp(-(((XX - cx) / sx) ** 2) - (((YY - cy) / sy) ** 2))
    cloud = e * (0.4 + 1.2 * fbm(H, W, 60, 4, 30 + i))
    lay(bleed(np.clip(cloud, 0, 1) * a, 3, 40 + i, 0.6))

# ---------------------------------------------------------------- 远山 / 中山
def mountain(base_y, amp, base_len, seed, darkness, x_env=None, fade=160, texture=1.0):
    xs = np.arange(W, dtype=np.float32)
    ridge = fbm1d(W, base_len, 6, seed)
    ridge = (ridge - ridge.min()) / (ridge.max() - ridge.min())
    if x_env is not None:
        ridge = ridge * x_env(xs)
    top = base_y - ridge * amp
    d = YY - top[None, :]
    body = smooth(-1.5, 2.0, d)
    # 山体：顶部浓，向下淡入雾中
    grad = np.exp(-np.clip(d, 0, None) / fade)
    # 皴擦纹理（竖向笔触）
    tex = fbm(H, W, 40, 4, seed + 100)
    streak = ndi.gaussian_filter(rng.random((H, W)).astype(np.float32), (9, 1.2))
    streak = (streak - streak.mean()) / (streak.std() + 1e-6)
    t = 0.65 + 0.5 * tex + 0.12 * streak * texture
    # 峰顶轮廓线略浓（勾勒）
    edge = np.exp(-np.clip(d, 0, None) / 6.0) * 0.35
    m = body * (grad * t + edge) * darkness
    return bleed(np.clip(m, 0, 1), 1.6, seed + 200, 0.5)


WATER_Y = 615
mtn = np.zeros((H, W), np.float32)


def lay_m(a):
    global mtn
    mtn = 1 - (1 - mtn) * (1 - np.clip(a, 0, 1))


# 最远的山：极淡
lay_m(mountain(560, 170, 420, 51, 0.16, lambda x: 0.35 + 0.65 * np.exp(-((x - 300) / 380) ** 2) + 0.5 * np.exp(-((x - 1350) / 260) ** 2), fade=90))
# 左侧主山：较浓
lay_m(mountain(600, 360, 360, 77, 0.42,
             lambda x: np.clip(np.exp(-((x - 180) / 330) ** 2) * 1.0 + 0.08 * np.exp(-((x - 700) / 200) ** 2), 0, 1), fade=120))
# 右侧低矮远渚
lay_m(mountain(612, 70, 200, 93, 0.28, lambda x: smooth(1050, 1300, x) * (0.6 + 0.4 * smooth(1300, 1536, x)), fade=40))
# 山脚隐入水雾，不越过水岸
mtn *= smooth(WATER_Y + 1, WATER_Y - 45, YY)
lay(mtn)
# 山的倒影：上下翻转、横向模糊、极淡
mref = np.roll(mtn[::-1, :], 2 * WATER_Y - H, axis=0)
mref = ndi.gaussian_filter(mref, (4, 10)) * smooth(WATER_Y + 140, WATER_Y, YY) * (YY > WATER_Y)
lay(mref * 0.35)
# 水天交界的淡淡雾带
lay(np.exp(-((YY - WATER_Y) / 6.0) ** 2) * 0.05 * (0.5 + fbm(H, W, 90, 3, 95)))

# ---------------------------------------------------------------- 水面（大量留白 + 几笔横波）
def stroke_line(cx, cy, length, thick, alpha, seed, taper=0.6):
    """一笔横向干笔：两端尖，中段有飞白。"""
    r = np.random.default_rng(seed)
    x0, x1 = int(cx - length / 2) - 4, int(cx + length / 2) + 4
    y0, y1 = int(cy - thick * 3) - 4, int(cy + thick * 3) + 4
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return
    sx = XX[y0:y1, x0:x1]
    sy = YY[y0:y1, x0:x1]
    u = (sx - (cx - length / 2)) / length
    wob = np.sin(u * np.pi * r.uniform(1, 3) + r.uniform(0, 6)) * thick * 0.6
    prof = np.clip(np.sin(np.clip(u, 0, 1) * np.pi), 0, 1) ** taper
    th = thick * prof + 0.2
    d = np.abs(sy - cy - wob) / th
    core = smooth(1.2, 0.6, d) * (u > 0) * (u < 1)
    dry = ndi.gaussian_filter(r.random(core.shape).astype(np.float32), (0.5, 6))
    dry = smooth(0.38, 0.55, dry)
    a = core * alpha * (0.35 + 0.65 * dry)
    patch = np.zeros((H, W), np.float32)
    patch[y0:y1, x0:x1] = a
    lay(patch)


# 月影：水中断续的亮带——在淡墨水波中留白
for i in range(60):
    y = WATER_Y + 10 + rng.uniform(0, 380) ** 1.0
    spread = 30 + (y - WATER_Y) * 0.35
    x = MX + rng.normal(0, spread * 1.6)
    if abs(x - MX) < spread * 0.6 and rng.random() < 0.85:
        continue  # 月影处留白
    L = rng.uniform(40, 200) * (0.5 + (y - WATER_Y) / 400)
    stroke_line(x, y, L, rng.uniform(0.6, 1.6) * (0.6 + (y - WATER_Y) / 300), rng.uniform(0.10, 0.28), 1000 + i)

# 水面极淡的整体渲染，让月影带显得更亮
water = 0.07 * (0.6 + 0.8 * fbm(H, W, 120, 4, 300)) * smooth(WATER_Y - 5, WATER_Y + 40, YY)
moon_path = np.exp(-((XX - MX) / (40 + np.clip(YY - WATER_Y, 0, None) * 0.25)) ** 2)
water *= 1 - 0.9 * moon_path
lay(bleed(water, 3, 301, 0.3))

# 月影中的几笔淡银色短横（用极淡墨勾月影边）
for i in range(14):
    y = WATER_Y + 20 + i * 22 + rng.uniform(-6, 6)
    w = 26 + i * 6
    for s in (-1, 1):
        stroke_line(MX + s * (w * rng.uniform(0.7, 1.1)), y, rng.uniform(18, 50), 0.9, 0.16, 2000 + i * 2 + (s > 0))

# ---------------------------------------------------------------- 孤舟与蓑笠翁
boat = Image.new("L", (W, H), 0)
bd = ImageDraw.Draw(boat)
BX, BY = 760, 735  # 船中心吃水线
S = 1.0
# 船身：弯月形
hull_top = []
hull_bot = []
for t in np.linspace(-1, 1, 80):
    x = BX + t * 150 * S
    yt = BY - 10 * S - (t ** 4) * 18 * S + t * 4  # 两端上翘
    yb = BY + 9 * S * (1 - t ** 2) ** 0.7 - (t ** 4) * 14 * S
    hull_top.append((x, yt))
    hull_bot.append((x, yb))
bd.polygon(hull_top + hull_bot[::-1], fill=255)
# 船篷（乌篷）
cab = []
for t in np.linspace(0, np.pi, 40):
    cab.append((BX + 10 + np.cos(t) * 58, BY - 12 - np.sin(t) * 34))
bd.polygon(cab, fill=150)
# 渔翁：蓑衣坐姿 + 斗笠
fx, fy = BX - 85, BY - 12
bd.polygon([(fx - 15, fy), (fx + 17, fy), (fx + 9, fy - 30), (fx - 5, fy - 32)], fill=235)
bd.ellipse([fx - 3, fy - 41, fx + 9, fy - 30], fill=230)
bd.polygon([(fx - 20, fy - 34), (fx + 3, fy - 52), (fx + 26, fy - 34), (fx + 3, fy - 38)], fill=255)
# 钓竿
bd.line([(fx + 10, fy - 22), (fx + 140, fy - 150)], fill=200, width=2)
boat_a = np.asarray(boat, np.float32) / 255
# 船篷用飞白干笔质感
dry = ndi.gaussian_filter(rng.random((H, W)).astype(np.float32), (2.5, 0.6))
cab_mask = (np.abs(boat_a - 150 / 255) < 0.02).astype(np.float32)
boat_a = boat_a * (1 - cab_mask) + cab_mask * (0.55 + 0.4 * smooth(0.45, 0.55, dry))
boat_ink = bleed(ndi.gaussian_filter(boat_a, 0.8), 0.6, 500, 0.25)
lay(np.clip(boat_ink * 0.95, 0, 0.95))
# 钓丝：极细淡线垂入水中
line_img = Image.new("L", (W, H), 0)
ImageDraw.Draw(line_img).line([(fx + 140, fy - 150), (fx + 150, BY + 30)], fill=90, width=1)
lay(ndi.gaussian_filter(np.asarray(line_img, np.float32) / 255, 0.5) * 0.8)
# 船的倒影：模糊、断续
refl = boat_a[::-1, :]
shift = 2 * BY - H
refl = np.roll(refl, shift + 4, axis=0)
refl = ndi.gaussian_filter(refl, (3, 2))
bands = 0.5 + 0.5 * np.sin(YY * 0.9 + fbm(H, W, 30, 2, 600) * 8)
refl *= smooth(BY + 60, BY, YY) * (YY > BY) * bands
lay(refl * 0.30)
# 船边涟漪
for i, (ox, oy, L) in enumerate([(-170, 14, 70), (170, 10, 60), (-120, 26, 110), (130, 24, 90), (0, 40, 180), (-30, 56, 120)]):
    stroke_line(BX + ox, BY + oy, L, 1.2, 0.35, 3000 + i)

# ---------------------------------------------------------------- 前景芦苇（左下角）
def reed(x0, y0, length, angle, width, alpha, seed, leaf=False):
    r = np.random.default_rng(seed)
    n = 60
    t = np.linspace(0, 1, n)
    bend = r.uniform(-0.25, 0.25)
    ang = angle + bend * t ** 2
    xs = x0 + np.cumsum(np.sin(ang)) * length / n
    ys = y0 - np.cumsum(np.cos(ang)) * length / n
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for i in range(n - 1):
        if leaf:
            w = 1.5 * width * np.sin(np.pi * min(1, t[i] * 1.15)) ** 0.7 + 1
        else:
            w = 1.4 * width * (1 - t[i] * 0.75) + 1
        d.line([(xs[i], ys[i]), (xs[i + 1], ys[i + 1])], fill=255, width=max(1, int(round(w))))
    a = np.asarray(img, np.float32) / 255
    a = ndi.gaussian_filter(a, 0.7)
    drym = smooth(0.42, 0.52, ndi.gaussian_filter(r.random((H, W)).astype(np.float32), 1.2))
    a *= 0.7 + 0.3 * drym
    lay(a * alpha)
    return xs[-1], ys[-1]


reed_rng = np.random.default_rng(77)
for i in range(16):
    x0 = reed_rng.uniform(0, 260)
    y0 = H + 10
    L = reed_rng.uniform(220, 420)
    ang = reed_rng.uniform(-0.05, 0.45)
    tx, ty = reed(x0, y0, L, ang, reed_rng.uniform(3.5, 6.0), reed_rng.uniform(0.7, 0.95), 400 + i)
    # 芦花：顶端几点淡墨散点
    if reed_rng.random() < 0.6:
        for k in range(10):
            px = tx + reed_rng.normal(8, 9)
            py = ty + reed_rng.normal(10, 8)
            e = np.exp(-(((XX[int(max(py-12,0)):int(py+12), int(max(px-12,0)):int(px+12)] - px) ** 2 + (YY[int(max(py-12,0)):int(py+12), int(max(px-12,0)):int(px+12)] - py) ** 2) / 10.0))
            patch = np.zeros((H, W), np.float32)
            patch[int(max(py-12,0)):int(py+12), int(max(px-12,0)):int(px+12)] = e * 0.35
            lay(patch)
for i in range(12):
    x0 = reed_rng.uniform(-40, 300)
    reed(x0, H + 10, reed_rng.uniform(150, 330), reed_rng.uniform(-0.4, 0.8), reed_rng.uniform(5, 9),
         reed_rng.uniform(0.4, 0.8), 600 + i, leaf=True)
# 芦苇根部的淡墨渲染
lay(bleed(np.exp(-(((XX - 100) / 220) ** 2) - (((YY - H) / 70) ** 2)) * 0.35, 4, 700, 0.6))

# 右下角淡淡几笔芦苇呼应
for i in range(5):
    reed(reed_rng.uniform(1420, 1530), H + 10, reed_rng.uniform(120, 200), reed_rng.uniform(-0.5, -0.1),
         reed_rng.uniform(2, 3.5), reed_rng.uniform(0.25, 0.4), 800 + i)

# ---------------------------------------------------------------- 合成墨色
# 墨色：浓处偏黑褐，淡处偏青灰
ink = np.clip(ink, 0, 1)
dark = np.array([22, 20, 22], np.float32) / 255
light_tint = np.array([0.93, 0.95, 1.0], np.float32)
img = np.empty_like(paper)
for c in range(3):
    tint = light_tint[c] + (1 - light_tint[c]) * ink
    img[..., c] = paper[..., c] * (1 - ink) * tint + dark[c] * ink
# 纸纹也会让墨色有颗粒感
img *= (1 + fib[..., None] * 0.03 * ink[..., None])
# 月亮：纸上留白再提一点亮
moon = smooth(MR + 1.5, MR - 1.5, dist)
moon_col = np.array([246, 240, 222], np.float32) / 255
img = img * (1 - moon[..., None] * 0.6) + moon_col * moon[..., None] * 0.6
img = np.clip(img, 0, 1)
out = Image.fromarray((img * 255).astype(np.uint8), "RGB")

# ---------------------------------------------------------------- 题款与印章
FONT_DIR = "/usr/share/fonts/opentype/noto/"
font_reg = os.path.join(FONT_DIR, "NotoSerifCJK-Regular.ttc")
font_bold = os.path.join(FONT_DIR, "NotoSerifCJK-Bold.ttc")


def vertical_text(layer, text_cols, x, y, size, font_path, gap=1.08, colgap=1.3):
    d = ImageDraw.Draw(layer)
    f = ImageFont.truetype(font_path, size)
    for ci, col in enumerate(text_cols):
        for i, ch in enumerate(col):
            d.text((x - ci * size * colgap, y + i * size * gap), ch, font=f, fill=255)


txt = Image.new("L", (W, H), 0)
vertical_text(txt, ["月下孤舟", "江天一色无纤尘", "丙午秋日写于灯下"], 1440, 80, 44, font_reg)
ta = np.asarray(txt, np.float32) / 255
# 第一列大字，后两列小字 —— 重绘小字
txt = Image.new("L", (W, H), 0)
vertical_text(txt, ["月下孤舟"], 1452, 70, 52, font_bold)
vertical_text(txt, ["江天一色无纤尘", "皎皎空中孤月轮"], 1386, 80, 30, font_reg, colgap=1.5)
ta = ndi.gaussian_filter(np.asarray(txt, np.float32) / 255, 0.6)
ta *= 0.8 + 0.2 * smooth(0.3, 0.6, fbm(H, W, 6, 2, 900))
arr = np.asarray(out, np.float32) / 255
arr = arr * (1 - ta[..., None] * 0.88) + dark * ta[..., None] * 0.88

# 朱文印章
seal = Image.new("L", (W, H), 0)
sd = ImageDraw.Draw(seal)
sx, sy, ss = 1300, 330, 54
sd.rounded_rectangle([sx, sy, sx + ss, sy + ss], radius=4, fill=255)
fseal = ImageFont.truetype(font_bold, 22)
for (ch, ox, oy) in [("孤", 29, 3), ("舟", 29, 28), ("墨", 4, 3), ("戏", 4, 28)]:
    sd.text((sx + ox, sy + oy - 2), ch, font=fseal, fill=0)
sa = np.asarray(seal, np.float32) / 255
grain = smooth(0.25, 0.45, fbm(H, W, 5, 2, 950))
sa *= 0.75 + 0.25 * grain
red = np.array([178, 42, 36], np.float32) / 255
arr = arr * (1 - sa[..., None] * 0.9) + red * sa[..., None] * 0.9

# 姓名小印于左下
seal2 = Image.new("L", (W, H), 0)
s2 = ImageDraw.Draw(seal2)
qx, qy, qs = 1452, 470, 36
s2.rectangle([qx, qy, qx + qs, qy + qs], outline=255, width=3)
s2.text((qx + 7, qy + 3), "月", font=ImageFont.truetype(font_bold, 22), fill=255)
sa2 = ndi.gaussian_filter(np.asarray(seal2, np.float32) / 255, 0.5) * (0.7 + 0.3 * grain)
arr = arr * (1 - sa2[..., None] * 0.85) + red * sa2[..., None] * 0.85

arr = np.clip(arr, 0, 1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
Image.fromarray((arr * 255).astype(np.uint8), "RGB").save(OUT)
print("saved", os.path.abspath(OUT))
