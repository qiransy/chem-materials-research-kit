# 在 Codex 和 Antigravity 安装

仓库的 [`skills/`](skills/) 是 27 个 Skill 的共用来源。本页说明两款客户端的项目级安装。其他 Agent 的兼容性待实测。

## 1. 获取仓库

在仓库页面选 **Code → Download ZIP** 后解压，或者克隆。使用最新仓库源码可获得这页所示的安装脚本。

```text
git clone https://github.com/qiransy/chem-materials-research-kit.git
```

## 2. 把 Skill 装到课题目录

在解压后的工具包目录运行下列任一命令。把 `<课题目录>` 换成已存在的项目路径。安装器需要 Python 3.9 或更高版本。Windows 可用 `py`，macOS/Linux 可用 `python3`。

```text
python scripts/install_skills.py codex --project "<课题目录>" --skill chemistry-evidence-review
python scripts/install_skills.py antigravity --project "<课题目录>" --skill chemistry-evidence-review
```

两条命令都会安装到同一个位置。同一课题同时使用 Codex 和 Antigravity 时，执行一次即可。

```text
课题目录/
└── .agents/skills/
    └── chemistry-evidence-review/
        ├── SKILL.md
        └── references/
```

省略 `--skill` 会安装全部 27 个目录。用 `--list` 查看名称，重复传 `--skill` 可选多个。安装器会带上已登记的共享资源，复用内容相符的现有安装，并提示有差异的同名目录。

### 手动复制

把工具包 `skills/` 下面所需的**完整子目录**复制到课题目录的 `.agents/skills/`。例如复制 `chemistry-evidence-review/` 后，应能看到 `.agents/skills/chemistry-evidence-review/SKILL.md`。Nature 系列所需的 [`nature-shared/`](skills/nature-shared/) 等共享资源放在同一级。

已有 Antigravity 插件版可继续使用 [`plugin.json`](plugin.json) 和现有插件目录。同一工作区有插件版时，选择一个发现入口，避免重复技能。

## 3. 在客户端检查

| 客户端 | 打开课题目录后 |
| --- | --- |
| **Codex** | 以课题目录开启新对话，从 Skill 选择器查找 `chemistry-evidence-review`。CLI 可使用 `/skills` 查看，或键入 `$` 选择。 [官方文档](https://learn.chatgpt.com/docs/build-skills) |
| **Antigravity** | 将课题目录作为工作区打开。IDE 可在 Agent 侧栏的 **Customizations** 查看 Skills。App 和交互式 CLI 可用 `/chemistry-evidence-review` 指定。 [官方文档](https://antigravity.google/docs/skills) |

粘贴 [XRD 案例](examples/xrd-phase-identification.md) 或 [动力学案例](examples/reaction-kinetics.md) 的输入，再对照案例下方的检查项。可按需把 [`rules/AGENTS.md`](rules/AGENTS.md) 中的科研原则合并到已有项目指令。

## 验证状态

- **Windows 安装器**：已实测复制全部 27 个目录、按需安装、共享依赖和同名冲突。
- **Codex**：使用本机 Codex 的技能列表接口，从安装后的项目实际识别了全部 27 个 Skill，项目内无识别错误。案例运行和外部工具集成待验证。
- **Antigravity**：安装器可写入工作区的共用目录，发现路径及调用方式已按官方文档核对。客户端识别和案例运行待验证。
- **其他 Agent**：待实测。
