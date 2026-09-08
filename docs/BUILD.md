# 安装与构建

## 条件

macOS 14 或以上、Apple Silicon、Xcode Command Line Tools。App 是本地签名测试包，未公证。运行环境使用 `~/.vx/venv/bin/python`（Python 3.12）、FFmpeg、yt-dlp、可选 Vision OCR / ASR；其他电脑需要单独安装。

以下操作由使用者明确执行，不会自动修改系统代理、证书或登录态：

```bash
xcode-select --install
brew install uv ffmpeg
bash scripts/install_runtime.sh
```

需要语音转写时执行 `bash scripts/install_runtime.sh --asr`。ASR 安装与模型下载体积较大；依赖清单是安装入口，未宣称在全新 Mac 上完整验收。已有环境不需要为纯下载重装 ASR。

视频号分享的可选本地解码器：安装 Go 后执行 `bash scripts/build_wx_decrypt.sh`。代码与 MIT 许可在 `scripts/src/vendor/wxdecrypt/`。

## 构建 App

```bash
# 下载固定版本的视频号连接组件并校验 SHA-256；不运行组件
python3 scripts/fetch_wx_helper.py
python3 macos-app/check_backend.py
python3 macos-app/build.py
```

输出 `outputs/拾影视频下载器-1.4.1测试版.app`。第三方连接组件的二进制不进入 Git，构建包保留其来源和许可证。构建需要该组件文件存在且哈希正确。

修改内核时，以 `scripts/src/` 为主源码；审查差异后将五个模块及 vendor 同步到 `macos-app/backend/`。构建保护会检查这些文件，差异必须先解决。

## 命令行与验证

```bash
~/.vx/venv/bin/python -B scripts/src/vx.py '视频链接' --download-only
python3 -B scripts/run_tests.py
codesign --verify --deep --strict 'outputs/拾影视频下载器-1.4.1测试版.app'
```

测试使用临时目录和合成样本，不需要重跑用户媒体库。App 测试需要先构建；部分内核测试需要安装 yt-dlp 的 Python 环境，运行器会使用 uv 的 yt-dlp 工具环境。网络真实样本的历史结果与模拟分支在 [VALIDATION.md](VALIDATION.md) 分开记录。

频道研究辅助脚本 `20_channel_catalog.sh`、`21_channel_survey.sh` 保留为命令行工具，未整合 App；不会在构建或测试时自动遍历频道。
