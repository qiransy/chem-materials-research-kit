# 安装说明

Computational Chemistry Skill 以完整仓库目录作为 Skill 使用，不是独立的 pip 软件包。必须保留 `SKILL.md`、`scripts/`、`references/`、`assets/` 和 `docs/` 的相对结构。

## 环境要求

- Windows 10/11、Linux 或 macOS
- Python 3.10 或更高版本
- Git
- 支持本地 Skill 的 AI 工具
- 用户自行准备的计算化学软件、许可证和计算环境
- 可选：PowerShell 7，用于受控的 Windows 本地自动化

项目不会自动安装 CP2K、Quantum ESPRESSO、Gaussian、ORCA、GROMACS、LAMMPS、VASP 或其他科研软件，也不会配置商业许可证或超算账户。

## 获取仓库

```bash
git clone https://github.com/jianzushen/Computational-chemistry-skill.git
cd Computational-chemistry-skill
```

更新前先保存本地修改，再使用 `git pull --ff-only`。

## Python 环境

Windows 可以直接使用虚拟环境中的 Python，无需激活脚本或修改执行策略：

```powershell
pwsh -NoLogo -NoProfile -NonInteractive -Command "py -3.10 -m venv .venv"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux、macOS 或 WSL：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

PowerShell 7 是可选执行器。所有 Skill 自动调用必须使用 `pwsh -NoLogo -NoProfile -NonInteractive`、有限超时和输出检查。不要用 `powershell.exe` 替代，也不建议永久放宽系统执行策略。

开发和测试依赖：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
ruff check .
```

测试通过只表示相应软件断言成立，不表示科研计算已经收敛。

## 加载和最小验证

在支持自定义 Skill 的工具中选择仓库根目录 `SKILL.md`。最小请求：

```text
帮我用 CP2K 优化这个结构。
```

正确行为是逐步询问目标、结构、软件版本、运行位置、环境配置、所需文件、回传文件和关键参数。信息完整前不得生成审查页面或计算文件。

阶段一信息完整后，默认终审固定为 `.review/review.html`，修改时覆盖。自动打开失败时手动打开返回的绝对路径；该失败不阻断科学分析。

## 项目数据

真实项目应放在仓库外，或放在 `.gitignore` 排除的工作目录中。不要提交 `.review/`、`*.out`、`*.err`、计算结果、用户本地路径、服务器地址、账户凭据、SSH 密钥、许可证文件、缓存或临时状态。

卸载前确认本地副本中没有唯一的科研输入、结果或尚未备份的数据。
