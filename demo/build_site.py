"""把实验结果做成网页：demo/site/index.html + 图片 + 源代码。

读取 prompts.json、[AB]/<题号>/log.json、verify.json、scores.json。
用法: python3 build_site.py
"""
import glob
import hashlib
import html
import json
import os
import shutil
import statistics

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
PR = json.load(open(os.path.join(HERE, "prompts.json")))
PROMPTS = {p["id"]: p for p in PR["prompts"]}
VER = {r["id"]: r for r in json.load(open(os.path.join(HERE, "verify.json")))} \
    if os.path.exists(os.path.join(HERE, "verify.json")) else {}
SCO = {r["id"]: r for r in json.load(open(os.path.join(HERE, "scores.json")))} \
    if os.path.exists(os.path.join(HERE, "scores.json")) else {}
TRACK = {"A": "只给文字", "B": "文字 + 授权照片"}


PROJ = os.path.dirname(HERE)


def clean(s):
    """公开副本里去掉本机绝对路径（含用户名）。"""
    return str(s).replace(PROJ, "<项目目录>").replace(os.path.expanduser("~"), "~")


def esc(s):
    return html.escape(clean(s), quote=True)


def save_jpg(src, dst, long_edge, q=86):
    im = Image.open(src).convert("RGB")
    k = min(1.0, long_edge / max(im.size))
    if k < 1:
        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
    im.save(dst, quality=q, optimize=True, progressive=True)
    return im.size


def strip(pngs, dst, h=220):
    ims = [Image.open(p).convert("RGB") for p in pngs]
    ims = [im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS) for im in ims]
    gap = 8
    out = Image.new("RGB", (sum(im.width for im in ims) + gap * (len(ims) - 1), h), (255, 255, 255))
    x = 0
    for im in ims:
        out.paste(im, (x, 0))
        x += im.width + gap
    out.save(dst, quality=84, optimize=True)


def item(track, pid):
    d = os.path.join(HERE, track, pid)
    key = f"{track}{pid}"
    lp = os.path.join(d, "log.json")
    if not os.path.exists(lp) or not os.path.exists(os.path.join(d, "final.png")):
        return None
    log = json.load(open(lp))
    v, s = VER.get(key, {}), SCO.get(key, {})
    w, h = save_jpg(os.path.join(d, "final.png"), os.path.join(SITE, "img", f"{key}.jpg"), 1600, 90)
    save_jpg(os.path.join(d, "final.png"), os.path.join(SITE, "img", f"{key}_s.jpg"), 900, 86)
    rounds = [os.path.join(d, r["png"]) for r in log.get("rounds", []) if os.path.exists(os.path.join(d, r["png"]))]
    if rounds:
        strip(rounds, os.path.join(SITE, "img", f"{key}_rounds.jpg"))
    codes = []
    generated = {"A06": {"scene.svg"}}            # draw.py 运行时生成的中间文件，不是源代码
    n_lines = 0
    for rel in v.get("code_files", []):
        if rel in generated.get(key, set()):
            continue
        dst = os.path.join(SITE, "code", key, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        src = os.path.join(d, rel)
        try:
            open(dst, "w").write(clean(open(src, encoding="utf-8").read()))
        except UnicodeDecodeError:
            shutil.copy(src, dst)
        n_lines += sum(1 for _ in open(src, errors="ignore"))
        codes.append(f"code/{key}/{rel}")
    if codes:
        v = dict(v, code_lines=n_lines)             # 行数只算页面上列出的源文件
    refs = []
    if track == "B":
        for i, rp in enumerate(sorted(glob.glob(os.path.join(d, "refs", "*")))):
            if rp.lower().endswith((".jpg", ".jpeg", ".png")):
                save_jpg(rp, os.path.join(SITE, "img", f"{key}_ref{i}.jpg"), 700, 84)
                refs.append(f"img/{key}_ref{i}.jpg")
    minutes = round((log["end"] - log["start"]) / 60) if log.get("end") and log.get("start") else None
    return dict(key=key, track=track, pid=pid, log=log, v=v, s=s, w=w, h=h, codes=codes, refs=refs,
                has_rounds=bool(rounds), minutes=minutes)


def figure(it):
    log, v, s = it["log"], it["v"], it["s"]
    fin = s.get("final", {})
    meta = [f"{len(log.get('rounds', []))} 轮", f"{it['minutes']} 分钟" if it["minutes"] is not None else "",
            f"代码 {v.get('code_lines', '?')} 行"]
    if fin:
        meta.append(f"CLIP 排名 {fin['rank']}/12")
    rounds_html = ""
    if it["has_rounds"]:
        notes = "".join(f"<li><span class=\"rn\">第 {r.get('n', i + 1)} 轮</span>{esc(r.get('what', ''))}</li>"
                        for i, r in enumerate(log.get("rounds", [])))
        rounds_html = (f"<details class=\"more\"><summary>每一轮的样子和改动</summary>"
                       f"<img class=\"strip\" loading=\"lazy\" src=\"img/{it['key']}_rounds.jpg\" alt=\"{it['key']} 各轮渲染\">"
                       f"<ol class=\"notes\">{notes}</ol></details>")
    code_html = ""
    if it["codes"]:
        opts = "".join(f"<button type=\"button\" class=\"codebtn\" data-src=\"{esc(c)}\">{esc(os.path.basename(c))}</button>"
                       for c in it["codes"])
        code_html = (f"<details class=\"more code\"><summary>源代码（{v.get('code_lines', '?')} 行，"
                     f"命令：<code>{esc(os.path.basename(log.get('cmd', '').split('&&')[-1].strip()))}</code>）</summary>"
                     f"<div class=\"codebar\">{opts}</div><pre class=\"src\"><code>点上面的文件名查看。</code></pre></details>")
    refs_html = ""
    if it["refs"]:
        cred = "".join(f"<li><a href=\"{esc(c.get('url', ''))}\" target=\"_blank\" rel=\"noopener\">{esc(c.get('title', ''))}</a>"
                       f" · {esc(c.get('author', ''))} · {esc(c.get('license', ''))}</li>" for c in log.get("credits", []))
        thumbs = "".join(f"<img loading=\"lazy\" src=\"{r}\" alt=\"参考照片\">" for r in it["refs"])
        refs_html = (f"<details class=\"more\"><summary>用到的照片（{len(it['refs'])} 张）</summary>"
                     f"<div class=\"refs\">{thumbs}</div><ul class=\"credits\">{cred}</ul></details>")
    regen = v.get("regen", "")
    issues = v.get("issues", [])
    check = "代码重新运行：" + esc(regen) if regen else ""
    if issues:
        check += "；问题：" + esc("；".join(issues))
    return f"""
      <figure class="work">
        <div class="tag"><span class="trk">{it['track']}</span>{TRACK[it['track']]}</div>
        <button type="button" class="zoom" data-full="img/{it['key']}.jpg" aria-label="放大 {it['key']}">
          <img loading="lazy" src="img/{it['key']}_s.jpg" alt="{esc(PROMPTS[it['pid']]['zh'])}（{TRACK[it['track']]}）"
               width="{it['w']}" height="{it['h']}">
        </button>
        <figcaption>
          <p class="meta">{' · '.join(m for m in meta if m)}</p>
          <p class="method">{esc(log.get('method', ''))}</p>
          <blockquote>{esc(log.get('self_review', ''))}</blockquote>
          <p class="check">{check}</p>
          {rounds_html}{refs_html}{code_html}
        </figcaption>
      </figure>"""


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(os.path.join(SITE, "img"))
    items = {}
    for track in ("A", "B"):
        for pid in PROMPTS:
            it = item(track, pid)
            if it:
                items[it["key"]] = it
    n = len(items)
    mins = [it["minutes"] for it in items.values() if it["minutes"] is not None]
    rounds = [len(it["log"].get("rounds", [])) for it in items.values()]
    lines = [it["v"].get("code_lines", 0) for it in items.values() if it["v"]]
    top1 = {t: sum(1 for it in items.values() if it["track"] == t and it["s"].get("final", {}).get("rank") == 1)
            for t in "AB"}
    nt = {t: sum(1 for it in items.values() if it["track"] == t) for t in "AB"}
    regen_ok = sum(1 for it in items.values() if it["v"].get("regen") == "完全一致")
    agents = json.load(open(os.path.join(HERE, "agents.json"))) if os.path.exists(os.path.join(HERE, "agents.json")) else []
    tok = {t: [a for a in agents if a["track"] == t and a.get("tokens")] for t in "AB"}
    tok_per = {t: (sum(a["tokens"] for a in tok[t]) / sum(len(a["prompts"]) for a in tok[t])) if tok[t] else None for t in "AB"}
    mins_t = {t: [it["minutes"] for it in items.values() if it["track"] == t and it["minutes"] is not None] for t in "AB"}
    lines_t = {t: [it["v"].get("code_lines", 0) for it in items.values() if it["track"] == t and it["v"]] for t in "AB"}
    sa = sorted(it["key"] for it in items.values() if any("SA" in (c.get("license") or "").upper()
                                                          for c in it["log"].get("credits", [])))
    sha = hashlib.sha256(open(os.path.join(HERE, "prompts.json"), "rb").read()).hexdigest()

    def avg(xs, nd=1):
        return f"{statistics.mean(xs):.{nd}f}" if xs else "–"

    # 分数表
    def srow(track, key):
        rows = [SCO[k][key] for k in SCO if SCO[k]["track"] == track and key in SCO[k]]
        if not rows:
            return ""
        return (f"<tr><td>{track} · {TRACK[track]}</td><td>{'最终图' if key == 'final' else '第一轮'}</td>"
                f"<td class=\"num\">{sum(r['rank'] == 1 for r in rows)}/{len(rows)}</td>"
                f"<td class=\"num\">{avg([r['rank'] for r in rows], 2)}</td>"
                f"<td class=\"num\">{avg([r['clip'] for r in rows])}</td><td class=\"num\">{avg([r['aes'] for r in rows], 2)}</td></tr>")
    refrows = [SCO[k]["refs"][0] for k in SCO if SCO[k]["track"] == "B" and SCO[k].get("refs")]
    ref_tr = ""
    if refrows:
        ref_tr = (f"<tr class=\"ref\"><td>对照 · B 下载的原始照片</td><td>未经代码处理</td>"
                  f"<td class=\"num\">{sum(r['rank'] == 1 for r in refrows)}/{len(refrows)}</td>"
                  f"<td class=\"num\">{avg([r['rank'] for r in refrows], 2)}</td>"
                  f"<td class=\"num\">{avg([r['clip'] for r in refrows])}</td><td class=\"num\">{avg([r['aes'] for r in refrows], 2)}</td></tr>")
    table = "".join(srow(t, k) for t in "AB" for k in ("final", "round1")) + ref_tr

    sections = []
    for pid, p in PROMPTS.items():
        figs = "".join(figure(items[f"{t}{pid}"]) for t in "AB" if f"{t}{pid}" in items)
        sections.append(f"""
    <section class="prompt" id="p{pid}">
      <header class="phead">
        <span class="idx">{pid}</span>
        <div><p class="cat">{esc(p['category'])}</p><h3>{esc(p['zh'])}</h3><p class="en">{esc(p['en'])}</p></div>
      </header>
      <div class="pair">{figs}</div>
    </section>""")

    page = TEMPLATE.format(
        n=n, top1a=top1["A"], na=nt["A"], top1b=top1["B"], nb=nt["B"], avgmin=avg(mins, 0), avground=avg(rounds, 1),
        avglines=avg(lines, 0), regen_ok=regen_ok, fixed_at=esc(PR["fixed_at"]), sha=sha,
        mina=avg(mins_t["A"], 0), minb=avg(mins_t["B"], 0), linesa=avg(lines_t["A"], 0), linesb=avg(lines_t["B"], 0),
        toka=f"{tok_per['A'] / 1e4:.0f}" if tok_per["A"] else "–", tokb=f"{tok_per['B'] / 1e4:.0f}" if tok_per["B"] else "–",
        sa="、".join(sa) if sa else "无",
        prompts="".join(f"<li><span class=\"idx s\">{pid}</span><span class=\"pc\">{esc(p['category'])}</span>{esc(p['zh'])}</li>"
                        for pid, p in PROMPTS.items()),
        table=table, sections="".join(sections))
    open(os.path.join(SITE, "index.html"), "w").write(page)
    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(SITE) for f in fs)
    nfiles = sum(len(fs) for _, _, fs in os.walk(SITE))
    print(f"{n} 张图，{nfiles} 个文件，共 {total / 1e6:.1f} MB → {SITE}/index.html")


TEMPLATE = """<title>代码画的 24 张图</title>
<style>
:root {{
  --paper: #ffffff; --ink: #17202a; --ink-soft: #26333c; --muted: #5a6570;
  --accent: #0d5277; --on-accent: #ffffff; --accent-soft: #eaf3f7; --rule: #b8c9d2; --code-bg: #f6f9fb;
  --serif: "Songti SC", "STSong", "Noto Serif CJK SC", Georgia, serif;
  --sans: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
  --numeral: Georgia, "Times New Roman", serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}}
/* 设计系统只定义了浅色；深色沿用同一个深青蓝色相，正文对比度都在 6:1 以上 */
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper: #0f161b; --ink: #e6edf2; --ink-soft: #cdd8df; --muted: #95a4af;
    --accent: #79b8d9; --on-accent: #0b1a22; --accent-soft: #162731; --rule: #2e3f49; --code-bg: #121d24;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --paper: #0f161b; --ink: #e6edf2; --ink-soft: #cdd8df; --muted: #95a4af;
  --accent: #79b8d9; --on-accent: #0b1a22; --accent-soft: #162731; --rule: #2e3f49; --code-bg: #121d24;
  color-scheme: dark;
}}
body {{ background: var(--paper); color: var(--ink-soft); font: 16px/1.7 var(--sans); }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-inline: 24px; padding-block: 48px 80px; }}
h1, h2, h3 {{ font-family: var(--serif); color: var(--ink); text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(28px, 4.6vw, 44px); line-height: 1.25; letter-spacing: .02em; }}
h2 {{ font-size: 28px; line-height: 1.3; letter-spacing: .02em; }}
h3 {{ font-size: 21px; line-height: 1.45; }}
p {{ margin: 0; }}
.kicker {{ font: 600 14px/20px var(--sans); letter-spacing: .12em; color: var(--muted); }}
.kicker b {{ color: var(--accent); font-weight: 600; margin-right: 10px; letter-spacing: .06em; }}
.lead {{ font-size: 19px; line-height: 1.7; max-width: 44em; color: var(--ink-soft); }}
.head {{ display: grid; gap: 14px; padding-bottom: 28px; border-bottom: 1px solid var(--rule); }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0; margin-top: 28px; }}
.stat {{ padding: 4px 20px 4px 0; }}
.stat + .stat {{ border-left: 1px solid var(--rule); padding-left: 20px; }}
.stat .v {{ font: 700 38px/1.1 var(--sans); color: var(--accent); font-variant-numeric: tabular-nums; }}
.stat .k {{ font-size: 14px; color: var(--muted); margin-top: 6px; }}
section.block {{ margin-top: 56px; display: grid; gap: 16px; }}
.cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; }}
.cols.two {{ grid-template-columns: repeat(auto-fit, minmax(min(100%, 440px), 1fr)); }}
p, li, blockquote {{ text-wrap: pretty; }}
.card {{ background: var(--accent-soft); border-radius: 8px; padding: 22px 24px; display: grid; gap: 8px; align-content: start; }}
.card h4 {{ margin: 0; font: 600 17px/1.5 var(--sans); color: var(--ink); }}
.card p, .card li {{ font-size: 15px; }}
.card ul {{ margin: 0; padding-left: 1.1em; display: grid; gap: 4px; }}
ol.plist {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 6px 32px; }}
ol.plist li {{ display: flex; gap: 12px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--rule); font-size: 15px; color: var(--ink-soft); }}
.idx {{ font: 700 26px/1 var(--numeral); color: var(--accent); min-width: 1.6em; }}
.idx.s {{ font-size: 17px; min-width: 1.6em; }}
.pc {{ font-size: 12px; color: var(--muted); letter-spacing: .08em; white-space: nowrap; }}
.proof {{ font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }}
.proof code {{ font-family: var(--mono); font-size: 12px; color: var(--ink-soft); }}
.tablewrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; min-width: 620px; font-size: 15px; }}
th, td {{ text-align: left; padding: 10px 12px 10px 0; border-bottom: 1px solid var(--rule); }}
th {{ font-size: 13px; font-weight: 600; color: var(--muted); letter-spacing: .04em; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tr.ref td {{ color: var(--muted); }}
.note {{ font-size: 14px; color: var(--muted); max-width: 60em; }}
section.prompt {{ margin-top: 48px; padding-top: 28px; border-top: 1px solid var(--rule); }}
.phead {{ display: flex; gap: 16px; align-items: flex-start; margin-bottom: 20px; }}
.phead .idx {{ font-size: 34px; padding-top: 2px; }}
.phead .cat {{ font-size: 13px; color: var(--muted); letter-spacing: .1em; }}
.phead .en {{ font-size: 14px; color: var(--muted); margin-top: 2px; }}
.pair {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 28px; }}
figure.work {{ margin: 0; display: grid; gap: 10px; align-content: start; min-width: 0; }}
.tag {{ font-size: 13px; color: var(--muted); display: flex; gap: 8px; align-items: center; }}
.trk {{ font: 700 13px/1 var(--sans); color: var(--on-accent); background: var(--accent); border-radius: 5px; padding: 4px 7px; }}
button.zoom {{ padding: 0; border: 0; background: none; cursor: zoom-in; display: block; }}
button.zoom img {{ display: block; width: 100%; height: auto; border-radius: 8px; background: var(--accent-soft); }}
figcaption {{ display: grid; gap: 8px; overflow-wrap: anywhere; }}
.meta {{ font-size: 14px; color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }}
.method {{ font-size: 14px; color: var(--ink-soft); }}
blockquote {{ margin: 0; padding: 10px 14px; background: var(--accent-soft); border-radius: 8px; font-size: 14px; color: var(--ink-soft); }}
blockquote::before {{ content: "画图的 agent 自评："; color: var(--muted); }}
.check {{ font-size: 13px; color: var(--muted); }}
details.more {{ border-top: 1px solid var(--rule); padding-top: 8px; }}
details.more summary {{ cursor: pointer; font-size: 14px; color: var(--accent); }}
details.more summary code {{ font-family: var(--mono); font-size: 12px; }}
img.strip {{ display: block; width: 100%; height: auto; margin-top: 10px; border-radius: 5px; }}
ol.notes {{ margin: 10px 0 0; padding-left: 0; list-style: none; display: grid; gap: 6px; font-size: 13px; }}
ol.notes .rn {{ font-family: var(--sans); color: var(--accent); font-weight: 600; margin-right: 8px; }}
.refs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
.refs img {{ height: 120px; width: auto; border-radius: 5px; }}
ul.credits {{ margin: 8px 0 0; padding-left: 1.1em; font-size: 12px; color: var(--muted); display: grid; gap: 2px; overflow-wrap: anywhere; }}
ul.credits a {{ color: var(--accent); }}
.codebar {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
.codebtn {{ font: 12px var(--mono); color: var(--accent); background: var(--accent-soft); border: 1px solid var(--rule); border-radius: 5px; padding: 3px 8px; cursor: pointer; }}
.codebtn[aria-pressed="true"] {{ background: var(--accent); color: var(--on-accent); border-color: var(--accent); }}
pre.src {{ margin: 8px 0 0; max-height: 420px; overflow: auto; background: var(--code-bg); border-radius: 8px; padding: 12px; font: 12px/1.55 var(--mono); color: var(--ink-soft); }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
#lb {{ position: fixed; inset: 0; background: rgba(23, 32, 42, .92); display: grid; place-items: center; padding: 16px; z-index: 10; cursor: zoom-out; }}
#lb[hidden] {{ display: none; }}
#lb img {{ max-width: 100%; max-height: 100%; border-radius: 4px; }}
@media (max-width: 560px) {{ .wrap {{ padding-inline: 16px; }} .stat + .stat {{ border-left: 0; padding-left: 0; }} .stat {{ padding-block: 8px; }} }}
</style>

<div class="wrap">
  <header class="head">
    <p class="kicker"><b>代码画图实验</b>NO IMAGE MODELS</p>
    <h1>不调用任何生图模型，coding agent 用代码画出的 {n} 张图</h1>
    <p class="lead">12 个题目在动手之前定下，每题画两张：一张只给文字，一张可以用授权照片当素材。每张图都由画图的 agent 写代码生成，渲染、看图、再改，最多 6 轮。好的坏的全部放在这里，每张附源代码。</p>
    <div class="stats">
      <div class="stat"><div class="v">{n}</div><div class="k">张图，0 次生图模型调用</div></div>
      <div class="stat"><div class="v">{regen_ok}/{n}</div><div class="k">重跑代码得到逐像素相同的图</div></div>
      <div class="stat"><div class="v">{mina}</div><div class="k">只给文字：平均每张用时（分钟）</div></div>
      <div class="stat"><div class="v">{linesa}</div><div class="k">只给文字：平均每张代码行数</div></div>
      <div class="stat"><div class="v">{toka} 万</div><div class="k">只给文字：平均每张 token</div></div>
    </div>
  </header>

  <section class="block">
    <h2>规则</h2>
    <div class="cols">
      <div class="card"><h4>A · 只给文字</h4><ul><li>不联网，不读取任何现成图片</li><li>画面里的一切都由代码生成：SVG、HTML canvas、numpy 像素绘制、程序化纹理</li></ul></div>
      <div class="card"><h4>B · 文字 + 授权照片</h4><ul><li>从 Wikimedia Commons 找公有领域 / CC 授权的照片当素材</li><li>只能用照片，不能用画作或 AI 生成图；裁切、拼接、风格化、加画都用代码</li><li>每张照片都署名。平均每张 {minb} 分钟（含找照片）、{linesb} 行代码、约 {tokb} 万 token</li></ul></div>
      <div class="card"><h4>两条赛道都一样</h4><ul><li>不调用生图模型，也不用任何神经网络</li><li>每轮渲染后 agent 自己看图再改，最多 6 轮</li><li>一条命令能从头重新生成最终图；画不好也照样展示</li></ul></div>
    </div>
  </section>

  <section class="block">
    <h2>题目</h2>
    <ol class="plist">{prompts}</ol>
    <p class="proof">题目定于 {fixed_at}，早于任何一张图的开始时间。题目文件 SHA-256：<code>{sha}</code></p>
  </section>

  <section class="block">
    <h2>打分</h2>
    <div class="tablewrap"><table>
      <thead><tr><th>赛道</th><th>哪一版</th><th class="num">CLIP 12 选 1 认对</th><th class="num">平均排名</th><th class="num">图文相似度</th><th class="num">美学分</th></tr></thead>
      <tbody>{table}</tbody>
    </table></div>
    <p class="note">CLIP（ViT-L/14）把每张图和 12 个英文题目逐一比较，自己的题目排第 1 就算认对；图文相似度是余弦 ×100。美学分是 LAION 美学预测器（1–10）。这些模型只在画完以后用来打分，画图时不允许用。认对率只能说明画的是这个题目：连没处理过的原始照片也是全部认对，它区分不出画得好坏。图文相似度和美学分多一点信息：B 赛道处理后的图比原始照片更贴题（代码补上了照片里缺的东西和画风），只给文字的 A 赛道美学分最高。这些分数都只能作参考，人工盲评更有说服力，需要混入生图模型画的同题目图，还没做。</p>
  </section>

  <section class="block">
    <h2>过程里出的问题</h2>
    <div class="cols two">
      <div class="card"><h4>一个 agent 卡住了</h4><p>8 个画图 agent 并行，每个画 3 题。B 赛道负责 04、08、12 的那个交了 04 以后，为 08 找照片找了约 1 小时（下载了 60 多张候选），然后 10 分钟没有进展，被判失败。08 和 12 交给一个新 agent 重画，这次限定每题看 10 张左右候选。</p></div>
      <div class="card"><h4>规则边界的判定</h4><p>A03、A10、B10 的文字（灯笼字、题诗、印章）用系统自带字体排出，A06 的后期处理读了同一条命令刚渲染出来的中间图。字体是字形数据、中间图是现场生成的，都不算"读取现成图片"，各自的 log 里写明了。</p></div>
      <div class="card"><h4>画不好的地方</h4><p>多数 agent 自评都提到：3D 渲染感偏重、人物偏僵、照片拼贴的光线对不上。有几处问题是在第 6 轮才发现、已经没有轮次可改的，照原样展示，见每张图下面的自评。</p></div>
      <div class="card"><h4>照片授权</h4><p>B 赛道只用 Wikimedia Commons 上公有领域、CC0、CC BY、CC BY-SA 的照片，每张都署名。用到 CC BY-SA 照片的成品（{sa}）按 CC BY-SA 授权分享。</p></div>
    </div>
  </section>

  <section class="block">
    <h2>全部 {n} 张</h2>
    <p class="note">点图放大。每张下面有：画图的 agent 的自评、每一轮的样子和改动、源代码。"代码重新运行"是我们事后在干净目录里重跑它的命令，和交上来的图比对的结果。</p>
  </section>
  {sections}
</div>
<div id="lb" hidden><img alt=""></div>
<script>
(function () {{
  var lb = document.getElementById("lb"), lbi = lb.querySelector("img");
  document.querySelectorAll("button.zoom").forEach(function (b) {{
    b.addEventListener("click", function () {{ lbi.src = b.dataset.full; lbi.alt = b.querySelector("img").alt; lb.hidden = false; }});
  }});
  lb.addEventListener("click", function () {{ lb.hidden = true; lbi.src = ""; }});
  document.addEventListener("keydown", function (e) {{ if (e.key === "Escape") {{ lb.hidden = true; }} }});
  document.querySelectorAll(".codebar").forEach(function (bar) {{
    var pre = bar.nextElementSibling.querySelector("code");
    bar.querySelectorAll(".codebtn").forEach(function (btn) {{
      btn.addEventListener("click", function () {{
        bar.querySelectorAll(".codebtn").forEach(function (x) {{ x.setAttribute("aria-pressed", "false"); }});
        btn.setAttribute("aria-pressed", "true");
        pre.textContent = "读取中…";
        fetch(btn.dataset.src).then(function (r) {{ if (!r.ok) throw new Error(r.status); return r.text(); }})
          .then(function (t) {{ pre.textContent = t; }})
          .catch(function () {{ pre.textContent = "读取失败"; }});
      }});
    }});
  }});
}})();
</script>
"""

if __name__ == "__main__":
    main()
