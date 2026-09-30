# stylize：照片风格化（不用任何生图模型）

给一张照片，输出某种画风的图。全部是图像处理和计算机图形学方法（保边平滑、区域合并、笔触模拟、三角网优化等），
热点在 C 里（`npr.c`，首次调用时自动编译）。依赖：Python 3、numpy、scipy、Pillow、系统 C 编译器。

## 什么时候用

- 手上有照片（或能搜到授权照片），想要某种画风的版本：插画、配图、海报、封面。
- 不适合：要照片级写实的新内容（照片里没有的东西）。那种需要自己用代码画，或者真的用生图模型。

## 风格

| 风格 | 效果 | 适合 | 长边 1600 耗时 |
|---|---|---|---|
| `ink` | 水墨：宣纸、墨色浓淡、飞白、勾勒、留白、印章 | 山水、风景、动物 | 约 1.8 秒 |
| `watercolor` | 水彩：色块概括、透明罩染、留白缝、边缘积色、颗粒 | 风景、建筑、街景 | 约 2.1 秒 |
| `oil` | 油画：多层曲线笔触、双色混笔、厚涂光照、画布纹理 | 人像、静物 | 约 2.3 秒 |
| `pencil` | 铅笔素描：方向线条 + 排线色调 | 建筑、人像、室内 | 约 1.4 秒 |
| `cartoon` | 卡通平涂：圆滑色块、粗描线、提亮加饱和 | 人像、简单场景 | 约 1.2 秒 |
| `lowpoly` | 低多边形：优化过的三角网（SVG） | 动物、人像、产品 | 约 0.4 秒 |
| `geometric` | 几何抽象：约 200 个半透明三角形（SVG，约 3KB） | 海报、封面、背景 | 约 2.2 秒 |

`python3 stylize.py --list` 也会列出这张表。展示图：`showcase.png`（5 张照片 × 7 种风格）。

## 命令行

```bash
python3 stylize.py photo.jpg --style watercolor --out out.png
python3 stylize.py --search "Kiyomizu-dera" --style ink --out kyoto.png   # 没有照片：从 Wikimedia Commons 搜授权照片
python3 stylize.py photo.jpg --style all --out out.png                     # 每种风格一张 + 总览图 out_all.png
python3 stylize.py photo.jpg --style lowpoly --out out.svg                 # 矢量输出
```

参数：`--strength`（风格强度，默认 1）、`--seed`、`--size`（输出长边，默认 1600）、`--no-seal`（水墨不盖章）。
用 `--search` 时，照片的署名写到 `<输出名>.credit.txt`；CC BY / BY-SA 的照片要求随成品保留署名。

## 函数接口

```python
import stylize
from PIL import Image
out = stylize.stylize(Image.open("photo.jpg"), "watercolor", strength=1.0, seed=0, size=1600)  # PIL 图
svg = stylize.stylize(img, "lowpoly")            # lowpoly / geometric 返回 SVG 文本
png = stylize.svg_to_image(svg)                  # 栅格化（不需要浏览器）
hits = stylize.search_commons("red fox")         # [{title, url, license, artist, page, width, height}]
img, credit = stylize.fetch_reference("red fox", pick=0)
```

各风格的细调参数在 `stylize.py` 顶部的 `INK`、`WATER`、`OIL`、`PENCIL`、`CARTOON`、`LOWPOLY`、`GEOM` 字典里，
通过 `params={...}` 传入，例如 `stylize.watercolor(img, params={"vignette": 0})`。

## 质量和已知问题

用 CLIP 零样本分类估的"像哪种画"的概率（8 张测试照片 × 3 个种子，长边 1024）：
低多边形 0.88，水墨 0.60，卡通 0.60，铅笔 0.59，水彩 0.58，几何抽象 0.56，油画 0.40。真画的分数是 0.82–0.92。
油画最弱：笔触渲染本身不够像颜料（把真油画送进去，分数会从 0.85 掉到 0.47）。
过程和每一版的记录：`results.tsv`、`../TASKS.md`。测试：`python3 test_stylize.py`。
