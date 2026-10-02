#!/usr/bin/env python3
"""验证门槛本身：正样本不能误判，对抗样本必须全部判不过。

用法：
  python3 harness/gate_validate.py --pilot-src ~/Desktop/千里江山图_代码复现   # 准备样本并跑门槛
  python3 harness/gate_validate.py --only redteam                             # 只跑手写对抗样本

样本放在 runs/_gate_samples/（不进仓库）：
  pos_A01 … pos_A12  试跑 A 赛道（只给文字、没用素材）的 12 张。它们是在 Mac 上直接跑的，不在镜像里：
                     有的写死了 Mac 上的字体或 Chrome 路径，有的换了库版本后像素不同。所以正样本只要求
                     "除了复现以外没有违规"，复现不过的记为环境差异，单独列出
  red_*              harness/redteam/ 里手写的对抗样本，每个目录有 src/、run.sh 和 EXPECT（应该命中的违规）
阶段 1 验收的运行直接用 `python3 harness/gate.py runs/pilot-*` 检查。
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "harness"))
import gate  # noqa: E402

SAMPLES = REPO / "runs" / "_gate_samples"
REDTEAM = REPO / "harness" / "redteam"


def prep_pilot(src):
    """试跑 A 赛道：保留原来的相对路径（A06 会调用 demo/tools/render.py），代码不改。"""
    from PIL import Image
    out = []
    for d in sorted((src / "demo" / "A").iterdir()):
        if not (d / "final.png").exists():
            continue
        run = SAMPLES / f"pos_A{d.name}"
        if run.exists():
            shutil.rmtree(run)
        ws = run / "workspace"
        code = ws / "src" / "demo" / "A" / d.name
        code.mkdir(parents=True)
        for f in d.iterdir():
            if f.suffix in (".py", ".js", ".html", ".sh"):
                shutil.copy(f, code / f.name)
        shutil.copytree(src / "demo" / "tools", ws / "src" / "demo" / "tools",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (ws / "src" / "stylize").mkdir()   # A05 用相对路径 import 项目里的 stylize（首次调用时编译 npr.c）
        for f in ("stylize.py", "npr.c"):
            shutil.copy(src / "stylize" / f, ws / "src" / "stylize" / f)
        (ws / "run.sh").write_text(f"set -e\ncd src/demo/A/{d.name}\n/opt/venv/bin/python draw.py\n"
                                   "cp final.png /workspace/out/final.png\n")
        (ws / "out").mkdir()
        shutil.copy(d / "final.png", ws / "out" / "final.png")
        out.append((run, list(Image.open(d / "final.png").size), None))
    return out


def prep_redteam():
    """手写对抗样本：先在门槛镜像里跑一遍生成 final.png（有的会故意失败，比如断网下载）。"""
    out = []
    for d in sorted(p for p in REDTEAM.iterdir() if p.is_dir()):
        run = SAMPLES / f"red_{d.name}"
        if run.exists():
            shutil.rmtree(run)
        ws = run / "workspace"
        shutil.copytree(d, ws, ignore=shutil.ignore_patterns("EXPECT", "__pycache__"))
        (ws / "out").mkdir(exist_ok=True)
        subprocess.run(["chmod", "-R", "a+rwX", str(ws)])
        subprocess.run(["docker", "run", "--rm", "--network", "none", "-v", f"{ws}:/workspace", "-w", "/workspace",
                        gate.IMAGE, "bash", "run.sh"], capture_output=True)
        expect = (d / "EXPECT").read_text().split()
        out.append((run, None, expect))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-src", type=pathlib.Path, default=None)
    ap.add_argument("--only", choices=["pilot", "redteam"], default=None)
    a = ap.parse_args()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    samples = []
    if a.only != "redteam" and a.pilot_src:
        samples += prep_pilot(a.pilot_src.expanduser())
    if a.only != "pilot":
        samples += prep_redteam()
    print("| 样本 | 应该 | 门槛 | 命中的违规 | 复现 | 结论 |")
    print("|---|---|---|---|---|---|")
    bad = 0
    for run, size, expect in samples:
        g = gate.gate(run, size)
        rules = sorted({x["rule"] for x in g["violations"]})
        if expect is None:
            ok = not (set(rules) - {"regen"})
            should = "无违规（复现可因环境差异不过）"
        else:
            ok = not g["pass"] and set(expect) <= set(rules)
            should = "不过：" + ", ".join(expect)
        bad += not ok
        print(f"| {run.name} | {should} | {'通过' if g['pass'] else '不过'} | {', '.join(rules) or '-'} | "
              f"{g['checks']['regen'].get('status')} | {'✓' if ok else '✗'} |", flush=True)
    print(f"\n{len(samples) - bad}/{len(samples)} 符合预期")


if __name__ == "__main__":
    main()
