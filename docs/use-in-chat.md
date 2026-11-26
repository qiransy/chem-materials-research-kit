# 在网页和通用对话 Agent 使用

## 文件或提示词模式

1. 在 [任务索引](../README.md) 选 Skill。打开它的 `SKILL.md`，保留正文及其中要求的参考文件。
2. 上传这些文件和可共享的输入；只支持文本时粘贴所需内容。也可附上 [科研原则](../rules/AGENTS.md)。如果 Agent 能读取公开仓库，可以给到具体文件链接并要求打开核对。
3. 指定任务、可以使用的资料和希望交付的格式。只有当前会话具备联网、运行脚本或访问文件的权限时，才可用相应功能。

例如：

> 请阅读我附上的 chemistry-evidence-review/SKILL.md 和 evidence-checklist.md，按流程审查下面这条结论。分别给出我可以写的表述、替代解释和一项判别验证。请以我附上的数据和测量条件为准。

可直接使用 [XRD 案例](../examples/xrd-phase-identification.md) 的输入试跑。对涉及多个文件的 Skill，先提供入口和当前任务确实需要的参考资料。含账号授权或未发表数据的工作留在用户授权的环境中。

## 平台有原生导入入口时

- **Claude 网页端**：可将独立的 `chemistry-evidence-review/` 文件夹压成 ZIP，在账户支持自定义 Skills 时从 Customize → Skills 上传。单独上传其他 Skill 前先检查其引用的同级目录是否会一并可读；也可以在对话里附件提供所需共享参考。 [Claude 帮助](https://support.claude.com/en/articles/12512180-use-skills-in-claude)
- **ChatGPT**：有可用的 Skill 或插件入口时可按平台的导入、分发方式操作；普通对话中使用上面的文件或提示词模式。 [OpenAI Skills 文档](https://learn.chatgpt.com/docs/build-skills)
- **其他 Agent 或自建系统**：可以将 `SKILL.md` 作为固定任务指令，把引用的参考加入该 Agent 的文件库，或按项目路径安装。工具名、运行环境和权限按自己的系统配置。
