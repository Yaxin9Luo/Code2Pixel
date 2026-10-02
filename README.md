# Code2Pixel

**把 coding agent 当生图模型用的 benchmark（草案）。**

给一段文字描述，coding agent 写代码、渲染、看图、再改，最后交一张静态图，和生图模型放在一起比。工具不限（SVG、Canvas、Three.js、Blender、numpy……），唯一的禁令是不能调用生图模型。目标用户是做后训练的模型公司：在这类任务上训练，在这个 benchmark 上测。

📄 **报告**：[yaxin9luo.github.io/Code2Pixel/report](https://yaxin9luo.github.io/Code2Pixel/report/)（单个 HTML，图片都嵌在里面；也可以下载 [`report/index.html`](report/index.html) 直接打开）

## 为什么做

大家默认生图必须用生图模型。我们的试跑里，coding agent 只拿到一句文字，就画出了带光影、倒影、透视的完整场景。我们不说它现在比扩散模型好，只说这是另一条路，而且这条路有扩散模型没有的性质：精确、可改、可复现、分辨率无关、不需要图像训练数据。

## Benchmark 草案

| | |
|---|---|
| 任务 | 只做静态图。输入文字，交最终 PNG + 生成它的代码 + 一条能重跑的命令 |
| 主赛道 | 只给文字；不联网，不读现成图片、素材、模型 |
| 素材赛道 | 可用授权照片、贴图、HDRI、3D 模型 |
| 辅助赛道 | 给参考图，用代码复刻，按像素相似度客观打分（适合当 RL 奖励） |
| harness | 直接用现成的 Claude Code 和 Codex（订阅账号登录），在统一镜像里 headless 运行；以后需要再加别的 agent |
| 档位 | 测一次正常调用、一轮长程运行的效果，harness 不强制多试。分不看图（禁止看任何图片）和正常运行（可看图）两档；上限都是 100 万 token、90 分钟，只防失控；报实际用的 token（只算新增输入和输出）、时间、看图次数 |
| 评测 | ① 程序化规则当门槛：能渲染、路径尺寸对、无嵌入位图、没联网没调模型、能复现、题目约束满足；任一条不过总分归零 ② VLM 裁判：细则写成能核对的具体说法，逐条判是或否（不打 1–5 分）；与固定图池两两比较（隐去作者、位置平衡）；读代码抓硬编码像素等作弊 ③ 人工校准：上线前先人工读一批打过分的样本；按类别公布裁判与人的一致率 |
| 题目 | 风景、街景、动物、人物、静物、多物体、指定画风，外加"代码该赢"的题：精确数量、画面文字、几何布局、精确修改 |
| 题目来源 | 优先用人们真实让 coding agent 画图的 prompt，其次人写，再次以真实 prompt 为锚的合成题；难度由人判定，不专挑当前模型做不好的题；所有模型都失败的题人工复查 |
| 数据格式 | 每条任务一行 `prompt` / `reward_model` / `extra_info`（任务 id、Docker 镜像）；统一渲染镜像，可直接接 verl |
| 数据划分 | train 公开、自动出题；dev 公开、细则人工核对；test 不公开、人写细则、定期更换、不进训练。三份共用一套环境 |
| 训练 vs 评测 | 训练：同题一组 rollout 组内比较给相对分（适合 GRPO）。评测：与生图模型和参考 agent 的固定图池比，报胜率或 Elo |
| 防刷分 | 断网；静态扫描 + 运行时检查（base64 位图、下载图片、调生图模型、加载权重）；重跑和 agent 作答全过程都用 strace 跟踪，读了现成图片就判违规；judge 只看像素并用对抗样本测试；作弊归零 |
| 效率 | 每档报 token、轮数、时间；分数接近饱和时比同等质量下的成本 |
| 评测自检 | 指标上线前要过：分数随模型能力和 effort 上升；最强模型离满分很远；多次运行的噪声小于要关心的差距（报置信区间）；judge 判两次结论稳定；对抗样本得 0 分。dev 涨而 test 不动视为过拟合 |

所有赛道禁止调用生图模型。

还没定：VLM 裁判选型、生图模型基线、test 集规模。

**当前进度（2026-10-02）**：阶段 1–3 已完成（阶段 1 剩 amd64 镜像），下一步阶段 4 VLM 裁判。逐项清单见 [TASKS.md](TASKS.md)。

环境打包、组内比较评分和门槛式奖励参考了 [MiMo-V2.6 开源的 RL 环境](https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss)和 [GAGAR](https://arxiv.org/abs/2609.32577)。它们没有公布 judge 和人的一致性，这是我们要补上的部分。评测自检、题目来源和细则格式参考了 [Automating eval design and hillclimbing](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)。

## 实现方案

完整方案见 [docs/PLAN.md](docs/PLAN.md)：任务和输出约定、题库、三层评分、评测自检、数据格式、实现步骤、还没定的问题。步骤概要：

1. 环境和 harness：统一 Docker 镜像、出口代理、用现成的 Claude Code 和 Codex 跑题，上限强制执行（已验收；amd64 镜像待建，见 [docs/PHASE1.md](docs/PHASE1.md)）
2. 门槛：路径校验、断网重跑比对、静态扫描、strace 跟踪重跑和作答过程、程序化约束框架；15 个手写对抗样本全部判不过，已有作品没有误判（见 [docs/PHASE2.md](docs/PHASE2.md)）
3. 题库 v0：dev 150 题（常规 100 + 代码该赢 50，32 题改写自 X 上的真实 prompt），细则两个模型交叉检查、subagent 复审，精确修改题的修改框用真实修改验证（v0 已完成，见 [docs/PHASE3.md](docs/PHASE3.md)）
4. VLM 裁判：逐条细则、图池两两比较与 Elo、读代码的 grader
5. 生图模型基线进图池
6. 验证评测：3 个模型 × 2 个 effort × 3 个种子，人工读样本和两两比较
7. 训练环境：自动出题、组内比较 reward，导出 Parquet 和镜像，用 verl 跑通一次小规模 RL
8. 发布：HF 数据集（train、dev）、镜像、评测代码、排行榜；test 集由我们来跑

## 试跑结果（2026-09）

12 个事先定好的题目，每题两张：A 只给文字，B 可用 Wikimedia Commons 授权照片。每张最多 6 轮。

- 24 张图，0 次生图模型调用；24/24 重跑代码逐像素一致
- A 赛道第一轮（agent 还没看过任何一张图）CLIP 12 选 1 就 12/12 对题
- A 平均每张 17 分钟、822 行代码、约 14 万 token；B 平均 28 分钟、258 行、约 13 万 token
- 不足：A 的 3D 渲染感偏重、人物偏僵；B 有几张基本是照片后期

CLIP 认对率分不出好坏（原始照片也全部认对），所以正式 benchmark 要换成上面的三层评测。

## 目录

```
demo/            试跑：prompts.json（题目）、RULES.md（规则）、A/ B/（每张图的代码、log.json、各轮代码快照）
                 verify.py（重跑比对）、score.py（CLIP 打分）、scores.json、verify.json
qianli/          前期探索：first_attempt/ 从零画千里江山图；fit/ 给参考图用三角形 SVG 复刻
autoresearch/    agent 自动优化三角形拟合算法（SSIM 0.764 → 0.818，58 秒 → 26 秒）
stylize/         照片风格化工具（水墨、水彩、油画等，传统算法 + C 内核，无神经网络）
docs/            PLAN.md：设计与实现方案；PHASE1.md：阶段 1 进度和验收；PHASE2.md：阶段 2 门槛；PHASE3.md：阶段 3 题库
env/             统一 Docker 镜像（Dockerfile、c2p-render）、出口代理（proxy/）、门槛镜像（gate/，加了 strace）
harness/         run.py：在镜像里跑 Claude Code 或 Codex、监控预算、收集产出；batch.sh：批量运行；
                 check.py：断网重跑比对和汇总；gate.py：门槛；gate_validate.py：门槛自检；
                 redteam/：手写对抗样本；tasks/：题目
report/          报告 index.html 及生成脚本
```

仓库不含图片。重跑 B 赛道需要先按 `log.json` 里的 `credits` 下载照片到对应的 `refs/`。

## 许可

代码 MIT。报告中的图片按 CC BY-SA 4.0 分享（B01、B02、B08、B10、B12 用到了 CC BY-SA 照片）；第三方照片的署名和许可见各题 `log.json`。
