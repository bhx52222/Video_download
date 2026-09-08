# 拾影视频下载器

Apple Silicon macOS 视频下载、字幕提取、语音转写和画面文字识别工具。原生 AppKit 界面，Python 内核，默认媒体库 `~/VideoExtract`。

**当前版本：1.4.1 测试版。** [下载 App](https://github.com/bhx52222/Video_download/releases/tag/v1.4.1)。这是依赖本机运行环境的测试包，未包含 Python、FFmpeg 和全部模型；采用本地签名，未经过 Apple 公证。

> **下载前必读：当前 App 不包含 `~/.vx` 运行环境。新电脑必须先安装 Python 环境、FFmpeg、yt-dlp 等，否则无法启动下载任务。请先阅读[环境配置说明](docs/ENVIRONMENT.md)。**

## 使用

1. 按[环境配置说明](docs/ENVIRONMENT.md)准备运行环境；原来已使用拾影的 Mac 通常已有此环境。
2. 解压 Releases 中的 `Shiying-1.4.1-macOS-arm64.zip`，打开 App。
3. 粘贴单条作品链接或分享文字，选择“仅下载”“下载并转写”或“下载、转写和 OCR”，确认保存目录后开始。
4. 也可添加本地视频。重新下载会保留旧媒体备份；取消停止拾影自身处理。

[使用说明](docs/USAGE.md) · [安装与构建](docs/BUILD.md) · [验证与限制](docs/VALIDATION.md) · [第三方组件](THIRD_PARTY_NOTICES.md)

## 当前能力

- YouTube、Bilibili、抖音、小红书、微博、Instagram、X 等通过内核或相应适配器处理；作品可用性、登录态与风控会影响结果。
- 快手：支持公开单作品页和分享短链接；1.4.1 新增公开页面解析，已真实下载指定样本并全片解码。
- YouTube 可选择 Downie 4 直接下载或失败备用；需要另行安装 Downie 4。
- 视频号 `weixin.qq.com/sph/…` 分享链接与“只有卡片”的采集是两条不同路径。无链接采集窗口仍属试验功能，尚未完成真实端到端验收。
- 优先已有字幕；没有字幕时可使用语音识别。OCR 失败、空结果、零散文字与有效识别分别记录，机器文字仍需核对。

## 目录

```text
scripts/src/          内核、OCR、抓流与链接工具的主源码
scripts/test_*.py     内核回归测试
scripts/              环境安装、构建辅助与频道研究工具
macos-app/            Swift App、Python 进程桥接、App 测试
macos-app/backend/    用于 App 打包的内核快照
macos-app/external/   可选视频号组件的来源与许可证
docs/                当前使用、构建和验证说明
```

`macos-app/backend/` 与主源码不一致时构建会停止；先审查并同步修改，不自动覆盖。构建结果写入本地 `outputs/`，不提交到 Git；App 发布到 Releases。

仓库不包含用户媒体、Cookie、账号、测试下载视频、旧交接文档或本机私钥。依赖和第三方组件遵循各自许可，特别是视频号连接组件附有 Commons Clause，不能将整包视作无附加限制的 MIT 软件。
