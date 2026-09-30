"""风格化结果打分（评测专用，需要 torch + open_clip，不是 stylize.py 的依赖）。

三个分数，都在 8 张测试照片上取平均：
  风格分 style : CLIP ViT-L/14 零样本分类，目标风格在一组"画种"里的概率。
                 类别里放了"加了滤镜的照片"和"照片"，照片套滤镜的假画会被分到这两类。
  内容分 content: 结果和原照片的 CLIP 图像向量余弦相似度（看不看得出是同一个场景）。
  美学分 aes    : LAION improved-aesthetic-predictor（CLIP ViT-L/14 向量上的小 MLP，1–10 分）。
每张图取长边方向左/中/右三个方形裁块分别算，再平均。

用法:
  python eval_style.py ink out/ink/v2          # 给一个结果目录打分（目录里是 <照片名>.png）
  python eval_style.py --calibrate             # 校准：参考画、原照片、v1 结果各自的分数
环境变量 EVAL_CACHE 指定模型缓存目录。
"""
import argparse
import glob
import os
import sys
import urllib.request

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("EVAL_CACHE", os.path.join(HERE, ".eval_cache"))
os.environ.setdefault("HF_HOME", os.path.join(CACHE, "hf"))
import open_clip  # noqa: E402

AES_URL = ("https://github.com/christophschuhmann/improved-aesthetic-predictor/raw/main/"
           "sac+logos+ava1-l14-linearMSE.pth")

# 画种类别：键是 stylize.py 里的风格名（或参照类），值是几种说法（取平均向量）
MEDIA = {
    "photo": ["a photograph", "a photo taken with a camera", "a high quality photo"],
    "filtered_photo": ["a photo with an artistic filter applied", "a photo processed with a photoshop effect",
                       "a noisy, posterized photo"],
    "ink": ["a Chinese ink wash painting", "a sumi-e ink painting on rice paper", "a traditional ink and brush painting"],
    "watercolor": ["a watercolor painting", "a loose watercolor sketch on paper", "an aquarelle painting"],
    "lowpoly": ["a low poly illustration", "a low polygon geometric artwork made of flat triangles",
                "a faceted triangulated vector art"],
    "oil": ["an oil painting", "an impasto oil painting with visible brush strokes", "an oil on canvas painting"],
    "pencil": ["a pencil sketch", "a graphite pencil drawing", "a hand-drawn pencil illustration"],
    "cartoon": ["a cartoon illustration", "an anime style drawing with flat colors", "a cel-shaded cartoon"],
    "geometric": ["an abstract geometric artwork of overlapping translucent triangles",
                  "a vector art made of many transparent polygons", "a primitive shapes abstract picture"],
    "digital": ["a digital painting", "a concept art illustration", "a 3D render"],
}
TEMPLATES = ["{}.", "{} of a scene.", "an image that looks like {}."]


class Scorer:
    def __init__(self, device=None):
        self.dev = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model, _, self.pre = open_clip.create_model_and_transforms(
            "ViT-L-14", pretrained="openai", cache_dir=os.path.join(CACHE, "clip"))
        self.model = self.model.to(self.dev).eval()
        tok = open_clip.get_tokenizer("ViT-L-14")
        names, vecs = [], []
        with torch.no_grad():
            for k, phrases in MEDIA.items():
                texts = [t.format(p) for p in phrases for t in TEMPLATES]
                e = self.model.encode_text(tok(texts).to(self.dev)).float()
                e = e / e.norm(dim=-1, keepdim=True)
                m = e.mean(0)
                vecs.append(m / m.norm())
                names.append(k)
        self.names, self.text = names, torch.stack(vecs)
        self.aes = self._aesthetic()

    def _aesthetic(self):
        path = os.path.join(CACHE, "aesthetic_l14_linearMSE.pth")
        if not os.path.exists(path):
            os.makedirs(CACHE, exist_ok=True)
            urllib.request.urlretrieve(AES_URL, path)
        sd = torch.load(path, map_location="cpu")
        net = torch.nn.Sequential(
            torch.nn.Linear(768, 1024), torch.nn.Dropout(0.2), torch.nn.Linear(1024, 128), torch.nn.Dropout(0.2),
            torch.nn.Linear(128, 64), torch.nn.Dropout(0.1), torch.nn.Linear(64, 16), torch.nn.Linear(16, 1))
        net.load_state_dict({k.replace("layers.", ""): v for k, v in sd.items()})
        return net.to(self.dev).eval()

    @staticmethod
    def crops(img):
        """长边方向取左/中/右三个方形块（短边不裁）。"""
        w, h = img.size
        s = min(w, h)
        if w >= h:
            xs = sorted({0, (w - s) // 2, w - s})
            return [img.crop((x, 0, x + s, s)) for x in xs]
        ys = sorted({0, (h - s) // 2, h - s})
        return [img.crop((0, y, s, y + s)) for y in ys]

    @torch.no_grad()
    def embed(self, img):
        """返回这张图各裁块的单位向量 (n, 768)。"""
        x = torch.stack([self.pre(c.convert("RGB")) for c in self.crops(img)]).to(self.dev)
        e = self.model.encode_image(x).float()
        return e / e.norm(dim=-1, keepdim=True)

    @torch.no_grad()
    def score(self, img, style, ref=None):
        e = self.embed(img)
        probs = (100.0 * e @ self.text.T).softmax(-1).mean(0).cpu().numpy()
        out = {"style": float(probs[self.names.index(style)]) if style in self.names else float("nan"),
               "aes": float(self.aes(e).mean().cpu()),
               "top": self.names[int(probs.argmax())]}
        out["probs"] = dict(zip(self.names, probs.round(3).tolist()))
        if ref is not None:
            r = self.embed(ref)
            out["content"] = float((e * r).sum(-1).mean().cpu())
        return out


def score_dir(sc, style, d, photos):
    rows = []
    for p in photos:
        name = os.path.splitext(os.path.basename(p))[0]
        q = os.path.join(d, name + ".png")
        if not os.path.exists(q):
            continue
        rows.append((name, sc.score(Image.open(q), style, Image.open(p))))
    return rows


def summarize(label, rows, show=True):
    st = np.mean([r["style"] for _, r in rows])
    ct = np.mean([r.get("content", np.nan) for _, r in rows])
    ae = np.mean([r["aes"] for _, r in rows])
    if show:
        for name, r in rows:
            print(f"  {name:18s} style {r['style']:.3f}  content {r.get('content', float('nan')):.3f}  "
                  f"aes {r['aes']:.2f}  top={r['top']}")
    print(f"{label}: style {st:.3f}  content {ct:.3f}  aes {ae:.2f}  (n={len(rows)})")
    return st, ct, ae


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("style", nargs="?")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    sc = Scorer()
    photos = sorted(glob.glob(os.path.join(HERE, "photos", "*.jpg")))
    if a.calibrate:
        for kind in ("ink", "watercolor"):
            rows = [(os.path.basename(p), sc.score(Image.open(p), kind))
                    for p in sorted(glob.glob(os.path.join(HERE, "refs", kind, "*.jpg")))]
            summarize(f"参考画 {kind}", rows)
        rows = [(os.path.basename(p), sc.score(Image.open(p), "photo", Image.open(p))) for p in photos]
        summarize("原照片（style=photo 概率）", rows)
        for style in ("ink", "watercolor", "lowpoly"):
            d = os.path.join(HERE, "out", style, "v1")
            if os.path.isdir(d):
                summarize(f"v1 {style}", score_dir(sc, style, d, photos))
        return
    rows = score_dir(sc, a.style, a.dir, photos)
    st, ct, ae = summarize(f"{a.style} {a.dir}", rows)
    with open(os.path.join(HERE, "results.tsv"), "a") as f:
        tag = os.path.relpath(a.dir, os.path.join(HERE, "out"))
        f.write(f"{tag}\t{st:.4f}\t{ct:.4f}\t{ae:.3f}\t{a.note}\n")


if __name__ == "__main__":
    sys.exit(main())
