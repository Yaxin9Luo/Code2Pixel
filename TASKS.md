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
- [ ] 抓出两家订阅需要的域名，写进白名单（已放行 api.anthropic.com、chatgpt.com、auth.openai.com、api.openai.com，跑完看代理日志补）
- [x] harness/run.py：建工作区、写题目说明、起容器、跑 agent、监控 token 和时间、收集产出和日志
- [x] 不看图档：两个 agent 都禁止读图片
- [x] 订阅登录（需要用户操作）
- [ ] 验收：3 题 × 2 agent × 3 档（进度见 docs/PHASE1.md；Codex 水墨题两档完成，其余待接电源重跑）
- [ ] 更新 PLAN.md（harness 定义、预算档）、README

发现并处理：
- colima 只挂载主目录，工作区必须放在 ~ 下（runs/ 在 repo 里，没问题）
- apt 的 Blender 4.0 没有降噪库，Cycles 要关降噪（已写进题目说明）
- Chromium 不允许 file:// 页面加载 ES module，c2p-render 改成本机 HTTP 服务打开页面
- Codex 自带 image_generation（经 chatgpt.com，代理拦不住）和服务端 web_search，已在配置里关掉并用 --strict-config 校验；Claude Code 禁用 WebSearch、WebFetch
- [ ] 登录后验证：两家的 effort 设置真的生效；不看图档真的看不到图；禁用的工具真的调不到
- [x] 电脑睡眠检测：caffeinate 防空闲睡眠、电池警告、两种时钟比较算睡眠时长，睡过 60 秒标无效
- [x] 卡住检测（10 分钟无新内容）和批量自动重跑一次
- [ ] 补跑：Codex 4 次（pilot-11、pilot-03 的不看图和低预算）、Claude 6 次（需接电源、开盖）
- [ ] 高预算档 3 题 × 2 agent
- [ ] amd64 镜像（建议在 Linux 服务器上构建）
