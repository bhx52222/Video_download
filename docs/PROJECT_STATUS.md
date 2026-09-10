# 项目当前状态与文件约定

更新：2026-09-10。

## 唯一正式目录

`/Users/beibei/Documents/GitHub/Video_download`

- `docs/`：最终安装、构建、交接、验收和历史文档，提交到 GitHub。
- `scripts/src/`：内核主源码；`macos-app/backend/`：逐字节打包快照。
- `macos-app/`、`windows-app/`、`packaging/`：界面与打包代码。
- `outputs/`：仅保留当前 1.5.1 安装包、App、源码包、校验值及依赖清单；大型产物发布到 GitHub Release，不纳入普通 Git 提交。
- 后续临时构建与测试放仓库内 `work/`，验证结束及时清理。用户媒体与实际使用的模型缓存不属于工作目录清理范围。

## 版本与分支

最新公开测试版：[v1.5.1](https://github.com/bhx52222/Video_download/releases/tag/v1.5.1)，发布标签固定在 `ed65fc4732840bea986762ab8670e723f9f77543`。

当前开发与文档分支：`claude/standalone-packaging`。本次目录整理属于发布后的文档维护，不改写已发布标签和安装包。

Claude 的另一条分支 `claude/incomplete-conversation-tasks-r7n9wk` 保留供查阅，运行时方案并未整套合并。`main` 仍是旧版，不能因为仓库首页默认显示 main 就认定 1.5.1 未上传；请查看 Release 或切换本开发分支。没有擅自合并两套实现或修改默认分支。

## 构建和验证

Mac：`python3 packaging/build_macos.py`。构建机需要已验证的 Python 3.12 与音视频工具，普通使用者不需要这些开发环境。

Windows：GitHub Actions 的 Windows standalone installer 工作流，正常构建时 assemble 保持 false；Windows 虚拟机只安装生成的 EXE。

组装附件的 assemble=true 分支专用于本次 1.5.1 附件，固定构建号和哈希；后续版本不要原样重用。

验收方法见 RELEASE-1.5.1.md、STANDALONE-1.5.md。额外 Windows 检查脚本收在 scripts/validation/，必须使用安装包内的 Python；其中网络样本测试不属于默认离线回归。

## 同步规则

在 GitHub Desktop 中选择本正式目录及 `claude/standalone-packaging`。Changes 为空且本地与 origin 同一提交才表示代码和文档同步完成。outputs 被 .gitignore 排除是有意设计，安装包同步看 GitHub Release 附件，而不是 Changes 列表。

最终文档只在此仓库维护；历史交接保留在 docs/history，版本验收保留明确日期和测试边界。不要让临时工作树成为唯一保存位置。
