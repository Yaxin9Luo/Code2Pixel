"""stylize.py 的回归测试：每种风格在各种输入上都能跑通，输出尺寸和取值正确；
SVG 栅格化与 Chrome 渲染一致；颜色都是合法的十六进制。

用法: python3 test_stylize.py [--quick]   （--quick 跳过几何抽象和 Chrome 对比）
"""
import os
import re
import sys
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import stylize  # noqa: E402

QUICK = "--quick" in sys.argv


def inputs():
    photo = Image.open(os.path.join(HERE, "photos", "bison.jpg"))
    yield "photo", photo
    yield "tiny", photo.resize((64, 42))
    yield "gray", photo.convert("L")
    rgba = photo.convert("RGBA")
    rgba.putalpha(128)
    yield "rgba", rgba
    yield "panorama", Image.open(os.path.join(os.path.dirname(HERE), "target.png"))
    yield "flat", Image.new("RGB", (300, 200), (200, 210, 230))


def check_svg(svg):
    cols = re.findall(r'fill="#([^"]*)"', svg)
    bad = [c for c in cols if not re.fullmatch(r"[0-9a-f]{6}", c)]
    assert not bad, f"非法颜色 {bad[:5]}"


def main():
    fails = 0
    for style in stylize.STYLES:
        if QUICK and style == "geometric":
            continue
        for name, img in inputs():
            t0 = time.time()
            try:
                out = stylize.stylize(img, style, size=512)
                if isinstance(out, str):
                    check_svg(out)
                    out = stylize.svg_to_image(out)
                arr = np.asarray(out.convert("RGB"))
                k = min(1.0, 512 / max(img.size))
                exp = (round(img.width * k), round(img.height * k))
                assert abs(out.width - exp[0]) <= 1 and abs(out.height - exp[1]) <= 1, f"尺寸 {out.size} ≠ {exp}"
                assert np.isfinite(arr).all() and arr.std() > 0 or name == "flat", "输出是常数图"
                print(f"ok   {style:10s} {name:9s} {out.size} {time.time() - t0:.2f}s")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {style:10s} {name:9s} {type(e).__name__}: {e}")
    if not QUICK:
        # SVG 栅格化 vs Chrome：同一个 SVG，两种渲染的 PSNR
        from evaluate import chrome_render, psnr
        prof = tempfile.mkdtemp(prefix="chrome-profile-")
        photo = Image.open(os.path.join(HERE, "photos", "portrait_obama.jpg"))
        for style in ("lowpoly", "geometric"):
            svg = stylize.stylize(photo, style, size=512)
            with tempfile.TemporaryDirectory() as td:
                sp = os.path.join(td, "x.svg")
                open(sp, "w").write(svg)
                im = stylize.svg_to_image(svg)
                ref = chrome_render(sp, im.width, im.height, os.path.join(td, "x.png"), prof)
            p = psnr(np.asarray(im, np.float32) / 255, ref)
            ok = p > 30
            fails += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {style:10s} SVG 栅格化 vs Chrome：PSNR {p:.1f} dB")
    print("全部通过" if fails == 0 else f"{fails} 项失败")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
