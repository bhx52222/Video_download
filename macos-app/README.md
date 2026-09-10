# 拾影 macOS App 1.5.1

AppKit 界面与 Python 进程桥接，面向 macOS 14+、Apple Silicon。App 内置运行环境，使用者无需配置 ~/.vx；构建机依赖与使用者要求分开说明。

在仓库根目录运行 `python3 packaging/build_macos.py`，输出 `outputs/拾影视频下载器-1.5.1独立版.app`。详见 [构建与验证](../docs/BUILD.md)、[安装说明](../docs/INSTALL-1.5.1.md)。

主源码在 `scripts/src/`，`backend/` 为经审查同步的快照。当前使用本地签名，未完成 Apple 公证。
