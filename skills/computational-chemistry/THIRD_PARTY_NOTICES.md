# 第三方组件声明

Computational Chemistry Skill 本身采用 MIT License。项目依赖或可选集成的第三方组件仍受各自许可证、使用条款和引用要求约束。

## Python 运行依赖

| 组件 | 用途 | 许可证 |
|---|---|---|
| Flask | 本地浏览器审查服务与 HTTP API | BSD-3-Clause |
| jsonschema | 结构化方案、请求和审批结果的 Schema 校验 | MIT |
| PyYAML | YAML 工作流、配置和参考数据读取 | MIT |

## 开发与测试依赖

| 组件 | 用途 | 许可证 |
|---|---|---|
| pytest | 单元、集成和端到端测试 | MIT |
| pytest-cov | 测试覆盖率 | MIT |
| coverage.py | Python 覆盖率统计 | Apache-2.0 |
| requests | HTTP 接口和集成测试 | Apache-2.0 |
| Ruff | Python 代码检查与格式规则 | MIT |
| mypy | 静态类型检查 | MIT |
| types-PyYAML | PyYAML 类型声明 | Apache-2.0 |
| types-requests | requests 类型声明 | Apache-2.0 |

实际版本范围以 `requirements.txt` 和 `requirements-dev.txt` 为准。许可证名称仅用于仓库说明，发布前应以对应组件当前发行包中的许可证文件为准。

## 前端组件

如果浏览器方案编辑器或审查页面集成 Monaco Editor、CodeMirror、图标库、字体或其他前端资源，必须在本文件中补充组件名称、版本、来源、许可证和是否修改。不得仅通过 CDN 引用而不记录来源和许可证。

## 科研软件与数据资源

Quantum ESPRESSO、CP2K、Gaussian、ORCA、GROMACS、LAMMPS、VASP、Multiwfn 及其他科研软件不随本仓库分发。用户必须自行获取软件、许可证、赝势、基组、力场和数据库，并遵守各自的使用与引用要求。

本项目中的开源替代建议仅用于复现、迁移或方法比较，不改变用户实际计算所使用的软件来源。商业软件结果不得被错误描述为由开源软件生成。

## 新增第三方组件的要求

贡献者新增依赖或复制第三方代码前，必须：

1. 确认许可证允许当前使用和再分发方式。
2. 记录组件名称、版本、来源和许可证。
3. 保留上游版权与许可证声明。
4. 说明是否对上游代码进行了修改。
5. 评估是否会上传用户数据、访问外部网络或扩大本地服务暴露范围。
6. 同步更新依赖文件、安装文档和本文件。

不得提交来源不明、许可证不兼容或受商业限制的代码、字体、图标、数据和模型文件。