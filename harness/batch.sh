#!/usr/bin/env bash
# 按顺序跑一批验收：batch.sh <agent> <tier...>，题目默认 pilot-10 pilot-11 pilot-03
# 例：harness/batch.sh codex nolook run；TASKS_FILE 换题库文件，MODEL 换模型，RUNS_DIR 换结果目录
set -u
cd "$(dirname "$0")/.."
agent=$1; shift
tasks=${TASKS:-"pilot-10 pilot-11 pilot-03"}
for tier in "$@"; do
  for t in $tasks; do
    if ls -d ${RUNS_DIR:-runs}/${t}_${agent}_${tier}_* >/dev/null 2>&1 && [ -z "${RERUN:-}" ]; then
      echo "skip $t $agent $tier (already ran)"; continue
    fi
    for attempt in 1 2; do
      echo "=== $t $agent $tier attempt $attempt $(date +%H:%M:%S)"
      line=$(python3 harness/run.py --task "$t" --agent "$agent" --tier "$tier" --tasks-file "${TASKS_FILE:-harness/tasks/pilot.jsonl}" --runs-dir "${RUNS_DIR:-runs}" ${MODEL:+--model "$MODEL"} | python3 -c \
        'import json,sys; r=json.load(sys.stdin); print(r["status"], r["minutes"], "min", r["budget_tokens"], "tok", "views", r["image_views"], "final", r["outputs"]["final_png"])')
      echo "$line"
      # 卡住、运行期间电脑睡过、或一个 token 都没用就结束（基础设施问题）时重跑一次；其余情况（包括超预算、超时）不重跑
      case "$line" in stalled*|invalid_host_slept*|*" 0 tok"*) continue ;; *) break ;; esac
    done
  done
done
