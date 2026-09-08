# 持续升级手册

给人看的。AI 会话的硬约束在仓库根目录 [CLAUDE.md](../CLAUDE.md)，提示词模板在 [PROMPTS.md](PROMPTS.md)。

## 一次升级的完整流程

分工原则：**云端会话改代码，Mac 负责编译、构建和实测。** 云端跑在 Linux 容器里，
编译不了 Swift、打不了包、做不了公证、碰不到界面，也访问不了视频平台。

### 第 0 步 · 说清楚要改什么

用 [PROMPTS.md](PROMPTS.md) 里的模板起手。关键是让 AI 先定位再动手——
这个仓库出过"同一逻辑三份实现"的事，不先摸清楚就改，很可能改了没人调用的那份。

### 第 1 步 · 云端改代码并自测

AI 应当在会话里完成：

- Python 侧的单元与回归测试
- Swift 侧编译不了，就把规则转写成 Python 跑同一批断言，验证**逻辑**（不能替代编译）
- 新增 backend 文件时同步三处（见 CLAUDE.md 硬规则 1）
- 更新 `docs/VALIDATION.md`，注明哪些验了、哪些没验

### 第 2 步 · Mac 上跑回归

```bash
cd /Users/beibei/Documents/GitHub/Video_download
git pull
python3 scripts/run_tests.py
```

这一步会编译 `LinkTools.swift` + `test_links.swift` 并跑全部 Python 回归。

⚠️ **它不编译 `App.swift`**。改了 `App.swift` 或 `WxPanel.swift` 的话，这步全绿也说明不了它们能编译。

### 第 3 步 · 构建（唯一编译 App.swift 的地方）

```bash
python3 macos-app/build.py
```

会先跑 `require_current()` 卡快照一致性，再 `swiftc` 编译三个 Swift 文件，最后本地签名。
成功会打印 `.app` 路径。

报"先运行 fetch_wx_helper"就补一步：

```bash
python3 scripts/fetch_wx_helper.py
```

### 第 4 步 · 验构建产物

```bash
python3 scripts/verify_link_fix.py
```

验的是 App 包里那份代码，不是仓库里的。**这一步不能省**——打包清单漏一个文件，
前三步全绿但用户跑的是错的那份。

新功能应当照着这个脚本的模式加自己的验证脚本：加载 `.app/Contents/Resources/` 下的模块来测。

### 第 5 步 · 界面实测

只有这一步必须手点。跑完把结果告诉 AI，由它更新 `docs/VALIDATION.md`。

按本项目约定：**用户自己测的要标明是用户测的，不并入开发者实测。**

## 验证阶梯速查

| 层级 | 命令 | 覆盖 | 在哪跑 |
|---|---|---|---|
| 逻辑 | AI 会话内的 Python 测试 | Python 内核、解析规则 | 云端 |
| 回归 | `scripts/run_tests.py` | 全部 Python + LinkTools.swift | Mac |
| 构建 | `macos-app/build.py` | 快照一致性 + App.swift 编译 + 签名 | Mac |
| 产物 | `scripts/verify_link_fix.py` | 打包清单 + 包内代码行为 | Mac |
| 界面 | 手动 | 按钮、剪贴板、真实下载 | Mac |

## 改动清单

改内核逻辑（`scripts/src/*.py`）：

- [ ] 同步 `macos-app/backend/` 对应文件
- [ ] 新增文件时改 `check_backend.py` 的 `FILES` 和 `build.py` 的拷贝元组
- [ ] 加或更新 `scripts/test_*.py`
- [ ] 走完验证阶梯第 2–4 层

改 App 界面（`macos-app/*.swift`）：

- [ ] `LinkTools.swift` 的改动在 `test_links.swift` 里加断言
- [ ] **必须跑 `build.py`**，`run_tests.py` 不编译 `App.swift`
- [ ] 界面文案与实际行为一致（尤其是隐私相关的承诺）
- [ ] 手动实测改动到的交互

发版：

- [ ] `docs/VALIDATION.md` 的未完成清单是最新的
- [ ] `docs/RELEASE-*.md` 不夸大：模拟测试不写成真实验收
- [ ] `codesign --verify --deep --strict` 通过

## 案例复盘：链接解析三份实现

2026-09-08 修的那个 bug，值得记下来，因为同类问题会再犯。

**现象**：同一条链接，命令行能下，App 下不了。

**根因**：链接解析有三份互不一致的实现——`LinkTools.swift`（剪贴板）、
`runner.py` 的 `targets()`（下载队列）、`vx_link.py`（本该收口的那份）。
`vx_link.py` 的模块说明写着"CLI 和 app 都调它"，但 App 两条路一条都没接上。

**表现出来的四个 bug**：

| 问题 | 后果 |
|---|---|
| 抖音精选页 `/jingxuan?modal_id=` 不规范化 | yt-dlp 报 `Unsupported URL`，必然失败 |
| 尾部标点表比 `vx_link` 短 | `？】》…` 被当作 URL 的一部分 |
| 域名白名单漏了 `x.com`、`t.cn` 等 | README 声明支持 X，粘贴却提示"没有可识别的链接" |
| 未知站点一律丢弃 | 内核的 yt-dlp 兜底支持上千个站，全被挡在门外 |

**教训**：

1. **查 bug 先搜"是不是还有第二份实现"。** 平台特定的 bug（只在 App 里复现、只在 CLI 里复现）
   十有八九是多份实现不一致，不是那份代码本身有错。
2. **收口不等于接上。** `vx_link.py` 写了收口的注释，但没人调用，等于没收。
   重构留下的"应该这样"的注释，要验证真的这样了。
3. **重构时保留原有的收紧约束。** 这次把解析统一到 `vx_link` 时，
   剪贴板自动收集本可以顺手改成"接受任意 URL"，但界面上写着"其他剪贴板内容不保存"。
   最后拆成两条策略：自动收集保持白名单，手动粘贴才放行未知站点。
4. **验产物不验源码。** 加 `vx_link.py` 时要同步三处，任何一处漏了都是主源码对、
   打包进去的错。`verify_link_fix.py` 就是为此写的。

## 还没做的事

见 `docs/VALIDATION.md` 末尾的未完成清单。当前主要是：

- 全新 Mac 安装验收、带完整运行环境的安装包、Apple 公证
- 视频号"只有卡片"的真实端到端
- 更多快手风控样本

其中**带完整运行环境的安装包**是纯工程活（把 venv、yt-dlp、`visionocr` 打进 `.app`），
可以交给云端会话写，最后在 Mac 上构建验证。其余几项都需要真机、真账号或真实网络。
