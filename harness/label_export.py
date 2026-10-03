#!/usr/bin/env python3
"""把跑完的作品整理成标注页（harness/label/index.html）的题目。

  python3 harness/label_export.py runs/dev-*_run_*/ --out runs/_label

输出（都在 --out，不进仓库）：
  img/<id>.jpg          要上传到标注页的图（JPEG 质量 92，原尺寸）
  items.json / pairs.json  要写进标注页数据库的文档，图片地址留空，上传后由 fill_urls 填
  key.json              题目 id 对应哪次运行、哪个 agent（标注页里看不到，算一致率时用）
题目 id 是运行名的哈希，标注的人看不出作者。同一道题有两次运行就生成一组比较。
"""
import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import judge  # noqa: E402


def hid(s):
    return hashlib.sha256(("c2p-label|" + s).encode()).hexdigest()[:12]


def to_jpg(src, dst):
    from PIL import Image
    if not dst.exists():
        Image.open(src).convert("RGB").save(dst, "JPEG", quality=92)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default=str(judge.REPO / "runs" / "_label"))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    (out / "img").mkdir(parents=True, exist_ok=True)
    tasks = judge.load_tasks()
    items, key, by_task = {}, {}, {}
    for r in a.runs:
        run = pathlib.Path(r).resolve()
        img = run / "workspace" / "out" / "final.png"
        if not (run / "result.json").exists() or not img.exists():
            continue
        res = json.loads((run / "result.json").read_text())
        task = tasks[res["task_id"]]
        i = hid(run.name)
        to_jpg(img, out / "img" / f"{i}.jpg")
        it = {"task_id": res["task_id"], "prompt": task["prompt"][0]["content"].split("\n")[0],
              "prompt_zh": task["extra_info"].get("prompt_zh", ""), "img_file": f"{i}.jpg",
              "claims": [{"text": c["text"], "weight": c["weight"]} for c in task["reward_model"]["claims"]]}
        if task["extra_info"].get("edit_base"):
            b = "base_" + pathlib.Path(task["extra_info"]["edit_base"]).name
            to_jpg(judge.TASKS.parent / task["extra_info"]["edit_base"] / "ref.png", out / "img" / f"{b}.jpg")
            it["base_file"] = f"{b}.jpg"
        items[i] = it
        key[i] = {"run": run.name, "agent": res["agent"], "tier": res["tier"], "task_id": res["task_id"]}
        by_task.setdefault(res["task_id"], []).append(i)
    pairs = {}
    for t, ids in sorted(by_task.items()):
        ids = sorted(ids, key=lambda x: key[x]["agent"])
        if len(ids) == 2:
            p = hid("pair|" + t)
            a_, b_ = ids
            pairs[p] = {"task_id": t, "prompt": items[a_]["prompt"], "prompt_zh": items[a_]["prompt_zh"],
                        "a_file": items[a_]["img_file"], "b_file": items[b_]["img_file"], "a_item": a_, "b_item": b_}
            if "base_file" in items[a_]:
                pairs[p]["base_file"] = items[a_]["base_file"]
            key[p] = {"pair": t, "a": key[a_]["run"], "b": key[b_]["run"], "a_agent": key[a_]["agent"], "b_agent": key[b_]["agent"]}
    (out / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    (out / "pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=1))
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))
    print(len(items), "张图，", len(pairs), "组比较 →", out)
    # 已上传的图（uploaded.json：文件名 → 标注页里的地址）对应的文档写到 docs/，再用 ArtifactData 批量写入
    up = json.loads((out / "uploaded.json").read_text()) if (out / "uploaded.json").exists() else {}
    todo = sorted({f.name for f in (out / "img").glob("*.jpg")} - set(up))
    docs = out / "docs"
    for sub in ("items", "pairs"):
        (docs / sub).mkdir(parents=True, exist_ok=True)
    ready = []
    for i, it in items.items():
        if it["img_file"] in up and it.get("base_file", it["img_file"]) in up:
            d = {k: v for k, v in it.items() if not k.endswith("_file")}
            d["img"] = up[it["img_file"]]
            if "base_file" in it:
                d["base"] = up[it["base_file"]]
            (docs / "items" / f"{i}.json").write_text(json.dumps(d, ensure_ascii=False))
            ready.append(("items", i))
    for i, p in pairs.items():
        fs = [p["a_file"], p["b_file"]] + ([p["base_file"]] if "base_file" in p else [])
        if all(f in up for f in fs):
            d = {"task_id": p["task_id"], "prompt": p["prompt"], "prompt_zh": p["prompt_zh"],
                 "a_img": up[p["a_file"]], "b_img": up[p["b_file"]]}
            if "base_file" in p:
                d["base"] = up[p["base_file"]]
            (docs / "pairs" / f"{i}.json").write_text(json.dumps(d, ensure_ascii=False))
            ready.append(("pairs", i))
    (out / "ready.json").write_text(json.dumps(ready))
    print("待上传的图：", len(todo), "；可写入的文档：", len(ready))
    for f in todo:
        print("  upload", out / "img" / f)


if __name__ == "__main__":
    main()
