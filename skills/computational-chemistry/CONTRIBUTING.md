# 贡献指南

感谢参与 Computational Chemistry Skill 的改进。本项目同时涉及软件工程、计算化学方法、科学证据边界和人机协同审批，因此修改不仅要“能运行”，还必须保证科学含义、来源链和用户控制不被破坏。

## 可贡献内容

- 修复浏览器审查、状态机、Schema、版本管理和文件处理问题
- 改进结构化方案编辑器和普通用户交互
- 新增或完善计算软件、模块、参数和输出映射
- 补充科学任务、证据链、可支持结论和不可支持结论规则
- 改进安装、使用、故障排查和示例文档
- 增加单元、集成和端到端测试
- 修复隐私、安全、路径、端口、锁和原子写入问题

## 开始前

先搜索现有 Issue 和 Pull Request，避免重复工作。涉及科学规则、软件关键字、单位、参考态、参数物理意义或结论边界的修改，建议先提交“科学规则问题”Issue，说明依据和影响范围。

不得提交：

- SSH 私钥、账户凭据、访问令牌或许可证文件
- 未经授权的未发表数据和合作方材料
- 大型真实计算输出、轨迹、波函数和检查点文件
- 无法确认来源或许可证的第三方代码与资源
- 将商业软件真实结果改写成由开源软件产生的虚假说明

## 开发环境

```bash
git clone https://github.com/jianzushen/Computational-chemistry-skill.git
cd Computational-chemistry-skill
python -m venv .venv
```

Windows PowerShell 7（无需激活脚本）：

```powershell
pwsh -NoLogo -NoProfile -NonInteractive -Command "py -3.10 -m venv .venv"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Linux 或 macOS：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## 分支与提交

从最新 `main` 创建独立分支：

```bash
git switch main
git pull --ff-only
git switch -c fix/short-description
```

推荐分支前缀：

- `fix/`：缺陷修复
- `feat/`：新功能
- `docs/`：文档
- `test/`：测试
- `refactor/`：不改变外部行为的重构
- `science/`：科学规则或软件映射

推荐使用清晰的提交信息，例如：

```text
fix: reject stale browser review decisions
docs: clarify stage 3 data-processing workflow
science: correct QE cutoff parameter mapping
```

一个提交尽量只解决一个逻辑问题。不要把格式化、无关重命名和功能修改混在同一个提交中。

## 修改要求

### 工作流与状态机

修改 `SKILL.md` 或 `workflows/` 时，必须说明：

- 进入条件
- 阻塞条件
- 用户必须确认的内容
- 输出文件和状态
- 失败返回位置
- 对后续阶段的影响

默认简单流程不得跳过阶段一完整性检查和最终用户审查。高级项目不得绕过其内容哈希、用户决定或科学证据要求。

### 浏览器审查

修改默认审查机制时必须保持：

- 信息完整前不生成任何审查文件
- 页面固定为 `.review/review.html`，修改时覆盖
- 只有回传机制需要时才生成 `.review/review_response.json`
- 浏览器自动打开失败时提供路径且不阻断流程
- 正式计算目录只包含必要文件和一个 `README.md`
- PowerShell 7 调用受限、可超时、可降级且不是单点依赖

修改高级兼容审查时，还必须保持 `request_id`、`stage`、`content_hash` 和 `status` 匹配、原子写入、陈旧决定拒绝及三种决定分支可验证。

### Schema 和数据转换

修改 Schema、表单转换或高级 JSON 模式时必须保证：

- 旧版本数据仍可读取，或提供明确迁移程序
- 未知扩展字段不会被静默删除
- 数字、布尔值、空值和字符串类型不会漂移
- 内部 ID、数组顺序和依赖关系不会无故改变
- `manual_overrides` 和版本记录不会丢失
- 系统字段不会被普通表单覆盖

### 科学规则和软件映射

任何科学规则修改都应提供可核查依据，优先使用官方软件手册、正式论文、方法论文或权威数据库。必须说明：

- 适用软件和版本
- 适用模块或任务类型
- 参数或输出的物理、化学含义
- 单位、参考态和符号约定
- 能支持的结论
- 不能单独支持的结论
- 与其他证据的相互验证关系
- 版本差异和已知限制

不得根据名称相似就把不同软件关键字视为一一等价。

## 测试

提交前至少运行：

```bash
python -m pytest
ruff check .
```

涉及类型标注时再运行：

```bash
mypy scripts
```

涉及浏览器审查、公共等待函数、原子写入、锁、端口或状态机时，必须运行逐阶段端到端回归测试，不能只运行单元测试。

涉及科学规则时，应增加最小测试夹具，验证字段、单位、版本边界和结论限制。

## 文档同步

以下变化必须同步更新文档：

- 安装方式或依赖变化
- 命令、路径和环境要求变化
- 阶段顺序、状态和回退规则变化
- Schema 或 JSON 字段变化
- 浏览器审批行为变化
- 软件支持范围和科学边界变化
- 用户输入输出要求变化

README 用于项目概览；详细规则应放在 `docs/`、`workflows/` 或 `references/`，不要维护互相矛盾的多套说明。

## Pull Request 要求

Pull Request 应说明：

- 修改目的和问题背景
- 主要修改文件
- 对用户流程和科学结论的影响
- 已执行测试和结果
- 是否修改 Schema、状态、版本或审批逻辑
- 是否新增第三方依赖
- 是否需要迁移旧项目
- 文档是否同步

Pull Request 未通过测试、证据不足或会绕过用户审批时，不应合并。

## 版本和兼容性

遵循语义化版本：

- 修订版本：兼容性缺陷修复
- 次版本：向后兼容的新功能
- 主版本：Schema、状态机、文件结构或行为存在不兼容变化

不兼容修改必须提供迁移说明，并在 `CHANGELOG.md` 中记录。
