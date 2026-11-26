# 跨 Agent 安装

仓库的 [`skills/`](skills/) 是 27 个 Skill 的共用来源。支持 [Agent Skills](https://agentskills.io/specification) 的客户端可按项目目录发现技能。网页聊天或仅能读取附件的助手可使用[文档模式](docs/use-in-chat.md)。同一项目使用同一发现目录的客户端可以共用一份安装。

## 1. 获取仓库

在仓库页面选 **Code → Download ZIP** 后解压，或者克隆。使用最新仓库源码可获得这页所示的安装脚本。

```text
git clone https://github.com/qiransy/chem-materials-research-kit.git
```

## 2. 选择项目和客户端

在解压后的工具包目录运行。安装器用 Python 3.9+ 标准库，Windows 可按本机环境将 `python` 改为 `py`，macOS/Linux 可用 `python3`。将示例中的项目路径改为已存在的课题目录。

```text
python scripts/install_skills.py agents --project "/path/to/project" --skill chemistry-evidence-review
python scripts/install_skills.py claude --project "/path/to/project" --skill nature-writing
python scripts/install_skills.py copilot --project "/path/to/project" --dry-run
```

不传 `--skill` 会安装全部 27 个目录。用 `--list` 查看名称，重复传 `--skill` 可选择多个，脚本会带上已登记的共享与引用依赖。安装时保留文件夹内的脚本、样例、参考与模板。内容相符的现有安装会复用，有差异的同名目录会报告冲突。安装脚本只复制到选中的项目。

| 客户端 | 脚本参数 | 项目内安装位置 |
| --- | --- | --- |
| Antigravity | `agents` 或 `antigravity` | `.agents/skills/` · [文档](https://antigravity.google/docs/skills) |
| Codex | `agents` 或 `codex` | `.agents/skills/` · [文档](https://learn.chatgpt.com/docs/build-skills) |
| Cursor | `agents` 或 `cursor` | `.agents/skills/` · [文档](https://cursor.com/docs/skills) |
| Gemini CLI | `agents` 或 `gemini` | `.agents/skills/` · [文档](https://geminicli.com/docs/cli/skills/) |
| OpenCode | `agents` 或 `opencode` | `.agents/skills/` · [文档](https://opencode.ai/docs/skills/) |
| OpenClaw | `agents` 或 `openclaw` | `.agents/skills/`（对应 Agent 的 workspace） · [文档](https://docs.openclaw.ai/skills) |
| Devin Local | `agents` 或 `devin` | `.agents/skills/` · [文档](https://docs.devin.ai/desktop/devin-local/customizations) |
| Claude Code | `claude` | `.claude/skills/` · [文档](https://code.claude.com/docs/en/skills) |
| GitHub Copilot（VS Code） | `copilot` | `.github/skills/` · [文档](https://code.visualstudio.com/docs/agent-customization/agent-skills) |
| Kiro | `kiro` | `.kiro/skills/` · [文档](https://kiro.dev/docs/skills/) |
| Qwen Code | `qwen` | `.qwen/skills/` · [文档](https://qwenlm.github.io/qwen-code-docs/en/users/features/skills/) |
| Roo Code | `roo` | `.roo/skills/` · [文档](https://roocodeinc.github.io/Roo-Code/features/skills/) |

其他支持 Agent Skills 的客户端可按其文档，用 `--skills-dir <项目内目录>` 指定技能目录。例如 `python scripts/install_skills.py --project "/path/to/project" --skills-dir .example/skills --skill chemistry-evidence-review`。

### 手动复制

把仓库中 `skills/` 的**子目录**放入上表位置。例如用 Codex 安装证据核查时，最终路径为 `项目/.agents/skills/chemistry-evidence-review/SKILL.md`。客户端有不同规则时，以该客户端文档中的技能位置为准。复制时保留整个技能目录，Nature 系列需要的 [`nature-shared/`](skills/nature-shared/) 等共享资源放在同一级。个别技能有可选的跨技能流程，按任务需要再安装。

已有 Antigravity 插件版可继续使用 [`plugin.json`](plugin.json) 和现有插件目录。同一工作区有插件版时，选择一个发现入口，避免重复技能。

## 3. 验证

1. 从课题目录启动客户端并开启新对话。查看客户端的技能列表，或明确指定 `chemistry-evidence-review`。
2. 粘贴 [XRD 案例](examples/xrd-phase-identification.md) 或 [动力学案例](examples/reaction-kinetics.md) 的输入，完成后再对照检查答案。
3. 可将 [`rules/AGENTS.md`](rules/AGENTS.md) 的内容合并到客户端使用的项目指令。也可在对话里明确让 Agent 读取这份文件。已有项目指令时保留原文再按需合并。

安装目录依据各客户端文档。自动匹配、脚本执行、联网检索和本地应用权限由实际客户端决定。使用 Skill 内命令时，将命令中的技能路径换成当前安装目录中的真实路径。
