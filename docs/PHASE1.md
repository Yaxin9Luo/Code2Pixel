# 阶段 1：环境和 harness（进行中）

更新于 2026-10-01。

## 已完成

- **镜像** `env/Dockerfile` → `code2pixel/env:0.1`（目前只构建了 arm64）：Python 科学计算栈、Node + Three.js、Playwright Chromium、Blender 4.0、rsvg、Noto CJK 字体、Claude Code 2.1.285、Codex 0.159.2。
- **渲染工具** `c2p-render`：SVG（含中文字体）、Three.js（WebGL）、Blender Cycles 都实测出图正确。
- **出口代理** `env/proxy/`：默认拒绝，只放行 `api.anthropic.com`、`chatgpt.com`、`auth.openai.com`、`api.openai.com`。实测：放行的域名能连上；example.com、GitHub、Hugging Face 被拦；绕过代理直连也不通。
- **harness** `harness/run.py` 和 `harness/batch.sh`：
  - 起容器，用 headless 模式跑 Claude Code 或 Codex，订阅账号登录；
  - 每 5 秒检查一次 token 和时间，超了就停；
  - 10 分钟没有新内容判定为卡住；
  - 收集产出、对话记录、代理日志，写 `result.json`；
  - 检测运行期间电脑有没有睡眠。

## 实测确认的配置

| 项目 | 结果 |
|---|---|
| Codex 模型和推理强度 | 会话记录里是 `gpt-6.1-sol`、`medium`，设置生效 |
| Claude Code 模型 | 订阅默认是 Sonnet 5.5，harness 默认改成 Opus（会话初始化信息里是 `claude-opus-5-5`） |
| Claude Code 禁用联网工具 | 会话初始化信息里的工具列表没有 WebSearch、WebFetch |
| Codex 关掉的功能 | `codex features list` 确认 9 个开关已关；`--strict-config` 会拒绝写错的配置 |
| Codex 不看图档 | 水墨题不看图档看图 0 次；低预算档看图 4 次 |
| 产出可复现 | 两次 Codex 产出在断网新容器里重跑，都逐像素一致 |

## 过程中发现并处理的问题

1. **服务端工具绕过代理**：Codex 自带图像生成（经 `chatgpt.com`，在白名单里），两家的联网搜索都在服务端执行。这些都必须在 agent 配置里关掉，代理管不到。
2. **Codex 间接看图**：Codex 在 `exec` 的代码里调用 `tools.view_image`，只按工具名统计会漏掉。看图次数改成数工具输出里实际带回的图片。
3. **token 计数**：Codex 每 5 秒重读会话记录，计数要每次从头算，否则调用次数会被重复累加。
4. **复制 token 时的换行**：终端折行会在 token 中间混进换行，读取时去掉所有空白。
5. **Blender 降噪**：apt 版 Blender 4.0 没有降噪库，Cycles 要关降噪，已写进题目说明。
6. **Chromium 本地页面**：不允许 `file://` 页面加载 ES module，`c2p-render` 改成用本机 HTTP 服务打开页面。
7. **colima 挂载**：只挂载主目录，工作区必须放在 `~` 下。
8. **电脑睡眠**：2026-09-30 晚 18:54 合盖后，电脑用电池反复睡眠，之后启动的 4 次 Codex 运行和一组对照实验全部表现为"卡住"。
   - 一开始我以为是代理的问题；对照实验里直接联网也一样卡，才查到是睡眠。
   - 现在 harness 用 `caffeinate` 阻止空闲睡眠，用电池时给出警告，并比较两种时钟算出睡眠时长：运行期间睡过 60 秒以上，结果标成无效。
   - 合盖仍然会睡眠，必须接电源、开着盖子跑。

## 验收进度（3 题 × 2 个 agent；高预算档之后补）

| 题目 | Codex 不看图 | Codex 低预算 | Claude 不看图 | Claude 低预算 |
|---|---|---|---|---|
| pilot-10 水墨 | 完成：约 4.5 万 token，看图 0 次，可复现 | 完成：15.7 分钟，约 5.4 万 token，看图 4 次，可复现 | 未跑 | 未跑 |
| pilot-11 像素画 | 无效（电脑睡眠），待重跑 | 无效（电脑睡眠），待重跑 | 未跑 | 未跑 |
| pilot-03 日式小巷 | 无效（电脑睡眠），待重跑 | 无效（电脑睡眠），待重跑 | 未跑 | 未跑 |

水墨题不看图档那次跨过了一段约 5.5 分钟的睡眠，所以记录的 13.1 分钟偏长，但产出有效。

**看图与不看图的第一个差别**：不看图档的水墨图里，山体边缘在两处被直直切断，agent 自己看不到；看图档的图里没有这个问题。

## 还没做

- 补跑 4 次无效的 Codex 运行；Claude 的 6 次。需要接电源、开着盖子。
- 高预算档（3 题 × 2 个 agent）。
- amd64 镜像：在 Mac 上靠模拟构建很慢，建议到 Linux 服务器上构建。
