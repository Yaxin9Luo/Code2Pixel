"""核对每张图的证据：log.json 完整、轮数不超过 6、代码能从头重新生成同一张 final.png、A 赛道没有联网或读现成图片。

用法: python3 verify.py            # 输出 verify.json，并打印一张表
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_EXT = (".py", ".js", ".html", ".svg", ".sh")
NET = re.compile(r"urllib|requests|https?://|curl |wget|socket|fetch_reference|search_commons")
READ_IMG = re.compile(r"Image\.open|imread|\.jpe?g['\"]|<image|drawImage|url\(")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def code_files(d):
    out = []
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ("rounds", "refs", "__pycache__")]
        for f in files:
            if f.endswith(CODE_EXT) and not f.startswith("final"):
                out.append(os.path.join(root, f))
    return sorted(out)


def check(d):
    rid = os.path.basename(d.rstrip("/"))
    track = os.path.basename(os.path.dirname(d.rstrip("/")))
    r = {"id": f"{track}{rid}", "dir": d, "issues": []}
    lp = os.path.join(d, "log.json")
    if not os.path.exists(lp):
        r["issues"].append("没有 log.json")
        return r
    log = json.load(open(lp))
    r["log"] = log
    fin = os.path.join(d, "final.png")
    if not os.path.exists(fin):
        r["issues"].append("没有 final.png")
        return r
    im = Image.open(fin)
    r["size"] = im.size
    if not 1200 <= max(im.size) <= 1600:
        r["issues"].append(f"长边 {max(im.size)} 不在 1200–1600")
    rounds = log.get("rounds", [])
    r["n_rounds"] = len(rounds)
    if len(rounds) > 6:
        r["issues"].append(f"{len(rounds)} 轮，超过 6 轮")
    missing = [x["png"] for x in rounds if not os.path.exists(os.path.join(d, x.get("png", "")))]
    if missing:
        r["issues"].append(f"缺少轮次图 {missing}")
    if rounds and os.path.exists(os.path.join(d, rounds[-1]["png"])):
        a = np.asarray(Image.open(os.path.join(d, rounds[-1]["png"])).convert("RGB"), np.float32)
        b = np.asarray(im.convert("RGB"), np.float32)
        if a.shape != b.shape or np.abs(a - b).mean() > 1.0:
            r["issues"].append("final.png 和最后一轮的图不一样")
    try:
        r["minutes"] = round((log["end"] - log["start"]) / 60, 1)
    except (KeyError, TypeError):
        r["issues"].append("没有开始/结束时间")
    cf = code_files(d)
    r["code_files"] = [os.path.relpath(f, d) for f in cf]
    r["code_lines"] = sum(sum(1 for _ in open(f, errors="ignore")) for f in cf)
    r["code_bytes"] = sum(os.path.getsize(f) for f in cf)
    # 静态检查：A 赛道不能联网、不能读现成图片（读自己渲染出来的中间 PNG 另行人工确认）
    flags = []
    for f in cf:
        for i, line in enumerate(open(f, errors="ignore"), 1):
            if NET.search(line) and not line.strip().startswith(("#", "//")):
                if track == "A" or "fetch_reference" in line or "search_commons" in line or "urllib" in line:
                    flags.append(f"{os.path.relpath(f, d)}:{i} 联网？ {line.strip()[:100]}")
            if track == "A" and READ_IMG.search(line):
                flags.append(f"{os.path.relpath(f, d)}:{i} 读图？ {line.strip()[:100]}")
    r["flags"] = flags
    if track == "A":
        imgs = [p for p in glob.glob(os.path.join(d, "**", "*"), recursive=True)
                if p.lower().endswith((".jpg", ".jpeg")) and "/rounds/" not in p]
        if imgs:
            r["issues"].append(f"A 赛道目录里有 JPG：{[os.path.relpath(p, d) for p in imgs]}")
    else:
        refs = glob.glob(os.path.join(d, "refs", "*"))
        r["n_refs"] = len(refs)
        if not log.get("credits"):
            r["issues"].append("B 赛道没有署名")
    # 重新生成：拷到临时目录，把命令里的原目录换成临时目录，断网不可控但命令本身不应联网
    before = sha(fin)
    # 临时目录保持和原目录相同的层级（项目/demo/赛道/题号），demo/tools 和 stylize 用符号链接，代码里的相对路径照样能用
    tmp = tempfile.mkdtemp(prefix="verify-")
    proj = os.path.dirname(HERE)
    troot = os.path.join(tmp, os.path.basename(proj))
    os.makedirs(os.path.join(troot, "demo", track))
    os.symlink(os.path.join(HERE, "tools"), os.path.join(troot, "demo", "tools"))
    os.symlink(os.path.join(proj, "stylize"), os.path.join(troot, "stylize"))
    dst = os.path.join(troot, "demo", track, rid)
    shutil.copytree(d, dst, ignore=shutil.ignore_patterns("rounds", "__pycache__"))
    os.remove(os.path.join(dst, "final.png"))
    cmd = log.get("cmd", "").replace(d.rstrip("/"), dst)
    t0 = time.time()
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=900)
    r["regen_s"] = round(time.time() - t0, 1)
    new = os.path.join(dst, "final.png")
    if p.returncode != 0 or not os.path.exists(new):
        r["issues"].append(f"重新生成失败：{(p.stderr or p.stdout)[-300:]}")
        r["regen"] = "fail"
    else:
        a = np.asarray(Image.open(new).convert("RGB"), np.float64)
        b = np.asarray(Image.open(fin).convert("RGB"), np.float64)
        if a.shape != b.shape:
            r["regen"] = f"尺寸不同 {a.shape} vs {b.shape}"
            r["issues"].append("重新生成的尺寸不同")
        else:
            mse = ((a - b) ** 2).mean()
            r["regen"] = "完全一致" if mse == 0 else f"PSNR {10 * np.log10(255 ** 2 / mse):.1f} dB"
            if mse > 0 and 10 * np.log10(255 ** 2 / mse) < 40:
                r["issues"].append(f"重新生成的图不一致（{r['regen']}）")
    if sha(fin) != before:
        r["issues"].append("重新生成时改写了原目录的 final.png（代码里写死了路径）")
    shutil.rmtree(tmp, ignore_errors=True)
    return r


def main():
    import sys
    tracks = sys.argv[1] if len(sys.argv) > 1 else "AB"   # 只核对某条赛道：python3 verify.py A [05,06]
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    res = []
    for d in sorted(glob.glob(os.path.join(HERE, f"[{tracks}]", "[0-9][0-9]"))):
        if only and os.path.basename(d) not in only:
            continue
        r = check(d)
        res.append(r)
        print(f"{r['id']:4s} 轮数 {r.get('n_rounds', '?')}  用时 {r.get('minutes', '?')} 分  代码 {r.get('code_lines', '?')} 行"
              f"  重新生成：{r.get('regen', '?')}  问题：{r['issues'] or '无'}  标记 {len(r.get('flags', []))}")
    out = os.path.join(HERE, "verify.json")
    old = {r["id"]: r for r in json.load(open(out))} if os.path.exists(out) else {}
    old.update({r["id"]: {k: v for k, v in r.items() if k != "log"} for r in res})
    json.dump([old[k] for k in sorted(old)], open(out, "w"), ensure_ascii=False, indent=1)
    for r in res:
        for f in r.get("flags", []):
            print(f"  {r['id']} 标记：{f}")


if __name__ == "__main__":
    main()
