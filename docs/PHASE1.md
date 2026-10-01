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
- **复现检查和汇总** `harness/check.py`：
  - 在断网的新容器里重跑交上来的 `run.sh`，和交上来的图逐像素比较；
  - 汇总成 Markdown 表，可选拼一张总览图。

## 实测确认的配置

| 项目 | 结果 |
|---|---|
| Codex 模型和推理强度 | 会话记录里是 `gpt-6.1-sol`、`medium`，设置生效 |
| Claude Code 模型 | 订阅默认是 Sonnet 5.5，harness 默认改成 Opus（会话初始化信息里是 `claude-opus-5-5`） |
| Claude Code 推理强度 | 用本地假 API 截下请求体：`--effort medium` 时请求里是 `output_config: {"effort": "medium"}`，换 `high` 也跟着变；没有消耗额度 |
| Claude Code 不看图档 | 读 `/workspace/t.png` 和 `/tmp/t.png` 都被拒绝（`permission_denials` 有记录），返回图片 0 张。绝对路径要用 `Read(//**/*.png)` 这类规则才拦得住。验收的 3 次不看图档看图 0 次，也没尝试读图 |
| Claude Code token 计数 | 修正后（见问题 12），运行中的实时统计和 Claude Code 结束时的报告逐个对上（3 次低预算档完全相等） |
| Claude Code 禁用联网工具 | 会话初始化信息里的工具列表没有 WebSearch、WebFetch；harness 把实际工具列表记进 `result.json` |
| Codex 关掉的功能 | `codex features list` 确认 9 个开关已关；`--strict-config` 会拒绝写错的配置 |
| Codex 不看图档 | 验收的 3 次不看图档看图都是 0 次；低预算档看了 1–4 次 |
| 产出可复现 | 验收的 12 次产出在断网新容器里重跑，全部逐像素一致（`harness/check.py --regen`） |

## 过程中发现并处理的问题

1. **服务端工具绕过代理**：Codex 自带图像生成（经 `chatgpt.com`，在白名单里），两家的联网搜索都在服务端执行。这些都必须在 agent 配置里关掉，代理管不到。
2. **Codex 间接看图**：Codex 在 `exec` 的代码里调用 `tools.view_image`，只按工具名统计会漏掉。看图次数改成数工具输出里实际带回的图片。
3. **token 计数**：Codex 每 5 秒重读会话记录，计数要每次从头算，否则调用次数会被重复累加。
4. **复制 token 时的换行**：终端折行会在 token 中间混进换行，读取时去掉所有空白。
5. **Blender 降噪**：apt 版 Blender 4.0 没有降噪库，Cycles 要关降噪，已写进题目说明。
6. **Chromium 本地页面**：不允许 `file://` 页面加载 ES module，`c2p-render` 改成用本机 HTTP 服务打开页面。
7. **colima 挂载**：只挂载主目录，工作区必须放在 `~` 下。
8. **Claude 看图次数**：原来按"调用 Read 读图片"计数，不看图档里被拒绝的尝试也会被算成看图。改成数工具结果里实际返回的图片，被拒绝的尝试单独记成 `read_image_attempts`。
9. **长时间渲染被误判为卡住**：日志 10 分钟没动静时，再看一眼容器 CPU，高于 5% 说明还在干活，不算卡住。
10. **电脑重启**：2026-10-01 约 05:46 电脑重启，正在跑的一次运行中断，已挪到 `runs/_aborted/`。之后的批量运行放在独立的进程会话里，app 退出不会把它带走。
11. **电脑睡眠**：2026-09-30 晚 18:54 合盖后，电脑用电池反复睡眠，之后启动的 4 次 Codex 运行和一组对照实验全部表现为"卡住"。
   - 一开始我以为是代理的问题；对照实验里直接联网也一样卡，才查到是睡眠。
   - 现在 harness 用 `caffeinate` 阻止空闲睡眠，用电池时给出警告，并比较两种时钟算出睡眠时长：运行期间睡过 60 秒以上，结果标成无效。
   - 合盖仍然会睡眠，必须接电源、开着盖子跑。
12. **Claude 输出 token 漏算**：Claude Code 的 stream-json 里，assistant 事件带的 usage 是请求刚开始时的快照，输出数停在个位数，之后不再更新。
   - 第一次正式运行（水墨、不看图档）时：
     - 按这个算是 24,485；
     - Claude Code 结束时报告的是 42,942；
     - 差的都是输出。
   - 这样运行中的预算上限对 Claude 基本不起作用。
   - 改法：
     - 加 `--include-partial-messages`，从流事件 `message_delta` 读每次调用最终的输出数；
     - 结果以 Claude Code 结束时报告的总用量为准，运行中实时统计的数另记为 `budget_tokens_live` 对账。
   - 用本地假 API 和真实运行都核对过。
   - 修好之前跑的 3 次（三题的不看图档）都远低于 20 万，预算没有真被超过。已按结束时的报告改正 `result.json`，并加了说明字段 `meter_note`。
   - Codex 的会话记录里是 API 返回的累计用量，推理 token 已含在输出里，没有这个问题。

## 验收：不看图、低预算两档（高预算档之后补）

3 题 × 2 个 agent × 2 档，共 12 次。

- **agent 和设置**：Claude Code 用 Opus 5.5（`claude-opus-5-5`），Codex 用 `gpt-6.1-sol`，推理强度都是 medium。
- **运行环境**：本机（Mac arm64 + colima），2026-09-30 至 10-01。
- **表怎么来的**：`python3 harness/check.py --regen` 生成。
- **复现**：把交上来的 `src/` 和 `run.sh` 拷到干净目录，在断网的新容器里重跑，和交上来的图逐像素比较。

| 题目 | agent | 档位 | 状态 | 用时（分钟） | token | 看图 | 复现 |
|---|---|---|---|---|---|---|---|
| pilot-03 日式小巷 | claude | low | completed | 8.99 | 83,409 | 4 | 逐像素一致 |
| pilot-03 日式小巷 | claude | nolook | completed | 11.87 | 112,015 | 0 | 逐像素一致 |
| pilot-03 日式小巷 | codex | low | completed | 9.71 | 40,063 | 3 | 逐像素一致 |
| pilot-03 日式小巷 | codex | nolook | completed | 7.72 | 47,202 | 0 | 逐像素一致 |
| pilot-10 水墨 | claude | low | completed | 2.88 | 33,395 | 3 | 逐像素一致 |
| pilot-10 水墨 | claude | nolook | completed | 3.36 | 42,942 | 0 | 逐像素一致 |
| pilot-10 水墨 | codex | low | completed | 15.72 | 53,980 | 4 | 逐像素一致 |
| pilot-10 水墨 | codex | nolook | completed | 13.12 | 44,719 | 0 | 逐像素一致 |
| pilot-11 像素画 | claude | low | completed | 1.51 | 21,828 | 2 | 逐像素一致 |
| pilot-11 像素画 | claude | nolook | completed | 2.99 | 34,146 | 0 | 逐像素一致 |
| pilot-11 像素画 | codex | low | completed | 5.2 | 20,939 | 1 | 逐像素一致 |
| pilot-11 像素画 | codex | nolook | completed | 7.99 | 36,076 | 0 | 逐像素一致 |

**运行结果**

- 12 次全部正常完成：
  - 没有卡住，也没有重跑；
  - 都在预算内；
  - 运行期间电脑没睡眠。
  - 例外：水墨题 Codex 不看图档跨过了一段约 5.5 分钟的睡眠，所以 13.1 分钟偏长，但产出有效。这次在睡眠检测加上之前。
- 不看图档的 6 次，看图次数都是 0。Claude 的 3 次连读图都没尝试过。
- 12 张图都能逐像素复现。最慢的是 Claude 日式小巷不看图档的 numpy 光线追踪，重跑要 63 秒。

**订阅额度**

- Claude 6 次合计约占 5 小时额度的 2%、7 天额度的 1%。
- Codex（Plus）6 次合计约占周额度的 2%。
- 数字来自运行记录里两家返回的额度信息。

**观察**

1. **预算上限没起作用**：
   - 最多的一次用了 11.2 万 token，最长的一次 15.7 分钟。
   - 每次都是 agent 自己停下的，离 20 万 token、30 分钟都还远。
   - 所以在 medium 推理强度下，只把上限调高，agent 的做法可能不会变，高预算档可能和低预算档差不多。要让档位真正拉开，可能得换个定义（见"还没做"）。
2. **两家节奏不同**：
   - 水墨和像素画，Claude 3 分钟左右交稿（5–9 次模型调用），Codex 用了 5–16 分钟。
   - 日式小巷，Claude 两次都写了 numpy 光线追踪，token 用了 8–11 万，是 Codex（4–5 万）的两倍左右。
3. **不看图时怎么检查**：Claude 在日式小巷不看图档里，把画面切成网格打印每块的平均亮度。它从数字发现画面中间被光雾冲淡了，然后调参数再算。
4. **看不到图会漏掉的问题**：Codex 水墨不看图档里，山体边缘有两处被直直切断，它自己没发现。看图档里没有这个问题。
5. **看图档的改法**：Claude 在日式小巷低预算档里看了 3 次全图，又把地面裁出一块放大看倒影。看图次数记为 4，读 `/tmp` 下的裁剪图也算进去了。
6. **两家风格不同**：
   - 日式小巷：Claude 两次都画了雨丝和地面倒影；Codex 两次色调偏青、几何更干净，但看不出在下雨。
   - 好坏要等阶段 4 的裁判和人工来判。

## 还没做

- **高预算档**（3 题 × 2 个 agent）：
  - 按上面的用量估计，额度花费和低预算档差不多。
  - 但需要先决定高预算档怎么定义：
    - 只放宽上限，看 agent 会不会多用；
    - 或者改成提高推理强度；
    - 或者在题目里要求"用满预算持续改进"。
- **amd64 镜像**：在 Mac 上靠模拟构建很慢，建议到 Linux 服务器上构建。
