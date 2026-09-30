"""给每张图打分（评测专用，需要 torch + open_clip；画图时不允许用）。

- 题目匹配：CLIP ViT-L/14 把图和 12 个英文题目比，记 (1) 和自己题目的相似度 ×100，(2) 自己题目在 12 个里排第几。
  排第 1 = CLIP 能从 12 个题目里认出这张图画的是哪个。
- 美学分：LAION improved-aesthetic-predictor（1–10）。
对照组：每题第一轮的图（看改图有没有用）、B 赛道下载的原始照片（没经过代码处理）。

用法: python score.py      # 输出 scores.json 并打印汇总
"""
import glob
import json
import os
import sys

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("STYLIZE_DIR", os.path.join(os.path.dirname(HERE), "stylize")))
from eval_style import Scorer  # noqa: E402
import open_clip  # noqa: E402

P = json.load(open(os.path.join(HERE, "prompts.json")))["prompts"]
IDS = [p["id"] for p in P]


def main():
    sc = Scorer()
    tok = open_clip.get_tokenizer("ViT-L-14")
    with torch.no_grad():
        T = sc.model.encode_text(tok([p["en"] for p in P]).to(sc.dev)).float()
        T = T / T.norm(dim=-1, keepdim=True)

    def score(path, pid):
        e = sc.embed(Image.open(path).convert("RGB"))
        m = e.mean(0)
        m = m / m.norm()
        sims = (m @ T.T).cpu().numpy()
        k = IDS.index(pid)
        return {"clip": round(float(sims[k] * 100), 2), "rank": int((sims > sims[k]).sum()) + 1,
                "top": IDS[int(sims.argmax())], "aes": round(float(sc.aes(e).mean()), 3)}

    out = []
    for track in ("A", "B"):
        for d in sorted(glob.glob(os.path.join(HERE, track, "[0-9][0-9]"))):
            pid = os.path.basename(d)
            fin = os.path.join(d, "final.png")
            if not os.path.exists(fin):
                continue
            row = {"id": f"{track}{pid}", "track": track, "prompt": pid, "final": score(fin, pid)}
            r1 = os.path.join(d, "rounds", "r1.png")
            if os.path.exists(r1):
                row["round1"] = score(r1, pid)
            if track == "B":
                refs = sorted(glob.glob(os.path.join(d, "refs", "*")))
                refs = [r for r in refs if r.lower().endswith((".jpg", ".jpeg", ".png"))]
                row["refs"] = [dict(file=os.path.basename(r), **score(r, pid)) for r in refs]
            out.append(row)
    json.dump(out, open(os.path.join(HERE, "scores.json"), "w"), ensure_ascii=False, indent=1)

    def summ(rows, key):
        v = [r[key] for r in rows if key in r]
        if not v:
            return "–"
        return (f"n={len(v)}  认对 {sum(x['rank'] == 1 for x in v)}/{len(v)}  平均排名 {np.mean([x['rank'] for x in v]):.2f}"
                f"  相似度 {np.mean([x['clip'] for x in v]):.1f}  美学 {np.mean([x['aes'] for x in v]):.2f}")
    for track in ("A", "B"):
        rows = [r for r in out if r["track"] == track]
        print(f"{track} 最终图  {summ(rows, 'final')}")
        print(f"{track} 第一轮  {summ(rows, 'round1')}")
    refs = [x for r in out if r["track"] == "B" for x in r.get("refs", [])[:1]]
    if refs:
        print(f"B 原始照片（每题第一张）  n={len(refs)}  认对 {sum(x['rank'] == 1 for x in refs)}/{len(refs)}"
              f"  相似度 {np.mean([x['clip'] for x in refs]):.1f}  美学 {np.mean([x['aes'] for x in refs]):.2f}")
    for r in out:
        f = r["final"]
        print(f"  {r['id']}  排名 {f['rank']:2d}（最像 {f['top']}）  相似度 {f['clip']:.1f}  美学 {f['aes']:.2f}"
              + (f"   第一轮：排名 {r['round1']['rank']} 相似度 {r['round1']['clip']:.1f}" if "round1" in r else ""))


if __name__ == "__main__":
    main()
