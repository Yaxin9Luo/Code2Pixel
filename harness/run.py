#!/usr/bin/env python3
"""Code2Pixel harness：在统一镜像里跑一个现成 agent（Claude Code 或 Codex）完成一道题。

用法：
  python3 harness/run.py --task pilot-10 --agent claude --tier run
  python3 harness/run.py --task pilot-10 --agent codex --tier nolook --model gpt-5.5

做的事：
  1. 建工作区，写题目说明 TASK.md
  2. 起容器：只接内部网络，通过出口代理上网（白名单见 env/proxy/allowlist）
  3. 在容器里以 headless 模式跑 agent，实时读 token 用量，超预算或超时就停
  4. 收集产出（out/final.png、src/、run.sh）、对话记录、token 和时间，写 result.json

token 口径：每次模型调用的"新增输入（不含缓存命中）+ 输出"累加。缓存读取的原始数字也记录。
登录凭据放在 ~/.code2pixel/（不进仓库）：
  claude_token      `claude setup-token` 生成的订阅 token
  codex/auth.json   `codex login` 生成的登录文件
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import threading
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
SECRETS = pathlib.Path.home() / ".code2pixel"
IMAGE = "code2pixel/env:0.1"
PROXY_IMAGE = "code2pixel/proxy:0.1"
NET_INTERNAL = "c2p-internal"
PROXY_NAME = "c2p-proxy"
PROXY_URL = f"http://{PROXY_NAME}:8888"

# 两档只差能不能看图。上限只防失控：验收里 agent 都是自己停下的，最多用了 13 万 token、22 分钟。
# （2026-10-01 之前还有 low：20 万 token、30 分钟；high：100 万、90 分钟，见 docs/PHASE1.md）
TIERS = {
    "nolook": dict(tokens=1_000_000, minutes=90, look=False),
    "run": dict(tokens=1_000_000, minutes=90, look=True),
}
CODEX_DISABLED_FEATURES = ["image_generation", "browser_use", "browser_use_external", "computer_use",
                           "in_app_browser", "apps", "plugins", "remote_plugin"]
STALL_MINUTES = 10   # 对话记录和会话记录连续这么久没有新内容、容器 CPU 也空闲，判定为卡住（比如模型流式回复挂住）
STALL_CPU_PERCENT = 5   # 容器 CPU 高于这个值说明还在干活（比如长时间渲染），不算卡住
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def sh(cmd, check=True, **kw):
    return subprocess.run(cmd, check=check, text=True, capture_output=True, **kw)


# ---------------------------------------------------------------- 网络
def ensure_network():
    nets = sh(["docker", "network", "ls", "--format", "{{.Name}}"]).stdout.split()
    if NET_INTERNAL not in nets:
        sh(["docker", "network", "create", "--internal", NET_INTERNAL])
    running = sh(["docker", "ps", "--format", "{{.Names}}"]).stdout.split()
    if PROXY_NAME not in running:
        sh(["docker", "rm", "-f", PROXY_NAME], check=False)
        sh(["docker", "build", "-t", PROXY_IMAGE, str(REPO / "env" / "proxy")])
        sh(["docker", "run", "-d", "--name", PROXY_NAME, "--network", "bridge", PROXY_IMAGE])
        sh(["docker", "network", "connect", NET_INTERNAL, PROXY_NAME])


# ---------------------------------------------------------------- 题目说明
def task_text(task, tier):
    t = TIERS[tier]
    size = task["reward_model"]["gate"]["size"]
    look = ("你可以渲染后查看自己画出的图片，再修改。" if t["look"] else
            "本档不允许查看任何图片，包括你自己渲染出的结果：不要读取或打开图片文件，写完代码、生成图片后直接交稿。")
    return f"""# 任务

用代码画一张图，内容如下：

> {task["prompt"][0]["content"]}

## 交付（路径固定）

- `/workspace/out/final.png`：最终图，尺寸 {size[0]}×{size[1]}
- `/workspace/src/`：生成它的全部代码
- `/workspace/run.sh`：一条命令，在干净环境里从头重新生成 `out/final.png`

## 规则

- 只能用代码画。不能调用任何图像生成模型或神经网络，不能加载预训练权重。
- 不能联网下载任何东西，不能读取环境里现成的图片或素材，不能把位图（比如 base64 图片）嵌进代码。
- {look}
- 预算：约 {t["tokens"] // 10000} 万 token、{t["minutes"]} 分钟，超出会被直接停止，只保留停止时已有的文件。

## 环境

- Python（/opt/venv）：numpy、scipy、pillow、matplotlib、scikit-image、opencv、shapely、cairosvg、pycairo、playwright
- Node：three、playwright（`NODE_PATH` 已设好）
- `c2p-render in.svg|in.html out.png --width W --height H [--wait-ms N]`：用 headless Chromium（支持 WebGL）把 SVG 或 HTML 渲染成 PNG。
  页面里可以直接 `import * as THREE from "/opt/node/node_modules/three/build/three.module.js"`；异步绘制完成后设 `window.C2P_READY = true`。
- Blender 4.0（`blender -b -P script.py`）：用 Cycles 时要设 `scene.cycles.use_denoising = False`（这个版本没有降噪库）。
- `rsvg-convert`、ImageMagick、中文字体（Noto CJK）
"""


# ---------------------------------------------------------------- token 统计
class Meter:
    def __init__(self):
        self.budget_tokens = 0          # 新增输入 + 输出
        self.raw = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "reasoning": 0}
        self.calls = 0
        self.image_views = 0
        self.model = None
        self.effort = None
        self.read_image_attempts = 0    # Claude：调用 Read 读图片的次数（不看图档里会被拒绝）
        self.tools = None               # Claude：会话实际启用的工具
        self.reported = None            # Claude：结束时自己报告的总用量，用来对账


def claude_line(meter, ev, usage, current):
    """Claude Code stream-json（加 --include-partial-messages）。
    assistant 事件里的 usage 是请求开始时的快照，输出数停在个位数、不会更新；最终输出数只在流事件
    message_delta 里。所以按 message_start 记下消息 id（子 agent 的流用 parent_tool_use_id 区分），
    再用 message_delta 的 usage 更新。没有流事件的消息退回用 assistant 事件的 usage。
    usage：消息 id → 这次调用的 usage；current：parent_tool_use_id → 正在流式输出的消息 id。
    看图次数按工具结果里实际返回的图片数：被拒绝的读图尝试单独记，不算看图。"""
    t = ev.get("type")
    if t == "system" and ev.get("subtype") == "init":
        meter.model = ev.get("model")
        meter.tools = ev.get("tools")
    if t == "result":
        meter.reported = {k: ev.get(k) for k in ("usage", "modelUsage", "num_turns", "total_cost_usd",
                                                  "is_error", "terminal_reason", "api_error")}
    if t == "user":
        content = ev.get("message", {}).get("content", [])
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                meter.image_views += sum(1 for x in block["content"] if isinstance(x, dict) and x.get("type") == "image")
    if t == "stream_event":
        se, key = ev.get("event", {}), ev.get("parent_tool_use_id")
        if se.get("type") == "message_start":
            msg = se.get("message", {})
            current[key] = msg.get("id")
            usage[msg.get("id")] = dict(msg.get("usage") or {})
        elif se.get("type") == "message_delta" and current.get(key) in usage:
            u = usage[current[key]]
            for k, v in (se.get("usage") or {}).items():   # 都是累计值，取大的
                u[k] = max(u.get(k) or 0, v) if isinstance(v, (int, float)) else (v if v is not None else u.get(k))
        else:
            return
    elif t == "assistant":
        msg = ev.get("message", {})
        for block in msg.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "Read":
                if str(block.get("input", {}).get("file_path", "")).lower().endswith(IMAGE_EXT):
                    meter.read_image_attempts += 1
        if not msg.get("id") or msg["id"] in usage:
            return
        usage[msg["id"]] = dict(msg.get("usage") or {})
    else:
        return
    us = usage.values()
    meter.calls = len(usage)
    meter.raw["input"] = sum(u.get("input_tokens") or 0 for u in us)
    meter.raw["cache_write"] = sum(u.get("cache_creation_input_tokens") or 0 for u in us)
    meter.raw["cache_read"] = sum(u.get("cache_read_input_tokens") or 0 for u in us)
    meter.raw["output"] = sum(u.get("output_tokens") or 0 for u in us)
    meter.raw["reasoning"] = sum((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0 for u in us)
    meter.budget_tokens = meter.raw["input"] + meter.raw["cache_write"] + meter.raw["output"]


def claude_reported_budget(reported):
    """Claude Code 结束时报告的总用量（modelUsage 含所有模型、所有调用），口径同上。没有就返回 None。"""
    mu = (reported or {}).get("modelUsage") or {}
    if not mu:
        return None
    return sum((m.get("inputTokens") or 0) + (m.get("cacheCreationInputTokens") or 0) + (m.get("outputTokens") or 0)
               for m in mu.values())


def codex_rollout(meter, codex_home):
    """Codex 的会话记录（CODEX_HOME/sessions/**/rollout-*.jsonl）里有逐次调用的累计 token。
    每次都从头重读，所以计数在函数里重新算。看图次数按工具输出里带回的图片（input_image）数，
    因为 Codex 可以在 exec 的代码里调用 tools.view_image，不一定直接调用 view_image 工具。"""
    files = sorted((codex_home / "sessions").rglob("rollout-*.jsonl")) if (codex_home / "sessions").exists() else []
    views = calls = 0
    for f in files:
        for line in f.read_text(errors="ignore").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = ev.get("payload", {})
            if ev.get("type") == "turn_context":
                meter.model = p.get("model", meter.model)
                meter.effort = p.get("effort") or p.get("reasoning_effort") or meter.effort
            if p.get("type") == "token_count" and p.get("info"):
                tot = p["info"].get("total_token_usage", {})
                meter.raw["input"] = tot.get("input_tokens", 0)
                meter.raw["cache_read"] = tot.get("cached_input_tokens", 0)
                meter.raw["output"] = tot.get("output_tokens", 0)
                meter.raw["reasoning"] = tot.get("reasoning_output_tokens", 0)
                meter.budget_tokens = meter.raw["input"] - meter.raw["cache_read"] + meter.raw["output"]
                calls += 1
            if p.get("type") in ("function_call_output", "custom_tool_call_output"):
                views += json.dumps(p.get("output")).count('"input_image"')
    meter.calls = calls
    meter.image_views = views


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--tasks-file", default=str(REPO / "harness" / "tasks" / "pilot.jsonl"))
    ap.add_argument("--agent", choices=["claude", "codex"], required=True)
    ap.add_argument("--tier", choices=list(TIERS), required=True)
    ap.add_argument("--model", default=None, help="不填用各 agent 的默认模型")
    ap.add_argument("--effort", default="medium", help="推理强度，默认 medium")
    ap.add_argument("--runs-dir", default=str(REPO / "runs"))
    ap.add_argument("--cpus", default="4")
    ap.add_argument("--memory", default="6g")
    a = ap.parse_args()

    tasks = {json.loads(l)["extra_info"]["task_id"]: json.loads(l) for l in open(a.tasks_file, encoding="utf-8") if l.strip()}
    task = tasks[a.task]
    tier = TIERS[a.tier]
    run_id = f"{a.task}_{a.agent}_{a.tier}_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run = pathlib.Path(a.runs_dir) / run_id
    ws = run / "workspace"
    (ws / "out").mkdir(parents=True)
    (ws / "src").mkdir()
    text = task_text(task, a.tier)
    (ws / "TASK.md").write_text(text, encoding="utf-8")
    os.chmod(ws, 0o777)
    for p in ws.rglob("*"):
        os.chmod(p, 0o777 if p.is_dir() else 0o666)

    ensure_network()
    env = ["-e", f"HTTPS_PROXY={PROXY_URL}", "-e", f"HTTP_PROXY={PROXY_URL}",
           "-e", f"https_proxy={PROXY_URL}", "-e", f"http_proxy={PROXY_URL}",
           "-e", "NO_PROXY=localhost,127.0.0.1", "-e", "no_proxy=localhost,127.0.0.1"]
    mounts = ["-v", f"{ws}:/workspace"]
    codex_home = None
    prompt = "请阅读 /workspace/TASK.md，按要求完成任务。"

    if a.agent == "claude":
        token = "".join((SECRETS / "claude_token").read_text().split())   # 复制时终端折行会混进换行
        env += ["-e", f"CLAUDE_CODE_OAUTH_TOKEN={token}",
                "-e", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1", "-e", "DISABLE_AUTOUPDATER=1"]
        # --include-partial-messages：输出 token 的最终数只在流事件里（见 claude_line）
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--dangerously-skip-permissions", "--effort", a.effort]
        cmd += ["--model", a.model or "opus"]   # 订阅默认是 Sonnet，benchmark 默认测最强模型
        # WebSearch 在服务端执行，不经过代理；WebFetch 也一并禁用
        blocked = ["WebSearch", "WebFetch"]
        if not tier["look"]:
            # 相对规则管工作目录，// 开头的绝对规则管其他位置（比如渲染到 /tmp 再读）
            blocked += [f"Read(**/*{e})" for e in IMAGE_EXT] + [f"Read(//**/*{e})" for e in IMAGE_EXT]
        cmd += ["--disallowedTools", *blocked]
    else:
        codex_home = run / "codex_home"
        codex_home.mkdir()
        shutil.copy(SECRETS / "codex" / "auth.json", codex_home / "auth.json")
        # 联网搜索和图像生成都在服务端执行，不经过我们的代理，必须在配置里关掉
        cfg = [f'model_reasoning_effort = "{a.effort}"', 'web_search = "disabled"', "", "[features]"]
        cfg += [f"{f} = false" for f in CODEX_DISABLED_FEATURES]
        if not tier["look"]:
            cfg += ["view_image = false"]
        (codex_home / "config.toml").write_text("\n".join(cfg) + "\n")
        os.chmod(codex_home, 0o777)
        for p in codex_home.iterdir():
            os.chmod(p, 0o666)
        mounts += ["-v", f"{codex_home}:/home/agent/.codex"]
        cmd = ["codex", "exec", "--json", "--strict-config", "--skip-git-repo-check",
               "--dangerously-bypass-approvals-and-sandbox", "-C", "/workspace"]
        if a.model:
            cmd += ["-m", a.model]
        cmd += [prompt]

    name = f"c2p-{run_id}".replace("_", "-").lower()[:60]
    sh(["docker", "run", "-d", "--name", name, "--network", NET_INTERNAL, "--cpus", a.cpus,
        "--memory", a.memory, *env, *mounts, IMAGE, "sleep", "infinity"])
    started = time.time()
    started_mono = time.monotonic()   # macOS 上睡眠期间不走，和墙钟的差就是电脑睡了多久
    on_battery = "Battery Power" in sh(["pmset", "-g", "batt"], check=False).stdout if shutil.which("pmset") else False
    if on_battery:
        print("警告：电脑在用电池。合盖或睡眠会中断运行，结果会被标成无效。", flush=True)
    if shutil.which("caffeinate"):   # 运行期间阻止空闲睡眠（合盖仍会睡）
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
    meter, usage, current = Meter(), {}, {}
    status = "completed"
    transcript = open(run / "transcript.jsonl", "w", encoding="utf-8")
    proc = subprocess.Popen(["docker", "exec", name, *cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=open(run / "stderr.log", "w"), text=True)

    stop = threading.Event()

    def last_activity():
        files = [run / "transcript.jsonl"]
        if codex_home and (codex_home / "sessions").exists():
            files += list((codex_home / "sessions").rglob("rollout-*.jsonl"))
        return max([started] + [f.stat().st_mtime for f in files if f.exists()])

    busy_at = [started]   # 最近一次发现容器 CPU 在忙的时间

    def container_cpu():
        out = sh(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}", name], check=False).stdout
        try:
            return float(out.strip().rstrip("%"))
        except ValueError:
            return 0.0

    def watchdog():
        nonlocal status
        while not stop.wait(5):
            if codex_home:
                codex_rollout(meter, codex_home)
            if time.time() - started > tier["minutes"] * 60:
                status = "timeout"
            elif time.time() - max(last_activity(), busy_at[0]) > STALL_MINUTES * 60:
                if container_cpu() >= STALL_CPU_PERCENT:
                    busy_at[0] = time.time()
                    continue
                status = "stalled"
            elif meter.budget_tokens > tier["tokens"]:
                status = "token_budget_exceeded"
            else:
                continue
            sh(["docker", "exec", name, "pkill", "-f", cmd[0]], check=False)
            proc.kill()
            return

    threading.Thread(target=watchdog, daemon=True).start()
    for line in proc.stdout:
        transcript.write(line)
        transcript.flush()
        if a.agent == "claude":
            try:
                claude_line(meter, json.loads(line), usage, current)
            except json.JSONDecodeError:
                pass
    proc.wait()
    stop.set()
    transcript.close()
    if codex_home:
        codex_rollout(meter, codex_home)
        # 登录 token 可能在运行中被刷新，写回共享的登录文件
        shutil.copy(codex_home / "auth.json", SECRETS / "codex" / "auth.json")
    if status == "completed" and proc.returncode not in (0, None):
        status = f"agent_exit_{proc.returncode}"
    elapsed = time.time() - started
    slept = max(0.0, elapsed - (time.monotonic() - started_mono))
    if slept > 60:
        status = f"invalid_host_slept({status})"

    versions = sh(["docker", "exec", name, "sh", "-c",
                   "claude --version 2>/dev/null | head -1; codex --version 2>/dev/null | head -1"], check=False).stdout
    sh(["docker", "rm", "-f", name], check=False)
    proxy_log = sh(["docker", "logs", "--since", dt.datetime.fromtimestamp(started, dt.timezone.utc).isoformat(),
                    PROXY_NAME], check=False)
    (run / "proxy.log").write_text(proxy_log.stdout + proxy_log.stderr)

    final = ws / "out" / "final.png"
    # Claude 以它结束时报告的总用量为准（含子 agent 等所有调用）；运行中实时统计的数另记一份，用来对账
    reported = claude_reported_budget(meter.reported)
    budget = reported if reported is not None else meter.budget_tokens
    result = dict(
        run_id=run_id, task_id=a.task, agent=a.agent, tier=a.tier, model=meter.model or a.model,
        effort=meter.effort or a.effort, status=status, minutes=round(elapsed / 60, 2),
        budget_tokens=budget, budget_tokens_live=meter.budget_tokens, over_budget=budget > tier["tokens"],
        raw_tokens=meter.raw, model_calls=meter.calls,
        image_views=meter.image_views, limits=tier,
        outputs=dict(final_png=final.exists(), run_sh=(ws / "run.sh").exists(),
                     src_files=sum(1 for p in (ws / "src").rglob("*") if p.is_file())),
        versions=versions.strip().splitlines(),
        read_image_attempts=meter.read_image_attempts,
        nolook_violation=(not tier["look"] and meter.image_views > 0),
        agent_tools=meter.tools, claude_reported=meter.reported,
        host_slept_seconds=round(slept), on_battery=on_battery,
    )
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
