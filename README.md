# Chemistry & Materials Research Kit (Antigravity Plugin)

面向**化学与材料方向**科研新手和研究生的 Antigravity 通用科研技能包（已做脱敏与普适化处理，不含任何个人配置、私有路径或 API 密钥）。

---

## 一、快速安装（30 秒上手）

### 方式 1：直接下载压缩包（推荐新手，不用装 Git）
1. 打开本仓库右侧的 **[Releases](https://github.com/qiransy/chem-materials-research-kit/releases/latest)**，下载 `chem-materials-research-kit.zip`。
2. 解压后得到 `chem-materials-research-kit` 文件夹（确保里面直接包含 `plugin.json`、`skills/` 和 `rules/`）。
3. 将整个文件夹放到你的 Antigravity 全局插件目录：
   - **Windows**：`C:\Users\<你的用户名>\.gemini\config\plugins\chem-materials-research-kit\`
   - **macOS / Linux**：`~/.gemini/config/plugins/chem-materials-research-kit/`
   - *（如果只想在某一个课题文件夹生效，也可以放到该项目的 `.agents/plugins/chem-materials-research-kit/` 目录下）*

### 方式 2：命令行一键克隆（熟悉 Git 的用户）
```bash
# macOS / Linux
git clone https://github.com/qiransy/chem-materials-research-kit.git ~/.gemini/config/plugins/chem-materials-research-kit

# Windows (PowerShell)
git clone https://github.com/qiransy/chem-materials-research-kit.git "$env:USERPROFILE\.gemini\config\plugins\chem-materials-research-kit"
```

放好后无需复杂配置，在 Antigravity 中开启下一轮对话即可自动加载生效；你也可以在 Antigravity 的 **Plugins / Customizations** 页面随时一键开启或关闭本插件。

---

## 二、强烈建议顺手安装的官方科研插件

因为本包侧重**文献管理、论文读写、审稿修回、数据分析、表征作图与汇报**，建议你在 Antigravity 插件市场（Plugins Manager）中直接搜索并一键安装以下两个官方免费插件，搭配使用效果最佳：

- **`chemistry`**：内置 RDKit、PubChem、ChEMBL、PubMed、OpenAlex、反应/物性/机器学习/分子对接等专业化学数据库与工具。
- **`scientific-literature`**：内置 arXiv、bioRxiv、Europe PMC、PubMed、OpenAlex、ClinicalTrials 等文献直连检索工具。

---

## 三、包含的 26 个科研技能一览

> **使用小技巧**：平时不需要背技能名，直接用自然语言提需求即可（Antigravity 会自动匹配调用对应技能）；如果想明确指定，也可以直接说出技能名。

### 1. 选题打磨与文献检索管理
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

## 四、通用科研原则（`rules/AGENTS.md`）

本插件附带了一套简洁、无个人信息的通用科研原则，启用插件后会自动约束助手：
- 严格区分**事实、推论与猜想**，不编造文献、DOI 或实验数据；
- 保留单位、误差棒、测试条件与计算级别；
- 先核验前提与隐藏变量，修改代码和文稿时坚持最小改动原则。

如果你更希望完全使用自己的全局规则，直接删掉插件内的 `rules/` 文件夹即可，不会影响 26 个技能的正常使用。

---

## 五、新手常用提问示例

- 「我想做一个关于 XXX 材料的课题，请用 `grill-me` 帮我一步步把实验设计和对照方案问清楚。」
- 「帮我精读这篇 PDF，用 `nature-paper-card` 做一份深度精读卡片，重点看它的实验证据链和局限性。」
- 「这是我整理的 20 条参考文献，请帮我核验每条的 DOI、作者、年份和卷期有没有错漏。」
- 「把这段中文实验结果改写成符合顶刊风格的英文 Results 段落，注意不要拔高结论。」
- 「请模拟两位严格审稿人帮我预审这篇初稿，列出 Major Concerns 和修改建议。」
