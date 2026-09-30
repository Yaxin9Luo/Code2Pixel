"""B11 像素画：勇者站在城堡前。

素材（refs/，不联网）：
  Bodiam_Castle_from_the_north_2019-05-28.jpg — 博迪亚姆城堡正面（护城河、木桥）
  French_-_Child's_Suit_of_Armor_-_Walters_51590_(2).jpg — 博物馆里的一套带羽饰的盔甲（勇者的身体）
像素化全部由代码完成（没有神经网络）：
  1. 城堡照片先做保边平滑，再按面积缩到 200x150 的像素网格；天空换成代码画的抖动渐变 + 像素云，
     护城河换成偏蓝的水色并加水面高光，桥上的游客抹掉；
  2. 盔甲按纹理从灰背景里抠出来，按“块内多数颜色”缩成 54 像素高的小人（钢色 5 级、黑布、金扣），
     照片里摊开的羽毛去掉、改用代码画的红羽饰；剑和剑尖闪光是代码逐像素画的；描 1 像素深色外轮廓；
  3. 背景用 k-means 限色到 20 色、去掉孤立杂点，城堡轮廓描深色边；最后最近邻放大 8 倍到 1600x1200。
用法：python3 draw.py [输出路径]   （默认 final.png）
"""
import sys
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402

HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/final.png"
GW, GH, K = 200, 150, 8                    # 像素网格和放大倍数
rng = np.random.default_rng(11)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def poly(pts, w, h, ss=4):
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return np.asarray(m.resize((w, h), Image.BOX), np.float32) / 255


def kmeans(X, k, iters=25, seed=0):
    r = np.random.default_rng(seed)
    C = [X[r.integers(len(X))]]
    for _ in range(k - 1):                                    # k-means++ 初始化
        d = np.min(((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1), 1)
        C.append(X[r.choice(len(X), p=d / d.sum())])
    C = np.array(C)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if np.any(lab == j):
                C[j] = X[lab == j].mean(0)
    return C, lab


def despeckle(idx, passes=1):
    """去孤立点：3x3 邻域里自己这种颜色少于 2 个（含自己）就换成邻域里最多的颜色。"""
    h, w = idx.shape
    for _ in range(passes):
        pad = np.pad(idx, 1, mode="edge")
        nb = np.stack([pad[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)], -1)
        same = (nb == idx[..., None]).sum(-1)
        # 邻域众数
        vals = nb.reshape(-1, 9)
        mode = np.array([np.bincount(v).argmax() for v in vals]).reshape(h, w)
        idx = np.where(same < 2, mode, idx)
    return idx


# ---------------- 1. 城堡：裁成 4:3，平滑后缩到像素网格 ----------------
cas = Image.open(f"{HERE}/refs/Bodiam_Castle_from_the_north_2019-05-28.jpg").convert("RGB")
cw, ch = cas.size                                             # 7176 x 4790
cx0 = (cw - ch * 4 // 3) // 2
cas = cas.crop((cx0, 0, cx0 + ch * 4 // 3, ch))
mid = np.asarray(cas.resize((800, 600), Image.LANCZOS), np.float32) / 255
mid_s = np.clip(stylize.l0_smooth(mid, 0.004), 0, 1)          # 保边平滑：压掉石头纹理的噪点，留下大块明暗
g = mid.mean(-1)
mx, mn = mid.max(-1), mid.min(-1)
sat = (mx - mn) / np.maximum(mx, 1e-3)
# 天空：亮、低饱和、和上边缘连通
skyc = (g > 0.42) & (sat < 0.16)
skyc[380:] = False                                            # 对岸树林以下不可能是天空
lab_, n_ = ndi.label(skyc)
edge_ids = np.unique(np.concatenate([lab_[0], lab_[:, 0], lab_[:, -1]]))
sky800 = np.isin(lab_, edge_ids[edge_ids > 0])
x800 = np.arange(800)[None, :]
side = ((x800 < 40) | (x800 > 781)) & (np.arange(600)[:, None] < 380)
sky800 |= side & (mid[..., 2] >= mid[..., 0] - 0.01) & (g > 0.3)   # 城堡两侧、树梢上方：偏蓝或中性灰的都是天空（地平线附近天带点蓝）
holes, nh = ndi.label(~sky800)
hs = ndi.sum(~sky800, holes, range(1, nh + 1))
sky800 |= np.isin(holes, np.nonzero(hs < 400)[0] + 1)          # 天空里的小黑点（鸟、噪点）并回天空
sky800 = ndi.binary_closing(sky800, iterations=1)
bg = np.asarray(Image.fromarray((mid_s * 255).astype(np.uint8)).resize((GW, GH), Image.BOX), np.float32) / 255
sky = np.asarray(Image.fromarray((sky800 * 255).astype(np.uint8)).resize((GW, GH), Image.BOX), np.float32) / 255 > 0.5

# 预览图(1920 宽)坐标 → 像素网格坐标
PX0 = cx0 / (cw / 1920)
S = GH / 1282.0


def P(x, y):
    return ((x - PX0) * S, y * S)


# 调色：更鲜亮一点（像素画不用照片的灰调）
lum = bg.mean(-1, keepdims=True)
bg = np.clip(lum + (bg - lum) * 1.45, 0, 1)
bg = np.clip((bg - 0.5) * 1.15 + 0.52, 0, 1)
Lb = bg.mean(-1, keepdims=True)
bg = bg * (np.power(np.clip(Lb, 1e-3, 1), 0.78) * 1.12 / np.maximum(Lb, 1e-3))    # 提亮：阴天 → 晴天
Lb = bg.mean(-1, keepdims=True)
tw = smoothstep(0.25, 0.65, Lb)
bg = bg * (np.array([0.88, 0.82, 1.10]) * (1 - tw) + np.array([1.10, 1.00, 0.78]) * tw)   # 亮部偏暖黄、暗部偏冷紫
bg = np.clip(bg, 0, 1)

# 抹掉桥上和城头的游客：用同一行左右的路面颜色填
for (x0, y0, x1, y1) in [(900, 725, 1025, 868), (1620, 212, 1645, 255), (1290, 455, 1370, 480)]:
    a0, b0 = P(x0, y0)
    a1, b1 = P(x1, y1)
    a0, b0, a1, b1 = int(a0) - 1, int(b0) - 1, int(np.ceil(a1)) + 1, int(np.ceil(b1)) + 1
    for yy_ in range(b0, b1):
        left, right = bg[yy_, a0 - 2], bg[yy_, a1 + 1]
        for xx_ in range(a0, a1):
            t = (xx_ - a0) / max(1, a1 - a0)
            bg[yy_, xx_] = left * (1 - t) + right * t

# ---------------- 2. 护城河：偏蓝绿，保留倒影明暗，加水面高光 ----------------
yy, xx = np.mgrid[0:GH, 0:GW].astype(np.float32)
bridge = poly([P(250, 1282), P(850, 822), P(1072, 822), P(1705, 1282)], GW, GH) > 0.5
islands = (poly([P(478, 845), P(860, 835), P(860, 1000), P(478, 1000)], GW, GH) > 0.5) | \
          (poly([P(1058, 835), P(1432, 845), P(1432, 1000), P(1058, 1000)], GW, GH) > 0.5)
bank_y = np.where((xx < P(180, 0)[0]) | (xx > P(1785, 0)[0]), P(0, 808)[1], P(0, 842)[1])
water = (yy > bank_y) & ~bridge & ~islands
wl = bg.mean(-1)
wcol = np.stack([0.20 + 0.55 * wl, 0.38 + 0.55 * wl, 0.52 + 0.45 * wl], -1)
bg = np.where(water[..., None], wcol, bg)

# ---------------- 3. 像素天空：分段渐变 + 4x4 Bayer 抖动 + 像素云 ----------------
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
SKY = np.array([[46, 92, 176], [62, 118, 204], [88, 148, 222], [124, 180, 236], [170, 212, 244]]) / 255
horizon = 100.0
tpos = np.clip(yy / horizon, 0, 1) * (len(SKY) - 1)
frac = smoothstep(0.3, 0.7, tpos - np.floor(tpos))
band = np.floor(tpos).astype(int) + (frac > BAYER[(yy % 4).astype(int), (xx % 4).astype(int)])
band = np.clip(band, 0, len(SKY) - 1)
skyimg = SKY[band]
# 云：几个圆叠成的“棉花糖”，底部压平，下沿一排浅蓝阴影
cloud = np.zeros((GH, GW), bool)
cshade = np.zeros((GH, GW), bool)
for cx, cy, parts in [(34, 22, [(-10, 2, 6), (-3, -2, 8), (6, 0, 7), (13, 3, 5)]),
                      (150, 14, [(-12, 2, 5), (-5, -1, 7), (4, -2, 8), (12, 1, 6), (18, 3, 4)]),
                      (104, 34, [(-6, 1, 4), (0, -1, 5), (6, 1, 4)])]:
    m = np.zeros((GH, GW), bool)
    for dx, dy, r in parts:
        m |= (xx - (cx + dx)) ** 2 + (yy - (cy + dy)) ** 2 <= r * r
    base = cy + 4
    m &= yy <= base
    cloud |= m
    cshade |= m & (yy >= base - 1)
skyimg = np.where(cloud[..., None], np.array([248, 250, 255]) / 255, skyimg)
skyimg = np.where(cshade[..., None], np.array([196, 214, 238]) / 255, skyimg)

# ---------------- 4. 背景限色 ----------------
X = bg[~sky].reshape(-1, 3)
C, lab = kmeans(X, 20, seed=2)
idx = np.full((GH, GW), -1)
idx[~sky] = lab
idx_c = despeckle(np.where(sky, 20, idx), passes=3)
pal = np.vstack([C, [[0, 0, 0]]])
bgq = pal[np.clip(idx_c, 0, 20)]
img = np.where(sky[..., None], skyimg, bgq)
# 水面：岸边一条暗影，水里随机几段浅色短横线（波光）
wr = np.random.default_rng(5)
top_w = water & ~np.roll(water, 1, 0)
img = np.where((top_w | np.roll(top_w, 1, 0))[..., None] & water[..., None], img * 0.72, img)
for _ in range(170):
    y_, x_ = int(wr.integers(0, GH)), int(wr.integers(0, GW))
    ln = int(wr.integers(2, 6))
    if water[y_, x_:x_ + ln].all() and y_ > 0 and water[y_ - 1, x_]:
        img[y_, x_:x_ + ln] = np.array([214, 236, 246]) / 255 if wr.random() < 0.6 else np.array([150, 196, 222]) / 255
# 城墙上个别比周围亮很多的孤点换成邻域中值（最终图里没有触发；城楼垛口里那两个白点其实是第三朵云从缝里露出来，属于天空，没处理）
above = (~sky) & (~water) & (yy < bank_y)
Lq = img.mean(-1)
medL = ndi.median_filter(Lq, 3)
spot = above & (Lq - medL > 0.3)
for c in range(3):
    img[..., c] = np.where(spot, ndi.median_filter(img[..., c], 3), img[..., c])
# 城堡、树和天空交界处描一圈深色边（只描在城堡一侧）
edge = ~sky & ndi.binary_dilation(sky, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
img = np.where(edge[..., None], img * 0.55, img)

# ---------------- 5. 勇者：盔甲抠图 → 小人 ----------------
arm = np.asarray(Image.open(f"{HERE}/refs/French_-_Child's_Suit_of_Armor_-_Walters_51590_(2).jpg").convert("RGB"), np.float32) / 255
ag = arm.mean(-1)
asd = np.sqrt(np.maximum(ndi.uniform_filter(ag * ag, 9) - ndi.uniform_filter(ag, 9) ** 2, 0))
amx, amn = arm.max(-1), arm.min(-1)
asat = (amx - amn) / np.maximum(amx, 1e-3)
fg = (asd > 0.022) | (ag < 0.45) | (asat > 0.2)
fg[1650:] &= ~((arm[1650:, :, 0] - arm[1650:, :, 2] > 0.06) & (asat[1650:] > 0.15))   # 底座：暖棕色
fg[1725:] = False
fg = ndi.binary_closing(fg, iterations=5)
fg = ndi.binary_fill_holes(fg)
fg = ndi.binary_opening(fg, iterations=3)
AH, AW = fg.shape
legs_gap = poly([(448, 1185), (498, 1185), (505, 1300), (512, 1500), (512, 1725), (400, 1725), (418, 1500), (436, 1300)], AW, AH) > 0.5
fg &= ~legs_gap
lab2, n2 = ndi.label(fg)
fg = lab2 == (np.argmax(ndi.sum(fg, lab2, range(1, n2 + 1))) + 1)
ys, xs = np.nonzero(fg)
by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
# 每个原图像素先归类：钢（按亮度分级）、黑衬裤、红羽、白羽、金扣
ay = np.arange(AH)[:, None]
cat = np.zeros((AH, AW), int)                                  # 0 钢
cat[ag < 0.15] = 1                                             # 黑布
red_ = (arm[..., 0] > arm[..., 1] + 0.15) & (asat > 0.35)
cat[red_] = 2
cat[(ay < 300) & ~red_ & (ag > 0.6) & (asat < 0.3) & ((ay < 250) | (np.arange(AW)[None, :] < 380) | (np.arange(AW)[None, :] > 575))] = 3   # 白羽（头盔以外的浅色）
cat[(arm[..., 0] > arm[..., 2] + 0.12) & (asat > 0.25) & ~red_ & (ay > 500)] = 4
HERO_H = 60
sc = HERO_H / (by1 - by0)
hw = int(round((bx1 - bx0) * sc))


def area(m):
    """原图上的 0/1 或数值图 → 小人尺寸的面积平均。"""
    m = m[by0:by1, bx0:bx1].astype(np.float32)
    return np.asarray(Image.fromarray(m, mode="F").resize((hw, HERO_H), Image.BOX))


ay_, ax_ = np.arange(AH)[:, None], np.arange(AW)[None, :]
plume_px = (ay_ < 262) | ((cat == 2) | (cat == 3)) & (ay_ < 330) | (ay_ < 350) & ((ax_ < 372) | (ax_ > 578))
# 头盔是个圆顶：圆心 (470,362)、半径 108 以外、y<360 的都是羽毛（顶上的尖脊保留）
plume_px |= (ay_ < 360) & (np.hypot(ax_ - 470, ay_ - 362) > 108) & ~((ax_ > 455) & (ax_ < 486) & (ay_ > 246))
fg &= ~plume_px                                                # 照片里的羽毛向两边摊开，缩小后是一条红白横杠，去掉重画
ys, xs = np.nonzero(fg)
by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
HERO_H = 54
sc = HERO_H / (by1 - by0)
hw = int(round((bx1 - bx0) * sc))
cov = area(fg)
wts = np.array([1.0, 1.0, 2.6, 1.6, 1.8])                      # 红羽、金扣这些小而关键的颜色加权，免得被钢色吃掉
votes = np.stack([area(fg & (cat == c)) * wts[c] for c in range(5)], -1)
hc = np.argmax(votes, -1)
steel_m = fg & (cat == 0)
steel_l = area(np.where(steel_m, ag, 0)) / np.maximum(area(steel_m), 1e-3)
hm = cov > 0.42
STEEL = np.array([[44, 48, 68], [86, 94, 118], [132, 142, 164], [182, 190, 208], [232, 236, 246]]) / 255
lvl = np.clip(np.digitize(steel_l, [0.28, 0.42, 0.56, 0.72]), 0, 4)
sprite = STEEL[lvl]
sprite[hc == 1] = np.array([30, 26, 40]) / 255
sprite[hc == 2] = np.array([228, 58, 50]) / 255
sprite[hc == 3] = np.array([244, 236, 224]) / 255
sprite[hc == 4] = np.array([222, 178, 64]) / 255


def rs(y):                                                     # 原图 y → 小人行号
    return int(round((y - by0) * sc))


def cs(x):
    return int(round((x - bx0) * sc))


# 头盔面罩的缝：一条深色横线；头盔顶一道高光
for x_ in range(cs(405), cs(560) + 1):
    if hm[rs(372), x_]:
        sprite[rs(372), x_] = np.array([30, 26, 40]) / 255
for y_ in range(rs(265), rs(350)):
    if hm[y_, cs(470)]:
        sprite[y_, cs(470)] = STEEL[4]
# 羽饰：从头盔顶往上、再向后（画面右侧）弯，三色（暗红、红、亮红）
PL_D, PL_M, PL_L = np.array([150, 28, 44]) / 255, np.array([226, 56, 50]) / 255, np.array([255, 128, 104]) / 255
plume = [(0, 0), (-1, 0), (-2, 0), (-3, 1), (-4, 1), (-5, 2), (-6, 3), (-6, 4), (-6, 5), (-5, 6), (-4, 7), (-3, 7), (-2, 8)]
# 剑：右手（画面左侧）握剑，剑身朝左上 45°
hand_y, hand_x = rs(1045), cs(262)
OX, OY = 34, 34                                                # 在扩边的画布上画，留出剑伸出去的空间
spr = np.zeros((HERO_H + 2 * OY, hw + 2 * OX, 3))
msk = np.zeros((HERO_H + 2 * OY, hw + 2 * OX), bool)
spr[OY:OY + HERO_H, OX:OX + hw] = sprite
msk[OY:OY + HERO_H, OX:OX + hw] = hm
BLADE, BLADE_HI, BLADE_SH = np.array([200, 208, 224]) / 255, np.array([255, 255, 255]) / 255, np.array([120, 130, 156]) / 255
GUARD, GUARD_SH, GRIP = np.array([240, 196, 72]) / 255, np.array([170, 118, 40]) / 255, np.array([116, 66, 36]) / 255
hx, hy = OX + hand_x, OY + hand_y
top_y = OY + min(np.nonzero(hm[:, cs(470)])[0])               # 头盔顶
top_x = OX + cs(470)
for i, (dy, dx) in enumerate(plume):
    y_, x_ = top_y + dy, top_x + dx
    spr[y_, x_] = PL_M; msk[y_, x_] = True                     # 中间一条
    spr[y_ + 1, x_] = PL_D; msk[y_ + 1, x_] = True             # 下沿暗
    if i > 1:
        spr[y_ - 1, x_] = PL_L; msk[y_ - 1, x_] = True         # 上沿亮
        if i < len(plume) - 2:
            spr[y_ - 1, x_ + 1] = PL_M; msk[y_ - 1, x_ + 1] = True


def put(y, x, c):
    spr[y, x] = c
    msk[y, x] = True


for t in range(0, 4):                                          # 剑柄 + 柄头
    put(hy + t, hx + t, GRIP if t < 3 else GUARD)
for t in range(-3, 4):                                         # 护手
    put(hy - 1 + t, hx - 1 - t, GUARD if t < 2 else GUARD_SH)
for t in range(2, 28):                                         # 剑身：三道（暗边、亮面、高光）
    put(hy - t + 1, hx - t, BLADE_SH)
    put(hy - t, hx - t + 1, BLADE)
    put(hy - t, hx - t, BLADE_HI)
put(hy - 28, hx - 28, BLADE_HI)
tip_y, tip_x = hy - 29, hx - 29                                 # 剑尖一颗四角星闪光（不描边）
glint = [(0, 0, BLADE_HI), (-1, 0, BLADE_HI), (1, 0, BLADE_HI), (0, -1, BLADE_HI), (0, 1, BLADE_HI),
         (-2, 0, np.array([255, 240, 160]) / 255), (2, 0, np.array([255, 240, 160]) / 255),
         (0, -2, np.array([255, 240, 160]) / 255), (0, 2, np.array([255, 240, 160]) / 255)]
# 1 像素深色外轮廓
outline = ndi.binary_dilation(msk, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])) & ~msk
OUTC = np.array([20, 18, 32]) / 255
FEET_Y = 148
ox = GW // 2 - (OX + hw // 2)
oy = FEET_Y - (OY + HERO_H)
img[FEET_Y - 1:FEET_Y + 1, GW // 2 - 12:GW // 2 + 12] *= 0.6          # 脚下的影子（先画，小人盖在上面）
for (sy_, sx_) in zip(*np.nonzero(msk | outline)):
    ty, tx = sy_ + oy, sx_ + ox
    if 0 <= ty < GH and 0 <= tx < GW:
        img[ty, tx] = spr[sy_, sx_] if msk[sy_, sx_] else OUTC
for dy, dx, c in glint:
    img[tip_y + dy + oy, tip_x + dx + ox] = c

# ---------------- 6. 放大 ----------------
out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
Image.fromarray(out).resize((GW * K, GH * K), Image.NEAREST).save(OUT)
print(OUT)
