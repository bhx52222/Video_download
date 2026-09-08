# 原生 macOS App

AppKit 界面与 Python 进程桥接。主源码在 `../scripts/src/`，`backend/` 为经审查同步的打包快照。

在仓库根目录运行 `python3 macos-app/build.py`；详细依赖、获取第三方组件和验证步骤见 [构建说明](../docs/BUILD.md)。

当前版本 1.4.1 测试版，输出到 `../outputs/`。使用现有 `~/.vx` 环境，本地签名，未公证。现有能力、真实验收和限制以仓库根 README 及 docs 为准，不依赖历史交接文件。
