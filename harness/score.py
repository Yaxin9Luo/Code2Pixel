#!/usr/bin/env python3
"""汇总一批运行的 benchmark 分数：python3 harness/score.py runs/dev-*_run_*/ [--min-req 0.8]

分数怎么算（2026-10-02 用户定"细则当门槛、两两比较当主分，再加质量细则"）：
  1. 门槛（gate.json）：不过的记 0。
  2. 要求细则（kind=requirement，题目明确要求的）：每条按裁判几遍判断的多数（平票按一半）算，
     加权通过比例 R ≥ --min-req 才算"满足题目"。
  3. 主分：两两比较（runs/_pairwise）。门槛没过或 R 没达标的一方直接判负，其余用裁判的比较结果；
     Bradley–Terry 算 Elo，bootstrap 给 95% 区间。
  4. 质量细则（kind=quality）的通过比例 Q 单独报告，不进主分。
每个裁判单独出一份结果，不混在一起：人工标注出来之前，不知道哪个裁判更可信。
"""
import argparse
import collections
import glob
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import judge  # noqa: E402
import pairwise  # noqa: E402


def claim_scores(run, model, tasks):
    files = sorted((run / "judge").glob(f"{model}_r*.json"))
    if not files:
        return None
    rounds = [json.loads(f.read_text())["claims"] for f in files]
    task = tasks[json.loads((run / "result.json").read_text())["task_id"]]
    kinds = [c.get("kind", "requirement" if c["weight"] == 2 else "quality") for c in task["reward_model"]["claims"]]
    if any(len(r) != len(kinds) for r in rounds):
        return None   # 旧细则判的，对不上
    yes = [sum(r[i]["yes"] for r in rounds) / len(rounds) for i in range(len(kinds))]
    w = [c["weight"] for c in task["reward_model"]["claims"]]
    req = [i for i, k in enumerate(kinds) if k == "requirement"]
    qual = [i for i, k in enumerate(kinds) if k == "quality"]
    R = sum(yes[i] * w[i] for i in req) / sum(w[i] for i in req) if req else 1.0
    Q = sum(yes[i] for i in qual) / len(qual) if qual else None
    return R, Q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--min-req", type=float, default=0.8)
    ap.add_argument("--models", nargs="+", default=list(judge.MODELS))
    a = ap.parse_args()
    tasks = judge.load_tasks()
    runs = [pathlib.Path(r).resolve() for r in a.runs]
    info = {}
    for r in runs:
        res = json.loads((r / "result.json").read_text())
        g = json.loads((r / "gate.json").read_text()) if (r / "gate.json").exists() else {"pass": False}
        info[r.name] = {"who": f"{res['agent']}/{res['tier']}", "task": res["task_id"], "gate": bool(g.get("pass")), "run": r}
    out = {"min_req": a.min_req, "models": {}}
    for m in a.models:
        per = collections.defaultdict(lambda: {"n": 0, "gate": 0, "req_ok": 0, "R": [], "Q": []})
        ok = {}
        for name, x in info.items():
            cs = claim_scores(x["run"], m, tasks)
            s = per[x["who"]]
            s["n"] += 1
            s["gate"] += x["gate"]
            if cs is None:
                ok[name] = None
                continue
            R, Q = cs
            s["R"].append(R)
            if Q is not None:
                s["Q"].append(Q)
            ok[name] = x["gate"] and R >= a.min_req
            s["req_ok"] += ok[name]
        games = []
        for f in glob.glob(str(judge.REPO / "runs" / "_pairwise" / f"*__{m}.json")):
            d = json.loads(pathlib.Path(f).read_text())
            if d["a"] not in info or d["b"] not in info:
                continue
            oa, ob = ok.get(d["a"]), ok.get(d["b"])
            if oa is None or ob is None:
                continue
            res = d["result"] if (oa and ob) else ("tie" if not oa and not ob else ("a" if oa else "b"))
            games.append((info[d["a"]]["who"], info[d["b"]]["who"], res))
        elo, ci = {}, {}
        if games:
            elo = pairwise.bradley_terry(games)
            rnd = random.Random(0)
            boots = collections.defaultdict(list)
            for _ in range(300):
                e = pairwise.bradley_terry([rnd.choice(games) for _ in games], iters=200)
                for k, v in e.items():
                    boots[k].append(v)
            ci = {k: (round(sorted(v)[7]), round(sorted(v)[292])) for k, v in boots.items()}
        wins = collections.Counter()
        for x, y, r in games:
            wins[(x, {"a": "win", "b": "loss", "tie": "tie"}[r])] += 1
            wins[(y, {"a": "loss", "b": "win", "tie": "tie"}[r])] += 1
        out["models"][m] = {who: {
            "runs": s["n"], "gate_pass": s["gate"], "meets_prompt": s["req_ok"],
            "mean_R": round(sum(s["R"]) / len(s["R"]), 3) if s["R"] else None,
            "mean_Q": round(sum(s["Q"]) / len(s["Q"]), 3) if s["Q"] else None,
            "pairwise": {k: wins[(who, k)] for k in ("win", "loss", "tie")},
            "elo": elo.get(who), "elo_95ci": ci.get(who)} for who, s in sorted(per.items())}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    (judge.REPO / "runs" / "_score.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
