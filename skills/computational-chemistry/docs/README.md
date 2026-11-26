# 文档中心

本目录保存面向用户、研究人员和贡献者的详细说明。仓库根目录中的 `README.md` 用于项目概览，`SKILL.md` 用于 AI 执行入口。

## 用户文档

- [安装说明](INSTALLATION.md)：环境要求、依赖安装、Skill 加载、浏览器访问和卸载
- [使用说明](USAGE.md)：各阶段提示词、浏览器审批、结果上传、数据分析和项目恢复
- [浏览器审查](BROWSER_REVIEW.md)：请求、内容哈希、独立页面、三种决定和回传校验
- [方案编辑器](FORM_EDITOR.md)：结构化表单、高级 JSON、受保护字段和双向同步
- [故障排查](TROUBLESHOOTING.md)：端口、浏览器、审批文件、锁、Schema 和 CI 问题
- [隐私指南](PRIVACY.md)：未发表数据、凭据、许可证、日志和本地服务边界

## 仓库与协作文档

- [项目自述文件](../README.md)
- [变更记录](../CHANGELOG.md)
- [贡献指南](../CONTRIBUTING.md)
- [安全策略](../SECURITY.md)
- [支持说明](../SUPPORT.md)
- [参与者行为准则](../CODE_OF_CONDUCT.md)
- [第三方组件声明](../THIRD_PARTY_NOTICES.md)
- [发布流程](../RELEASE.md)
- [引用信息](../CITATION.cff)
- [MIT License](../LICENSE)

## 首次使用阅读顺序

```text
README.md
   ↓
docs/INSTALLATION.md
   ↓
docs/USAGE.md
   ↓
docs/BROWSER_REVIEW.md
   ↓
加载 SKILL.md 并开始阶段 1
```

方案编辑遇到问题时阅读 `FORM_EDITOR.md`；页面、端口、锁或回传异常时阅读 `TROUBLESHOOTING.md`；上传真实计算记录前阅读 `PRIVACY.md`。

参与开发或修改科学规则时，应先阅读 `CONTRIBUTING.md`、`SECURITY.md` 和 `RELEASE.md`，并使用仓库提供的 Issue 或 Pull Request 模板。