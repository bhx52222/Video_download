# 拾影视频下载器

macOS / Windows 视频下载、字幕提取、语音转写和画面文字识别工具。Mac 使用原生 AppKit 界面，Windows 使用 WinForms 界面，两者共享 Python 内核。

**当前版本：1.5.1 一体化测试包。** 内置 Python、FFmpeg、下载工具和识别依赖；使用者不需配置 `~/.vx`。语音模型首次使用联网下载，Downie 4 / IDM 不包含在包内。安装包尚未完成 Apple 公证或 Windows 发布者签名。

- [1.5.1 安装与使用](docs/INSTALL-1.5.1.md)
- [本版改动、实测记录与未完成项目](docs/RELEASE-1.5.1.md)
- [下载安装包：GitHub Release v1.5.1](https://github.com/bhx52222/Video_download/releases/tag/v1.5.1)

旧 [v1.4.1 Release](https://github.com/bhx52222/Video_download/releases/tag/v1.4.1) 仍依赖外部环境；只有运行旧版或准备开发环境才需要阅读 [旧版环境说明](docs/ENVIRONMENT.md)。不要把旧版包和 1.5 安装说明混用。

## 使用

1. Windows 双击 `Shiying-1.5.1-Windows-x64-Setup.exe` 安装；Mac 解压 `Shiying-1.5.1-macOS-arm64.zip` 后将完整 App 拖入“应用程序”。
2. 打开拾影，粘贴单个作品链接或分享文字，选择处理方式和保存目录后开始。默认只下载，默认媒体库为用户目录下的 `VideoExtract`。
3. 也可添加本地视频。重新下载保留旧媒体备份；取消停止拾影自身处理。
4. 模型首次使用自动下载。需要登录的平台仍取决于浏览器登录态、网站风控与可用网络。

[第三方组件](THIRD_PARTY_NOTICES.md) · [持续升级](docs/UPGRADE.md)

## 当前能力

- YouTube、Bilibili、抖音、小红书、微博、Instagram、X 等通过内核或相应适配器处理；作品可用性、登录态与风控会影响结果。
- 快手：支持公开单作品页和分享短链接；1.4.1 新增公开页面解析，已真实下载指定样本并全片解码。
- YouTube：Mac 可选择 Downie 4；Windows 可选择 IDM。外部软件需自行安装授权，IDM 仅交接已经解析出的单文件媒体地址，不能视为 Downie 的同等页面解析器。
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
windows-app/         Windows GUI、OCR 适配与安装器定义
packaging/           独立运行时打包、安装后验证
docs/                当前使用、构建和验证说明
```

`macos-app/backend/` 与主源码不一致时构建会停止；先审查并同步修改，不自动覆盖。构建结果写入本地 `outputs/`，不提交到 Git；App 发布到 Releases。

仓库不包含用户媒体、Cookie、账号、测试下载视频、旧交接文档或本机私钥。依赖和第三方组件遵循各自许可，特别是视频号连接组件附有 Commons Clause，不能将整包视作无附加限制的 MIT 软件。
