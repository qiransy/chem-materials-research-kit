# Third-Party Notices & Upstream Attribution

本插件包整合了多套开源科研 Agent 技能，并对部分路由描述进行了面向**化学与材料研究**的普适化调整（移除个人配置与无关垂直领域路由）。各上游组件的版权与开源许可归各自原作者及仓库所有：

| 技能 / 组件 | 上游项目 | 许可协议 |
| :--- | :--- | :--- |
| `academic-research-suite` | [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) | 见上游仓库 LICENSE |
| `nature-paper-card`、`nature-reader`、`nature-writing`、`nature-polishing`、`nature-figure`、`nature-paper2ppt`、`nature-ref-verifier`、`nature-reviewer`、`nature-response`、`review-response`、`nature-shared` | [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) | Apache-2.0 |
| `computational-chemistry` | [jianzushen/Computational-chemistry-skill](https://github.com/jianzushen/Computational-chemistry-skill) | MIT |
| `editaplot` | [hang-jin/editaplot](https://github.com/hang-jin/editaplot) | Apache-2.0 |
| `ppt-master` | [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) | MIT |
| `chemistry-evidence-review` 及 `examples/`（XRD / 动力学模拟案例） | 面向化学与材料场景整理的开放工作流与合成示例 | 本仓库分发 |
| 其余通用科研技能（`paper-lookup`、`literature-review`、`research-ideation`、`managing-zotero`、`citation-verification`、`results-analysis`、`results-report`、`scientific-visualization`、`scientific-writing`、`humanizer`、`grill-me`） | 社区/个人整理之通用科研技能 | 保留各自目录内自带的许可与说明文件（如有） |

### 免责与使用提示
- 如需获取某一上游技能的最新更新或单独安装，请直接访问上表对应的上游仓库。
- 本仓库不包含任何个人 API Key、私有数据库凭据或个人本地配置；部分依赖外部工具或数据库的功能（如 Zotero 本地写入、Origin 自动化绘图、文献 API 检索）需由使用者在本地自行准备相应运行环境。
