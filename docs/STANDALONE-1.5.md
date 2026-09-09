# 1.5 独立安装包开发与验收

本分支将 Mac 与 Windows 的运行依赖放入 App / EXE 安装包。使用者不需配置 `~/.vx`、Python、FFmpeg、Go 或 PATH。安装步骤见 [INSTALL-1.5.md](INSTALL-1.5.md)。当前是测试版；并非所有平台和模式均已实测。

## 运行方式

- Mac：Apple Silicon App，内置 Python、下载工具、FFmpeg、Vision OCR 和 ASR 依赖。
- Windows：x64 EXE 安装器、WinForms 界面、内置 Python、FFmpeg、下载工具、RapidOCR 与 ASR 依赖。Visual C++ 运行库使用应用目录部署，无需用户手动安装。
- 语音模型首次联网自动下载；这不是所有模型预置的完全离线包。
- Mac 英文用 parakeet-mlx，Windows 英文用 faster-whisper，中文均保留 FunASR。识别结果可能不同。
- Downie 4 / IDM 由使用者自行安装授权。IDM 先接收解析出的单文件媒体地址，等待有效媒体后归档，不保证能够补救页面解析失败。

## 已获得的证据

2026-09-08 至 2026-09-09：

| 范围 | 结果与边界 |
| --- | --- |
| Mac 包内运行时 | 新 HOME、受限 PATH，本地视频导入、媒体标记与全片解码通过；未生成 `.vx` |
| Mac 路径与签名 | Mach-O 非系统绝对路径审计、严格本地签名校验通过 |
| Mac GUI / 回归 | 主界面启动；包内流程测试覆盖重新下载备份、下载后补 OCR、取消子进程 |
| Mac 快手真实下载 | 用户提供的公开作品下载、归档与全片解码通过，不代表所有快手作品 |
| Mac 英文转写 | 首次下载模型后，短英文语音正确识别出 video downloader、English speech |
| macOS 虚拟机 | 无 `.vx`，包内依赖导入、本地视频处理与解码通过；开发工具审计因无 otool 未运行；随后 Parallels 虚拟机发生崩溃，未算完整 GUI 验收 |
| Windows x64 CI（372ebec） | EXE 编译、安装到新目录、依赖导入、中文文件路径处理、全片解码、实际 OCR、GUI 进程启动通过 |
| Windows 11 ARM64 虚拟机初测 | EXE 安装成功，发现缺少 Visual C++ DLL 导致 PyTorch 加载失败，推动补包；不能把 CI 通过当作干净系统完整通过 |
| Windows 快手真实下载 | 使用本次测试进程的可用代理后，15.4 MB 视频下载、归档和全片解码通过；原系统代理指向过期地址，系统设置未修改 |
| IDM | 参数、取消、拒绝无效媒体地址的模拟测试通过；虚拟机未装 IDM，真实联动未验收 |

2026-09-10 最终补包验收（Windows 构建源码 `3f867f3`，GitHub Actions `34324643861`）：

- 在同一 Windows 11 ARM64 虚拟机重新安装 EXE，退出码 0，无需重启；未额外安装 Python、开发工具或系统级 VC++ 运行库。
- 安装目录内的 Visual C++ DLL 加载路径检查通过；FunASR、faster-whisper、RapidOCR 等实际导入通过。
- 包内 FFmpeg 生成视频、含中文 / 空格 / `&` 的本地文件导入、全片解码均通过。
- 英文 OCR 和底部识别区域通过，中文 OCR 正确输出“视频下载测试12345”。
- 英文语音首次模型下载及实际推理通过，43.1 秒完成；结果包含“video downloader”和“clear English speech”。无需 HF Token、管理员权限或开发者模式，缓存的符号链接警告不影响结果。
- 包内 Deno 和 yt-dlp 可执行；快手指定作品再次真实下载约 15.4 MB、归档并全片解码通过。
- GUI 进程及主界面已实际启动。尚未逐个点击验收全部界面操作，不能把核心流程测试扩大为完整 UI 回归。
- 网络测试使用仅限测试进程的有效代理。虚拟机原系统代理地址过期，未修改系统代理、Surge 设置、证书或登录态。

真实中文转写、完整平台回归、IDM 实机联动、无链接视频号端到端仍未完成。

## 与 Claude 分支的关系

验收期间发现本地 `claude/incomplete-conversation-tasks-r7n9wk` 已有 Claude 新提交 `6c43cd0`。该分支保留原样，没有用本次打包方案覆盖。本文与交付的源码包对应 `claude/standalone-packaging`，两套运行时实现尚未合并，构建时不可混用。

## 构建与分发

Mac 构建：`python3 packaging/build_macos.py`，仅构建机需已验证的 Python 3.12 和工具；产物会复制并重定位依赖。Windows 在 GitHub Windows runner 运行 `python packaging/build_windows.py`，输出 Inno Setup EXE，再安装并运行 `packaging/smoke_windows.py`。Windows 11 虚拟机只安装最终 EXE，未配置开发环境。

Apple 公证与 Windows 发布者签名未配置。正式公开发布前仍需完整依赖许可 / 对应源码资料核验。源码已推送开发分支，GitHub Actions 构建产物与正式 Release 分开管理。
