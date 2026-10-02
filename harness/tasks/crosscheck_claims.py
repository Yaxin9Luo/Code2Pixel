#!/usr/bin/env python3
"""用两个模型交叉检查 dev 集细则：python3 harness/tasks/crosscheck_claims.py claude|codex

在 agent 用的镜像里 headless 跑 Claude Code（Opus）或 Codex（gpt-6.1-sol），推理强度 medium，
网络、登录和关掉的工具都和 harness/run.py 一样。模型读 claims_review_input.json，
把发现的问题写进 /workspace/review.json。结果存到 runs/_claims_review/<agent>.json。
两个模型都标出来的问题、或者只有一个模型标但理由充分的，交给用户定。
"""
import json
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "harness"))
import run  # noqa: E402  复用网络、镜像、登录的设置

PROMPT = """Read /workspace/claims_review_input.json. It holds an image-generation benchmark task bank: each task has an
English prompt and a list of claims. A vision judge will look at the generated image and answer each claim yes or no.

Review every claim of every task and report problems. A claim has a problem if:
- "not_in_prompt": it checks something the prompt does not ask for or imply (quality claims about artifacts and
  composition are intended and fine);
- "not_visual": it cannot be decided by looking at the image alone;
- "ambiguous": two careful judges could reasonably disagree on yes or no;
- "wrong": it contradicts the prompt or a fact (for example a wrong chess setup or clock-hand position).
Also report "missing": an explicit requirement of the prompt that no claim checks.

Write /workspace/review.json as a JSON list. Each item:
{"task_id": "...", "claim": "<exact claim text, or empty for missing>", "problem": "not_in_prompt|not_visual|ambiguous|wrong|missing",
 "reason": "<one sentence>", "suggestion": "<rewritten claim, or the claim to add>"}
Only list real problems; do not list claims that are fine. Do not change any other file."""


def main():
    agent = sys.argv[1]
    rows = [json.loads(l) for l in open(REPO / "harness" / "tasks" / "dev.jsonl", encoding="utf-8")]
    data = [{"task_id": r["extra_info"]["task_id"], "prompt": r["prompt"][0]["content"],
             "claims": [c["text"] for c in r["reward_model"]["claims"]]} for r in rows]
    out_dir = REPO / "runs" / "_claims_review"
    ws = out_dir / f"ws_{agent}"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    (ws / "claims_review_input.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    subprocess.run(["chmod", "-R", "a+rwX", str(ws)], check=True)
    run.ensure_network()
    env = ["-e", f"HTTPS_PROXY={run.PROXY_URL}", "-e", f"HTTP_PROXY={run.PROXY_URL}",
           "-e", f"https_proxy={run.PROXY_URL}", "-e", f"http_proxy={run.PROXY_URL}",
           "-e", "NO_PROXY=localhost,127.0.0.1", "-e", "no_proxy=localhost,127.0.0.1"]
    mounts = ["-v", f"{ws}:/workspace"]
    if agent == "claude":
        token = "".join((run.SECRETS / "claude_token").read_text().split())
        env += ["-e", f"CLAUDE_CODE_OAUTH_TOKEN={token}", "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
                "-e", "DISABLE_AUTOUPDATER=1"]
        cmd = ["claude", "-p", PROMPT, "--output-format", "json", "--dangerously-skip-permissions",
               "--effort", "medium", "--model", "opus", "--disallowedTools", "WebSearch", "WebFetch"]
    else:
        home = ws.parent / "codex_home"
        if home.exists():
            shutil.rmtree(home)
        home.mkdir()
        shutil.copy(run.SECRETS / "codex" / "auth.json", home / "auth.json")
        cfg = ['model_reasoning_effort = "medium"', 'web_search = "disabled"', "", "[features]"]
        cfg += [f"{f} = false" for f in run.CODEX_DISABLED_FEATURES]
        (home / "config.toml").write_text("\n".join(cfg) + "\n")
        subprocess.run(["chmod", "-R", "a+rwX", str(home)], check=True)
        mounts += ["-v", f"{home}:/home/agent/.codex"]
        cmd = ["codex", "exec", "--json", "--strict-config", "--skip-git-repo-check",
               "--dangerously-bypass-approvals-and-sandbox", "-C", "/workspace", PROMPT]
    p = subprocess.run(["docker", "run", "--rm", "--network", run.NET_INTERNAL, *env, *mounts, run.IMAGE, *cmd],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3600)
    (out_dir / f"{agent}_stdout.log").write_text(p.stdout[-200000:] + "\n--- stderr\n" + p.stderr[-20000:])
    if agent == "codex":
        shutil.copy(home / "auth.json", run.SECRETS / "codex" / "auth.json")   # 登录 token 可能被刷新
    review = ws / "review.json"
    if not review.exists():
        sys.exit(f"{agent}: 没有写出 review.json，见 {out_dir / (agent + '_stdout.log')}")
    items = json.loads(review.read_text())
    (out_dir / f"{agent}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(agent, len(items), "条问题")


if __name__ == "__main__":
    main()
