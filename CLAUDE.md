# 拾影 · AI 协作约束

这份文件会被 Claude Code 自动读取。改这个仓库之前先读完。
面向人的升级流程见 [docs/UPGRADE.md](docs/UPGRADE.md)，可直接粘贴的提示词见 [docs/PROMPTS.md](docs/PROMPTS.md)。

## 这是什么项目

macOS / Windows 视频下载、字幕、转写与 OCR 工具。Mac 使用 AppKit，Windows 使用 WinForms，共享 Python 内核。1.5 独立包内置运行环境，旧 1.4.1 才依赖 `~/.vx`。参见 `docs/INSTALL-1.5.md` 与 `docs/STANDALONE-1.5.md`。

```
scripts/src/          内核主源码（唯一事实来源）
macos-app/backend/    上面那份的逐字节快照，用于打包
macos-app/            Swift App、进程桥接、App 测试
docs/                 使用、构建、验证说明
```

## 环境能做什么、不能做什么

先核对当前会话的实际主机。**如果当前是在没有 Mac / Windows 连接的 Linux 容器里，以下事情做不到，别假装做到了：**

- 编译 Swift（无 `swiftc`）、构建 `.app`、Apple 公证、代码签名
- 任何 GUI 操作
- 访问视频平台做真实下载（出口策略拦截，且需要浏览器登录态）
- 读写用户 Mac 上的文件

能做的：改代码、跑 Python 测试、跑 Python 逻辑等价性验证、写脚本让用户在 Mac 上一条命令跑完。

**写给用户的命令要带 `cd /Users/beibei/Documents/GitHub/Video_download`**，用户经常在新终端里从家目录执行。

## 必须遵守的硬规则

### 1. 主源码与 App 快照逐字节一致

`scripts/src/` 改了，必须同步 `macos-app/backend/`。`check_backend.py` 会比对 SHA-256，
不一致时 `build.py` 直接停止构建，**不自动覆盖**。

新增一个 backend 文件要改三处，漏一处就是"主源码对、用户跑的那份错"：

```
1. cp scripts/src/新文件.py macos-app/backend/新文件.py
2. macos-app/check_backend.py 的 FILES 元组加进去
3. 检查 packaging/build_macos.py 与 packaging/build_windows.py 的快照复制范围
```

### 2. `run_tests.py` 不编译 `App.swift`

`scripts/run_tests.py` 只编译 `LinkTools.swift` + `test_links.swift`。
`App.swift` 和 `WxPanel.swift` 只有 `macos-app/build.py` 会编译。
所以"回归全过"不等于 App 能编译——改了这两个文件必须让用户跑一次 `build.py`。

### 3. 验构建产物，不是验主源码

主源码正确不代表打包进去的正确。打包清单、快照、bundle 内 `sys.path` 任一处漏了，
用户跑的都是错的那份。`scripts/verify_link_fix.py` 是这个模式的样板：
加载 **App 包内**的 `runner.py` 来测，不是加载仓库里的。

### 4. 验证记录必须诚实

`docs/VALIDATION.md` 是验收记录，不是宣传稿。写进去之前分清楚：

- 模拟测试 ≠ 真实验收
- 单个样本成功 ≠ 全平台可用
- **用户自行测试通过的，标明是用户测的，不并入开发者实测**
- 做不到的事写进"未完成"清单，不要悄悄略过

### 5. 不因为署名删功能

原作者或开发工具的名字出现在代码里，不是删除该功能的理由。

### 6. 隐私边界不能顺手放宽

重构时保留既有的收紧约束。例：剪贴板自动收集只收白名单域名，
界面上写着"其他剪贴板内容不保存"——重构成"接受任意 URL"就是违约，
即使那样功能更强。要放宽必须是用户明确要求，且改掉界面文案。

## 提交与分支

- 在指定的 `claude/*` 分支开发，推送用 `git push -u origin <branch>`
- 提交信息用中文，说清"为什么"而不只是"改了什么"；实测数据写进正文
- 不主动开 PR，除非用户明确要求

## 容易踩的坑

| 坑 | 说明 |
|---|---|
| 同一逻辑存在多份实现 | 查 bug 先搜"是不是还有第二份"。链接解析曾有三份互相不一致 |
| `build.py` 缺连接组件 | 需要 `macos-app/external/wx_channels_download/wx_video_download`，不在 Git，用 `python3 scripts/fetch_wx_helper.py` 取 |
| 测试用的解释器 | `run_tests.py` 用 `~/.vx/venv/bin/python`；`test_download_policy.py` 单独用 yt-dlp 工具环境的 python |
| `outputs/` 和 `work/` | 构建产物，不提交 Git |

## 最终文件存放约定

唯一正式目录为 `/Users/beibei/Documents/GitHub/Video_download`。最终文档放 `docs/` 并维护 `docs/README.md`；发布产物放 `outputs/` 并上传 GitHub Release。临时文件使用仓库内 `work/`，验收后清理；不清理用户媒体、登录态或实际模型缓存。分支和构建入口见 `docs/PROJECT_STATUS.md`。
