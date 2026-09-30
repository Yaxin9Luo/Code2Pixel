"""B07 海边放风筝的小女孩。

素材（refs/，不联网）：Platja_dels_Terrers_kite_girl_(42427128840).jpg — 海滩上放彩虹风筝的小女孩（背侧面）。
做法（全部是代码，没有神经网络）：
  1. 在照片上用代码改天气：阴天的灰天空按颜色抠掉，换成代码画的夏日天空（渐变 + 程序化积云），
     海面偏蓝绿、湿沙反光跟着变蓝、干沙变暖；
  2. 用本项目 stylize.py 的水彩流水线把整张画成水彩（固定种子）；
  3. 在水彩上用代码补画被水彩吃掉的细节：风筝下挂着彩穗的细线、几只海鸥，最后统一纸色。
用法：python3 draw.py [输出路径]   （默认 final.png）
"""
import sys
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "stylize"))
import stylize  # noqa: E402

HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/final.png"
N = 1600
SEED = 0
rng = np.random.default_rng(7)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


photo = ImageOps.exif_transpose(Image.open(f"{HERE}/refs/Platja_dels_Terrers_kite_girl_(42427128840).jpg")).convert("RGB")
a = np.asarray(photo.resize((N, N), Image.LANCZOS), np.float32) / 255
yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
mx, mn = a.max(-1), a.min(-1)
sat = (mx - mn) / np.maximum(mx, 1e-3)
val = mx

# ---------------- 1. 天空遮罩：阴天天空是低饱和、偏蓝灰、较亮的像素 ----------------
# 每一列的海天线：从上往下第一次明显变暗的位置
dark = val < 0.64
hz = np.full(N, 858.0)
for x in range(N):
    col = np.nonzero(dark[800:920, x])[0]
    if len(col):
        hz[x] = 800 + col[0]
hz = ndi.median_filter(hz, 41)
hz = ndi.gaussian_filter1d(hz, 8)
skyish = (sat < 0.15) & (val > 0.58) & (a[..., 2] >= a[..., 0] - 0.03) & (yy < hz[None, :])
skyish = ndi.binary_opening(skyish, iterations=1)
fg = ndi.binary_dilation(~skyish & (yy < hz[None, :] + 4), iterations=1)       # 风筝、飘带、手臂、头发往外扩 1 像素
sky_m = (skyish & ~fg).astype(np.float32)
sky_m = ndi.gaussian_filter(sky_m, 1.0)

# ---------------- 2. 代码画的夏日天空 ----------------
t = np.clip(yy / hz[None, :], 0, 1)
# 天空大部分用同一种蓝（水彩流水线会把它当成一片洗染，自带颜料不匀），只在海天线附近变浅
stops_t = [0.0, 0.55, 0.86, 0.97, 1.0]
stops_c = np.array([[0.47, 0.66, 0.88], [0.50, 0.69, 0.89], [0.55, 0.73, 0.90], [0.80, 0.86, 0.91], [0.88, 0.89, 0.88]])
sky = np.stack([np.interp(t, stops_t, stops_c[:, c]) for c in range(3)], -1)


def fbm(h, w, scale, octaves, seed):
    return stylize.fbm(h, w, scale, octaves, seed)


# 积云：每朵云是一串圆（云团）的并集，底部压平，边缘用分形噪声扰动，下半部略带灰蓝
CLOUDS = [
    (360, [(1060, 350, 45), (1130, 330, 70), (1200, 290, 90), (1290, 268, 100), (1380, 298, 80), (1445, 335, 55)]),
    (465, [(150, 440, 50), (220, 408, 66), (300, 424, 56), (362, 446, 36)]),
    (792, [(1170, 772, 28), (1250, 760, 42), (1330, 745, 56), (1420, 755, 46), (1500, 772, 34)]),
    (142, [(420, 122, 34), (470, 104, 46), (528, 122, 30)]),
]
edge_n = fbm(N, N, 40, 4, 31) - 0.5
cloud = np.zeros((N, N), np.float32)
shade = np.zeros((N, N), np.float32)
for bottom, puffs in CLOUDS:
    m = np.zeros((N, N), np.float32)
    for cx, cy, r in puffs:
        m = np.maximum(m, 1 - np.hypot(xx - cx, yy - cy) / r)
    m = smoothstep(0.0, 0.18, m + 0.22 * edge_n) * smoothstep(bottom + 6, bottom - 14, yy)
    top_y = min(cy - r for cx, cy, r in puffs)
    shade = np.maximum(shade, m * smoothstep(top_y + 0.45 * (bottom - top_y), bottom, yy))
    cloud = np.maximum(cloud, m)
cloud_col = np.array([0.985, 0.98, 0.97]) - shade[..., None] * np.array([0.22, 0.18, 0.10])
sky = sky * (1 - cloud[..., None]) + cloud_col * cloud[..., None]
a = a * (1 - sky_m[..., None]) + sky * sky_m[..., None]

# ---------------- 3. 海面、湿沙、干沙的颜色 ----------------
below = smoothstep(0, 6, yy - hz[None, :])
lum = a.mean(-1, keepdims=True)
blueish = smoothstep(0.0, 0.06, a[..., 2] - a[..., 0]) * below                   # 海水、湿沙上的天光反射
a = a + (blueish[..., None] * ((a - lum) * 0.6 + np.array([-0.05, 0.0, 0.05]) * lum))
warmish = smoothstep(0.0, 0.05, a[..., 0] - a[..., 2]) * smoothstep(1270, 1330, yy)  # 沙滩
a = a * (1 + warmish[..., None] * np.array([0.07, 0.02, -0.08]))
a = np.clip(a, 0, 1)

# ---------------- 4. 水彩 ----------------
wc = stylize.stylize(Image.fromarray((a * 255 + 0.5).astype(np.uint8)), "watercolor", 1.0, SEED, N).convert("RGB")
w = np.asarray(wc, np.float32) / 255

# ---------------- 5. 补画细节：挂彩穗的细线、海鸥（叠加方式：像颜料一样乘上去） ----------------
SS = 3


def stroke_layer(polys, width, seed):
    """polys: [[(x,y),...], ...]，画成略带抖动的细线，返回 0..1 覆盖度。"""
    im = Image.new("L", (N * SS, N * SS), 0)
    d = ImageDraw.Draw(im)
    r = np.random.default_rng(seed)
    for pts in polys:
        pts = np.array(pts, float)
        # 沿折线插值成密点，再加一点低频抖动
        seg = [pts[0]]
        for p0, p1 in zip(pts[:-1], pts[1:]):
            k = max(2, int(np.hypot(*(p1 - p0)) / 4))
            for s in np.linspace(0, 1, k)[1:]:
                seg.append(p0 + (p1 - p0) * s)
        seg = np.array(seg)
        seg = ndi.gaussian_filter1d(seg, 3, axis=0, mode="nearest")
        jit = ndi.gaussian_filter1d(r.normal(0, 1.2, seg.shape), 6, axis=0)
        seg = seg + jit
        d.line([(x * SS, y * SS) for x, y in seg], fill=255, width=int(width * SS), joint="curve")
    m = np.asarray(im.resize((N, N), Image.BOX), np.float32) / 255
    return m


string_pts = [(800, 553), (812, 568), (822, 588), (821, 640), (819, 690), (812, 740), (806, 775), (799, 805),
              (791, 860), (787, 920), (788, 960), (795, 1020), (801, 1060), (815, 1120), (831, 1191), (838, 1260),
              (842, 1330), (846, 1395), (838, 1438), (800, 1470), (750, 1492), (700, 1510), (665, 1521), (600, 1520),
              (500, 1518), (400, 1515), (300, 1513), (200, 1511), (95, 1511)]
line = stroke_layer([string_pts], 1.8, 3)
ink = np.array([0.36, 0.33, 0.33])                      # 细线用淡墨色
w = w * (1 - 0.45 * line[..., None] * (1 - ink))

# 海鸥：两段弧，像随手几笔
gulls = []
for gx, gy, s in [(1185, 470, 46), (1300, 530, 34), (1080, 548, 27)]:
    left = [(gx - s, gy - 0.25 * s), (gx - 0.55 * s, gy - 0.55 * s), (gx - 0.15 * s, gy - 0.3 * s), (gx, gy)]
    right = [(gx, gy), (gx + 0.2 * s, gy - 0.35 * s), (gx + 0.6 * s, gy - 0.6 * s), (gx + 1.05 * s, gy - 0.2 * s)]
    gulls += [left, right]
gm = stroke_layer(gulls, 4.4, 5)
gm = ndi.gaussian_filter(gm, 0.6)
gull_col = np.array([0.30, 0.34, 0.42])
w = w * (1 - 0.8 * gm[..., None] * (1 - gull_col))

out = np.clip(w, 0, 1)
Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(OUT)
print(OUT)
