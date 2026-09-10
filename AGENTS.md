# 拾影项目文件约定

- 唯一正式目录：`/Users/beibei/Documents/GitHub/Video_download`。
- 最终文档写入本仓库 `docs/`，更新 `docs/README.md`；不要把 Codex 临时目录作为最终文档存放处。
- 安装包、源码包、校验文件放 `outputs/`，通过 GitHub Release 分发；不提交大型产物到普通 Git。
- 主源码与 App 快照必须一致。先阅读 `CLAUDE.md`、`docs/PROJECT_STATUS.md` 和当前验收记录。
- 不按旧交接擅自修改系统代理、证书或登录态，不清理用户媒体和实际使用的模型缓存。
- 当前开发分支为 `claude/standalone-packaging`；Claude 的其他分支保留，不直接覆盖或整套合并未经核验的运行时方案。
