#!/usr/bin/env python3
"""B06 窗边看书的老人。

素材：一张授权照片（Shixart1985 拍的老人在窗前沙发上叼着烟斗看书，CC BY 2.0），存在 refs/。
画法：代码先把窗帘后面的窗子"找"出来（窗帘区域的亮部色阶拉开：两扇窗格留白、窗框和窗下墙面成淡灰紫），
画面中心（脸、书、手、烟斗）保留细节，四周的花靠垫、毯子先概括掉；然后用 stylize 的水彩算法
（色块概括、透明罩染、边缘积色、留白缝、颜料颗粒、铅笔底稿、四周留白）画成水彩。
用法：python3 draw.py [输出路径，默认 final.png]
"""
import os
import sys
import time

sys.dont_write_bytecode = True                      # 不在 stylize/ 下写 __pycache__
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[4] / "stylize"))
import numpy as np                                  # noqa: E402
from PIL import Image                               # noqa: E402
from scipy import ndimage as ndi                    # noqa: E402
import stylize as S                                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "refs", "elderly_man_reading_pipe_window_shixart1985.jpg")
W = 1500
SEED = 3


def load():
    im = Image.open(REF).convert("RGB")
    im = im.resize((W, round(W * im.height / im.width)), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255


def background_mask(rgb):
    """窗帘（窗子）区域：上半部分、很亮、和画面上边连通的一片。"""
    h, w = rgb.shape[:2]
    yy = np.mgrid[0:h, 0:w][0]
    Ls = ndi.gaussian_filter(rgb @ S.LUMA, 2)
    cand = (Ls > 0.82) & (yy < 540)
    lbl, _ = ndi.label(cand)
    keep = [k for k in np.unique(lbl[0]) if k != 0]
    bg = np.isin(lbl, keep)
    bg = ndi.binary_opening(ndi.binary_closing(bg, iterations=2), iterations=1)
    return ndi.gaussian_filter(bg.astype(np.float32), 1.5)


def window_structure(rgb, bg):
    """窗帘区域亮部色阶拉开：窗格仍是最亮（留白），窗框、窗下墙面露出淡灰；暗处偏冷、亮处略暖。"""
    L = rgb @ S.LUMA
    st = np.clip((L - 0.80) / 0.20, 0, 1)
    Ln = 0.66 + 0.34 * st ** 0.9
    out = np.clip(rgb * (Ln / np.maximum(L, 1e-3))[..., None], 0, 1)
    cool = np.array([0.93, 0.95, 1.04], np.float32)            # 窗框、窗下墙面：灰紫偏冷
    warm = np.array([1.02, 1.0, 0.95], np.float32)             # 窗格：一点暖的阳光
    t = st[..., None]
    out = np.clip(out * (cool * (1 - t) + warm * t), 0, 1)
    return rgb * (1 - bg[..., None]) + out * bg[..., None]


def simplify_periphery(rgb):
    """画面中心（脸、烟斗、书、手）保留细节，四周（花靠垫、毯子、椅子）先用 L0 概括，水彩里就不会碎。"""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    focus = np.exp(-(((xx - 800) / 430) ** 2 + ((yy - 470) / 390) ** 2))
    focus = np.clip(1.4 * focus, 0, 1)[..., None]
    simp = S.l0_smooth(rgb, 0.03)
    return np.clip(rgb * focus + simp * (1 - focus), 0, 1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "final.png")
    t0 = time.time()
    rgb = load()
    bg = background_mask(rgb)
    rgb = window_structure(rgb, bg)
    rgb = simplify_periphery(rgb)
    src = Image.fromarray((rgb * 255 + 0.5).astype(np.uint8))
    out = S.stylize(src, "watercolor", strength=1.0, seed=SEED, size=W,
                    params=dict(pencil=0.25, detail=0.8, vignette=0.6))
    out.save(out_path)
    print(out_path, out.size, "bg frac = %.3f" % float(bg.mean()), "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
