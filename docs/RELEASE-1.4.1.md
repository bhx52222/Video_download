# 拾影 1.4.1 测试版

新增快手公开页面解析，修复分享短链接无法下载的问题；整理源码、构建脚本、维护测试和当前说明文档。

- 原生 AppKit 界面与 Python 内核。
- 快手真实样本下载、归档和全片解码通过。
- 保留 Downie 4 联动、OCR 状态修复和视频号试验窗口。
- 全部维护回归通过，主源码与打包快照一致，本地签名校验通过。

下载 `Shiying-1.4.1-macOS-arm64.zip` 并解压打开 App。运行需要 macOS 14+、Apple Silicon 和预装本机 `~/.vx` 环境；不包含全部 Python 依赖或模型，未经过 Apple 公证。安装入口与限制见仓库 README。

`Shiying-1.4.1-source.zip` 为干净源码包，固定版本的视频号辅助二进制通过 `scripts/fetch_wx_helper.py` 下载并校验。App 包内保留第三方 MIT + Commons Clause 等许可。

快手页面直链与 Downie 不受 App 画质上限控制。视频号“只有卡片”的真实端到端采集仍未完成，不作为已可用能力发布。真实样本结果不代表所有平台或作品均可下载。
