# 1.5 独立安装包开发与验收

开发目标：Mac 内置 Python、下载工具、FFmpeg、OCR 与 ASR 依赖，不再要求外部 `~/.vx`；Windows 使用独立 WinForms 界面、同一内核与 IDM 交接。当前分支是开发阶段，不能将构建产物视为完整正式发布。

模型暂采用首次自动下载，位于用户数据目录。Mac 使用 FunASR / parakeet-mlx 与 Vision OCR；Windows 中文保留 FunASR，英文使用 faster-whisper，OCR 使用 RapidOCR。功能目的相同，识别引擎与结果不会完全相同。

IDM 由使用者自行安装授权。拾影先解析出可用单文件媒体地址，再交给 IDM，等待有效视频后归档。仅发送请求不算成功；取消拾影不取消 IDM。IDM 不具备 Downie 的页面解析能力，内核连媒体地址都无法解析时，IDM 不能自动补足这部分。当前先支持可解析的单文件音视频直链，多轨合并不交 IDM。

Mac 构建：`python3 packaging/build_macos.py`，需要构建机上已经验证的 Python 3.12 环境与工具。该构建过程将依赖复制并重定位到 App；使用者运行产物不应访问构建机环境。Windows 构建：在 Windows x64/Python 3.12 上执行 `python packaging/build_windows.py`，编译 WinForms 启动器与 Inno Setup 安装器。CI 用于验证 Windows 安装及基础本地媒体流程，不能替代真实浏览器、IDM 与视频号交互测试。

在正式发布前还需：依赖许可/对应源码资料整理、包内外部路径审计、完整安装测试、真实下载/转写/OCR、IDM 实机验证。Apple 与 Windows 发布签名未配置。
