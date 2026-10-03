#!/usr/bin/env python3
"""生成 report/index.html：一个自包含的 HTML，图片全部压成 JPEG 后以 base64 嵌入。

图片不进仓库，来自原工作目录（--src）。用法：
  python3 report/build_report.py --src <原工作目录>   # 第一次尝试的图在它的上一级：千里江山图.png
"""
import argparse
import base64
import html
import io
import json
import os
import statistics

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GH = "https://github.com/Yaxin9Luo/Code2Pixel/blob/main/"
TRACK = {"A": "只给文字", "B": "文字 + 授权照片"}


def esc(s):
    return html.escape(str(s), quote=True)


def b64(path, width=None, q=80, crop=None):
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def raw_b64(path):
    return "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="原工作目录（含 demo/site/img、overview.png 等图片）")
    a = ap.parse_args()
    S = a.src
    D = os.path.join(REPO, "demo")
    prompts = json.load(open(os.path.join(D, "prompts.json")))
    P = {p["id"]: p for p in prompts["prompts"]}
    scores = {s["id"]: s for s in json.load(open(os.path.join(D, "scores.json")))}
    ver = {v["id"]: v for v in json.load(open(os.path.join(D, "verify.json")))}
    agents = json.load(open(os.path.join(D, "agents.json")))

    items = {}
    for t in "AB":
        for pid in P:
            lp = os.path.join(D, t, pid, "log.json")
            if os.path.exists(lp):
                log = json.load(open(lp))
                code = sorted(f for f in os.listdir(os.path.join(D, t, pid)) if f.endswith(".py"))
                lines = sum(sum(1 for _ in open(os.path.join(D, t, pid, f))) for f in code)
                mins = round((log["end"] - log["start"]) / 60)
                items[t + pid] = dict(t=t, pid=pid, log=log, code=code, lines=lines, mins=mins)

    def avg(xs):
        return statistics.mean(xs)

    tok = {t: sum(x["tokens"] for x in agents if x["track"] == t and x.get("tokens")) /
          sum(len(x["prompts"]) for x in agents if x["track"] == t and x.get("tokens")) for t in "AB"}
    st = {t: dict(mins=round(avg([i["mins"] for i in items.values() if i["t"] == t])),
                  lines=round(avg([i["lines"] for i in items.values() if i["t"] == t])),
                  tok=round(tok[t] / 1e4)) for t in "AB"}
    regen_ok = sum(1 for v in ver.values() if v.get("regen") == "完全一致")

    def srow(label, track, key):
        rows = [s[key] for s in scores.values() if s["track"] == track and key in s]
        top1 = sum(1 for r in rows if r["rank"] == 1)
        return (f"<tr><td>{label}</td><td class=num>{top1}/{len(rows)}</td>"
                f"<td class=num>{avg([r['clip'] for r in rows]):.1f}</td><td class=num>{avg([r['aes'] for r in rows]):.2f}</td></tr>")
    refrows = [s["ref"] for s in scores.values() if "ref" in s]
    score_html = (srow("A 只给文字 · 最终图", "A", "final") + srow("A 只给文字 · 第一轮（还没看过图）", "A", "round1")
                  + srow("B 文字 + 照片 · 最终图", "B", "final") + srow("B 文字 + 照片 · 第一轮", "B", "round1"))
    if refrows:
        score_html += (f"<tr class=ref><td>对照：B 下载的原始照片</td><td class=num>{sum(r['rank'] == 1 for r in refrows)}/{len(refrows)}</td>"
                       f"<td class=num>{avg([r['clip'] for r in refrows]):.1f}</td><td class=num>{avg([r['aes'] for r in refrows]):.2f}</td></tr>")

    img = os.path.join(S, "demo", "site", "img")

    def fig(key):
        it = items[key]
        log, s = it["log"], scores.get(key, {}).get("final", {})
        links = " · ".join(f'<a href="{GH}demo/{it["t"]}/{it["pid"]}/{f}" target=_blank rel=noopener>{f}</a>' for f in it["code"])
        cred = ""
        if log.get("credits"):
            cred = "<details><summary>用到的照片</summary><ul class=cred>" + "".join(
                f'<li><a href="{esc(c.get("url", ""))}" target=_blank rel=noopener>{esc(c.get("title", ""))}</a> · {esc(c.get("author", ""))} · {esc(c.get("license", ""))}</li>'
                for c in log["credits"]) + "</ul></details>"
        rounds = "".join(f"<li><b>第 {r.get('n', i + 1)} 轮</b> {esc(r.get('what', ''))}</li>" for i, r in enumerate(log.get("rounds", [])))
        return f"""<figure>
  <div class=tag><span class=trk>{it['t']}</span>{TRACK[it['t']]}</div>
  <img loading=lazy src="{raw_b64(os.path.join(img, key + '_s.jpg'))}" alt="{esc(P[it['pid']]['zh'])}">
  <p class=meta>{len(log.get('rounds', []))} 轮 · {it['mins']} 分钟 · {it['lines']} 行代码 · CLIP 排名 {s.get('rank', '–')}/12 · 重跑{esc(ver.get(key, {}).get('regen', '–'))}</p>
  <p class=method>{esc(log.get('method', ''))}</p>
  <details><summary>agent 自评</summary><p class=review>{esc(log.get('self_review', ''))}</p></details>
  <details><summary>每一轮的样子和改动</summary><img loading=lazy class=strip src="{raw_b64(os.path.join(img, key + '_rounds.jpg'))}" alt="{key} 各轮"><ol class=rounds>{rounds}</ol></details>
  {cred}
  <p class=code>源代码：{links}</p>
</figure>"""

    gallery = "".join(
        f"""<section class=prompt><div class=phead><span class=idx>{pid}</span><div><h3>{esc(p['zh'])}</h3><p class=en>{esc(p['category'])} · {esc(p['en'])}</p></div></div>
<div class=pair>{''.join(fig(t + pid) for t in 'AB' if t + pid in items)}</div></section>"""
        for pid, p in P.items())

    X = {
        "first": b64(os.path.join(S, "..", "千里江山图.png"), 1800, 78),
        "overview": b64(os.path.join(S, "overview.png"), 1800, 80),
        "detail": b64(os.path.join(S, "detail.png"), 1500, 80),
        "chart": b64(os.path.join(S, "chart.png"), 1400, 82),
        "progress": b64(os.path.join(S, "autoresearch", "progress.png"), 1400, 82),
        "before_after": b64(os.path.join(S, "autoresearch", "before_after.png"), 1500, 80),
        "showcase": b64(os.path.join(S, "stylize", "showcase.png"), 1300, 80),
    }

    page = TEMPLATE.format(
        css=CSS, n=len(items), regen=regen_ok, gh=GH, fixed=esc(prompts["fixed_at"]),
        a_mins=st["A"]["mins"], a_lines=st["A"]["lines"], a_tok=st["A"]["tok"],
        b_mins=st["B"]["mins"], b_lines=st["B"]["lines"], b_tok=st["B"]["tok"],
        scores=score_html, gallery=gallery, **X)
    out = os.path.join(HERE, "index.html")
    open(out, "w", encoding="utf-8").write(page)
    print(out, f"{os.path.getsize(out) / 1e6:.1f} MB")


CSS = """
:root{--paper:#fff;--ink:#17202a;--ink-soft:#26333c;--muted:#5a6570;--accent:#0d5277;--on-accent:#fff;--soft:#eaf3f7;--rule:#b8c9d2;
--serif:"Songti SC","STSong","Noto Serif CJK SC",Georgia,serif;--sans:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif;--num:Georgia,serif}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--paper:#0f161b;--ink:#e6edf2;--ink-soft:#cdd8df;--muted:#95a4af;--accent:#79b8d9;--on-accent:#0b1a22;--soft:#162731;--rule:#2e3f49;color-scheme:dark}}
:root[data-theme=dark]{--paper:#0f161b;--ink:#e6edf2;--ink-soft:#cdd8df;--muted:#95a4af;--accent:#79b8d9;--on-accent:#0b1a22;--soft:#162731;--rule:#2e3f49;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink-soft);font:16px/1.75 var(--sans)}
.wrap{max-width:1120px;margin:0 auto;padding:48px 24px 80px}
h1,h2,h3{font-family:var(--serif);color:var(--ink);margin:0;text-wrap:balance}
h1{font-size:clamp(30px,5vw,46px);line-height:1.25}h2{font-size:28px;margin-bottom:14px}h3{font-size:19px;line-height:1.45}
p{margin:0 0 10px}a{color:var(--accent)}img{max-width:100%;display:block}
.kicker{font:600 14px/20px var(--sans);letter-spacing:.12em;color:var(--muted)}.kicker b{color:var(--accent);margin-right:10px}
.lead{font-size:19px;max-width:46em;margin-top:14px}
header{padding-bottom:28px;border-bottom:1px solid var(--rule)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-top:26px}
.stat{padding:4px 20px 4px 0}.stat+.stat{border-left:1px solid var(--rule);padding-left:20px}
.stat .v{font:700 36px/1.15 var(--sans);color:var(--accent)}.stat .k{font-size:14px;color:var(--muted)}
section.block{margin-top:56px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:20px}
.card{background:var(--soft);border-radius:8px;padding:20px 22px}.card h4{margin:0 0 6px;font:600 17px/1.5 var(--sans);color:var(--ink)}
.card p,.card li{font-size:15px}.card ul{margin:0;padding-left:1.1em}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:560px;font-size:15px}
th,td{text-align:left;padding:9px 12px 9px 0;border-bottom:1px solid var(--rule)}th{font-size:13px;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}tr.ref td{color:var(--muted)}
.note{font-size:14px;color:var(--muted)}
.shot{margin:14px 0 6px;border-radius:6px}.cap{font-size:13px;color:var(--muted);margin-bottom:18px}
section.prompt{margin-top:44px;padding-top:24px;border-top:1px solid var(--rule)}
.phead{display:flex;gap:14px;margin-bottom:16px}.idx{font:700 32px/1 var(--num);color:var(--accent)}
.en{font-size:14px;color:var(--muted);margin:2px 0 0}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:28px}
figure{margin:0;display:grid;gap:8px;align-content:start;min-width:0;overflow-wrap:anywhere}figure>img{border-radius:8px}
.tag{font-size:13px;color:var(--muted);display:flex;gap:8px;align-items:center}
.trk{font:700 13px/1 var(--sans);color:var(--on-accent);background:var(--accent);border-radius:5px;padding:4px 7px}
.meta{font-size:14px;color:var(--accent);font-weight:600;margin:0}.method{font-size:14px;margin:0}
details{border-top:1px solid var(--rule);padding-top:6px}summary{cursor:pointer;font-size:14px;color:var(--accent)}
.review,.rounds,.cred{font-size:13px}.review{background:var(--soft);border-radius:8px;padding:10px 12px;margin-top:8px}
.rounds{padding-left:0;list-style:none;display:grid;gap:4px}.rounds b{color:var(--accent);margin-right:6px}
.strip{margin-top:8px;border-radius:4px}.code{font-size:13px;color:var(--muted);margin:0}
@media (max-width:560px){.wrap{padding-inline:16px}.stat+.stat{border-left:0;padding-left:0}}
"""

TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Code2Pixel</title><style>{css}</style></head><body><div class=wrap>

<header>
<p class=kicker><b>Code2Pixel</b>BENCHMARK DRAFT · 2026-09</p>
<h1>把 coding agent 当生图模型</h1>
<p class=lead>给一段文字描述，coding agent 写代码、渲染、看图、再改，最后交一张静态图，和生图模型放在一起比。用什么工具都可以：SVG、Canvas、Three.js、Blender、numpy。唯一的禁令是不能调用生图模型。这是一个给模型公司做后训练用的 benchmark 的草案，下面是想法、spec 和前期试跑的全部结果。</p>
<div class=stats>
<div class=stat><div class=v>{n}</div><div class=k>张试跑图，0 次生图模型调用</div></div>
<div class=stat><div class=v>{regen}/{n}</div><div class=k>重跑代码得到逐像素相同的图</div></div>
<div class=stat><div class=v>12/12</div><div class=k>只给文字：第一轮（还没看过图）就对题</div></div>
<div class=stat><div class=v>{a_mins} 分钟</div><div class=k>只给文字：每张平均用时，{a_lines} 行代码，约 {a_tok} 万 token</div></div>
</div>
</header>

<section class=block>
<h2>我们想说明什么</h2>
<div class=cols>
<div class=card><h4>反常识的事实</h4><p>大家默认生图必须用生图模型。试跑里 coding agent 只拿到一句文字，就画出了带光影、倒影、透视的完整场景。我们不说它现在比扩散模型画得好，我们说这是另一条路。</p></div>
<div class=card><h4>它为什么能画</h4><ul><li>语义知识：知道狐狸长什么样、光从左边来影子就往右。</li><li>代码按物体、形状、光照控制像素，一行就定下成千上万个像素，搜索发生在程序空间，不在像素空间。</li><li>反馈：渲染、看图、再改。</li></ul></div>
<div class=card><h4>它的上限在哪</h4><p>所有信息都要装进一段程序。能用短程序说清的（构图、几何、光影、程序化纹理）画得好；毛发、皮肤、照片级纹理这类说不清的细节画得差，这是试跑图 CG 感的来源。更强的库和后训练都能把上限往上推。</p></div>
<div class=card><h4>代码路线自带的优势</h4><p>精确（数量、文字、几何、布局）、可改（改一个数就只动一处）、可复现（试跑 24/24 逐像素一致）、分辨率无关、不需要图像训练数据。这些是生图模型很难做到的，benchmark 里会专门出题。</p></div>
</div>
</section>

<section class=block>
<h2>Benchmark 草案</h2>
<div class=cols>
<div class=card><h4>任务</h4><p>只做静态图。输入一段文字，交三样东西：最终 PNG、生成它的代码、一条能从头重跑的命令。可交互场景和 3D 建模已有不少 benchmark，不在范围内。</p></div>
<div class=card><h4>赛道</h4><ul><li><b>主赛道</b>：只给文字。不联网，不读现成图片、素材和模型。</li><li><b>素材赛道</b>：可以用授权的照片、贴图、HDRI、3D 模型。</li><li><b>辅助赛道</b>：给一张参考图，用代码画出来，按像素相似度客观打分，适合当 RL 奖励（千里江山图属于这类）。</li></ul><p>所有赛道都禁止调用生图模型。</p></div>
<div class=card><h4>档位</h4><p>测的是一次正常调用、一轮长程运行的效果，也就是大家平时实际的用法。harness 不强制 agent 多试几轮：差模型多试很多次也能刷分，还白白增加测试成本。分两档报分：<b>不看图</b>（禁止看任何图片，包括自己渲染的结果）和<b>正常运行</b>（可以看图）。不看图档衡量模型一次写对的本事；它和正常运行之间的差距，就是后训练能把"看图再改"搬进权重的空间。</p><p>两档上限都是 100 万 token、90 分钟，只用来防失控，结果报实际用的 token（只算新增输入和输出）、时间和看图次数。第一轮验收里，两家 agent 都是自己停下的，最多用了 13 万 token、22 分钟。原来按上限分的低预算、高预算两档拉不开差别，所以合并了。</p></div>
<div class=card><h4>评测三层</h4><ul><li><b>程序化规则，当门槛</b>：能渲染、输出路径和尺寸对、没有嵌入位图、没联网、没调模型、代码能重跑出同一张图、题目里可检查的约束（数量、文字、颜色、位置）满足。任何一条不过，总分归零，judge 分再高也不算。</li><li><b>VLM 裁判</b>：细则写成能核对的具体说法（"正好 3 只猫""月亮在右上角"），逐条判是或否，不打 1–5 分；再和固定图池两两比较，隐去作者，比较顺序做位置平衡，抵消 judge 偏爱某个位置的问题。grader 还会读代码：抓出把像素数组硬编码进代码这类作弊，也给可改、参数化这些代码自带的优势打分（次要维度）。</li><li><b>人工校准</b>：上线前先人工读一批打过分的样本，确认 judge 判得对；每个题目类别公布 VLM 裁判和人工的一致率；同一张图判几次结果不稳的维度，不交给裁判。</li></ul></div>
<div class=card><h4>题目</h4><p>风景、街景、动物、人物、静物、多物体、指定画风（水墨、像素、动画背景等），外加一组"代码该赢"的题：精确数量、画面里的文字、几何布局、对已有图的精确修改。</p><p>来源优先用人们真实让 coding agent 画图的 prompt，其次人写，再次以真实 prompt 为锚的合成题。难度由人判定，不专挑当前模型做不好的题；所有模型都失败的题人工复查。</p></div>
<div class=card><h4>数据和环境格式</h4><p>每条任务一行：<code>prompt</code>、<code>reward_model</code>（怎么判分）、<code>extra_info</code>（任务 id、Docker 镜像）。渲染环境（Chrome、Blender、Node、Python）做成统一镜像，可以直接接进 verl 这类训练框架。数据分三份，共用同一套环境代码：<b>train</b> 公开、量大，可自动出题、自动生成细则；<b>dev</b> 公开、细则经人工核对，用来报分；<b>test</b> 不公开、细则由人写、定期更换，不进训练。</p></div>
<div class=card><h4>训练 reward 和 benchmark 分数分开算</h4><p>训练时同一题跑一组（比如 8 个）rollout，组内互相比较给相对分，适合 GRPO。benchmark 不能只和自己比：和固定图池两两比较，图池里有生图模型的同题图和参考 agent 的图，最后给胜率或 Elo，回答"和生图模型比怎么样"。</p></div>
<div class=card><h4>防刷分</h4><p>提前堵上这类手法：base64 塞位图、下载图片、安装或调用生图模型、加载预训练权重、在画面里写字骗 judge 或写 prompt injection。沙盒断网，静态扫描加运行时检查，judge 只看像素，另出一批对抗样本测 judge。确认作弊的 reward 归零。</p></div>
<div class=card><h4>评测本身先过检查</h4><ul><li>分数随模型能力和 effort 上升；</li><li>最强模型开最高 effort 也离满分很远（试跑的 CLIP 认对率第一轮就 12/12，是反例）；</li><li>多次运行的噪声小于要关心的差距，报分附置信区间；</li><li>judge 判两次结论稳定；</li><li>对抗样本得 0 分。</li></ul><p>dev 分数涨而 test 不动，视为过拟合。</p></div>
<div class=card><h4>效率也是指标</h4><p>每个档位都报 token、轮数和时间。同样质量下用得更少，本身就是后训练要优化的目标。</p></div>
</div>
<p class=note style="margin-top:14px">还没定：VLM 裁判选型、生图模型基线用哪几个、渲染镜像的具体内容。环境打包、组内比较评分和门槛式奖励参考了小米 <a href="https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss" target=_blank rel=noopener>MiMo-V2.6 开源的 RL 环境</a>和 <a href="https://arxiv.org/abs/2609.32577" target=_blank rel=noopener>GAGAR</a>；人工校准是它们没做的部分。评测自检、题目来源和细则格式参考了 <a href="https://claude.dev/blog/automating-eval-design-and-hillclimbing/" target=_blank rel=noopener>Automating eval design and hillclimbing</a>。</p>
</section>


<section class=block>
<h2>实现方案</h2>
<p>完整方案（任务和输出约定、题库规模、评分细节、数据格式示例、还没定的问题）见 <a href="{gh}docs/PLAN.md" target=_blank rel=noopener>docs/PLAN.md</a>。</p>
<div class=tablewrap><table><thead><tr><th>阶段</th><th>做什么</th><th>完成标准</th></tr></thead><tbody>
<tr><td>0</td><td>试跑（已完成）</td><td>24 张图、结论和局限都在本报告里</td></tr>
<tr><td>1</td><td>环境和 harness：统一 Docker 镜像（Python、Node + Three.js、headless Chromium、Blender、中文字体）；出口代理只放行模型服务；直接用现成的 Claude Code 和 Codex 跑题；上限强制执行；卡住和电脑睡眠检测；日志</td><td>3 题 × 2 个 agent 跑通各档（已完成：18 次全部在上限内完成，全部逐像素复现，见 <a href="{gh}docs/PHASE1.md" target=_blank rel=noopener>docs/PHASE1.md</a>）；amd64 镜像待建</td></tr>
<tr><td>2</td><td>门槛：输出路径校验、断网重跑比对、静态扫描、运行时检查（strace 跟踪重跑和作答过程）、程序化约束</td><td>对抗样本全部判 0；试跑里正常的图全部通过（已完成：手写对抗样本 15/15 判不过，已有作品没有误判，见 <a href="{gh}docs/PHASE2.md" target=_blank rel=noopener>docs/PHASE2.md</a>）</td></tr>
<tr><td>3</td><td>题库 v0：dev 150 题，细则人工核对，"代码该赢"类至少 30 题</td><td>每题有来源、类别和人判的难度（已完成 v0：常规 100 + 代码该赢 50，32 题改写自 X 上的真实 prompt；细则由两个模型交叉检查、subagent 复审，还没有人逐条核对；精确修改题的修改框用真实修改验证过。见 <a href="{gh}docs/PHASE3.md" target=_blank rel=noopener>docs/PHASE3.md</a>）</td></tr>
<tr><td>4</td><td>VLM 裁判（进行中）：逐条细则；图池两两比较（位置平衡、Elo）；读代码的 grader</td><td>judge 两次判定不一致的比例低于 5%（裁判自洽 98–100%，两个裁判逐条一致 92%；60 次实跑上细则得分接近满分，两两比较结论随裁判反转，等人工标注。见 <a href="{gh}docs/PHASE4.md" target=_blank rel=noopener>docs/PHASE4.md</a>）</td></tr>
<tr><td>5</td><td>生图模型基线：2–3 个生图模型画 dev 全部题，放进图池</td><td>图池覆盖 dev 全部题</td></tr>
<tr><td>6</td><td>验证评测：3 个模型 × 2 个 effort × 3 个种子；人工读 50 个样本；人工两两比较</td><td>评测自检全部通过</td></tr>
<tr><td>7</td><td>训练环境：自动出题、自动生成细则得到 train 集；组内比较 reward；导出 Parquet 和镜像</td><td>用 verl 在 train 集上跑通一次小规模 RL，看到 dev 分数变化</td></tr>
<tr><td>8</td><td>发布：HF 数据集（train、dev）、镜像、评测代码、排行榜；test 集由我们来跑</td><td>分赛道、分档报分，附置信区间和成本</td></tr>
</tbody></table></div>
<p class=note style="margin-top:10px">还没定：VLM 裁判用哪个模型、生图模型基线用哪几个、隐藏 test 集怎么跑（对方给 API 由我们跑，还是限时评测窗口）、从 X 收集的 prompt 怎么处理授权、test 集规模和更换频率。</p>
</section>

<section class=block>
<h2>试跑：12 个题目，24 张图</h2>
<p>12 个题目在动手前定下（{fixed}），每题画两张：A 只给文字，B 可以从 Wikimedia Commons 找授权照片当素材。8 个 coding agent 并行画，每张最多 6 轮"写代码 → 渲染 → 看图"。A 平均每张 {a_mins} 分钟、{a_lines} 行代码、约 {a_tok} 万 token；B 平均 {b_mins} 分钟、{b_lines} 行、约 {b_tok} 万 token。好的坏的全部展示。</p>
<div class=tablewrap><table><thead><tr><th>哪一版</th><th class=num>CLIP 12 选 1 认对</th><th class=num>图文相似度</th><th class=num>美学分</th></tr></thead><tbody>{scores}</tbody></table></div>
<p class=note style="margin-top:10px">CLIP（ViT-L/14）拿每张图和 12 个英文题目比，自己的题目排第一算认对；相似度是余弦 ×100；美学分是 LAION 美学预测器（1–10）。认对率只能说明画的是这个题目：连原始照片也全部认对，分不出好坏。这正是正式 benchmark 要换成规则 + VLM 裁判 + 人工校准的原因。</p>
<div class=cols style="margin-top:18px">
<div class=card><h4>画得不好的地方</h4><p>A 赛道 3D 渲染感偏重、人物偏僵；B 赛道有几张（B01、B04、B05、B09）基本是照片后期，agent 自评也承认。每张图下面都有 agent 的自评。</p></div>
<div class=card><h4>过程里的问题</h4><p>一个 B 赛道 agent 找照片找了约 1 小时后卡住，08 和 12 换新 agent 重画。系统字体排字（A03、A10、B10）和读自己刚渲染的中间图（A06）判定为不违规。</p></div>
</div>
</section>

<section class=block>
<h2>全部 24 张</h2>
{gallery}
</section>

<section class=block>
<h2>前期探索：千里江山图</h2>
<p>这个项目从"用代码画一张《千里江山图》"开始，中间走过几条路，最后才落到"coding agent 当生图模型"。</p>
<h3>1. 从零画</h3>
<p>只凭对画的了解，用 numpy 程序化生成山体、云雾、水面、题字和印章。能看出青绿山水的意思，但和原画差得很远。</p>
<img class=shot loading=lazy src="{first}" alt="第一次从零画的千里江山图"><p class=cap>第一次尝试：纯代码从零画（<a href="{gh}qianli/first_attempt/draw.py" target=_blank rel=noopener>代码</a>）</p>
<h3>2. 给参考图，用代码复刻</h3>
<p>下载原画扫描（公有领域），两种做法：优化器一次放一个半透明三角形去拟合原图，输出的 SVG 本身就是程序；或者模型看带网格的截图、凭目测手写 SVG。三角形越多越像，5 万个三角形 SSIM 0.899；手写版只有 0.673，但只有 11KB。</p>
<img class=shot loading=lazy src="{overview}" alt="整卷对比"><p class=cap>整卷：原图、1,000 / 10,000 / 50,999 个三角形、手写 SVG</p>
<img class=shot loading=lazy src="{detail}" alt="局部对比"><p class=cap>桥附近局部放大，含同字节数的 JPEG 对照</p>
<img class=shot loading=lazy src="{chart}" alt="相似度随字节数变化"><p class=cap>相似度随字节数的变化（<a href="{gh}qianli/fit/README.md" target=_blank rel=noopener>完整表格和复现命令</a>）</p>
<h3>3. 让 agent 自动优化拟合算法（autoresearch）</h3>
<p>固定评分规则，让 agent 自己改算法、跑实验、留下有效的改动。30 多次实验后收敛：同样的字节预算下 SSIM 从 0.764 提到 0.818，时间从约 58 秒降到 26 秒；在一张没参与调参的画上也从 0.893 提到 0.922。</p>
<img class=shot loading=lazy src="{progress}" alt="实验进展"><img class=shot loading=lazy src="{before_after}" alt="优化前后对比"><p class=cap>实验进展和优化前后对比（<a href="{gh}autoresearch/README.md" target=_blank rel=noopener>autoresearch 说明</a>）</p>
<h3>4. 照片 → 风格化工具</h3>
<p>做了一套给 coding agent 调用的风格化工具：水墨、水彩、油画、铅笔、卡通、低多边形、几何抽象，全部是传统算法和 C 内核，不用神经网络。</p>
<img class=shot loading=lazy src="{showcase}" alt="风格化工具效果"><p class=cap>风格化工具总览（<a href="{gh}stylize/stylize.py" target=_blank rel=noopener>stylize.py</a>）</p>
<h3>5. 转向</h3>
<p>做到这里发现，我们在迭代算法，而真正想说明的是另一件事：coding agent 本身就会画，不需要调生图模型，也不需要事先写好的算法。于是有了上面的试跑，再往下就是这个 benchmark。</p>
</section>

<section class=block>
<h2>讨论过的几个决定</h2>
<div class=cols>
<div class=card><h4>主线是文字生成，不是拟合</h4><p>用户用 coding agent 时，给的是一段描述，不会指定用什么算法去拟合。所以主赛道只给文字。拟合参考图保留为辅助赛道：它分数客观、奖励稠密，适合训练。</p></div>
<div class=card><h4>不限工具，只做静态图</h4><p>scope 是"coding agent 当生图模型"，SVG 只是其中一种工具。只做静态图，是为了和生图模型直接比，评测也最好做。</p></div>
<div class=card><h4>claim 的边界</h4><p>说"能做、有另一条路"，不说"已经做得更好"。试跑一张图要十几分钟、十几万 token，扩散模型只要几秒；照片级质量也还有差距。</p></div>
</div>
</section>

<p class=note style="margin-top:56px">代码和数据：<a href="https://github.com/Yaxin9Luo/Code2Pixel" target=_blank rel=noopener>github.com/Yaxin9Luo/Code2Pixel</a>。B 赛道成品中用到 CC BY-SA 照片的（B01、B02、B08、B10、B12）按 CC BY-SA 4.0 分享，照片署名见各图下方。</p>
</div></body></html>
"""

if __name__ == "__main__":
    main()
