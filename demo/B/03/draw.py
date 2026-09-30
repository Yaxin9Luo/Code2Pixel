"""B03 夜晚的日式小巷：红灯笼、发光的自动售货机、被雨打湿的石板路。

素材（都在 refs/，不联网）：
  Yokocho.jpg — 新宿思い出横丁雨夜的小巷（底图）
  Akai-Hane_Beverage_vending_machine_in_Japan_2014.jpg — 正面拍的自动售货机（透视校正后贴进小巷）
做法：
  1. 用单应性把售货机正面校正成矩形，按小巷的灭点、相机高度算出比例，放进左侧店面，补画侧板、踢脚、接触阴影；
  2. 代码画发光：灯箱提亮、泛光、地面光斑、湿地倒影；白墙压暗成只被售货机照亮；
  3. 中间的水泥路面按地面透视铺成石板（石缝、每块石头明暗不同），再按镜面几何加一层雨后倒影；
  4. 夜景调色：压暗中间调、暗部偏冷、泛光、暗角、颗粒。
用法：python3 draw.py [输出路径]   （默认 final.png）
"""
import sys
import numpy as np
from PIL import Image, ImageOps, ImageDraw
from scipy import ndimage as ndi

HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
OUT = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/final.png"
W, H = 1600, 1200
rng = np.random.default_rng(3)

# 相机：灭点、地平线、焦距、相机高度（看图量灭点，焦距按小相机广角端估计）
VPX, VPY, F, HC = 805.0, 590.0, 1143.0, 1.45


def load(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def to_lin(x):
    return np.power(np.clip(x, 0, None), 2.2)


def to_srgb(x):
    return np.power(np.clip(x, 0, 1), 1 / 2.2)


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.array(A, float))
    Hm = vt[-1].reshape(3, 3)
    return Hm / Hm[2, 2]


def warp_rect(a, quad, w, h):
    """把数组 a 中四边形 quad(TL,TR,BR,BL) 校正成 w x h 的矩形（双线性采样）。"""
    Hm = homography([(0, 0), (w, 0), (w, h), (0, h)], quad)
    ys, xs = np.mgrid[0:h, 0:w].astype(float) + 0.5
    p = Hm @ np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size)])
    sx, sy = p[0] / p[2], p[1] / p[2]
    out = np.stack([ndi.map_coordinates(a[..., c], [sy - 0.5, sx - 0.5], order=1, mode="nearest") for c in range(3)], -1)
    return out.reshape(h, w, 3)


def gauss(x, s):
    if x.ndim == 3:
        return np.stack([ndi.gaussian_filter(x[..., c], s) for c in range(x.shape[2])], -1)
    return ndi.gaussian_filter(x, s)


def poly_mask(pts, ss=4):
    m = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(m).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return np.asarray(m.resize((W, H), Image.BOX), np.float32) / 255


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def value_noise(h, w, cell, seed):
    r = np.random.default_rng(seed)
    g = r.random((h // cell + 3, w // cell + 3)).astype(np.float32)
    return ndi.zoom(g, cell, order=3)[:h, :w]


yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

# ---------------- 底图 ----------------
base = np.asarray(load(f"{HERE}/refs/Yokocho.jpg").resize((W, H), Image.LANCZOS), np.float32) / 255
img = to_lin(base)
orig = img.copy()

# ---------------- 中间路面：铺石板 ----------------
# 路面范围（看图描的）：左缘、右缘两条线收向灭点；排除排水沟盖板和两个井盖
path = poly_mask([(548, 1200), (612, 1000), (700, 800), (752, 700), (790, 640), (822, 640),
                  (858, 700), (884, 800), (930, 1000), (968, 1200)])
path *= 1 - poly_mask([(608, 1010), (936, 1010), (936, 1046), (604, 1046)])
path *= 1 - poly_mask([(848, 922), (912, 922), (912, 948), (848, 948)])
path *= 1 - poly_mask([(866, 1060), (948, 1060), (948, 1104), (866, 1104)])
SS = 3                                                   # 3 倍超采样画石缝，避免远处闪烁
ys, xs = np.mgrid[0:H * SS, 0:W * SS].astype(np.float32) / SS
yv = np.maximum(ys - VPY, 1.0)
Z = F * HC / yv                                          # 地面点的深度（米）
X = (xs - VPX) * Z / F                                   # 横向位置（米）
rr = np.random.default_rng(11)
bounds = np.cumsum(0.34 + 0.16 * rr.random(4000)).astype(np.float32)   # 每排石板长 34–50cm，不等长
ri = np.searchsorted(bounds, Z.ravel()).reshape(Z.shape)
lo = np.where(ri > 0, bounds[np.maximum(ri - 1, 0)], 0.0)
row_len = bounds[np.minimum(ri, 3999)] - lo
offs = rr.random(4000).astype(np.float32)                # 每一排石板的横向错缝
widths = 0.34 + 0.22 * rr.random(4000).astype(np.float32)
ri_i = ri.astype(np.int64) % 4000
u = X / widths[ri_i] + offs[ri_i] * 3.0
ci = np.floor(u)
fz = (Z - lo) / row_len                                  # 在这一排里的纵向位置 0..1
fu = u - ci                                              # 在这块石头里的横向位置 0..1
jw = 0.012                                               # 石缝宽 1.2cm
dz = np.minimum(fz, 1 - fz) * row_len
dx = np.minimum(fu, 1 - fu) * widths[ri_i]
px_m = Z / F                                             # 1 个（超采样前）像素对应多少米
joint = np.maximum(1 - smoothstep(jw * 0.5, jw * 0.5 + px_m * 0.8, dz), 1 - smoothstep(jw * 0.5, jw * 0.5 + px_m * 0.8, dx))
sid = (ri_i * 131 + ci.astype(np.int64) * 7919) % 100003
tone = 0.80 + 0.32 * ((sid * 2654435761) % 1000 / 1000.0)          # 每块石头的明暗
edge_hi = np.exp(-((fz - 0.06) / 0.05) ** 2) * 0.35                  # 石头靠远端边缘一点反光
del ys, xs, yv, X, u, ci, fu, dz, dx, sid, lo, row_len
def down(a):
    return a.reshape(H, SS, W, SS).mean((1, 3))
joint, tone, edge_hi, Zp = down(joint), down(tone), down(edge_hi), down(Z)
del Z
grain = value_noise(H, W, 3, 5) * 0.25 + 0.875                        # 石面细颗粒
slab = (tone * grain) * (1 - 0.7 * joint)
far = smoothstep(640, 760, yy)                                        # 太远的地方石缝看不清，淡出
slab = 1 + (slab - 1) * far
img = img * (1 + path[..., None] * (slab[..., None] - 1))
img = img + path[..., None] * (edge_hi * far * (1 - joint))[..., None] * gauss(orig, 3) * 0.25

# ---------------- 雨后倒影：按地面镜面几何，把两侧墙面镜像到路面 ----------------
# 左墙在 X=-1.3m，右墙在 X=+1.2m；某一列 x 上墙根在 y_g(x)，墙上的点在地面的倒影在 2*y_g - y
xl = np.arange(W, dtype=np.float32)
yg = np.where(xl < VPX, VPY + HC * (xl - VPX) / -1.3, VPY + HC * (xl - VPX) / 1.2)
yg = np.maximum(yg, VPY + 8)
src_y = 2 * yg[None, :] - yy
valid = (yy > yg[None, :] + 2) & (src_y > 0)
refl = np.stack([ndi.map_coordinates(orig[..., c], [np.clip(src_y, 0, H - 1), xx], order=1) for c in range(3)], -1)
refl *= valid[..., None]
# 越远离墙根，倒影拉得越长越糊（竖向模糊）
refl = 0.5 * np.stack([ndi.gaussian_filter(refl[..., c], (5, 1.2)) for c in range(3)], -1) + \
       0.5 * np.stack([ndi.gaussian_filter(refl[..., c], (18, 2.5)) for c in range(3)], -1)
cos_t = HC / np.sqrt(HC ** 2 + np.clip(F * HC / np.maximum(yy - VPY, 1), 0, 60) ** 2)
fresnel = 0.04 + 0.96 * (1 - cos_t) ** 5
puddle = smoothstep(0.52, 0.70, value_noise(H, W, 90, 21) * 0.7 + value_noise(H, W, 30, 22) * 0.3)
wet = path * (0.45 + 0.55 * puddle) * (1 - 0.8 * joint)
img = img + (wet * fresnel)[..., None] * refl * 1.3

# ---------------- 售货机 ----------------
vm_src = np.asarray(load(f"{HERE}/refs/Akai-Hane_Beverage_vending_machine_in_Japan_2014.jpg"), np.float32) / 255
QUAD = [(194, 65), (1731, 106), (1550, 2505), (304, 2535)]   # 原图里机身正面四角（看放大图量的）
MW, MH = 700, 1225
vm = to_lin(warp_rect(vm_src, QUAD, MW, MH))
my, mx = np.mgrid[0:MH, 0:MW] / np.array([MH, MW])[:, None, None]
window = gauss(((mx > 0.07) & (mx < 0.93) & (my > 0.04) & (my < 0.515)).astype(np.float32), 5)
# 陈列窗是灯箱：暗处提亮到约 4 倍、亮处少提，偏冷白；机身面板只被灯箱的光照到，越往下越暗
body_k = (0.48 - 0.30 * np.clip((my - 0.5) / 0.5, 0, 1) ** 0.8) * (1 - window)
vlum = vm.mean(-1, keepdims=True)
win_gain = 1 + 3.0 / (1 + 4 * vlum)                                  # 暗处提得多、本来就亮的少提，免得糊成一片白
vm = vm * (body_k[..., None] + window[..., None] * win_gain) + 0.05 * window[..., None] * np.array([0.8, 0.93, 1.0])
warm = np.array([1.0, 0.55, 0.3])
vm = vm + (smoothstep(0.90, 1.0, mx) * (1 - window) * 0.035)[..., None] * warm    # 右边缘被小巷暖光扫到一点
header = gauss(((mx > 0.1) & (mx < 0.9) & (my < 0.04)).astype(np.float32), 3)
vm = vm * (1 + 0.6 * header[..., None])                              # 顶部招牌
edge = np.minimum(mx, 1 - mx)
vm = vm * (0.72 + 0.28 * smoothstep(0.0, 0.035, edge))[..., None]    # 左右圆角边缘略暗

# 按透视放置：正面底边在 y=1100（深度 3.25m），比例 = (y-地平线)/相机高
BASE_Y = 1100
s = (BASE_Y - VPY) / HC                    # 像素/米
Zf = F * HC / (BASE_Y - VPY)
mh_px, mw_px = round(1.83 * s), round(1.83 * s * MW / MH)
X1 = 332
X0 = X1 - mw_px
Y1 = BASE_Y - round(0.035 * s)             # 白色机身底，下面是踢脚
Y0 = BASE_Y - mh_px
def resize_f(a, w, h):
    """浮点数组逐通道缩放（保留线性空间里 >1 的灯箱亮度）。"""
    return np.stack([np.asarray(Image.fromarray(a[..., c].astype(np.float32), mode="F").resize((w, h), Image.LANCZOS))
                     for c in range(a.shape[2])], -1)
vm_small = np.clip(resize_f(vm, mw_px, Y1 - Y0), 0, None)

# 侧板：从正面右边缘往灭点收，到白墙(深度 3.9m)为止
Zb = 3.9
def proj(Xm, Ym, Zm):
    return VPX + F * Xm / Zm, VPY + F * (HC - Ym) / Zm
Xr = (X1 - VPX) * Zf / F
p_ft, p_fb = (X1, Y0), (X1, BASE_Y)
p_bt, p_bb = proj(Xr, 1.83, Zb), proj(Xr, 0.0, Zb)
side = poly_mask([p_ft, p_bt, p_bb, p_fb])
side_col = to_lin(np.array([0.30, 0.27, 0.25])) * (0.45 + 0.55 * (1 - (yy - Y0) / (BASE_Y - Y0)))[..., None]

# 白墙：原来被日光灯照得很亮，夜景里压暗，只留售货机照亮的部分
wall = poly_mask([(0, 196), (356, 300), (356, 1012), (0, 1012)])      # 白墙 + 顶上日光灯那一角（关灯）
glow_wall = np.exp(-(((xx - (X0 + X1) / 2) / 260.0) ** 2 + ((yy - Y0) / 110.0) ** 2))
img = img * (1 - wall[..., None] * (0.93 - 0.08 * glow_wall[..., None]))
# 左侧地砖也压暗
floor = poly_mask([(0, 1012), (362, 1012), (300, 1200), (0, 1200)])
img = img * (1 - 0.55 * floor[..., None])

# 接触阴影
shadow = np.exp(-((yy - BASE_Y) / 9.0) ** 2) * smoothstep(X0 - 30, X0, xx) * (1 - smoothstep(X1 + 10, X1 + 50, xx))
img = img * (1 - 0.75 * gauss(shadow.astype(np.float32), 4)[..., None])

# 侧板、机身、踢脚
img = img * (1 - side[..., None]) + side[..., None] * side_col
x0c = max(X0, 0)
img[Y0:Y1, x0c:X1] = vm_small[:, x0c - X0:]
img[Y1:BASE_Y, x0c:X1 - 3] = np.array([0.010, 0.010, 0.012])
door = poly_mask([(356, 300), (410, 300), (410, 1032), (356, 1032)])  # 门框在售货机侧板前面，重新盖回去
img = img * (1 - door[..., None]) + door[..., None] * orig * 0.8

# ---------------- 售货机的光：地面光斑 + 地面倒影 ----------------
light_col = np.array([0.78, 0.9, 1.0])
cx = (max(X0, 0) + X1) / 2
pool = np.exp(-(((xx - cx) / 200.0) ** 2)) * np.exp(-np.maximum(yy - BASE_Y, 0) / 70.0) * smoothstep(BASE_Y - 2, BASE_Y + 6, yy)
lit_floor = gauss(poly_mask([(0, 1012), (362, 1012), (318, 1200), (0, 1200)]), 6)
img = img + (lit_floor * pool)[..., None] * light_col * (0.9 * orig + 0.03)
refl = np.zeros_like(img)
for y in range(BASE_Y, H):
    sy = 2 * BASE_Y - y
    if Y0 <= sy < BASE_Y:
        refl[y, x0c:X1] = img[sy, x0c:X1]
refl = np.stack([ndi.gaussian_filter(refl[..., c], (10, 2)) for c in range(3)], -1)
fade = np.clip(1 - (yy - BASE_Y) / 110.0, 0, 1) ** 1.3
img = img + 0.35 * refl * fade[..., None] * lit_floor[..., None]
# 门框和墙角被售货机的冷光照到一点
spill = np.exp(-(((xx - X1) / 70.0) ** 2 + ((yy - (Y0 + BASE_Y) / 2) / 300.0) ** 2)) * (xx > X1)
img = img + spill[..., None] * light_col * 0.5 * orig

# 灯箱的冷光晕
win_canvas = np.zeros((H, W), np.float32)
wy0, wy1 = Y0 + round(0.04 * (Y1 - Y0)), Y0 + round(0.515 * (Y1 - Y0))
win_canvas[wy0:wy1, max(X0 + round(0.07 * mw_px), 0):X1 - round(0.07 * mw_px)] = 1
machine = np.zeros((H, W), np.float32)
machine[Y0:BASE_Y, max(X0, 0):X1] = 1
machine = np.maximum(machine, side)
halo = 0.07 * gauss(win_canvas, 14) + 0.045 * gauss(win_canvas, 45) + 0.025 * gauss(win_canvas, 120)
above = 0.35 + 0.65 * smoothstep(Y0 - 60, Y0 + 20, yy)               # 灯箱朝前照，机顶上方的墙只沾一点
img = img + (halo * (1 - machine) * above)[..., None] * light_col     # 光晕只落在机器外面（墙、门框、空气）

# ---------------- 夜景调色 + 泛光 ----------------
img = 0.85 * np.power(img, 1.22)                          # 压暗中间调，高光基本不动
bright = np.maximum(img - 0.55, 0)
bloom = 0.30 * gauss(bright, 5) + 0.22 * gauss(bright, 18) + 0.14 * gauss(bright, 55)
img = img + bloom
lumi = img.mean(-1, keepdims=True)
img = img * (1 + np.array([-0.06, -0.01, 0.10]) * (1 - smoothstep(0.0, 0.08, lumi)))  # 暗部偏冷
vign = 1 - 0.42 * (((xx - W * 0.5) / (W * 0.62)) ** 2 + ((yy - H * 0.55) / (H * 0.72)) ** 2)
img = img * np.clip(vign, 0, 1)[..., None]
out = to_srgb(img / (1 + 0.18 * img))
out = out + rng.normal(0, 0.010, out.shape[:2])[..., None]
Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT)
print(OUT)
