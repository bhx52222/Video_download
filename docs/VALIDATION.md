# 验证记录与未完成事项

日期：2026-09-08。历史测试视频、原始网页和日志已按维护清理要求移除；这里保留结论、样本 ID 和必要校验摘要。用户自行测试通过的平台与开发者实测不混用。

| 范围 | 证据与边界 |
| --- | --- |
| 快手 1.4.1 | 分享短链 X-8YjOXuCJVPO1ig → 作品 3xwkcyyv3r6hp8g。主源码和打包 App runner 各自使用空库联网下载成功，44.373991 秒、720×1280、H.264/AAC、16,191,319 字节；均全片解码通过。未以鼠标操作 GUI 进行此样本验收。 |
| 快手首次文件 SHA-256 | `68704872636f752581d7d2e1b66d1ca54fdf7cf41cb2833c23720a244b010f4c`。不保证所有快手作品。 |
| Downie 4 直接模式 | YouTube jNQXAC9IVRw 与 DBpE9WcC11E 真实下载、归档、全片解码通过。后者 837.962 秒、1920×1080、H.264/AAC、40,218,027 字节。 |
| Downie 自动备用 | 失败后触发分支通过模拟测试；未将直接模式结果称为真实 TLS 失败自动备用验收。 |
| App 回归 | 本地导入、后续 OCR、重下备份、取消进程树、链接解析、Downie 任务隔离等已验证。整理后的回归结果见发布记录。 |
| 视频号无链接采集 | 本机服务启动/停止及状态区分已验证，历史记录与分享 URL 绑定有合成测试；真实卡片 → 链接 → 有效视频仍未完成。 |
| ISAAC64 | 离线解码测试不等于真实加密作品验收，真实样本仍需另测。 |
| NeatDownloadManager | 受控媒体直链下载通过；YouTube 页面只得到 HTML，未作为自动备用接入。 |
| 一体化运行时组装 | `scripts/bundle_runtime.py` 把 Python 独立发行版、truststore、yt-dlp、ffmpeg/ffprobe（连同非系统 dylib 重定位）、visionocr 组装到 `work/runtime/`；转写模型不进包。版本经 `macos-app/runtime.lock.json` 固定并校验 SHA-256，与 wx helper 同一套做法。纯逻辑部分（资产匹配、otool 解析、dylib 相对引用层级）有回归，并用三个变异确认断言有效。开发机首跑暴露两个真实缺陷，均由脚本自带的自检当场拦下：`@rpath` 引用被错误跳过（Homebrew 的 `libwebp.7.dylib` 以 `@rpath` 引 `libsharpyuv.0.dylib`，未打包导致 `Library not loaded`），以及 yt-dlp 包装脚本依赖 `dirname`。已改为按原始位置两阶段解析依赖并读取 `LC_RPATH`，包装脚本改用 shell 内建展开，自检 PATH 由空目录改为 `/usr/bin:/bin`（要验的是不依赖 Homebrew 与 `~/.vx`，不是不依赖系统命令）。修复后的解析逻辑有回归，并用变异确认能捕获这两个缺陷。开发机组装全流程通过：Python 3.12.14（已锁定并提交）、yt-dlp 2026.08.19、ffmpeg 7.1.1_2 连带 92 个依赖库全部重定位，产物 183 MB，自检在 `PATH=/usr/bin:/bin` 下五项全过。`build.py` 打包与 `verify_bundle.py` 复验在开发机通过：成包 238 MB，在 `PATH=/usr/bin:/bin:/usr/sbin:/sbin` 下包内 Python 能 import 依赖、yt-dlp/ffmpeg/ffprobe 均可执行、内核解析到的是包内工具、可写状态仍在包外 `~/.vx`、内核可启动、`codesign --verify --deep --strict` 通过。这些证明包不依赖本机 Homebrew/`~/.vx`/uv，但都在开发机上执行，不等于全新 Mac 安装验收；真实下载与 GUI 亦未实测。 |
| 运行时定位层 | 一体化安装包的地基。`~/.vx` 的九处硬编码收口到 `scripts/src/vx_runtime.py` 与 `macos-app/Runtime.swift`：只读运行时（Python、ffmpeg、yt-dlp、visionocr）可整体切到 `.app` 内，可写状态仍留在 `~/.vx`（`.app` 内部不可写）。不设 `VX_RUNTIME` 时行为与改造前完全一致。`scripts/test_runtime_paths.py` 覆盖默认路径、打包切换、状态分离、缺失工具退回 PATH、venv 布局，连同 vx_link 与 OCR 状态回归在 Linux 上通过。Swift 侧未编译，尚未打入任何真实运行时。 |
| 链接解析统一 | App 队列改为调用 `vx_link`，与 CLI 同一份规则；`LinkTools.swift` 域名表与标点表对齐 `vx_link`，手动粘贴放行未知站点、自动收集仍只收已知平台。开发机 `scripts/run_tests.py` 完整通过，其中 `LinkTools` 经 swiftc 编译并通过 15 条断言（含仿冒域名与凭据 URL 拒绝）。`build.py` 在开发机构建成功，`App.swift` 的粘贴与收集改动随之通过 swiftc 编译，本地签名已重签。`scripts/verify_link_fix.py` 对构建产物复验通过：包内 `backend/vx_link.py` 与主源码 SHA-256 一致（`365458c2f55c0054…`），用包内 `runner.py` 跑 7 条改动前会出错的真实形态全部符合预期。界面部分由使用者自行测试通过（粘贴与剪贴板收集），未留开发者实测日志。 |

已保留 OCR 状态修复、快手 ID、OCR 区域、强制重抽帧、Cookie 提示和下载策略等有效改动。原作者/开发工具名称不是删除功能代码的依据。

未完成：全新 Mac 安装验收（一体化包已能构建，但未在没装过环境的机器上实测）、Apple 公证、视频号无链接真实端到端、更多快手风控样本。仅单个样本成功不能推出全平台可用。

## 整理后发布复验

从最终本地仓库重新构建 1.4.1 成功。`scripts/run_tests.py` 完整通过：内核抓流、下载策略、适配器、链接分类、OCR 状态、平台路由、重试与重下；App 导入、取消、Downie、快手解析、视频号桥接、源码快照保护及 Swift 链接解析。单元/回归使用临时目录和合成样本，未重新下载全部平台样本。构建包 `codesign --verify --deep --strict` 通过。
