"""找素材用（联网，只在找照片阶段跑；draw.py 不联网）。
用法:
  python3 search.py "关键词" [--n 24]                  # 搜 Commons，下载小缩略图到 candidates/，拼一张总览 sheet_<k>.png
  python3 search.py --get "File:xxx.jpg" [--width 2400]  # 下载原图（或指定宽度的缩略图）到 refs/，署名写进 refs/credits.json
只保留公有领域 / CC0 / CC BY / CC BY-SA；列出相机型号（EXIF）帮助确认是照片。
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "CodegenDrawingDemo/1.0 (one-off photo reference lookup for a research demo) python-urllib"}
HERE = os.path.dirname(os.path.abspath(__file__))
OK = ("public domain", "cc0", "cc by", "cc-by", "pd")


def fetch(url, timeout=60):
    """带退避重试的 GET（Commons 限流时返回 429）。"""
    import time
    for k in range(7):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or k == 6:
                raise
            wait = float(e.headers.get("Retry-After") or 0) or 4 * 2 ** k
            print(f"  限流 {e.code}，等 {wait:.0f} 秒", file=sys.stderr)
            time.sleep(min(wait, 90))


def api(params):
    q = urllib.parse.urlencode(dict(params, format="json"))
    return json.loads(fetch(f"{API}?{q}"))


def strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def info(pages):
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        low = lic.lower()
        if not low.startswith(OK) or "nc" in low.split("-") or "nd" in low.split("-"):
            continue
        if ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        exif = {m["name"]: m["value"] for m in (ii.get("metadata") or []) if isinstance(m, dict) and "name" in m}
        cam = " ".join(str(exif.get(k, "")) for k in ("Make", "Model")).strip()
        out.append(dict(title=p["title"], thumb=ii.get("thumburl"), url=ii.get("url"), width=ii.get("width"),
                        height=ii.get("height"), license=lic, license_url=meta.get("LicenseUrl", {}).get("value", ""),
                        artist=strip(meta.get("Artist", {}).get("value", "")),
                        credit=strip(meta.get("Credit", {}).get("value", "")),
                        desc=strip(meta.get("ImageDescription", {}).get("value", ""))[:160],
                        cats=meta.get("Categories", {}).get("value", "")[:200], camera=cam,
                        page=ii.get("descriptionurl", "")))
    return out


def search(query, n):
    d = api({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrsearch": f"{query} filetype:bitmap",
             "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime|metadata", "iiurlwidth": 300})
    pages = sorted(d.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    return info(pages)


def sheet(hits, path):
    cells = []
    for i, h in enumerate(hits):
        try:
            im = Image.open(io.BytesIO(fetch(h["thumb"]))).convert("RGB")
            __import__("time").sleep(0.3)
        except Exception as e:  # noqa: BLE001
            print("skip", h["title"], e, file=sys.stderr)
            continue
        im.thumbnail((360, 300))
        cells.append((i, im))
    cols = 4
    W, H = 370, 330
    rows = (len(cells) + cols - 1) // cols
    sh = Image.new("RGB", (cols * W, max(1, rows) * H), "white")
    dr = ImageDraw.Draw(sh)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for k, (i, im) in enumerate(cells):
        x, y = (k % cols) * W + 5, (k // cols) * H + 26
        sh.paste(im, (x, y))
        dr.text((x, y - 24), f"#{i}", fill="red", font=font)
    sh.save(path)


def get(title, width):
    q = {"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime|metadata"}
    if width:
        q["iiurlwidth"] = width
    d = api(q)
    h = info(list(d["query"]["pages"].values()))
    if not h:
        sys.exit("授权不合要求或文件不存在：" + title)
    h = h[0]
    src = h["url"] if not width or width >= h["width"] else h["thumb"]
    os.makedirs(os.path.join(HERE, "refs"), exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", title.split(":", 1)[1])
    data = fetch(src, 180)
    open(os.path.join(HERE, "refs", name), "wb").write(data)
    cj = os.path.join(HERE, "refs", "credits.json")
    cr = json.load(open(cj)) if os.path.exists(cj) else {}
    cr[name] = dict(title=h["title"], author=h["artist"], license=h["license"], license_url=h["license_url"],
                    url=h["page"], credit=h["credit"], camera=h["camera"], downloaded_from=src)
    json.dump(cr, open(cj, "w"), ensure_ascii=False, indent=1)
    print(name, len(data), "bytes", h["width"], "x", h["height"], h["license"], "|", h["artist"], "|", h["camera"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--tag", default="0")
    ap.add_argument("--get")
    ap.add_argument("--width", type=int, default=0)
    a = ap.parse_args()
    if a.get:
        get(a.get, a.width)
        sys.exit()
    hits = search(a.query, a.n)
    os.makedirs(os.path.join(HERE, "candidates"), exist_ok=True)
    for i, h in enumerate(hits):
        print(f"#{i} {h['title']} | {h['width']}x{h['height']} | {h['license']} | {h['artist'][:40]} | cam: {h['camera'][:30]}")
        print(f"     {h['desc'][:150]}")
    json.dump(hits, open(os.path.join(HERE, "candidates", f"hits_{a.tag}.json"), "w"), ensure_ascii=False, indent=1)
    sheet(hits, os.path.join(HERE, "candidates", f"sheet_{a.tag}.png"))
