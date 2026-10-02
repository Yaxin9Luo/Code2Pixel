"""Pixel art: a hero standing before a castle. Drawn at 192x128, upscaled x8."""
import numpy as np
from PIL import Image
import os

W, H, S = 192, 128, 8
rng = np.random.default_rng(7)
img = np.zeros((H, W, 3), np.uint8)

def hx(c):
    c = c.lstrip('#')
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.uint8)

def px(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        img[y, x] = hx(c) if isinstance(c, str) else c

def rect(x0, y0, x1, y1, c):
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, W), min(y1, H)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = hx(c)

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
YY, XX = np.mgrid[0:H, 0:W]
BAY = BAYER[YY % 4, XX % 4]

def dither_pal(t, pal, mask=None):
    """t in [0,1] mapped onto palette with ordered dithering."""
    n = len(pal)
    v = np.clip(t, 0, 1) * (n - 1)
    idx = np.clip(np.floor(v + BAY), 0, n - 1).astype(int)
    P = np.array([hx(c) for c in pal])
    out = P[idx]
    if mask is None:
        img[:] = out
    else:
        img[mask] = out[mask]

# ---------------- sky ----------------
sky = ['#1b1f4a', '#2a2d6a', '#43408c', '#6c4c9e', '#9c5a9c', '#cf6f88', '#ef9370', '#fbbd78', '#ffe0a0']
t = (YY / 92.0) ** 1.1
dither_pal(t, sky)

# stars
for _ in range(45):
    x, y = rng.integers(0, W), rng.integers(0, 28)
    px(x, y, '#fff6d8' if rng.random() < .5 else '#b8b8ff')
for (x, y) in [(20, 8), (120, 5), (170, 12), (75, 14)]:
    px(x, y, '#ffffff'); px(x - 1, y, '#9aa0ff'); px(x + 1, y, '#9aa0ff')
    px(x, y - 1, '#9aa0ff'); px(x, y + 1, '#9aa0ff')

# sun with halo (upper left -> light from left)
sx, sy = 34, 50
d = np.hypot(XX - sx, YY - sy)
halo = (d < 22) & (BAY < np.clip((22 - d) / 14, 0, 1) * 0.6)
img[halo] = (img[halo] * 0.55 + hx('#ffe6a8') * 0.45).astype(np.uint8)
img[d < 11] = hx('#fff1c0')
img[(d < 11) & (d >= 9.5)] = hx('#ffd27a')
img[(d < 6) & (XX < sx) & (YY < sy)] = hx('#fffbe8')

# clouds
def cloud(cx, cy, blobs, light='#f8cfd0', mid='#e6a0b4', dark='#b07aa8'):
    m = np.zeros((H, W), bool)
    for (ox, oy, r) in blobs:
        m |= np.hypot(XX - (cx + ox), (YY - (cy + oy)) * 1.25) < r
    m &= YY <= cy + 3
    img[m] = hx(mid)
    top = m & ~np.roll(m, 2, axis=0)
    hi = m & (YY < cy - 1)
    img[hi] = hx(light)
    low = m & (YY >= cy + 1)
    img[low] = hx(dark)
    img[top & ~hi] = hx(light)

cloud(150, 24, [(0, 0, 7), (8, 1, 6), (-8, 2, 5), (15, 2, 4), (-14, 3, 3)])
cloud(80, 14, [(0, 0, 5), (6, 1, 4), (-6, 1, 4), (11, 2, 3)])
cloud(178, 44, [(0, 0, 4), (6, 1, 3), (-5, 1, 3)])
cloud(12, 30, [(0, 0, 4), (6, 1, 3), (-5, 1, 3)])

# birds
for (bx, by) in [(60, 34), (66, 30), (71, 36)]:
    px(bx - 1, by - 1, '#2a2040'); px(bx, by, '#2a2040'); px(bx + 1, by - 1, '#2a2040')

# ---------------- mountains ----------------
xs = np.arange(W)
far = 62 + 8 * np.sin(xs / 17.0 + 1) + 5 * np.sin(xs / 7.3) + 3 * np.sin(xs / 3.1 + 2)
near = 74 + 5 * np.sin(xs / 11.0 + 3) + 3 * np.sin(xs / 5.7 + 1)
for x in xs:
    y0 = int(far[x])
    img[y0:92, x] = hx('#8a68a8')
    img[y0, x] = hx('#b88ab8')
    # snow-ish highlights on peaks lit from left
    if far[x] < 56:
        img[y0:y0 + 3, x] = hx('#e8c8e0')
for x in xs:
    y0 = int(near[x])
    img[y0:92, x] = hx('#5a4a86')
    img[y0, x] = hx('#7a68a0')
    if x % 2 == 0 and near[x] < near[max(x - 1, 0)]:
        img[y0 + 1, x] = hx('#7a68a0')

# distant tree line
for x in xs:
    h = 3 + int(2 * abs(np.sin(x * 1.7)) + (x % 3 == 0))
    img[86 - h:92, x] = hx('#2e4a4a')

# ---------------- ground ----------------
ground_top = (86 + 1.5 * np.sin(xs / 13.0)).astype(int)
gmask = YY >= ground_top[None, :]
tg = (YY - 84) / 44.0
dither_pal(tg, ['#3f7a3e', '#4d8c40', '#5ea044', '#6db44a', '#7cc450'], gmask)
for x in xs:
    img[ground_top[x], x] = hx('#2f5e36')

# path from gate to foreground
def path_geo(y):
    s = np.clip((y - 88) / 39.0, 0, 1)
    cx = 106 + (58 - 106) * (s ** 1.2) + 4 * np.sin(s * 3.0)
    w = 3 + 17 * s ** 1.1
    return cx, w

pmask = np.zeros((H, W), bool)
for y in range(87, H):
    cx, w = path_geo(y)
    pmask[y, int(cx - w):int(cx + w) + 1] = True
img[pmask] = hx('#d0a872')
tp = (YY - 87) / 40.0
dither_pal(tp * 0.6 + 0.2, ['#b88c5a', '#d0a872', '#e0bc88'], pmask)
edge = pmask & ~(np.roll(pmask, 1, 1) & np.roll(pmask, -1, 1))
img[edge] = hx('#8a6a40')
for _ in range(90):
    y = rng.integers(90, H); cx, w = path_geo(y)
    x = int(cx + rng.uniform(-w + 2, w - 2))
    if pmask[y, x]:
        px(x, y, '#9a7448')
        if y > 105 and pmask[y, x + 1]:
            px(x + 1, y, '#9a7448'); px(x, y - 1, '#f0d4a0')

# grass tufts & flowers
for _ in range(260):
    x, y = rng.integers(0, W), rng.integers(90, H)
    if pmask[y, x] or not gmask[y, x]:
        continue
    if y < 100:
        px(x, y, '#3a7038')
    else:
        px(x, y, '#3a7038'); px(x - 1, y - 1, '#3a7038'); px(x + 1, y - 1, '#3a7038')
        px(x, y - 1, '#8ed060')
for _ in range(55):
    x, y = rng.integers(0, W), rng.integers(98, H)
    if pmask[y, x] or (40 < x < 72 and y > 110):
        continue
    c = ['#ff6080', '#ffe060', '#ffffff', '#a080ff'][rng.integers(0, 4)]
    px(x, y + 1, '#2f6a30'); px(x, y, c)
    if y > 112:
        px(x - 1, y, c); px(x + 1, y, c); px(x, y - 1, c); px(x, y, '#ffd040')

# ---------------- trees ----------------
def tree(cx, base, r):
    rect(cx - 1, base - r - 2, cx + 2, base + 1, '#5a3a24')
    px(cx - 1, base - 2, '#7a5034')
    cy = base - r - 4
    m = np.hypot(XX - cx, (YY - cy) * 1.1) < r
    m |= np.hypot(XX - cx + r * .5, YY - cy - r * .4) < r * .7
    m |= np.hypot(XX - cx - r * .5, YY - cy - r * .4) < r * .7
    img[m] = hx('#2f6a3a')
    hi = m & (np.hypot(XX - cx + r * .35, YY - cy + r * .35) < r * .6)
    img[hi] = hx('#4a9046')
    hh = m & (np.hypot(XX - cx + r * .5, YY - cy + r * .55) < r * .28)
    img[hh] = hx('#6cb456')
    dk = m & (np.hypot(XX - cx - r * .3, YY - cy - r * .5) < r * .75) & ~hi & (BAY > .5)
    img[dk] = hx('#1f4a30')
    ol = np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    img[ol & ~m & (YY < base - 2)] = hx('#173424')

tree(30, 92, 7)
tree(18, 96, 6)
tree(176, 94, 8)
tree(186, 100, 6)

# ---------------- castle ----------------
K = '#1e1830'
STONE = ['#e6dccf', '#c7bcb4', '#a49aa0', '#7c7088']  # light, base, mortar/shade, dark

def stone_block(x0, x1, y0, y1):
    for y in range(y0, y1):
        for x in range(x0, x1):
            row = (y - y0) // 3
            mortar = (y - y0) % 3 == 2 or (x + (row % 2) * 3) % 6 == 0
            rel = (x - x0) / max(x1 - x0 - 1, 1)
            if rel < 0.18:
                c = STONE[0] if not mortar else STONE[1]
            elif rel > 0.78:
                c = STONE[2] if not mortar else STONE[3]
            else:
                c = STONE[1] if not mortar else STONE[2]
            px(x, y, c)
    for y in range(y0, y1):
        px(x0, y, K); px(x1 - 1, y, K)

def merlons(x0, x1, y):
    rect(x0, y, x1, y + 1, K)
    x = x0
    while x + 3 <= x1:
        stone_block(x, x + 3, y - 3, y + 1)
        rect(x, y - 4, x + 3, y - 3, K)
        px(x + 1, y - 3, STONE[0])
        x += 5

def roof(x0, x1, ybase, h, light, mid, dark):
    cx = (x0 + x1 - 1) / 2.0
    half = (x1 - x0) / 2.0 + 2
    apex = ybase - h
    for y in range(apex, ybase + 1):
        hw = half * (y - apex) / h
        for x in range(int(np.floor(cx - hw)), int(np.ceil(cx + hw)) + 1):
            if abs(x - cx) > hw + 0.5:
                continue
            band = (y - apex) % 3 == 2
            c = light if x < cx - hw * 0.3 else (mid if x < cx + hw * 0.4 else dark)
            if band:
                c = dark if c != dark else K
            px(x, y, c)
        # outline
        px(int(np.floor(cx - hw)) - 1 if hw > 0 else int(cx) - 1, y, K)
        px(int(np.ceil(cx + hw)) + 1 if hw > 0 else int(cx) + 1, y, K)
    rect(int(cx - half) - 1, ybase + 1, int(cx + half) + 3, ybase + 2, K)
    return int(round(cx)), apex

def flag(x, apex, col, dcol):
    for y in range(apex - 8, apex):
        px(x, y, '#3a3040')
    px(x, apex - 9, '#ffd040')
    shape = [(0, 6), (0, 6), (1, 7), (1, 6), (0, 4)]
    for i, (a, b) in enumerate(shape):
        for j in range(a, b):
            px(x + 1 + j, apex - 8 + i, col if i < 3 else dcol)

def window(x, y, w=2, h=4, lit=True):
    rect(x - 1, y - 1, x + w + 1, y + h + 1, K)
    rect(x, y, x + w, y + h, '#ffd060' if lit else '#2a2440')
    if lit:
        rect(x, y + h - 1, x + w, y + h, '#ff9a40')
        px(x, y, '#fff0a0')

# back wall with crenellations
stone_block(60, 153, 62, 91)
merlons(60, 153, 62)

# keep
stone_block(86, 127, 36, 72)
merlons(86, 127, 36)
window(93, 46, 3, 5); window(117, 46, 3, 5)
# central tower
stone_block(97, 116, 20, 40)
cx, ap = roof(97, 116, 20, 16, '#5a7ad0', '#3a56a8', '#28367a')
flag(cx, ap, '#e83a4a', '#a82034')
window(105, 26, 3, 6)
# round rose window on keep
for (dx, dy) in [(0, -1), (-1, 0), (0, 0), (1, 0), (0, 1)]:
    px(106 + dx, 50 + dy, '#ff9a40')
for (dx, dy) in [(-1, -2), (0, -2), (1, -2), (-2, -1), (2, -1), (-2, 0), (2, 0), (-2, 1), (2, 1), (-1, 2), (0, 2), (1, 2)]:
    px(106 + dx, 50 + dy, K)

# side towers
for (x0, x1) in [(48, 68), (145, 165)]:
    stone_block(x0, x1, 44, 92)
    cx, ap = roof(x0, x1, 44, 20, '#e8605a', '#c03a3e', '#86243a')
    flag(cx, ap, '#3a6ae0', '#2442a0')
    window(cx - 1, 54, 2, 5); window(cx - 1, 70, 2, 4)
    # arrow slit
    rect(cx, 81, cx + 1, 86, K)

# small inner turrets on wall
for (x0, x1) in [(74, 82), (131, 139)]:
    stone_block(x0, x1, 52, 63)
    cx, ap = roof(x0, x1, 52, 9, '#5a7ad0', '#3a56a8', '#28367a')

# wall windows
for x in (76, 135):
    window(x, 70, 2, 3)

# gate
gx0, gx1, gtop = 97, 116, 70
gcx = (gx0 + gx1 - 1) / 2
r = (gx1 - gx0) / 2
for y in range(gtop - 2, 92):
    for x in range(gx0 - 2, gx1 + 2):
        dyy = y - (gtop + r)
        rr = np.hypot(x - gcx, dyy)
        inside = (abs(x - gcx) <= r - 0.5) and (y >= gtop + r or rr <= r - 0.5)
        frame = (abs(x - gcx) <= r + 1.5) and (y >= gtop + r or rr <= r + 1.5)
        if inside:
            px(x, y, '#3a2418')
            # wooden door planks + portcullis
            if (x - gx0) % 4 == 0:
                px(x, y, '#24140e')
            if y > 82:
                px(x, y, '#7a4a2a' if (x - gx0) % 3 else '#5a3420')
            if (x - gx0) % 4 == 2 and y <= 82 or (y - gtop) % 4 == 0 and y <= 82:
                px(x, y, '#6a6070')
        elif frame:
            px(x, y, '#e6dccf' if x < gcx else '#8a7e8e')
for x in range(gx0 - 3, gx1 + 3):
    pass
# keystone
rect(int(gcx) - 1, gtop - 3, int(gcx) + 2, gtop, '#fff4e0')
# torches beside gate
for tx in (gx0 - 5, gx1 + 4):
    rect(tx, 78, tx + 1, 82, '#4a3020')
    px(tx, 77, '#ffb040'); px(tx, 76, '#ffe080'); px(tx - 1, 77, '#ff7a30'); px(tx + 1, 77, '#ff7a30')

# banners on wall
for bx in (88, 122):
    rect(bx, 74, bx + 4, 83, '#c03a3e')
    rect(bx + 1, 76, bx + 3, 79, '#ffd040')
    px(bx, 83, '#c03a3e'); px(bx + 3, 83, '#c03a3e')
    rect(bx, 83, bx + 4, 84, K); px(bx + 1, 84, '#86243a'); px(bx + 2, 84, '#86243a')
    rect(bx - 1, 73, bx + 5, 74, '#3a3040')

# ground contact shading at castle base
for x in range(46, 168):
    if not pmask[91, x]:
        px(x, 91, '#2f5e36'); px(x, 92, '#3f7a3e')

# ---------------- hero (seen from behind, facing the castle) ----------------
HERO = [
    "       KKKKKK",
    "      KHHHHHHK",
    "     KHHhHHhHHK",
    "     KHHHHHHHHK",
    "     KHhHHHHhHK",
    "     KHHHhHHHHK",
    "      KHSHHSHK",
    "       KSSSSK",
    "  KAAKCCCCCCCCKAAK",
    " KAAAKCCCCCCCCKAAAK",
    " KaAaKCCCcCCCCKaAaK",
    " KaaKCCCCCCCCCCKaaK",
    " KaaKCCCcCCCcCCKaaK",
    " KaaKCCCCCCCCCCKaaK",
    " KBBKCCCcCCCcCCKBBK",
    " KBBKCCCcCCCcCCKBBK",
    "  KCCCCcCCCCcCCCCK",
    "  KCCCCcCCCCcCCCCK",
    "  KCCCCcCCCCcCCCCK",
    " KCCCCcCCCCCCcCCCCK",
    " KCCCCcCCCCCCcCCCCK",
    " KCcCCCcCCCCcCCCcCK",
    " KcCCCcCCCCCCcCCCcK",
    "  KKKKKKKKKKKKKKKK",
    "     KaaK  KaaK",
    "     KaaK  KaaK",
    "     KaAK  KAaK",
    "     KBBK  KBBK",
    "    KBBBK  KBBBK",
    "    KKKKK  KKKKK",
]
HP = {'K': '#1a1420', 'H': '#8a4b2a', 'h': '#5e3020', 'S': '#f0c090',
      'A': '#d8e0f0', 'a': '#8890a8', 'C': '#c0303a', 'c': '#861c2c', 'B': '#6a4024'}
hx0, hy0 = 48, 92

# shadow
for y in range(hy0 + 28, hy0 + 32):
    for x in range(hx0 - 2, hx0 + 24):
        if ((x - (hx0 + 10)) / 13.0) ** 2 + ((y - (hy0 + 29.5)) / 2.0) ** 2 < 1:
            img[y, x] = (img[y, x] * 0.6).astype(np.uint8)

# sword (held upright in right hand) drawn behind hand first
sxp = hx0 + 16
for y in range(hy0 - 6, hy0 + 13):
    px(sxp, y, '#f4f8ff'); px(sxp + 1, y, '#a8b4cc')
    px(sxp - 1, y, '#1a1420'); px(sxp + 2, y, '#1a1420')
px(sxp, hy0 - 7, '#1a1420'); px(sxp + 1, hy0 - 7, '#1a1420')
px(sxp, hy0 - 6, '#ffffff')
# glint
px(sxp, hy0 - 3, '#ffffff'); px(sxp - 2, hy0 - 3, '#fff6c0'); px(sxp + 3, hy0 - 3, '#fff6c0')
px(sxp, hy0 - 5 + 0, '#ffffff')
# crossguard
rect(sxp - 3, hy0 + 12, sxp + 5, hy0 + 13, '#ffd040')
rect(sxp - 4, hy0 + 11, sxp + 6, hy0 + 12, '#1a1420')
rect(sxp - 4, hy0 + 13, sxp + 6, hy0 + 14, '#1a1420')
px(sxp - 4, hy0 + 12, '#1a1420'); px(sxp + 5, hy0 + 12, '#1a1420')
px(sxp + 3, hy0 + 12, '#c09020'); px(sxp + 4, hy0 + 12, '#c09020')
px(sxp, hy0 + 12, '#4080ff')  # gem

for r_, row in enumerate(HERO):
    for c_, ch in enumerate(row):
        if ch == '.' or ch == ' ':
            continue
        # keep the sword visible where it crosses the arm region
        if hy0 + r_ <= hy0 + 13 and hx0 + c_ in (sxp, sxp + 1) and ch == 'K':
            continue
        px(hx0 + c_, hy0 + r_, HP[ch])

# grip / pommel below hand
for y in (hy0 + 16,):
    px(sxp, y, '#5a3420'); px(sxp + 1, y, '#5a3420')
px(sxp, hy0 + 17, '#ffd040'); px(sxp + 1, hy0 + 17, '#c09020')
px(sxp - 1, hy0 + 16, '#1a1420'); px(sxp + 2, hy0 + 16, '#1a1420')
px(sxp - 1, hy0 + 17, '#1a1420'); px(sxp + 2, hy0 + 17, '#1a1420')
rect(sxp, hy0 + 18, sxp + 2, hy0 + 19, '#1a1420')

# shield on left arm
SH = [
    " KKKKKK ",
    "KAAAAAaK",
    "KA3yy3aK",
    "KAyyyyaK",
    "KA3yy3aK",
    " KAyyaK ",
    "  KAaK  ",
    "   KK   ",
]
SHP = {'K': '#1a1420', 'A': '#d8e0f0', 'a': '#8890a8', 'y': '#2a52b8', '3': '#ffd040'}
for r_, row in enumerate(SH):
    for c_, ch in enumerate(row):
        if ch != ' ':
            px(hx0 - 5 + c_, hy0 + 9 + r_, SHP[ch])
# cape highlight on lit (left) side
for y in range(hy0 + 9, hy0 + 22):
    if img[y, hx0 + 6].tolist() == hx(HP['C']).tolist():
        px(hx0 + 6, y, '#e04a50')
# hair highlight from sun
px(hx0 + 7, hy0 + 1, '#b86a3a'); px(hx0 + 8, hy0 + 1, '#b86a3a'); px(hx0 + 6, hy0 + 2, '#b86a3a')

# ---------------- output ----------------
out = np.repeat(np.repeat(img, S, axis=0), S, axis=1)
os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'out'), exist_ok=True)
Image.fromarray(out).save(os.path.join(os.path.dirname(__file__), '..', 'out', 'final.png'))
print('saved', out.shape)
