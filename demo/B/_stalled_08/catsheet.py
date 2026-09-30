"""找素材用（联网）：列出 Commons 分类里的照片（授权合格、长边够大），可按标题关键词过滤，拼成总览图分页。
用法: python3 catsheet.py "Category:xxx" tag [--kw "fruit|apple|jar"] [--max 400] [--minw 1200]
"""
import argparse
import json
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from search import api, info, sheet  # noqa: E402
from PIL import Image  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("cat")
ap.add_argument("tag")
ap.add_argument("--kw", default="")
ap.add_argument("--max", type=int, default=400)
ap.add_argument("--minw", type=int, default=1200)
a = ap.parse_args()
pages, cont = [], {}
while True:
    d = api(dict({"action": "query", "generator": "categorymembers", "gcmtitle": a.cat, "gcmtype": "file",
                  "gcmlimit": 50, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime|metadata",
                  "iiurlwidth": 300}, **cont))
    pages += list(d.get("query", {}).get("pages", {}).values())
    if "continue" in d and len(pages) < a.max:
        cont = d["continue"]
    else:
        break
hits = info(sorted(pages, key=lambda p: p["title"]))
hits = [h for h in hits if max(h["width"] or 0, h["height"] or 0) >= a.minw]
if a.kw:
    hits = [h for h in hits if re.search(a.kw, h["title"] + " " + h["desc"], re.I)]
print(len(pages), "files,", len(hits), "kept")
for i, h in enumerate(hits):
    print(f"#{i} {h['title'][5:90]} | {h['width']}x{h['height']} | {h['license']} | {h['artist'][:30]} | {h['camera'][:25]}")
json.dump(hits, open(f"candidates/hits_{a.tag}.json", "w"), ensure_ascii=False, indent=1)
sheet(hits, f"candidates/sheet_{a.tag}.png")
im = Image.open(f"candidates/sheet_{a.tag}.png")
H = 330
rows = im.size[1] // H
for p in range(0, rows, 7):
    im.crop((0, p * H, im.size[0], min(rows, p + 7) * H)).save(f"candidates/sheet_{a.tag}_p{p // 7}.png")
print("pages:", (rows + 6) // 7)
