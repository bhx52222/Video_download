# 第三方组件与来源

本项目集成组件遵循各自许可。本仓库未为自有代码额外授予统一开源许可证；不能将整包按无附加条件的 MIT 分发。

- `wx_channels_download`：https://github.com/ltaoo/wx_channels_download ，固定版本 v260907，MIT + Commons Clause。完整许可证及 SHA-256 位于 `macos-app/external/wx_channels_download/`。二进制通过构建辅助脚本获取，并随 App 保留许可证，不提交 Git。
- 本地视频号解码组件：源自 https://github.com/oliver-zch/wx-video-channel-download ，固定源版本及原始署名见 `scripts/src/vendor/wxdecrypt/NOTICE.md`，MIT 许可证随源码和 App 保留。
- yt-dlp：https://github.com/yt-dlp/yt-dlp 。1.5.1 将其及相关依赖放入包内，按各组件许可使用。
- 1.5.1 内置 Python、FFmpeg、FunASR、ModelScope、PyTorch 和下载依赖；Mac 还包含 parakeet-mlx，Windows 包含 faster-whisper、RapidOCR / ONNX Runtime。Python 包的 dist-info / licenses 保留在运行时目录，Windows 下载来源与 SHA-256 写入 resources/provenance.json；模型使用各自许可，首次使用下载。公开正式发布前仍需完成完整依赖清单与对应源码资料核验。
- Downie 4 为用户自行安装的软件；拾影通过系统 URL 协议调用，未打包 Downie。
- TikWM 备用通过独立适配器访问第三方服务，只发送用户选择的作品链接，不发送浏览器 Cookie；不属于第一方媒体来源。

- IDM：https://www.internetdownloadmanager.com/ ，由用户自行安装授权；未打包 IDM 或其许可证。
- Deno：https://github.com/denoland/deno ，作为包内 JavaScript 运行工具。
