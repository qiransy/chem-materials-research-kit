# Chemistry & Materials Research Kit

面向**化学与材料方向**科研新手和研究生的跨 Agent 科研工具包。包含 **27 个 Skill 目录**、[通用科研原则](rules/AGENTS.md) 和两份模拟案例。各客户端共用开放 [Agent Skills](https://agentskills.io/specification) 格式的 `skills/`，可按需安装。

---

## 一、选择你的使用方式

- **本地客户端** · 下载仓库源码或克隆，按[跨 Agent 安装指南](INSTALL.md)选平台和项目。Antigravity、Codex、Cursor、Gemini CLI、OpenCode、OpenClaw 和 Devin Local 可共用 `.agents/skills/`。Claude Code、Copilot、Kiro、Qwen Code 和 Roo Code 有各自的目录。
- **网页聊天或通用 Agent** · 按[文档模式](docs/use-in-chat.md)提供任务所需的 Skill、参考资料和输入。平台有自定义 Skill 入口时也可按其规则导入。
- **Antigravity 插件** · 已安装的插件可继续通过原来的 `plugin.json` 入口启用。

---

## 二、用模拟案例试跑

不确定有没有装成功、或者想立刻看看效果？直接打开本包内的模拟案例：
- **[XRD 物相指认案例](examples/xrd-phase-identification.md)**
- **[反应动力学案例](examples/reaction-kinetics.md)**

明确指定 `chemistry-evidence-review`，并提交案例里的 **「输入给 Agent」**。任务完成后，再用案例下半部分的 **「检查答案时看这些点」** 核对证据、结论和建议验证是否对应。

---

## 三、工具和运行条件

证据审查、文献阅读、分析规划和稿件检查可以用用户提供的材料开展。联网检索用当前 Agent 可访问的学术来源；Antigravity 用户也可以按需选用 `chemistry` 或 `scientific-literature` 插件。Zotero 写入、Origin 自动化、实际量化计算和 PPTX 渲染各有工具与运行环境要求。执行前核对所需能力，交付时说明实际做过的验证。

---

## 四、包含的 27 个科研技能一览

> 可直接描述任务。要确认走哪个流程时，明确指定技能名或提供它的 `SKILL.md`。

### 1. 证据核查、选题打磨与文献管理
- `chemistry-evidence-review`：审查化学与材料中的物相、结构、性能、动力学或机理论断，界定证据边界、列出竞争解释并设计下一项判别验证（附[证据核查模板](skills/chemistry-evidence-review/references/evidence-checklist.md)）
- `grill-me`：通过交互式追问帮你把模糊的课题想法、实验方案或技术路线打磨清楚
- `research-ideation`：从宽泛方向收敛研究问题、科学假设、Gap 分析与验证计划
- `paper-lookup`：跨 PubMed / OpenAlex / Crossref / arXiv / Europe PMC / Semantic Scholar 等多库检索论文与引用
- `literature-review`：按规范协议开展系统性/范围性文献综述
- `managing-zotero`：通过 Zotero 本地接口安全整理文献库、去重与补全元数据（写操作前会先预览确认）
- `citation-verification` / `nature-ref-verifier`：逐条或批量核验参考文献的 DOI、作者、标题、年份、卷期与页码

### 2. 论文精读、写作、润色与审稿修回
- `nature-paper-card`：将单篇 PDF/论文提炼为固定 16 节的结构化深度精读卡片（含证据链与结论边界审计）
- `nature-reader`：按段落生成忠实原文的中英双语精读文档（支持公式与图表）
- `nature-writing`：基于你的实验与计算证据起草 Abstract、Introduction、Results、Discussion 等章节
- `nature-polishing`：学术英文/中文段落润色、逻辑衔接与 LaTeX 排版修正（不篡改事实与引用）
- `humanizer`：去除明显的 AI 腔套话，让行文更自然贴近真实学者风格
- `scientific-writing`：稿件科学严谨性审计（证据溯源、报告规范、前后数据一致性）
- `nature-reviewer`：模拟顶刊审稿人做投稿前自审（输出 Major/Minor Comments）
- `nature-response` / `review-response`：撰写逐点审稿意见回复信（Rebuttal / Response Letter）与修回 Cover Letter
- `nature-shared`：Nature 系列写作/润色/审稿技能的共享参考库（由上述技能自动调用）
- `academic-research-suite`：需要从选题到成文走完整多阶段科研流水线时调用

### 3. 计算化学、数据分析、表征作图与组会汇报
- `computational-chemistry`：计算化学与材料计算方案规划、输入文件检查与结果解读（DFT/量化/表面/界面等）
- `results-analysis`：实验数据集统计分析、对比评估与不确定度核算
- `results-report`：将阶段性实验或计算结果整理为面向决策的科研进展报告
- `scientific-visualization`：日常科研数据可视化与图表真实性/配色无障碍审查
- `nature-figure`：面向投稿的多面板科研插图排版与机理示意图设计
- `editaplot`：面向 Windows + Origin/OriginPro 用户的自动化表征绘图（支持 XPS、XRD、XAS、FTIR、NMR、UV-Vis、PL/TRPL、DSC、电化学等）
- `nature-paper2ppt`：把单篇论文拆解为适合组会/文献汇报的中文 PPT 叙事框架与讲稿
- `ppt-master`：生成、美化与重构可编辑的 PPTX 演示文稿

---

## 五、通用科研原则（`rules/AGENTS.md`）

使用本仓库作为工作区时，根目录 `AGENTS.md` 指向共用科研原则。安装到其他课题时，可按客户端的指令格式把 [`rules/AGENTS.md`](rules/AGENTS.md) 合并到项目规则，或者在任务中明确引用：
- 严格区分**事实、推论与猜想**，不编造文献、DOI 或实验数据；
- 保留单位、误差棒、测试条件与计算级别；
- 先核验前提与隐藏变量，修改代码和文稿时坚持最小改动原则。

---

## 六、开源归属与许可

本合集整合了多套优秀的开源科研技能，各上游项目来源与许可协议详见 **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**。
