# 拾影 1.5.1 项目状态

## 统一入口

本地正式目录：`/Users/beibei/Documents/GitHub/Video_download`。

代码、说明和后续开发统一在默认分支 `main`，GitHub Desktop 也使用该分支。[当前发布](https://github.com/bhx52222/Video_download/releases/tag/v1.5.1)。

## 文件

- `docs/`：当前版本的最终安装、使用、构建和验收说明。
- `scripts/src/`：内核主源码；`macos-app/backend/`：经审查同步的打包快照。
- `macos-app/`、`windows-app/`、`packaging/`：界面与安装包代码。
- `outputs/`：1.5.1 App、安装器、源码包、依赖清单和校验文件；大型文件通过 Release 分发，不提交普通 Git。
- `work/`：可重建的临时构建和测试文件，完成后清理；不包含用户媒体和实际模型缓存。

## 同步判定

GitHub Desktop 选择 Video_download / main。Changes 为空，并且本地 main 与 origin/main 相同才表示代码与文档同步完成。安装包是否同步以 Release 附件及 SHA-256 为准。

1.5.1 程序构建与验收见 RELEASE-1.5.1.md。本次统一 main 和删除旧文档不改变已经验收的安装器二进制；源码包与发布文字同步更新。
