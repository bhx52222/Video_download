# 第三方组件与来源

本项目集成组件遵循各自许可。本仓库未为自有代码额外授予统一开源许可证；不能将整包按无附加条件的 MIT 分发。

- `wx_channels_download`：https://github.com/ltaoo/wx_channels_download ，固定版本 v260907，MIT + Commons Clause。完整许可证及 SHA-256 位于 `macos-app/external/wx_channels_download/`。二进制通过构建辅助脚本获取，并随 App 保留许可证，不提交 Git。
- 本地视频号解码组件：源自 https://github.com/oliver-zch/wx-video-channel-download ，固定源版本及原始署名见 `scripts/src/vendor/wxdecrypt/NOTICE.md`，MIT 许可证随源码和 App 保留。
- yt-dlp：https://github.com/yt-dlp/yt-dlp ，作为独立运行依赖安装，按其许可使用。
- FFmpeg、FunASR、ModelScope、PyTorch、parakeet-mlx 等作为运行依赖单独安装，具体组件和模型遵循各自许可。
- Downie 4 为用户自行安装的软件；拾影通过系统 URL 协议调用，未打包 Downie。
- TikWM 备用通过独立适配器访问第三方服务，只发送用户选择的作品链接，不发送浏览器 Cookie；不属于第一方媒体来源。
