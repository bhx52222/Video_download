# 下载前必读：环境配置（1.4.1 测试版）

> **当前 App 不是独立安装包。只有 App 文件，没有本机运行环境，无法直接执行下载、转写或 OCR。**
>
> 请先完成下列配置，再打开 App。安装指引根据当前源码和安装脚本整理，尚未在全新 Mac 上完成全流程验收；不能把开发机可用理解为任意电脑下载即用。

## 1. `~/.vx` 是什么？App 里有没有？

`~` 代表当前登录用户的个人目录。例如用户名是 `alice`，`~/.vx` 就是 `/Users/alice/.vx`；开头的点表示隐藏文件夹。

App 开始任务时固定调用 `~/.vx/venv/bin/python`。这个路径不存在时会提示“处理环境不可用”，并停止启动任务。只安装系统 Python、Conda 或在其他目录建立虚拟环境，不能满足此检查；单纯创建一个空的 `.vx` 文件夹也不够。

| 项目 | 当前 App 是否包含 | 使用者需要准备什么 |
| --- | --- | --- |
| 原生界面、Python 内核与进程桥接 | 包含 | 下载并解压 App |
| Python 解释器及运行依赖 | 不包含 | 在自己的 `~/.vx/venv` 安装 Python 3.12 环境 |
| yt-dlp 和 EJS 组件 | 不包含 | 由仓库安装脚本通过 uv 安装 |
| FFmpeg / ffprobe | 不包含 | 单独安装，用于媒体处理和校验 |
| JavaScript 运行时 | 不包含 | YouTube 内核下载建议安装 Deno |
| Vision OCR 可执行工具 | 不包含；源码在仓库 | 安装脚本编译到 `~/.vx/bin/visionocr` |
| ASR 依赖与模型 | 不包含 | 转写需要额外安装依赖，模型首次使用下载 |
| 视频号本机 API 连接组件 | 包含 | 不代表无链接卡片采集已完成验收 |
| 视频号本地解码工具 `vx-wx-decrypt` | 不包含 | 需要相应解码路径时另行编译 |
| Downie 4 | 不包含 | 仅使用 Downie 下载模式时另行安装 |
| 浏览器、Cookie、账号登录态 | 不包含 | 需要时由使用者在自己的浏览器登录 |

不要复制或索取开发者整份 `~/.vx`。虚拟环境可能引用原电脑路径，该目录也可能包含运行记录；应在自己的电脑上安装。

## 2. 支持的电脑

当前 App 构建目标是 **Apple Silicon（M 系列芯片）、macOS 14 或以上**，没有发布 Intel Mac、Windows 或 Linux App。安装工具及依赖可能有各自的系统要求。

需要联网获取工具和依赖，以及足够的磁盘空间。仅下载不需要安装全部语音模型；转写依赖及模型会额外占用数 GB，具体取决于实际安装的引擎与模型。

当前 App 采用本地签名，未经过 Apple 公证。遇到 macOS 的打开限制，请核对下载来源并按系统提示处理；这与缺少 Python 环境是不同问题。不需要为配置环境关闭系统安全功能。

## 3. 首次配置：先让“仅下载”可用

### 准备工具与源码

1. 从 [Release](https://github.com/bhx52222/Video_download/releases/tag/v1.4.1) 下载 App 压缩包。
2. 下载[当前源码 ZIP](https://github.com/bhx52222/Video_download/archive/refs/heads/main.zip)，解压，里面包含环境安装脚本。使用已打包 App 不需要重新构建 App。
3. 如果没有 Homebrew，按 [Homebrew 官网](https://brew.sh/) 的指引安装，并完成其显示的终端环境设置。
4. 在终端执行以下命令。若 Command Line Tools 弹出安装窗口，需要等待安装完成，再继续后续命令：

```bash
xcode-select --install
brew install uv ffmpeg deno
```

Deno 用于 YouTube 的 JavaScript 挑战；yt-dlp 还需要配套 EJS 组件。安装脚本已请求安装 EJS，但不会安装 Deno。依据：[yt-dlp 官方 EJS 配置说明](https://github.com/yt-dlp/yt-dlp/wiki/EJS)。

### 安装本机环境

切换到刚解压的源码根目录。以下假设文件夹在“下载”中，名称为 `Video_download-main`；如果放在其他位置，请修改 `cd` 后面的路径。

```bash
cd "$HOME/Downloads/Video_download-main"
bash scripts/install_runtime.sh
```

脚本会创建 Python 3.12 环境、安装最小依赖与 yt-dlp，并编译 Vision OCR。不会安装全部转写依赖、自动修改代理或证书，也不会登录浏览器。如果中途报错，请先解决错误，不能仅因 `.vx` 文件夹出现就视为安装成功。

### 检查环境

以下 PATH 与当前 App 使用的工具查找路径一致。`export` 仅影响当前终端，不写入系统配置：

```bash
export PATH="$HOME/.vx/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
"$HOME/.vx/venv/bin/python" --version
"$HOME/.vx/venv/bin/python" -c 'import truststore; print("Python 基础依赖正常")'
command -v yt-dlp ffmpeg ffprobe deno
yt-dlp --version
ffmpeg -version
ffprobe -version
deno --version
test -x "$HOME/.vx/bin/visionocr" && echo 'Vision OCR 工具存在'
```

Python 应显示 3.12，命令查找应分别给出四个工具的路径，版本命令应能运行。工具检查通过仅代表基础组件可访问，不能保证所有网站或视频都能下载。

解压并打开 App，先选择“仅下载”，用一条自己能在浏览器播放的公开单作品链接测试。确认生成有效视频后，再按需添加转写功能。

## 4. 按需增加的功能

### 语音转写

在源码根目录执行：

```bash
bash scripts/install_runtime.sh --asr
```

这会安装中文 FunASR / ModelScope、英文 parakeet-mlx 等转写依赖。首次实际转写还需要联网下载模型；完成依赖安装不代表模型已就位。模型缓存可能在用户的缓存目录，不一定全部位于 `.vx`。不要在首次运行期间删除这些缓存。

只使用“仅下载”不需要此步骤；使用无字幕视频的转写或完整 OCR 互校流程时，应准备相应 ASR 环境。装包失败或模型加载失败需要单独排查，不能用开发机测试记录替代新电脑验收。

### 视频号解码工具

需要视频号相应解码路径时，在源码根目录执行：

```bash
brew install go
bash scripts/build_wx_decrypt.sh
```

已有 `sph` 分享链接的下载与“只有卡片”的采集是两条路径；部分分享解析需要使用者自己的 Edge / Chrome 元宝登录态。安装全部环境也不意味着无链接采集已可用，目前真实端到端验证仍未完成。

### Downie 4 与浏览器

只有选择 Downie 模式才需要单独安装 Downie 4；电脑同时安装 Downie 3 时，应核对 `downie://` 的关联。取消拾影不会取消 Downie 中的下载。

需要登录的作品，请在 App 所选浏览器中登录自己的账号。不要把 Cookie、账号文件、签名媒体 URL 或完整个人运行目录上传到 GitHub 排错。

## 5. 常见问题

| 现象 | 应检查什么 |
| --- | --- |
| App 提示“处理环境不可用” | 当前用户的 `~/.vx/venv/bin/python` 是否存在且可执行；只安装别处的 Python 不够 |
| 终端能运行工具，App 却找不到 | 工具是否位于上方列出的 App PATH 中；App 不会自动读取交互终端的完整配置 |
| 提示找不到 ffmpeg、ffprobe 或 yt-dlp | 重做命令查找与版本检查，确认安装没有中途失败 |
| YouTube 提示 JavaScript / EJS 相关错误 | 核对 Deno 和 yt-dlp/EJS；环境齐全后仍可能遇到登录验证或平台变化 |
| 转写提示缺少模块、模型下载或加载失败 | 确认使用 `--asr` 安装；检查网络、磁盘空间和完整错误信息 |
| 下载返回登录、验证或链接过期 | 这是平台访问条件，不能仅通过重建 `.vx` 解决；核对新链接和自己的浏览器登录态 |
| 删除 `.vx` 后不能运行 | 该目录是运行依赖，不是可随意删除的测试垃圾；重新安装环境 |

默认媒体库 `~/VideoExtract`、Python 环境 `~/.vx` 和 App 文件是不同内容。删除 App 不会自动删除环境或媒体；卸载前请分别确认哪些数据需要保留。

## 6. 当前发布承诺的范围

1.4.1 是需要配置环境的测试版，不是“下载解压即可使用”的独立安装包。开发机已完成构建和功能回归，尚未完成干净 Mac 的安装验收。详细功能验证见 [VALIDATION.md](VALIDATION.md)，自行构建见 [BUILD.md](BUILD.md)。
