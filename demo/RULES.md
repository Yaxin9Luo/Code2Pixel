# 代码画图实验：规则

目的：证明 coding agent 不调用任何生图模型，只写代码也能画出图来。
题目在 `prompts.json`，动手之前已经定下，不改。每个题目画两张：A 赛道一张、B 赛道一张。

## 两条赛道

- **A：只给文字。** 不联网（不许 curl、urllib、requests、pip install），不读取任何现成的图片文件（包括本项目里的照片和参考画），
  所有内容都由代码生成。
- **B：文字 + 授权照片。** 可以从 Wikimedia Commons 搜索并下载照片当素材（公有领域 / CC0 / CC BY / CC BY-SA），
  可以裁切、拼接多张、风格化、在上面用代码加画。只能用**照片**，不能用画作、插画或 AI 生成的图。
  用到的每张照片都要记署名（标题、作者、授权、链接），原图存到自己目录的 `refs/` 里。

## 两条赛道都要遵守

1. **不调用任何生图模型，也不用任何神经网络**（包括用 CLIP 之类的模型给自己打分）。能用的是代码：SVG、HTML canvas、
   Python（numpy、scipy、Pillow），以及本项目的 `stylize/stylize.py`（照片/图片风格化和程序化纹理，只能 import，不能改）。
2. **每轮都要看图。** 一轮 = 写或改代码 → 渲染成 PNG → 用 Read 工具看这张 PNG → 判断哪里不对。
   **每张图最多 6 轮**。每轮的渲染结果存为 `rounds/r1.png`、`rounds/r2.png`……
   最终图 `final.png` 就是最后一轮的结果。长边 1200–1600 像素。
3. **图就是代码。** 一条命令就能从头重新生成 `final.png`（随机数固定种子）。B 赛道的命令可以读 `refs/` 里的照片，但不能联网。
4. **只在自己的目录里写文件**（`demo/A/<题号>/` 或 `demo/B/<题号>/`），不改目录外的任何文件。
5. **画不好也要交。** 在 `log.json` 里写清楚哪里不行，不要美化。
6. 开始画一张图前运行 `date +%s` 记开始时间，交稿时再记结束时间。

## 渲染工具

- SVG / HTML：`python3 demo/tools/render.py in.svg out.png`
  （HTML 要加 `--width W --height H`，页面写 `body{margin:0}`）
- Python 直接画像素（Pillow / numpy）则不需要渲染工具。
- 风格化库：`sys.path.insert(0, "stylize"); import stylize`，
  `stylize.stylize(PIL图, 风格, strength, seed, size)`，风格有 ink、watercolor、oil、pencil、cartoon、lowpoly、geometric；
  lowpoly、geometric 返回 SVG 文本（`stylize.svg_to_image` 可栅格化）。还有 `fbm`、`paper_texture`、`warp` 等程序化纹理函数。
  B 赛道搜图：`stylize.search_commons("关键词")` 返回带授权信息的结果列表，`stylize.fetch_reference("关键词", pick=i)` 下载第 i 个。

## log.json（每张图一个）

```json
{
  "id": "A01",
  "track": "A",
  "prompt_zh": "……",
  "start": 1790000000,
  "end": 1790000900,
  "rounds": [{"n": 1, "png": "rounds/r1.png", "what": "这一轮做了什么、看图发现了什么问题"}],
  "cmd": "cd <本目录> && python3 draw.py",
  "method": "一句话说明画法",
  "self_review": "诚实自评：哪里画得像、哪里不像",
  "credits": [{"title": "", "author": "", "license": "", "url": ""}]
}
```

A 赛道的 `credits` 留空列表。
