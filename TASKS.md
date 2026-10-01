# 阶段 1：环境和 harness

spec（2026-09-30 和用户对齐）：
- harness 用现成的 Claude Code 和 Codex，订阅账号登录
- 先本机（Mac arm64 + colima）跑通，镜像同时出 amd64 版给 Linux 服务器
- 网络：容器只放行两家登录和模型域名，其余断开
- 预算三档：不看图（禁止读图片）/ 低 20 万 token、30 分钟 / 高 100 万 token、90 分钟；由外层脚本监控，超了就停
- 一个全家桶镜像
- 验收：3 题 × 2 个 agent × 3 档

- [x] env/Dockerfile：Python 科学计算栈、Node + Three.js、Playwright Chromium、Blender、resvg、中文字体、Claude Code、Codex
- [x] 本机构建 arm64 镜像，检查各渲染器能用
- [x] 出口代理：域名白名单，agent 容器只能通过它上网
- [x] 抓出两家订阅需要的域名，写进白名单：
  - 已有的白名单不用改。
  - 代理日志里实际只连了 `chatgpt.com`（Codex）和 `api.anthropic.com`（Claude）。
  - `auth.openai.com` 留给 Codex 刷新登录。
  - Codex 的 `ab.chatgpt.com` 被拦，不影响运行。
- [x] harness/run.py：建工作区、写题目说明、起容器、跑 agent、监控 token 和时间、收集产出和日志
- [x] 不看图档：两个 agent 都禁止读图片
- [x] 订阅登录（需要用户操作）
- [x] 验收（不看图、低预算两档）：3 题 × 2 个 agent 共 12 次：
  - 全部完成，预算内；
  - 不看图档看图 0 次；
  - 全部逐像素复现；
  - 结果见 docs/PHASE1.md。
- [x] 更新 PLAN.md（harness 定义、预算档）、README、报告

发现并处理：
- colima 只挂载主目录，工作区必须放在 ~ 下（runs/ 在 repo 里，没问题）
- apt 的 Blender 4.0 没有降噪库，Cycles 要关降噪（已写进题目说明）
- Chromium 不允许 file:// 页面加载 ES module，c2p-render 改成本机 HTTP 服务打开页面
- Codex 自带 image_generation（经 chatgpt.com，代理拦不住）和服务端 web_search，已在配置里关掉并用 --strict-config 校验；Claude Code 禁用 WebSearch、WebFetch
- [x] 登录后验证：两家的 effort 设置真的生效；不看图档真的看不到图；禁用的工具真的调不到（见 docs/PHASE1.md）
- [x] 电脑睡眠检测：caffeinate 防空闲睡眠、电池警告、两种时钟比较算睡眠时长，睡过 60 秒标无效
- [x] 卡住检测（10 分钟无新内容）和批量自动重跑一次
- [x] Claude 输出 token 漏算：
  - 改成从流事件读，结果以 Claude Code 结束时的报告为准；
  - 修好前跑的 3 次已补正（见 docs/PHASE1.md 第 12 条）。
- [x] 补跑：
  - Codex 4 次（pilot-11、pilot-03 的不看图和低预算）、Claude 6 次；
  - 2026-10-01 06:26–07:28，日志在 runs/_driver.log。
- [x] 复现检查和汇总脚本 harness/check.py
- [x] 高预算档 3 题 × 2 agent（用户 2026-10-01 确认，先按"只放宽上限"跑）：
  - 6 次全部完成，全部逐像素复现；
  - 最多用了上限的 13%（token）和 25%（时间）；
  - 结果见 docs/PHASE1.md"高预算档"一节。
- [x] check.py：复现只拷 `src/` 里的文本文件（中间产物必须由 run.sh 重新生成），时间上限按档位
- [x] 不用 harness 强制多轮、不要求用满预算：以一次正常调用的长程运行为准（用户 2026-10-01 定）
- [x] 低预算、高预算合并成一档"正常运行"：两档上限都是 100 万 token、90 分钟，只防失控（用户 2026-10-01 同意）；run.py、PLAN、README、报告已改
- [ ] 推理内容没进日志：Claude 的 thinking 是空的，Codex 的推理是加密的；要查能不能打开推理摘要
- [ ] amd64 镜像（建议在 Linux 服务器上构建）
