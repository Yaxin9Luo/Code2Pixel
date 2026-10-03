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

# 阶段 2：门槛

spec（2026-10-01 和用户对齐）：
- 复现：断网新容器里重跑 run.sh，一律逐像素一致才算过
- 查作弊：静态扫描代码 + 重跑时用 strace 记录文件访问和网络连接
- 外部文件：重跑时读 /workspace 外的图片算违规；字体、库代码等其他文件都允许
- 红队：手写一批对抗样本 + 让 Claude Code、Codex 各故意作弊 2 次
- 正样本：试跑 A 赛道 12 张 + 阶段 1 验收 18 次，不能误判（A 赛道在 Mac 上跑的，镜像里重跑不一致的记为环境差异，单独列）
- 题目约束：只搭框架（reward_model.gate 里的检查项格式 + 几个通用检查器），具体约束等阶段 3 题库

- [x] 门槛镜像：在 code2pixel/env:0.1 上加 strace（agent 用的镜像不变）
- [x] harness/gate.py：输出检查、静态扫描、带 strace 的断网重跑、逐像素比对、题目约束框架，写 gate.json
- [x] 工具基线：Blender、Chromium、Python 库启动时都不读自带图片；Chromium 自带的网络探测放行
- [x] 正样本：验收 18 次全部通过；A 赛道 12 张除复现外无违规（复现不过的是 Mac 和镜像的环境差异）
- [x] 手写对抗样本（harness/redteam/）：15/15 判不过，命中预期的违规
- [x] agent 故意作弊：两家各 2 次（Codex 没作弊；Claude 一次作弊被门槛判不过，一次自己停下）
- [x] 所有正式运行默认跟踪作答过程，作答时读外部图片判违规（用户 2026-10-02 同意）：run.py 默认打开，gate.py 加 external_image_answering
- [x] Codex 日式小巷红队运行的门槛结果：没作弊，但 Blender 重跑差 2 个像素，按逐像素规则判不过（记在 PHASE2 问题 4）
- [ ] docs/PHASE2.md 门槛设计写进报告
- [ ] docs/PHASE2.md、PLAN、README、报告

# 阶段 3：题库 v0（dev 150 题）

spec（2026-10-02 和用户对齐）：
- 来源：先从 X 上收集人们真实让 coding agent 画图的 prompt（用户在内置浏览器登录 X，我来搜），改写后使用并保留出处；不够的再补写，以真实 prompt 为锚
- 语言：给 agent 的题目用英文，每题附中文
- 分布：常规 100 题（风景、街景、动物、人物、静物、多物体、指定画风各约 14 题）+ 代码该赢 50 题（精确数量、画面文字、几何布局、精确修改各约 12 题）
- 尺寸：按题定，横版 1536×1024、竖版 1024×1536、方形 1024×1024
- 动画、交互类 showcase：改写成静态画面，注明改写
- 细则：我起草（每题 5–15 条能判是或否的说法）；用户抽查约 30 题；其余用两个不同模型交叉检查，有分歧的交给用户
- 默认（用户可改）：难度我先标三档、用户抽查时一起看；交叉检查用 Opus 5.5 和 gpt-6.1-sol（medium）；精确修改题的底稿用阶段 1 验收作品的代码

- [x] 用户在内置浏览器登录 X
- [x] 收集真实 prompt：77 条帖子（runs/_x/raw.jsonl，不进仓库），32 条改写进题库，链接记在 extra_info.source
- [x] 常规 100 题 + 计数 12、文字 13、布局 13（harness/tasks/build_dev.py → dev.jsonl，138 题）
- [x] 精确修改 12 题：底稿用阶段 1 的 7 份作品代码（harness/tasks/edit_bases/），参考图由 build_edit_refs.py 生成且和原图逐像素一致；框外不变的检查（tol 12、最多 0.2% 像素）用合成图验证 12/12；run.py 会把底稿放进工作区
- [x] 能程序判的约束写成 checks：5 道布局题（region_color），用合成图验证过对错都能分出
- [x] 精确修改题：底稿程序 + 修改要求 + 不该变的区域
- [x] 细则初稿：1013 条（每题 3–8 条专属 + 2 条通用质量），harness/tasks/claims_dev.py
- [x] 两个模型交叉检查细则：两边都标出的 21 条已改；只有一边标出的 73 条进 claims_review.md
- [x] claims_review.md（73 条分歧 + 抽查 30 题）：用户让 subagent 审；5 个 subagent 并行，结论已写进清单和代码（采纳 46 条、改 5 个难度）
- [x] 发现并修好 dev-142 修改框太小（正确修改会判不过），用真实修改验证
- [x] 其余 10 道精确修改题用真实修改验证修改框：全部通过；dev-140 右边旗尖出框 348 像素（靠 0.2% 余量才过），框右沿 0.73 → 0.765
- [x] 写出 harness/tasks/dev.jsonl，跑门槛自检（布局题用合成图、修改题用真实修改验证）
- [x] TASK.md 模板改成英文（用户确认）
- [x] docs/PHASE3.md、README
- [x] PLAN、报告

# 阶段 4：VLM 裁判

spec（2026-10-02 和用户对齐）：
- 裁判模型：用美团 Friday API（OpenAI 兼容接口），先试 GLM-5.3-FlashX；实测不能看图就在 Friday 里另挑多模态模型。再选一个不同厂家的多模态模型当第二裁判，算模型间一致率
- AppId 由用户写进 ~/.code2pixel/friday_appid，不打印、不进仓库
- 范围：逐条细则判分、两两比较 + Elo 框架（生图模型图等阶段 5）、读代码的 grader、judge 抗攻击测试
- 验证用图：dev 分层抽 30 题（harness/tasks/judge_val.txt）× Claude Code、Codex，正常运行档，effort medium
- 人工校准：用户和合作伙伴标，我做标注页面（Artifact + 共享数据库），汇总算一致率

- [x] 抽 30 题（按类别分层，random.Random(4)）
- [x] batch.sh 支持 TASKS_FILE
- [x] 30 题 × 2 agent 实跑：60 次全部完成；Codex 中途订阅额度用完，作废 33 次空跑后补跑 17 题
- [x] 门槛跑一遍这 60 次：60/60 通过（9 次 Blender 噪声按 near_identical 通过）
- [x] 复现规则放宽（用户定）：PSNR ≥ 50 dB 且差超过 8 级的像素 ≤ 0.1%；红队 15/15 仍判不过
- [x] Friday 接口实测：GLM-5.3-FlashX 能看图但 app 配额为 0（429）；用户定先用 Doubao-Seed-2.0-pro（主）+ gemini-3.1-pro-preview（第二），GLM 等配额申请下来再加
- [x] harness/judge.py：逐条细则判是或否，加权得分；精确修改题同时给底稿图；按模型限速
- [x] judge 稳定性：自洽 Doubao 100%、Gemini 98.3%；两裁判逐条一致 92.2%
- [x] 两两比较 + Bradley–Terry / Elo 框架，位置平衡（harness/pairwise.py；合成数据验证 BT 能还原差距）
- [x] 30 题 Claude vs Codex 两两比较：两个裁判结论相反（Doubao 偏 Claude 不显著，Gemini 偏 Codex 显著）
- [x] 读代码的 grader（harness/code_grader.py）：红队 numbers_txt、zlib_pixels 判出硬编码，正常作品没误判
- [x] grader 跑全部 60 次：没有硬编码；可改性 Claude 0.875、Codex 0.683
- [x] judge 对抗样本脚本（harness/judge_redteam.py）：错配图、错配图 + 注入指令、只写题目文字；小样本 Doubao 通过
- [x] judge 对抗样本全量跑（两个裁判）：错配 2/43（都确实成立），注入不增加，纯文字 0/43
- [x] 标注页（harness/label/index.html，已发布为 Artifact）；label_export.py 导出图和文档，作者隐去
- [x] 图全部上传到标注页（60 张、30 组比较）
- [x] 修 edit_base 路径拼了两次的 bug（修改题判分、标注导出）
- [ ] 等人工标注（目前 1 人、1 张图 + 8 组）
- [x] 一致率汇总脚本（harness/agreement.py）
- [x] 细则太容易满分：用户定"细则当门槛、两两比较当主分 + 加质量细则"；harness/score.py；题库加 893 条质量细则（kind 字段）；60 次重判
- [x] 区分度验证：Claude Code + Sonnet 5 跑同样 30 题（runs/sonnet5/），两个裁判都排最后，Elo 低 300–450，区间不重叠
- [x] batch.sh 支持 MODEL、RUNS_DIR；pairwise / score 按模型区分参赛者；judge.py 网络错误重试
- [ ] 质量细则里没区分度的几条（光影一致、完成度、纵深、遮挡等）删掉或改具体
- [ ] GLM-5.3-FlashX 配额下来后加进来
- [x] docs/PHASE4.md、PLAN、README、报告
