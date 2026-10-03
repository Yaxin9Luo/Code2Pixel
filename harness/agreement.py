#!/usr/bin/env python3
"""裁判和人的一致率汇总。

  python3 harness/agreement.py --runs runs/dev-*_run_*/ [--labels runs/_label/db/labels] [--label-dir runs/_label]

人的标注：先用 ArtifactData list（out_dir=runs/_label/db）把标注页的 labels 集合存到本地，每人一个 JSON。
报告：
  - 裁判自洽：同一模型判两遍，逐条结论一致的比例
  - 裁判之间：两个模型（各取第 1 遍）逐条一致的比例，按题目类别分
  - 裁判和人：裁判和人的多数意见一致的比例（只算有人标过的条目）；人和人之间两两一致的比例
  - 两两比较：裁判（两种顺序都一致才算）和人的多数意见一致的比例
没有数据的项跳过不报。
"""
import argparse
import collections
import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import judge  # noqa: E402


def load_judges(runs):
    """{run_name: {model: {round: [bool,...]}}}"""
    out = {}
    for r in runs:
        r = pathlib.Path(r)
        for f in sorted((r / "judge").glob("*_r*.json")) if (r / "judge").exists() else []:
            if f.name.startswith("code_"):
                continue
            model, rnd = f.stem.rsplit("_r", 1)
            j = json.loads(f.read_text())
            if "claims" in j:
                out.setdefault(r.name, {}).setdefault(model, {})[int(rnd)] = [c["yes"] for c in j["claims"]]
    return out


def rate(pairs):
    pairs = list(pairs)
    return (round(sum(a == b for a, b in pairs) / len(pairs), 3), len(pairs)) if pairs else (None, 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--label-dir", default=str(judge.REPO / "runs" / "_label"))
    a = ap.parse_args()
    tasks = judge.load_tasks()
    J = load_judges(a.runs)
    res = json.loads
    cat = {}
    for r in a.runs:
        p = pathlib.Path(r) / "result.json"
        if p.exists():
            t = res(p.read_text())["task_id"]
            e = tasks[t]["extra_info"]
            cat[pathlib.Path(r).name] = e["category"] if e["category"] != "code_wins" else "code_wins/" + e["subtype"]
    models = sorted({m for v in J.values() for m in v})
    report = {"self_consistency": {}, "between_models": {}, "judge_vs_human": {}, "human_vs_human": None, "pairwise": {}}

    for m in models:
        report["self_consistency"][m] = rate((x, y) for v in J.values() if m in v and 1 in v[m] and 2 in v[m]
                                             for x, y in zip(v[m][1], v[m][2]))
    for m1, m2 in itertools.combinations(models, 2):
        by = collections.defaultdict(list)
        for run, v in J.items():
            if m1 in v and m2 in v and 1 in v[m1] and 1 in v[m2]:
                for x, y in zip(v[m1][1], v[m2][1]):
                    by[cat.get(run, "?")].append((x, y))
        report["between_models"][f"{m1} vs {m2}"] = {"all": rate(p for l in by.values() for p in l),
                                                    **{k: rate(l) for k, l in sorted(by.items())}}

    ld = pathlib.Path(a.label_dir)
    key = json.loads((ld / "key.json").read_text()) if (ld / "key.json").exists() else {}
    lab_dir = ld / "db" / "labels"
    people = [json.loads(f.read_text()) for f in sorted(lab_dir.glob("*.json"))] if lab_dir.exists() else []
    people = [p.get("data", p) for p in people]
    if people:
        # 逐条：每个条目每个人的答案
        votes = collections.defaultdict(list)    # (run, i) -> [bool]
        per_person = []
        for p in people:
            mine = {}
            for item, ans in (p.get("claims") or {}).items():
                if item not in key:
                    continue
                for i, v in enumerate(ans):
                    if v in ("y", "n"):
                        votes[(key[item]["run"], i)].append(v == "y")
                        mine[(key[item]["run"], i)] = v == "y"
            per_person.append(mine)
        hh = []
        for x, y in itertools.combinations(per_person, 2):
            hh += [(x[k], y[k]) for k in x.keys() & y.keys()]
        report["human_vs_human"] = rate(hh)
        major = {k: sum(v) > len(v) / 2 for k, v in votes.items() if sum(v) * 2 != len(v)}   # 平票不算
        for m in models:
            report["judge_vs_human"][m] = rate((J[run][m][1][i], h) for (run, i), h in major.items()
                                               if run in J and m in J[run] and 1 in J[run][m])
        # 两两比较
        pv = collections.defaultdict(list)
        for p in people:
            for pid, v in (p.get("pairs") or {}).items():
                if pid in key:
                    pv[pid].append(v)
        pdir = judge.REPO / "runs" / "_pairwise"
        for m in models:
            agree = []
            for pid, vs in pv.items():
                c = collections.Counter(vs).most_common()
                if len(c) > 1 and c[0][1] == c[1][1]:
                    continue
                h = c[0][0]
                k = key[pid]
                f = pdir / f"{k['pair']}__{k['a']}__{k['b']}__{m}.json"
                if f.exists():
                    agree.append((json.loads(f.read_text())["result"], h))
            report["pairwise"][m] = rate(agree)
        report["labelers"] = len(people)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    out = judge.REPO / "runs" / "_agreement.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
