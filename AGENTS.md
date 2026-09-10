# 拾影项目约定

- 当前版本 1.5.1，统一在 `main` 维护；本地正式目录 `/Users/beibei/Documents/GitHub/Video_download`。
- 最终文档放 `docs/` 并更新 `docs/README.md`；发布附件放 `outputs/`，通过 GitHub Release 分发。
- 内核主源码在 `scripts/src/`，App 快照在 `macos-app/backend/`。修改后审查并同步，构建前运行 `python3 macos-app/check_backend.py`。
- 以当前源码、实际运行和 `docs/RELEASE-1.5.1.md` 判断能力；模拟、缓存和单个样本结果不能扩大为全平台保证。
- 代码改动运行适当回归，App 改动还需实际构建。普通文档调整检查链接和版本一致性。
- 不擅自修改系统代理、证书、登录态；不删除用户媒体和实际模型缓存。
- 不再保留重复交接、旧版本说明和临时工作树中的最终文档；必要操作入口写入本文件和当前文档。
