# 拾影 1.5.1 构建与验证

普通使用者下载 [Release](https://github.com/bhx52222/Video_download/releases/tag/v1.5.1) 安装包即可，无需配置开发环境；见 [安装说明](INSTALL-1.5.1.md)。以下要求仅适用于构建机。

## macOS

需要 Apple Silicon、macOS 14+、Xcode Command Line Tools、已验证的 Python 3.12 环境和 FFmpeg、Deno 等工具。构建器默认读取 `~/.vx/venv/bin/python`，支持用 `SHIYING_BUILD_PYTHON` 指定解释器；会把运行依赖复制进 App。

开发环境安装入口为 `scripts/install_runtime.sh --asr`。视频号解码器用 `scripts/build_wx_decrypt.sh` 构建；视频号连接组件通过以下脚本获取固定版本并校验。

在仓库根目录运行：

```bash
python3 scripts/fetch_wx_helper.py
python3 macos-app/check_backend.py
python3 packaging/build_macos.py
python3 packaging/verify_macos.py 'outputs/拾影视频下载器-1.5.1独立版.app'
python3 scripts/run_tests.py
```

构建会重建同名输出 App。验证实际包内运行环境和本地视频处理，并检查非系统绝对动态库依赖与签名。完整回归还编译 Swift 链接解析测试，不能代替 App 构建。

## Windows

GitHub Actions 的 **Windows standalone installer** 工作流在 Windows 构建机执行 `python packaging/build_windows.py`。支持从 main 手动运行，相关源码变化也会触发。

产物 `outputs/Shiying-1.5.1-Windows-x64-Setup.exe` 包含运行环境和应用目录内的 Visual C++ DLL。工作流实际安装到新目录，再执行包内 `smoke_windows.py` 和 GUI 启动检查。最终用户不需要安装开发环境。

## 发布检查

- 主源码与 App 快照哈希一致。
- 验证最终安装包，不把源码测试当成安装成功。
- 分开记录本机实测、虚拟机实测、模拟分支和未完成事项。
- 打包源码、安装说明、验收记录、依赖清单及 SHA-256，上传 Release 后核对远端摘要。
- Apple 公证、Windows 发布者签名尚未配置；功能边界见 [验收说明](RELEASE-1.5.1.md)。
