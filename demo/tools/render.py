"""把 SVG 或 HTML（含 <canvas> + JS）用 headless Chrome 渲染成 PNG。

用法:
  python3 render.py in.svg out.png                 # SVG 不给尺寸时读 <svg width= height=>
  python3 render.py in.html out.png --width 1536 --height 1024
每次调用用独立的临时 Chrome 配置目录，可以多个进程同时跑。JS 最多给 10 秒虚拟时间执行完再截图。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def render(src, out, width=None, height=None, timeout=120):
    src = os.path.abspath(src)
    if width is None or height is None:
        head = open(src, encoding="utf-8", errors="ignore").read(4000)
        m_w = re.search(r'<svg[^>]*\swidth="([0-9.]+)', head)
        m_h = re.search(r'<svg[^>]*\sheight="([0-9.]+)', head)
        if not (m_w and m_h):
            sys.exit("需要 --width/--height（或 SVG 根元素上写 width/height）")
        width, height = int(float(m_w.group(1))), int(float(m_h.group(1)))
    out = os.path.abspath(out)
    if os.path.exists(out):
        os.remove(out)
    profile = tempfile.mkdtemp(prefix="chrome-render-")
    # 页面默认有 8px 边距：SVG 直接打开没有边距；HTML 请自己写 body{margin:0}
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                          "--virtual-time-budget=10000", f"--user-data-dir={profile}",
                          f"--window-size={width},{height}", f"--screenshot={out}", "file://" + src],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last, t0 = -1, time.time()
    while time.time() - t0 < timeout:          # macOS 上 headless Chrome 截完图有时不退出：等文件写完就结束
        time.sleep(0.5)
        size = os.path.getsize(out) if os.path.exists(out) else -1
        if size > 0 and size == last:
            break
        last = size
    p.terminate()
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
    shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(out):
        sys.exit("渲染失败：没有生成截图")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--width", type=int)
    ap.add_argument("--height", type=int)
    a = ap.parse_args()
    print(render(a.src, a.out, a.width, a.height))
