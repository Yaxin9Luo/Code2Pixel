#!/usr/bin/env python3
"""B10 中国水墨画：月下孤舟。

素材（都是照片，存在 refs/）：
  - 漓江雾中的喀斯特山峰（Dcrjsr，CC BY-SA 3.0）→ 远山
  - 布拉马普特拉河上划船人的剪影（Inu Etc，CC BY-SA 4.0）→ 小船和船夫
  - 逆光的芦苇（Keven Law，CC BY-SA 2.0）→ 左下角近景的芦苇
画法：三张照片各取一部分，换算成"墨的浓度"，再按水墨画的章法重新布局：左边远山，山脚和两端隐入云雾；
右上一轮月亮（烘云托月：月亮留白，四周淡墨渲染）；中下方大片水面留白，一叶小舟，月影在水面上碎成一道；
左下角几枝芦苇。远山用没骨法：墨色软量化成几层，交界处积墨，浓淡不匀，沿纸纤维洇开，
山脊用 stylize 的水墨笔触内核（mode 1）顺着流线 DoG 勾几笔干笔；船和芦苇是剪影直接落墨；天和水是淡墨渲染，
水纹是代码画的两头尖的短横笔。最后铺宣纸纹理，题字（孟浩然"江清月近人"，用系统自带的行楷字体排），
盖朱文印（代码画的印）。
用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys

sys.dont_write_bytecode = True                      # 不在 stylize/ 下写 __pycache__
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
import numpy as np                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont         # noqa: E402
from scipy import ndimage as ndi                    # noqa: E402
import stylize as S                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF_HILLS = os.path.join(HERE, "refs", "li_river_hills_in_mist_dcrjsr.jpg")
REF_BOAT = os.path.join(HERE, "refs", "brahmaputra_fisherman_boat_silhouette_inu_etc.jpg")
REF_REEDS = os.path.join(HERE, "refs", "reeds_through_the_reeds_keven_law.jpg")
W, H = 1500, 1000
s = W / 1600.0
SEED = 11
MOON = (1150.0, 190.0, 56.0)                        # 月亮圆心 x, y, 半径
PAPER = (0.95, 0.925, 0.87)
INK = np.array([0.08, 0.075, 0.07], np.float32)
FONTS = ["/System/Library/AssetsV2/com_apple_MobileAsset_Font8/13b8ce423f920875b28b551f9406bf1014e0a656.asset/"
         "AssetData/Xingkai.ttc",
         "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/88d6cc32a907955efa1d014207889413890573be.asset/"
         "AssetData/Kaiti.ttc",
         "/System/Library/Fonts/Supplemental/Songti.ttc"]

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)


def lum(path):
    return np.asarray(Image.open(path).convert("RGB"), np.float32) @ (S.LUMA / 255.0)


def place(src, scale, x0, y0):
    """把 src（浮点二维图）缩放 scale 倍后贴到画布坐标 (x0, y0)，返回画布大小的图（其余为 0）。"""
    h, w = src.shape
    im = Image.fromarray(src.astype(np.float32), mode="F").resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    a = np.asarray(im, np.float32)
    out = np.zeros((H, W), np.float32)
    X0, Y0 = int(round(x0)), int(round(y0))
    xs, ys = max(0, X0), max(0, Y0)
    xe, ye = min(W, X0 + a.shape[1]), min(H, Y0 + a.shape[0])
    out[ys:ye, xs:xe] = a[ys - Y0:ye - Y0, xs - X0:xe - X0]
    return np.clip(out, 0, 1)


def hills_target():
    """远山：照片里雾中山峰（原图 y 430–980），比天空暗多少就上多少墨；山脚（竹林之上）渐渐隐入雾里。"""
    L = lum(REF_HILLS)[430:980]
    sky = ndi.gaussian_filter1d(np.median(L[:50], axis=0), 40)
    d = np.clip((sky[None, :] - L) / 0.30, 0, 1) ** 1.1
    y = np.arange(430, 980, dtype=np.float32)[:, None]
    x = np.arange(L.shape[1], dtype=np.float32)[None, :]
    rng = np.random.default_rng(5)
    wob = ndi.gaussian_filter1d(rng.normal(0, 60, L.shape[0]), 25)[:, None]      # 雾的边缘不齐
    wy = ndi.gaussian_filter1d(rng.normal(0, 90, L.shape[1]), 60)[None, :]      # 雾线沿 x 起伏
    fade = S.smoothstep(975, 740, y + wy) * S.smoothstep(40, 260, x + wob) * S.smoothstep(2540, 2250, x + wob)
    # 山体和"隐入雾里"分开返回：墨色分层只作用在山体上，雾是平滑的渐隐，不会出一圈圈等高线
    return place(d, 1080 / 2560, -40, 318), place(fade, 1080 / 2560, -40, 318)


def boat_target():
    """小船：剪影照片（原图 x 1120–1560，y 1180–1430）。暗的地方就是墨；去掉横穿船头的远岸细线；
    水线（y≈1345）以下是倒影，只留三成墨并很快淡掉。"""
    L = lum(REF_BOAT)
    x0, x1, y0, y1 = 1120, 1560, 1180, 1430
    c = L[y0:y1, x0:x1]
    dark = S.smoothstep(0.42, 0.12, c)
    ys = np.arange(y0, y1)[:, None]
    xs = np.arange(x0, x1)[None, :]
    band = (ys >= 1226) & (ys <= 1252)
    below = np.zeros_like(dark)
    below[:-22] = dark[22:]                                  # 远岸线约 16 像素粗：往下 22 像素还是暗的才是船身
    keep = ((below > 0.5) & (xs >= 1158)) | ((xs >= 1390) & (xs <= 1475))
    dark = np.where(band & ~keep, 0, dark)
    wl = 1345
    refl = S.smoothstep(wl + 2, wl - 2, ys.astype(np.float32))
    fade = 0.22 * S.smoothstep(wl + 70, wl, ys.astype(np.float32)) * (1 - refl)
    d = dark * (refl + fade)
    return place(d, 0.5, 870, 735 - (wl - y0) * 0.5)


def reeds_ink(seed):
    """近景芦苇：逆光照片里比背景暗的细茎和苇穗（形态学闭运算估出背景，减去原图就是细暗的结构），
    只取上半部分稀疏的茎和穗，下半部分密的草丛渐渐淡掉，放在左下角。"""
    L = lum(REF_REEDS)[40:1111, 0:660]
    bgd = ndi.gaussian_filter(ndi.grey_closing(L, size=(17, 17)), 6)
    d = np.clip((bgd - L) / 0.22, 0, 1)
    d = S.smoothstep(0.12, 0.45, d)                                                  # 去掉天空本身的起伏（否则整块是灰的）
    y = np.arange(40, 1111, dtype=np.float32)[:, None]
    x = np.arange(0, 660, dtype=np.float32)[None, :]
    d *= S.smoothstep(1000, 700, y) * S.smoothstep(40, 90, y) * S.smoothstep(0, 30, x) * S.smoothstep(660, 560, x)
    d = place(d, 0.40, 10, 600)
    tex = 0.8 + 0.2 * S.fbm(H, W, 5, 2, seed + 70)
    d = np.clip(0.78 * d ** 0.9 * tex, 0, 0.9)
    return np.maximum(d, 0.35 * ndi.gaussian_filter(d, 1.5))                       # 一点洇


def flow(target):
    tx, ty, coh = S.flow_field(ndi.gaussian_filter(target, 3.0), s, sigma=2.0, rho=6.0)
    flat = 1 - S.smoothstep(0.05, 0.3, coh) * S.smoothstep(0.01, 0.05, ndi.gaussian_filter(target, 4))
    flip = tx < 0
    tx, ty = np.where(flip, -tx, tx), np.where(flip, -ty, ty)
    tx, ty = (1 - flat) * tx + flat, (1 - flat) * ty
    n = np.hypot(tx, ty) + 1e-6
    return (tx / n).astype(np.float32), (ty / n).astype(np.float32)


def brush_hills(target, fade, seed):
    """远山用没骨法：照片的明暗换成墨色，软量化成几层墨（墨分五色），每层交界处积一点墨（水痕），
    墨色有浓淡不匀，沿纸纤维洇开；离得近、墨重的山脊再用淡墨勾一笔。"""
    tx, ty = flow(target)
    t = ndi.gaussian_filter(target, 1.2)
    d = S.soft_quantize(np.clip(0.8 * t, 0, 0.8), [0.0, 0.07, 0.16, 0.28, 0.42, 0.58, 0.8], soft=0.32)
    gm = ndi.gaussian_gradient_magnitude(d, 1.0)
    d = d + 0.25 * np.clip(gm / 0.03, 0, 1) * S.smoothstep(0.02, 0.1, d)            # 水痕
    d *= 0.88 + 0.24 * S.fbm(H, W, 10 * s, 3, seed + 3)                             # 浓淡不匀
    d *= 0.92 + 0.16 * S.fbm(H, W, 60 * s, 3, seed + 4)
    d *= ndi.gaussian_filter(fade, 1.0)                                               # 山脚、两端平滑地隐入雾里
    fib = np.random.default_rng(seed + 9).random((H, W)).astype(np.float32)
    fib = ndi.gaussian_filter(fib, (0.5 * s, 3 * s)) + ndi.gaussian_filter(fib, (3 * s, 0.5 * s))
    fib = S.smoothstep(0.95, 1.05, fib / fib.mean())
    wash = np.maximum(d, 1.15 * ndi.gaussian_filter(d, 2.5 * s) * fib)                 # 洇
    # 勾：流线 DoG 找山的轮廓，按轮廓一笔笔勾；淡的远山几乎不勾
    A = 1 - ndi.gaussian_filter(target, 1.0)
    E = S.fdog(A, tx, ty, s, sigma_c=1.2, sigma_m=3.0, tau=0.55)
    gmA = ndi.gaussian_gradient_magnitude(A, 2.0 * s)
    lref = (1 - E) * S.smoothstep(0.01, 0.04, gmA) * S.smoothstep(0.25, 0.55, ndi.gaussian_filter(target, 3))
    lref *= S.smoothstep(0.6, 0.95, fade)                                             # 雾里的部分不勾
    lref = np.clip(ndi.gaussian_filter(lref, 0.6 * s) * 1.3, 0, 0.8).astype(np.float32)
    lines = np.zeros((H, W), np.float32)
    S.paint_layer(lref, lines, tx, ty, 1, seed * 31 + 7, R=max(0.8, 1.2 * s), step=max(1.5, 2.5 * s),
                  grid=max(2, int(3 * s)), T=0.08, min_len=3, max_len=24, fc=0.8, stop=0.3, rj_lo=0.7, rj_hi=1.5,
                  tin=0.2, tout=0.35, op=1.0, grad=0.3, dry_p=0.5, dry=0.55, soft=0.15, bristle=0.3, deplete=0.3)
    return np.clip(1 - (1 - wash) * (1 - 0.28 * lines), 0, 1)


def boat_ink(target, seed):
    """小船用浓墨直接落：剪影本身 + 一点笔触的浓淡和干湿。"""
    tex = 0.85 + 0.15 * S.fbm(H, W, 6, 3, seed + 21)
    edge = np.clip(target - ndi.gaussian_filter(target, 1.5), 0, 1)
    d = np.clip(0.92 * target * tex + 0.3 * edge, 0, 0.95)
    return ndi.gaussian_filter(d, 0.5)


def sky_wash(seed):
    """天：淡墨渲染，越往上越重，靠近地平线淡成雾；月亮留白，月边的墨略重，把月亮托出来。"""
    mx, my, r = MOON
    dist = np.hypot(xx - mx, yy - my)
    moon = S.smoothstep(r + 1.5, r - 1.5, dist)
    w = 0.09 + 0.07 * S.smoothstep(560, 0, yy)
    w *= 1 + 0.35 * (S.fbm(H, W, 160, 4, seed + 30) - 0.5) * 2
    w += 0.07 * np.exp(-np.clip(dist - r, 0, None) / 40) * (dist > r)
    w *= S.smoothstep(600, 450, yy)
    w *= 1 - moon
    return np.clip(w, 0, 1), moon


def water_wash(seed):
    """水：大片留白，只有很淡的横向水纹；月亮在水里的倒影是一道断断续续的白。"""
    mx = MOON[0]
    small = S.fbm(H, W // 10, 6, 3, seed + 40)
    streak = np.asarray(Image.fromarray(small, mode="F").resize((W, H), Image.BICUBIC), np.float32)
    w = 0.028 * S.smoothstep(560, 680, yy) * (1 + 0.9 * (streak - 0.5) * 2)
    w *= S.smoothstep(1000, 820, yy) * 0.6 + 0.4
    half = 18 + 22 * np.clip((yy - 600) / 300, 0, 1)
    path = S.smoothstep(half + 6, half - 6, np.abs(xx - mx)) * S.smoothstep(595, 620, yy) * S.smoothstep(900, 820, yy)
    dashes = S.smoothstep(0.42, 0.58, streak)
    w *= 1 - path * dashes
    return np.clip(w, 0, 1)


def ripples(seed):
    """水纹：月影两侧和船边几道淡墨短横笔，两头尖、中间粗，略带弧度。"""
    rng = np.random.default_rng(seed + 50)
    k = 3
    im = Image.new("L", (W * k, H * k), 0)
    dr = ImageDraw.Draw(im)

    def stroke(x, y, L, t, val):
        n = 12
        u = np.linspace(-1, 1, n)
        th = t * (1 - u ** 2) ** 0.7 + 0.3
        bend = rng.uniform(-1.5, 1.5) * (1 - u ** 2)
        xs = x + u * L / 2
        top = [(k * xi, k * (y + b - ti)) for xi, b, ti in zip(xs, bend, th)]
        bot = [(k * xi, k * (y + b + ti)) for xi, b, ti in zip(xs[::-1], bend[::-1], th[::-1])]
        dr.polygon(top + bot, fill=int(val))

    mx = MOON[0]
    for _ in range(16):
        y = rng.uniform(630, 870)
        half = 18 + 22 * np.clip((y - 600) / 300, 0, 1)
        side = rng.choice([-1, 1])
        stroke(mx + side * (half + rng.uniform(0, 30)), y, rng.uniform(20, 70), rng.uniform(0.8, 1.8), rng.uniform(80, 160))
    for _ in range(7):                                    # 船底一带
        stroke(rng.uniform(880, 1090), rng.uniform(740, 762), rng.uniform(30, 90), rng.uniform(0.8, 1.6),
               rng.uniform(70, 140))
    a = np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255
    return 0.5 * a * (0.7 + 0.3 * S.fbm(H, W, 8, 2, seed + 51))


def inscription(seed):
    """题字：孟浩然《宿建德江》"江清月近人"，竖排；字的墨色随纸纹有点浓淡。"""
    text = "江清月近人"
    size = 54
    font = None
    for p in FONTS:
        try:
            font = ImageFont.truetype(p, size)
            break
        except OSError:
            continue
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    x, y = 1395, 70
    for ch in text:
        dr.text((x, y), ch, fill=255, font=font)
        y += int(size * 1.08)
    a = np.asarray(im, np.float32) / 255
    a = a * (0.8 + 0.2 * S.fbm(H, W, 5, 2, seed + 60))
    return np.clip(a * 0.9, 0, 1), y


def seal(out, x0, y0, S0, seed):
    """朱文印：红底白字"孤舟"，边缘残破一点。"""
    font = None
    for p in FONTS[1:]:
        try:
            font = ImageFont.truetype(p, int(S0 * 0.42))
            break
        except OSError:
            continue
    m = Image.new("L", (S0, S0), 0)
    dr = ImageDraw.Draw(m)
    dr.rectangle([0, 0, S0 - 1, S0 - 1], fill=255)
    cs = int(S0 * 0.42)
    for i, ch in enumerate("孤舟"):
        dr.text((S0 // 2 - cs // 2, int(S0 * 0.06) + i * int(S0 * 0.46)), ch, fill=0, font=font)
    a = np.asarray(m, np.float32) / 255
    rng = np.random.default_rng(seed + 99)
    a *= (rng.random(a.shape) > 0.05) * (S.fbm(S0, S0, S0 / 6, 3, seed + 98) > 0.25)
    a = ndi.gaussian_filter(a, 0.6)
    red = np.array([0.72, 0.16, 0.12], np.float32)
    reg = out[y0:y0 + S0, x0:x0 + S0]
    out[y0:y0 + S0, x0:x0 + S0] = reg * (1 - 0.88 * a[..., None]) + red * reg * 1.05 * (0.88 * a[..., None])
    return out


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    hills, fade = hills_target()
    boat = boat_target()
    a_hills = brush_hills(hills, fade, SEED)
    a_boat = boat_ink(boat, SEED)
    a_sky, moon = sky_wash(SEED)
    a_water = water_wash(SEED)
    a_rip = ripples(SEED)
    a_reed = reeds_ink(SEED)
    a_txt, ty_end = inscription(SEED)
    T = (1 - a_hills) * (1 - a_boat) * (1 - a_sky) * (1 - a_water) * (1 - a_rip) * (1 - a_txt) * (1 - a_reed)
    alpha = np.clip(1 - T, 0, 0.96)
    paper = S.paper_texture(H, W, s, SEED + 10, PAPER)
    out = paper * (1 - alpha[..., None]) + INK * alpha[..., None]
    out = seal(out, 1398, ty_end + 14, 52, SEED)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(out_path)
    print(out_path, (W, H), "hills max %.2f boat max %.2f" % (hills.max(), boat.max()))


if __name__ == "__main__":
    main()
