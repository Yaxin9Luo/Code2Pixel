# Pixel art: a hero standing before a castle. Drawn at 192x128, upscaled x8 -> 1536x1024.
import numpy as np
from PIL import Image
import random

W, H = 192, 128
rng = random.Random(7)
img = np.zeros((H, W, 3), np.uint8)

def hexc(s):
    s = s.lstrip('#'); return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))

def px(x, y, c):
    if 0 <= x < W and 0 <= y < H:
        img[y, x] = c if isinstance(c, tuple) else hexc(c)

def rect(x0, y0, x1, y1, c):  # inclusive
    c = c if isinstance(c, tuple) else hexc(c)
    x0, x1 = max(0, x0), min(W - 1, x1); y0, y1 = max(0, y0), min(H - 1, y1)
    if x0 <= x1 and y0 <= y1:
        img[y0:y1 + 1, x0:x1 + 1] = c

BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0

# ---------- sky: banded sunset with ordered dithering ----------
sky = [hexc(c) for c in ['#1b1f4b', '#2d2a6b', '#4a3a86', '#7a4a93', '#b55a8a', '#e27a7a', '#f6a76b', '#fcd38a']]
for y in range(H):
    t = min(1.0, y / 78.0) * (len(sky) - 1)
    for x in range(W):
        i = int(t); f = t - i
        if i < len(sky) - 1 and f > BAYER[y % 4, x % 4]:
            i += 1
        img[y, x] = sky[min(i, len(sky) - 1)]

# stars in upper sky
for _ in range(45):
    x, y = rng.randrange(W), rng.randrange(28)
    px(x, y, '#fff6d8' if rng.random() < 0.5 else '#a9b4ff')
for (x, y) in [(20, 8), (150, 12), (100, 5)]:
    for d in (-1, 1):
        px(x + d, y, '#8f94d8'); px(x, y + d, '#8f94d8')
    px(x, y, '#ffffff')

# setting sun behind castle
cx, cy, r = 44, 74, 14
for y in range(cy - r, cy + r + 1):
    for x in range(cx - r, cx + r + 1):
        d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        if d <= r:
            px(x, y, '#fff1b8' if d < r - 3 else '#ffe08a')
        elif d <= r + 3 and BAYER[y % 4, x % 4] < 0.5:
            px(x, y, '#fbc37a')

# clouds
def cloud(x, y, w, light='#f7b3a0', mid='#d97f93', dark='#9b5a8f'):
    rect(x + 3, y, x + w - 4, y, light)
    rect(x + 1, y + 1, x + w - 2, y + 1, light)
    rect(x, y + 2, x + w - 1, y + 2, mid)
    rect(x + 2, y + 3, x + w - 3, y + 3, dark)
cloud(8, 30, 30); cloud(26, 26, 18); cloud(150, 22, 34); cloud(165, 18, 16); cloud(70, 38, 22)
cloud(178, 44, 20)

# ---------- distant mountains ----------
def ridge(base, amp, seed, col, freq):
    r = random.Random(seed); h = base
    ys = []
    for x in range(W):
        h += r.choice([-1, 0, 0, 1]) * amp
        h = max(base - 14, min(base + 4, h))
        ys.append(h)
    for x in range(W):
        rect(x, ys[x], x, H - 1, col)
    return ys
ridge(70, 1, 3, hexc('#6b4a86'), 1)
ridge(78, 1, 11, hexc('#4f3a72'), 1)

# ---------- castle ----------
STONE_L, STONE, STONE_D, STONE_DD = hexc('#c9b8c8'), hexc('#9d8aa6'), hexc('#6f5d80'), hexc('#4a3b5c')
ROOF, ROOF_D, ROOF_L = hexc('#3b5ba8'), hexc('#28407a'), hexc('#5d82cc')
WIN, WIN_G = hexc('#ffd56a'), hexc('#ff9f3a')

def bricks(x0, y0, x1, y1):
    rect(x0, y0, x1, y1, STONE)
    for y in range(y0, y1 + 1):
        row = (y - y0)
        if row % 4 == 3:
            rect(x0, y, x1, y, STONE_D)
        else:
            off = 0 if (row // 4) % 2 == 0 else 4
            for x in range(x0, x1 + 1):
                if (x - x0 + off) % 8 == 7:
                    px(x, y, STONE_D)
    # light on left, shade on right
    rect(x0, y0, x0, y1, STONE_L); rect(x1, y0, x1, y1, STONE_DD)
    rect(x1 - 1, y0, x1 - 1, y1, STONE_D)

def crenel(x0, x1, y):
    for x in range(x0, x1 + 1):
        if ((x - x0) // 3) % 2 == 0:
            rect(x, y - 3, x, y - 1, STONE)
            if (x - x0) % 3 == 0: px(x, y - 3, STONE_L)
            if (x - x0) % 3 == 2: rect(x, y - 3, x, y - 1, STONE_D)
    rect(x0, y, x1, y, STONE_L)

def roof(xc, base, half, height):
    for i in range(height):
        w = int(round(half * (i + 1) / height))
        y = base - height + i + 1
        for x in range(xc - w, xc + w + 1):
            c = ROOF
            if x < xc - w + 2 or x == xc - w // 2 - 1: c = ROOF_L
            if x > xc: c = ROOF_D if x > xc + w // 3 else ROOF
            if i % 3 == 2 and (x + i) % 2 == 0: c = ROOF_D if x > xc else ROOF
            px(x, y, c)
    rect(xc - half - 1, base + 1, xc + half + 1, base + 1, ROOF_D)
    return base - height + 1

def flag(x, ytop, col='#e23b3b', col2='#a8213a'):
    rect(x, ytop - 7, x, ytop, '#3a2a2a')
    for i in range(5):
        rect(x + 1, ytop - 7 + (1 if i >= 3 else 0), x + 1 + i, ytop - 4 + (1 if i >= 3 else 0), col)
    rect(x + 1, ytop - 4, x + 5, ytop - 4, col2)
    px(x, ytop - 8, '#ffd56a')

def window(x, y, h=4, lit=True):
    rect(x, y + 1, x + 1, y + h, WIN if lit else STONE_DD)
    px(x, y, STONE_DD); px(x + 1, y, STONE_DD)
    if lit: px(x, y + h, WIN_G); px(x + 1, y + h, WIN_G)

GROUND_Y = 92
# back keep
bricks(104, 40, 152, GROUND_Y); crenel(104, 152, 40)
tip = roof(128, 30, 10, 0)
# central tall keep tower
bricks(120, 26, 136, 40)
rect(118, 26, 138, 26, STONE_L)
t = roof(128, 25, 10, 14); flag(128, t - 1)
window(127, 30, 5); window(112, 50); window(143, 50); window(122, 48); window(133, 48)
# curtain wall
bricks(84, 62, 172, GROUND_Y); crenel(84, 172, 62)
# side towers
for (x0, x1, top) in [(76, 92, 46), (164, 180, 46)]:
    bricks(x0, top, x1, GROUND_Y)
    rect(x0 - 1, top, x1 + 1, top, STONE_L)
    xc = (x0 + x1) // 2
    t = roof(xc, top - 1, 10, 16); flag(xc, t - 1, '#f0c040', '#b8862a')
    window(xc - 1, top + 6, 5); window(xc - 1, top + 22, 4)
# far small towers
for (x0, x1, top) in [(98, 106, 54), (150, 158, 54)]:
    bricks(x0, top, x1, 62)
    xc = (x0 + x1) // 2
    roof(xc, top - 1, 5, 9)
# gate
gx0, gx1, gy = 120, 136, 72
rect(gx0 - 2, gy - 2, gx1 + 2, GROUND_Y, STONE_DD)
for y in range(gy, GROUND_Y + 1):
    for x in range(gx0, gx1 + 1):
        dx = (x - 128) / 8.5; dy = (y - (gy + 7)) / 7.0
        if y >= gy + 7 or dx * dx + dy * dy <= 1:
            px(x, y, '#2a1d2e')
# portcullis
for x in range(gx0 + 1, gx1, 3):
    for y in range(gy + 1, GROUND_Y - 4):
        if img[y, x].tolist() == list(hexc('#2a1d2e')): px(x, y, '#6a5a4a')
for y in range(gy + 4, GROUND_Y - 4, 3):
    for x in range(gx0, gx1 + 1):
        if img[y, x].tolist() == list(hexc('#2a1d2e')): px(x, y, '#6a5a4a')
# warm glow from gate inside
rect(124, GROUND_Y - 3, 132, GROUND_Y, '#ff9f3a')
rect(126, GROUND_Y - 4, 130, GROUND_Y - 4, '#ffd56a')
# keystone & banners beside gate
rect(127, gy - 3, 129, gy - 2, STONE_L)
for bx in (110, 142):
    rect(bx, 66, bx + 4, 76, '#c0303a'); rect(bx + 1, 77, bx + 3, 77, '#c0303a'); px(bx + 2, 78, '#c0303a')
    rect(bx + 1, 69, bx + 3, 71, '#ffd56a'); px(bx + 2, 70, '#c0303a')
    rect(bx, 66, bx + 4, 66, '#7a1c28')

# ---------- ground ----------
G1, G2, G3, G4 = hexc('#5aa84a'), hexc('#3f8a3e'), hexc('#2e6a3a'), hexc('#7cc45a')
for y in range(GROUND_Y + 1, H):
    for x in range(W):
        t = (y - GROUND_Y) / (H - GROUND_Y)
        c = G2 if (t < 0.15 and BAYER[y % 4, x % 4] < 0.6) else G1
        if t > 0.55 and BAYER[y % 4, x % 4] < (t - 0.55) * 1.5: c = G2
        img[y, x] = c
# grass tufts
for _ in range(140):
    x, y = rng.randrange(W), rng.randrange(GROUND_Y + 3, H)
    px(x, y, G4); px(x, y - 1, G4) if rng.random() < 0.5 else None; px(x + 1, y, G3)
# path from gate widening to foreground
PATH, PATH_D, PATH_L = hexc('#d8b07a'), hexc('#b08658'), hexc('#ecd09a')
for y in range(GROUND_Y + 1, H):
    t = (y - GROUND_Y) / (H - GROUND_Y)
    hw = 8 + t * 34
    c = 128 - t * 42
    for x in range(int(c - hw), int(c + hw) + 1):
        e = min(x - (c - hw), (c + hw) - x)
        col = PATH_D if e < 1.5 else PATH
        if 0 <= x < W: img[y, x] = col
for _ in range(70):
    t = rng.random(); y = int(GROUND_Y + 2 + t * (H - GROUND_Y - 3))
    tt = (y - GROUND_Y) / (H - GROUND_Y); c = 128 - tt * 42; hw = 8 + tt * 34
    x = int(c + rng.uniform(-hw + 3, hw - 3))
    px(x, y, PATH_D); px(x + 1, y, PATH_L) if rng.random() < 0.6 else None
# castle shadow line on ground
rect(76, GROUND_Y + 1, 180, GROUND_Y + 1, G3)
rect(118, GROUND_Y + 1, 138, GROUND_Y + 1, PATH_D)

# trees left and right
def tree(x, y, s=1):
    rect(x - 1, y - 3, x + 1, y, '#5a3a2a')
    layers = [(9, '#2e6a3a'), (7, '#3f8a3e'), (5, '#3f8a3e'), (3, '#5aa84a')]
    yy = y - 4
    for i, (w, c) in enumerate(layers):
        for k in range(4):
            ww = w - k
            rect(x - ww, yy - k, x + ww, yy - k, c)
            px(x - ww, yy - k, '#5aa84a'); px(x + ww, yy - k, '#2e6a3a')
        yy -= 4
    px(x, yy + 1, '#7cc45a')
tree(14, 98); tree(30, 95); tree(56, 93); tree(186, 100); tree(68, 92)

# bushes
for (bx, by) in [(8, 112), (176, 118), (60, 104)]:
    rect(bx - 5, by - 2, bx + 5, by, G3); rect(bx - 4, by - 3, bx + 4, by - 3, G3)
    rect(bx - 3, by - 4, bx + 3, by - 4, G2); rect(bx - 2, by - 5, bx + 2, by - 5, G2)
    px(bx - 1, by - 5, G4); px(bx - 2, by - 4, G4); px(bx + 3, by - 1, '#e8eef6'); px(bx - 3, by - 2, '#ffd56a')

# ---------- hero (foreground, back to viewer 3/4, facing castle) ----------
OUT = hexc('#1a1220')
SKIN, SKIN_D = hexc('#f2c29a'), hexc('#c98f6a')
ARM_L, ARM, ARM_D = hexc('#e8eef6'), hexc('#a9b8cc'), hexc('#5f6f8a')
CAPE, CAPE_D, CAPE_L = hexc('#c0283a'), hexc('#801a30'), hexc('#e8504a')
GOLD, GOLD_D = hexc('#ffd56a'), hexc('#c08a2a')
BOOT, BOOT_D = hexc('#6a4430'), hexc('#43291f')
HAIR, HAIR_D = hexc('#8a4a2a'), hexc('#5a2e1e')
TUNIC, TUNIC_D = hexc('#3a64b8'), hexc('#25438a')

HX, HY = 62, 124   # feet baseline, x center
sprite = [
"..........................................",
]
# Define hero via pixel map (each char a color), width 30, scaled 1:1
P = {
 'o': OUT, 's': SKIN, 'S': SKIN_D, 'w': ARM_L, 'a': ARM, 'A': ARM_D,
 'c': CAPE, 'C': CAPE_D, 'l': CAPE_L, 'g': GOLD, 'G': GOLD_D, 'b': BOOT, 'B': BOOT_D,
 'h': HAIR, 'H': HAIR_D, 't': TUNIC, 'T': TUNIC_D, 'e': hexc('#ffffff'), 'k': hexc('#2a1d2e'),
 'x': hexc('#dfe8f2'), 'X': hexc('#8a9ab0'), 'r': hexc('#e23b3b'),
}
hero = r"""
..........................................
.......................ox.................
......................oxXo................
......................oxXo................
......................oxXo................
..........ooo.........oxXo................
.........orrro........oxXo................
........orrlro........oxXo................
.......oowwaaoo.......oxXo................
......owwwaaaAAo......oxXo................
.....owwwaaaaaAAo.....oxXo................
.....owgggggggGAo.....oxXo................
.....owaaaaaaaaAo.....oxXo................
.....oahhhhhhhhAo.....oxXo................
.....oahsssssshAo.....oxXo................
.....oahsksskshAo.....oxXo................
......ohssssssSo......oxXo................
.......ossSSSSo.......oxXo................
.....ooolsssslooo...oogggGoo..............
...oollcwwaaaawccloooGGgggGGo.............
..olllcwwwaaaaaAwcco.oo sso...............
..olccowwwaaaaaAAwco..osSso...............
.olccowaawgggGaaAAo..oaAo.................
.olcc.owaaaaaaaaAoaoaaAo..................
.olcc.otttttttttTTaaaAo...................
olccc.oagggggggGGAooo.....................
olccc.otttttttttTTo.......................
olcccoottttTttttTTo.......................
olccco.ottTo.otTTTo.......................
olcccC.oaaAo.oaAAo........................
olccCC.oaaAo.oaAAo........................
.olcCC.owaAo.owaAo........................
.oocCC.oaaAo.oaAAo........................
...ooooobbBo.obbBo........................
......obbbBBoobbBBo.......................
......oooooo.oooooo.......................
"""
rows = [r for r in hero.strip('\n').split('\n')]
hh = len(rows)
x0 = HX - 10; y0 = HY - hh + 1
# shadow under hero
for x in range(x0 + 2, x0 + 24):
    px(x, HY + 1, G3 if img[HY + 1, x].tolist() != list(PATH) else PATH_D)
    px(x, HY, PATH_D) if img[HY, x].tolist() == list(PATH) else None
for j, row in enumerate(rows):
    for i, ch in enumerate(row):
        if ch in P:
            px(x0 + i, y0 + j, P[ch])

out = Image.fromarray(img).resize((W * 8, H * 8), Image.NEAREST)
out.save('/workspace/out/final.png')
print('saved', out.size)
