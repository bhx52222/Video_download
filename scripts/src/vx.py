#!/usr/bin/env python3
"""
vx —— 全平台视频内容提取内核

一条视频从链接到可用文本的全过程：
  解析元数据 → 建目录 → 下载 → 取字幕(官方优先，无则 ASR) → 抽帧 → 可选 OCR 互校 → 落盘

设计上的几个取舍，写在这里免得以后忘：
  · 官方字幕永远优先于 ASR。YouTube 有 30 种人工字幕轨，跑 ASR 是纯浪费。
  · 国内平台一律带浏览器 cookie。不带的话抖音直接拒绝、B 站概率性 412。
    用 --cookies-from-browser 直读，不生成 cookies.txt——那文件等同全平台登录态。
  · 拿不到的字段写 null，不写 0 也不写空串。抖音不公开播放量，写 0 会被误读成零播放。
  · 断点续跑靠目录里的 .done 标记，不靠 index.csv 反查，后者会被人手改乱。
"""
import tempfile
from urllib.parse import urlsplit
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import ssl
# truststore 让 Python 走系统钥匙串里的根证书。装了 Surge 的 MITM CA 之后，
# 抓流拿到的直链才验得过。但它只服务于少数几个下载路径，
# 没有理由因为它缺席就让整个程序起不来——上一版是顶层裸 import，
# 结果 venv 里没装的时候，vx 的每一条命令都 ImportError。
try:
    import truststore
    TLS_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    HAS_TRUSTSTORE = True
except Exception:
    TLS_CONTEXT = ssl.create_default_context()
    HAS_TRUSTSTORE = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vx_runtime import configure
configure()
VXHOME = Path(os.environ.get("VX_HOME", str(Path.home() / ".vx")))
DEFAULT_LIB = Path(os.environ.get("VX_LIB", str(Path.home() / "VideoExtract")))
VISIONOCR = Path(os.environ.get("VX_BIN", str(VXHOME / "bin"))) / ("visionocr.py" if os.name == "nt" else "visionocr")

CN_HOSTS = ("douyin.com", "bilibili.com", "b23.tv", "xiaohongshu.com", "xhslink",
            "kuaishou.com", "weibo.c", "ixigua.com", "zhihu.com", "qq.com",
            "iqiyi.com", "youku.com")

PLATFORM_MAP = {
    "youtube.com": "youtube", "youtu.be": "youtube",
    "bilibili.com": "bilibili", "b23.tv": "bilibili",
    "douyin.com": "douyin", "kuaishou.com": "kuaishou",
    "xiaohongshu.com": "xiaohongshu", "xhslink.com": "xiaohongshu",
    "weibo.com": "weibo", "weibo.cn": "weibo", "ixigua.com": "xigua", "zhihu.com": "zhihu",
    "v.qq.com": "tencent", "iqiyi.com": "iqiyi", "youku.com": "youku",
    "channels.weixin.qq.com": "wxchannel", "mp.weixin.qq.com": "wxarticle",
    "instagram.com": "instagram", "tiktok.com": "tiktok", "tiktokv.com": "tiktok",
}

def log(msg, lvl="·"):
    print(f"  {lvl} {msg}", flush=True)

def die(msg):
    print(f"  ✗ {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)

# ---------------------------------------------------------------- 元数据

def platform_of(url):
    u = (urlsplit(url).hostname or "").lower()
    if u == "weixin.qq.com" and urlsplit(url).path.startswith("/sph/"):
        return "wxchannel"
    for k, v in PLATFORM_MAP.items():
        if u == k or u.endswith("." + k):
            return v
    return u.removeprefix("www.").split(".")[0] if u else "unknown"

# YouTube 是否带 cookie。默认关，理由见 needs_cookies。
YOUTUBE_COOKIES = False

def needs_cookies(url):
    """默认对所有站点带 cookie，唯独 YouTube 默认不带。

    yt-dlp 只会把 cookie 发给对应域名，带上没有额外风险，
    不带则很多站白白失败——实测 Vimeo 一条公开视频也要求登录态。

    但 YouTube 是反的：带上登录 cookie 之后，它只返回视频轨、不给音频轨，
    于是 `bv*+ba/b` 选不到东西，报 "Requested format is not available"。
    实测同一条视频不带 cookie 正常、带 Chrome cookie 就失败，
    --list-formats 里清一色 "video only"。公开视频占绝大多数，
    所以默认不带；会员或年龄限制的内容用 --youtube-cookies 显式打开。"""
    if platform_of(url) == "youtube":
        return YOUTUBE_COOKIES
    return True

# YouTube 的反爬会在两种失败之间来回摆：
#   带 cookie  → "Requested format is not available"（只给 video-only 轨）
#   不带 cookie → "Sign in to confirm you're not a bot"
# 两种都实测遇到过，同一台机器上相隔几小时。所以不能靠一个静态默认值，
# 必须两个方向都能兜。注意 YouTube 用的是弯引号 U+2019，直引号匹配不到。
BOT_CHECK_MARKERS = (
    "confirm you're not a bot",
    "confirm you\u2019re not a bot",
    "sign in to confirm",
    "please sign in",
    "cookies for the authentication",
)

def looks_like_bot_check(msg):
    m = (msg or "").lower()
    return any(k in m for k in BOT_CHECK_MARKERS)

# 真实 Chrome 的 UA。yt-dlp 默认 UA 会被 B 站的 WAF 标记，短时间多次请求就返回 412。
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

def browser_list(spec):
    """cookie 来源可以给多个浏览器，按序尝试。

    实测场景：Chrome 里登了抖音微博、Edge 里登了快手。写死一个浏览器
    就必然有平台拿不到 cookie。yt-dlp 一次只接受一个 --cookies-from-browser，
    所以由这里逐个试，谁先成功后续步骤就一直用谁。"""
    if not spec or spec == "none":
        return ["none"]
    return [b.strip() for b in spec.split(",") if b.strip()]

def ytdlp_base(url, browser, force_cookies=False):
    cmd = ["yt-dlp", "--no-warnings", "--socket-timeout", "20",
           "--user-agent", UA,
           "--extractor-retries", "3", "--retry-sleep", "http:exp=2:20",
           "--sleep-requests", "1"]
    if platform_of(url) == "tiktok":
        # TikTok 保留提取器默认 UA，避免覆盖其平台请求设置。
        ua_index = cmd.index("--user-agent")
        del cmd[ua_index:ua_index + 2]
    if browser and browser != "none" and (force_cookies or needs_cookies(url)):
        cmd += ["--cookies-from-browser", browser]
    # B 站校验 Referer；缺了会提高被 WAF 拦的概率
    if "bilibili" in url.lower() or "b23.tv" in url.lower():
        cmd += ["--referer", "https://www.bilibili.com/"]
    elif "douyin" in url.lower():
        cmd += ["--referer", "https://www.douyin.com/"]
    return cmd

def alt_urls(url):
    """同一条内容的其他入口形式。

    yt-dlp 的 extractor 常常只对其中一种 URL 形态适配良好。实测微博
    weibo.com/tv/show/1034:xxx 会抛 KeyError('Component_Play_Playinfo')，
    换成 video.weibo.com/show?fid=1034:xxx 走的是另一条解析路径。"""
    out = []
    m = re.search(r"weibo\.com/tv/show/([\d:]+)", url)
    if m:
        out.append(f"https://video.weibo.com/show?fid={m.group(1)}")
    m = re.search(r"video\.weibo\.com/show\?fid=([\d:]+)", url)
    if m:
        out.append(f"https://weibo.com/tv/show/{m.group(1)}")
    m = re.search(r"b23\.tv/(\w+)", url)
    if m:
        out.append(url)  # 短链交给 yt-dlp 自己跟随跳转
    return out

# 同平台两次请求之间的最小间隔（秒）。批量档里这是防 412 的主力手段——
# 退避是撞上之后的补救，节流是不让它撞上。
# 实测 09-07：三条 YouTube 打完紧接着两条 B站，第一条 B站 15/45/90 三档退避
# 全用完（累计 150s）仍然 412，第二条只等 15s 就过了。说明卡的是请求密度，
# 不是固定时间窗口——所以间隔比退避有用。
PLATFORM_MIN_GAP = {
    "bilibili": 8.0,     # 唯一实测撞穿退避的平台，给最大间隔
    "douyin": 4.0,
    "xiaohongshu": 4.0,
    "weibo": 3.0,
    "tiktok": 3.0,       # 实测出现过一次"风控"退避
}
DEFAULT_MIN_GAP = 1.5
_LAST_REQ = {}

def throttle(url):
    """同平台连续请求之间补足最小间隔。单条跑时几乎无感（首次不等），
    批量档里才起作用。按平台分别计时，不同平台互不影响。"""
    p = platform_of(url)
    gap = PLATFORM_MIN_GAP.get(p, DEFAULT_MIN_GAP)
    last = _LAST_REQ.get(p)
    if last is not None:
        wait = gap - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _LAST_REQ[p] = time.monotonic()


def fetch_meta_multi(url, spec, attempts=4):
    """按序试每个浏览器的 cookie。返回 (raw, err, 用了哪个浏览器)。"""
    last = ""
    cands = browser_list(spec)
    if platform_of(url) in ("instagram", "tiktok"):
        cands = list(dict.fromkeys(["none"] + cands))
    for i, b in enumerate(cands):
        raw, err = fetch_meta(url, b, attempts=attempts if i == 0 else 2)
        if raw is not None:
            if len(cands) > 1 and b != cands[0]:
                log(f"用 {b} 的 cookie 拿到了（{cands[0]} 不行）", "✓")
            return raw, None, raw.get("_vx_browser", b)
        last = err or ""
        # 只有在像是登录态问题时才换浏览器；限速换了也没用
        if not any(k in last.lower() for k in ("cookie", "log in", "logged-in", "login", "sign in", "403")):
            break
        if i + 1 < len(cands):
            log(f"{b} 的 cookie 不行，换 {cands[i+1]} 再试", "↻")
    return None, last, cands[0]

def fetch_meta(url, browser, attempts=4):
    """412 / 403 这类风控是速率相关的，等一会儿重试通常就好。
    不重试的话，连着跑批量档时前几条成功、后面全挂，很难排查。"""
    last = ""
    for i in range(attempts):
        throttle(url)
        cmd = ytdlp_base(url, browser) + ["--skip-download", "--dump-single-json", "--no-playlist", url]
        r = run(cmd)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout), None
            except json.JSONDecodeError as e:
                return None, f"yt-dlp 输出不是合法 JSON: {e}"
        last = "\n".join(l for l in r.stderr.splitlines() if l.strip())[:600]
        # 带 cookie 反而拿不到格式，是平台对登录态返回了残缺的格式集。
        # 不限于 YouTube，所以放在通用位置：去掉 cookie 再试一次。
        if "format is not available" in last.lower() and "--cookies-from-browser" in cmd:
            log("带 cookie 时平台没给出可用格式，去掉 cookie 重试", "↻")
            throttle(url)
            r2 = run(ytdlp_base(url, "none") + ["--skip-download", "--dump-single-json", "--no-playlist", url])
            if r2.returncode == 0:
                try:
                    retry_raw = json.loads(r2.stdout)
                    retry_raw["_vx_browser"] = "none"
                    return retry_raw, None
                except json.JSONDecodeError:
                    pass
        # 反方向：不带 cookie 撞上机器人校验，就强行带上 cookie 再试。
        # 这条专治 YouTube——needs_cookies() 默认给它剥掉 cookie，
        # 而平台在被判定为可疑 IP 时又非要登录态不可。
        if (looks_like_bot_check(last) and browser and browser != "none"
                and not needs_cookies(url)):
            log("平台要求登录态才肯给数据，带 cookie 再试", "↻")
            throttle(url)
            r3 = run(ytdlp_base(url, browser, force_cookies=True)
                     + ["--skip-download", "--dump-single-json", "--no-playlist", url])
            if r3.returncode == 0:
                try:
                    retry_raw = json.loads(r3.stdout)
                    retry_raw["_vx_browser"] = browser
                    retry_raw["_vx_force_cookies"] = True
                    return retry_raw, None
                except json.JSONDecodeError:
                    pass
        if i < attempts - 1 and any(c in last for c in ("412", "403", "429", "Precondition", "Too Many")):
            # 15/45/90 实测扛不住 B 站；累计从 150s 提到 230s。
            # 再往上加意义不大——真正管用的是上面的 throttle。
            wait = (20, 60, 150)[min(i, 2)]
            log(f"被限速（{'412' if '412' in last else '风控'}），等 {wait}s 再试（第 {i+2}/{attempts} 次）", "↻")
            time.sleep(wait)
            continue
        break
    # 主 URL 走不通时，试试同一条内容的其他入口形式
    for u2 in alt_urls(url):
        log(f"换个入口再试：{u2}", "↻")
        throttle(u2)
        cmd = ytdlp_base(u2, browser) + ["--skip-download", "--dump-single-json", u2]
        r = run(cmd)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout), None
            except json.JSONDecodeError:
                pass
    return None, last

def _trim_raw(raw):
    """缓存时丢掉 formats 和自动字幕的正文，只留后续真正会用到的字段。
    完整的 yt-dlp JSON 一条能有几百 KB，绝大部分是无用的清晰度枚举。"""
    r = dict(raw)
    r.pop("formats", None); r.pop("requested_formats", None)
    r.pop("thumbnails", None); r.pop("heatmap", None)
    if isinstance(r.get("automatic_captions"), dict):
        r["automatic_captions"] = {k: [] for k in r["automatic_captions"]}
    if isinstance(r.get("subtitles"), dict):
        r["subtitles"] = {k: [] for k in r["subtitles"]}
    return r

def meta_cache_path(lib, url):
    return lib / ".cache" / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json")

def fetch_meta_cached(url, browser, lib, refresh=False):
    """先查本地缓存再上网。重跑转写、补抽帧、改参数这些场景本来就不需要联网，
    每次都去请求一遍，只会白白撞上平台限速——B 站的 412 就是这么来的。"""
    cp = meta_cache_path(lib, url)
    if cp.exists() and not refresh:
        try:
            log("元数据用本地缓存（要强制刷新加 --refresh-meta）", "↷")
            return json.loads(cp.read_text(encoding="utf-8")), None
        except Exception:
            pass
    raw, err, used = fetch_meta_multi(url, browser)
    if raw is not None:
        cp.parent.mkdir(parents=True, exist_ok=True)
        raw["_vx_browser"] = used
        cp.write_text(json.dumps(_trim_raw(raw), ensure_ascii=False), encoding="utf-8")
        return raw, None
    if cp.exists():
        log("联网取元数据失败，改用本地缓存继续", "!")
        try:
            return json.loads(cp.read_text(encoding="utf-8")), None
        except Exception:
            pass
    return None, err

def safe(s, n=40):
    s = re.sub(r"[/\\:*?\"<>|\s]+", "_", str(s or "")).strip("_.")
    return (s[:n] or "unknown")

def build_meta(url, raw, platform, channel, engine_note=None):
    subs = list((raw.get("subtitles") or {}).keys())
    auto = list((raw.get("automatic_captions") or {}).keys())
    play = raw.get("view_count")
    # 抖音不公开播放量，yt-dlp 返回 0。0 和"没有"是两回事，统一记 null。
    if platform in ("douyin", "kuaishou") and not play:
        play = None
    return {
        "url": url,
        "platform": platform,
        "video_id": raw.get("id"),
        "title": raw.get("title"),
        "author": {
            "name": raw.get("uploader") or raw.get("channel"),
            "id": str(raw.get("uploader_id") or raw.get("channel_id") or "") or None,
            "url": raw.get("uploader_url") or raw.get("channel_url"),
        },
        "published_at": raw.get("upload_date"),
        "language": raw.get("language"),
        "duration_sec": raw.get("duration"),
        "stats": {
            "play": play,
            "like": raw.get("like_count"),
            "comment": raw.get("comment_count"),
            "share": raw.get("repost_count"),
        },
        "capture": {
            "channel": channel,
            "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "tool": ("m.weibo.cn" if raw.get("extractor") == "weibo-mobile-api" else "yt-dlp"),
            "evidence": "一手",
        },
        "text": {
            "source": None, "engine": None,
            "has_timestamps": None, "dual_check": False,
            "available_subs": subs, "available_auto_subs_count": len(auto),
        },
        "notes": engine_note or "",
    }

# ---------------------------------------------------------------- 下载

SUB_LANGS = "zh-Hans,zh-CN,zh,zh-TW,en,en-US,en-orig"

def _grab_subs(url, browser, outdir, auto, force_cookies=False):
    """人工轨和自动轨必须分开下。yt-dlp 两者的输出文件名完全一样（都是 .<lang>.srt），
    混在一个目录里就分不清哪条是人工的——而人工轨和自动轨的可信度差一档。
    实测：3Blue1Brown 有人工英文轨，混下时拿到的却是自动轨，
    文本里 sloppily 被听成 slapperly，且没有大小写和标点。"""
    sub = outdir / "media" / ("subs_auto" if auto else "subs_manual")
    sub.mkdir(parents=True, exist_ok=True)
    cmd = ytdlp_base(url, browser, force_cookies=force_cookies) + [
        "--skip-download",
        "--write-auto-subs" if auto else "--write-subs",
        "--sub-langs", SUB_LANGS, "--convert-subs", "srt",
        "--sleep-subtitles", "1",
        "-o", str(sub / "%(id)s.%(ext)s"), "--no-playlist", url,
    ]
    if auto:
        cmd.append("--no-write-subs")
    r = subprocess.run(cmd, capture_output=True, text=True)
    got = sorted(sub.glob("*.srt"))
    return got, (r.stderr or "")

def ensure_subs(url, outdir, browser, force_cookies=False):
    """确保字幕已尝试获取过。

    必须独立于视频下载：媒体文件已经在本地时，主流程会整段跳过 download()，
    字幕也就一起跳了——实测 YouTube 那条视频在本地、字幕目录却是空的，
    于是白跑了一遍 ASR 去转一个本来有官方字幕的视频。
    用一个标记文件记录"取过了"，避免每次重跑都去打平台接口。"""
    mark = outdir / "media" / ".subs_fetched"
    if mark.exists():
        return
    man, err = _grab_subs(url, browser, outdir, auto=False, force_cookies=force_cookies)
    if man:
        log(f"取到人工字幕轨 {len(man)} 个：{', '.join(f.name.split('.')[-2] for f in man)}")
    else:
        auto, err2 = _grab_subs(url, browser, outdir, auto=True, force_cookies=force_cookies)
        if auto:
            log(f"没有人工轨，取到自动字幕轨 {len(auto)} 个", "!")
        else:
            why = "被限流(429)" if "429" in (err + err2) else "该平台没有字幕轨"
            log(f"没拿到官方字幕（{why}），走 ASR")
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_text(datetime.now().isoformat(), encoding="utf-8")

def build_format_selector(max_res=1080):
    """Prefer direct HTTP, keep the known-height cap in every fallback.

    Unknown heights remain eligible. HLS is a fallback, not a reason to select 4K
    above a user-requested 1080p limit. Codec preference is applied separately.
    """
    if max_res < 1:
        raise ValueError("max_res must be positive")
    direct = "[protocol^=http][protocol!*=m3u8]"
    cap = f"[height<=?{max_res}]"
    return (f"bv*{direct}{cap}+ba{direct}/b{direct}{cap}"
            f"/bv*{cap}+ba/b{cap}")


def download(url, outdir, browser, want_subs=True, max_res=1080, force_cookies=False):
    """视频和字幕分开下。合在一起的话，YouTube 字幕接口一个 429
    会让 yt-dlp 整体返回非零，视频明明下好了也被判成失败。
    字幕拿不到只是降级到 ASR，不是致命错误。"""
    tpl = str(outdir / "media" / "%(id)s.%(ext)s")
    if want_subs:
        ensure_subs(url, outdir, browser, force_cookies=force_cookies)

    # 格式选择器优先普通 https，避开 m3u8/HLS。
    # 原来只写 bv*+ba/b，它只比码率，于是挑中 YouTube 那个 4164k 的
    # "m3u8 + Premium" 变体：153 个分片、大量短连接，在走代理的机器上
    # 每片都 SSL: UNEXPECTED_EOF_WHILE_READING，整条必挂。
    # 同一条视频的 https progressive/dash 变体是单连接下完，稳定得多。
    fmt = build_format_selector(max_res)

    def attempt(br, force):
        throttle(url)
        cmd = ytdlp_base(url, br, force_cookies=force) + [
            "-f", fmt,
            # 排序：协议第一（别再被分片流吸走），然后分辨率，
            # 然后编码——h264/aac 放在 vp9/av1/opus 前面。
            # 原因：--merge-output-format mp4 会把 VP9+Opus 塞进 mp4 容器，
            # 文件是有效的，但 QuickTime、Finder 预览、多数剪辑软件都打不开，
            # 实测 YouTube 一条会挑中 format 313（2160p VP9）就是这个下场。
            "-S", f"proto:https,res:{max_res},vcodec:h264,acodec:m4a,br",
            "--merge-output-format", "mp4",
            "-o", tpl, "--no-playlist", "--newline",
            url,
        ]
        return subprocess.run(cmd).returncode == 0

    if attempt(browser, force_cookies):
        return True

    # 下载这步是流式跑的，拿不到 stderr，没法按报错内容判断。
    # 但 YouTube 的两种拒绝方式是互补的——带 cookie 只给 video-only 轨，
    # 不带 cookie 撞机器人校验——失败之后换一次姿势再来是划算的：
    # 最多多花一次尝试，能救回其中一种。
    #
    # 关键是要判断第一次到底带没带 cookie，而不是看 force_cookies 这个入参：
    # 非 YouTube 站点 needs_cookies() 本来就返回 True，此时把 force_cookies
    # 从 False 翻成 True 前后完全一样，纯属白跑一次。
    if not browser or browser == "none":
        return False
    used_cookies = force_cookies or needs_cookies(url)
    if used_cookies:
        log("带 cookie 下载被拒，去掉 cookie 再试一次", "↻")
        return attempt("none", False)
    log("不带 cookie 下载被拒，带上 cookie 再试一次", "↻")
    return attempt(browser, True)

def download_direct(media_url, dest, referer=None, user_agent=None, allow_encrypted=False):
    """用已知直链下载视频文件。

    微博走的是移动端接口，元数据能拿到，但下载这步如果还交给 yt-dlp，
    还是会卡在同一个解析失败上。接口里本来就给了 mp4 直链，直接用它。"""
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(media_url, headers={
        "User-Agent": user_agent or MOBILE_UA,
        "Referer": referer or "",
    })
    try:
        with urllib.request.urlopen(req, timeout=120, context=TLS_CONTEXT) as r, open(dest, "wb") as f:
            if r.headers.get("X-encflag") == "1" and not allow_encrypted:
                dest.unlink(missing_ok=True)
                return False, "媒体响应声明加密（X-encflag=1），需要对应作品的解码信息"
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk); total += len(chunk)
        if total < 10000:
            dest.unlink(missing_ok=True)
            return False, f"下下来只有 {total} 字节，不像是视频"
        return True, None
    except Exception as e:
        dest.unlink(missing_ok=True)
        return False, f"{type(e).__name__}: {e}"

def find_media(outdir):
    md = outdir / "media"
    if not md.exists():
        return None
    vids = [f for f in md.iterdir()
            if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".flv")]
    return max(vids, key=lambda f: f.stat().st_size) if vids else None

def stash_media(outdir):
    """把已有媒体挪进 media/_replaced/，让主流程重新下载。

    为什么需要这个：--force 只忽略 .done 标记，主流程仍然是
    "find_media() 非空就跳过下载"，所以画质策略变了之后没有任何办法
    在原目录里换掉那个文件。实测场景：昨晚下的是 2160p VP9（173.8 MB，
    QuickTime 打不开），限高改好之后重跑，拿到的还是那个旧文件。

    挪而不删：删掉的东西找不回来，而这里删的是用户几分钟前下的几百 MB。
    留在 _replaced/ 里，由用户自己决定什么时候清。"""
    old = find_media(outdir)
    if old is None:
        return None
    dest_dir = outdir / "media" / "_replaced" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest_dir.mkdir(parents=True, exist_ok=False)
    # 保留所有旧媒体及完成标记，防止第二个旧文件被当成新下载结果。
    for item in list((outdir / "media").iterdir()):
        if item.is_file():
            item.rename(dest_dir / item.name)
    for name in (".done", ".downloaded"):
        marker = outdir / name
        if marker.exists(): marker.rename(dest_dir / name)
    return dest_dir / old.name



def _lang_of(f):
    """从 aircAruvnKk.zh-CN.srt 这样的文件名里取出语言码。"""
    parts = f.name.split(".")
    return parts[-2] if len(parts) >= 3 else "und"

def find_official_srt(outdir, prefer_lang=None):
    """返回 (字幕路径, kind, 语言码, 是否翻译轨)。找不到返回四个 None。

    人工轨永远优先于自动轨。人工轨内部则优先原声语言——翻译轨哪怕质量再好，
    也是加工过的表述，直引它就不是引原话了。实测 3Blue1Brown 一条英文视频
    挂着 en / zh-CN / zh-TW / zh 四条人工轨，默认选中文的话，
    正文会变成一份译文，而落盘规范里写着"一手可直引"。
    """
    if prefer_lang == "en":
        order = ("en-US", "en", "en-orig", "zh-Hans", "zh-CN", "zh", "zh-TW")
    else:
        order = ("zh-Hans", "zh-CN", "zh", "zh-TW", "en-US", "en", "en-orig")
    for kind in ("manual", "auto"):
        d = outdir / "media" / f"subs_{kind}"
        pool = sorted(d.glob("*.srt")) if d.exists() else []
        if not pool:
            continue
        for pref in order:
            for f in pool:
                if f".{pref}." in f.name:
                    lg = _lang_of(f)
                    is_tr = bool(prefer_lang) and not lg.lower().startswith(prefer_lang)
                    return f, kind, lg, is_tr
        f = pool[0]
        return f, kind, _lang_of(f), False
    old = sorted((outdir / "media").glob("*.srt"))
    if old:
        return old[0], "unknown", _lang_of(old[0]), False
    return None, None, None, None

def copy_extra_subs(outdir):
    """把其余人工轨也留一份到 subs/，命名 transcript.<语言>.srt。
    正文只认原声轨，但译文对阅读有用，没理由丢掉。"""
    kept = []
    d = outdir / "media" / "subs_manual"
    if not d.exists():
        return kept
    for f in sorted(d.glob("*.srt")):
        dst = outdir / "subs" / f"transcript.{_lang_of(f)}.srt"
        shutil.copy(f, dst)
        kept.append(dst.name)
    return kept

# ---------------------------------------------------------------- 音频与转写

def extract_wav(video, wav):
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(wav)])
    if not (wav.exists() and wav.stat().st_size > 1000):
        return False
    # 顺手量一下音量。全静音的音轨送进 ASR 只会浪费时间并产出噪音文本。
    r = run(["ffmpeg", "-i", str(wav), "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr or "")
    if m:
        mv = float(m.group(1))
        log(f"音轨平均音量 {mv:.1f} dB")
        if mv < -50:
            log("音轨接近静音，转写不会有结果。这条应该走 OCR。", "!")
    return True

def guess_lang(meta, forced=None):
    """判定语种。

    不能拿 available_subs 判断——YouTube 一条英文视频挂着 30 种语言的字幕轨，
    里面有 zh 只说明有中文翻译可选，跟原声是什么语言无关。
    实测就是这么把 3Blue1Brown 的英文视频送进 FunASR 的。"""
    if forced:
        return forced
    lang = (meta.get("language") or "")
    if lang:
        return "zh" if lang.lower().startswith("zh") else "en"
    title = meta.get("title") or ""
    if title:
        han = sum(1 for c in title if "\u4e00" <= c <= "\u9fff")
        if han / max(len(title), 1) > 0.15:
            return "zh"
    return "en" if meta.get("platform") in ("youtube", "instagram", "tiktok") else "zh"

def srt_ts(sec):
    ms = int(round(sec * 1000)); h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(segs, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, (st, en, tx) in enumerate(segs, 1):
            f.write(f"{i}\n{srt_ts(st)} --> {srt_ts(en)}\n{tx.strip()}\n\n")

SENT_END = "。！？!?；;…"

PUNC_SET = "，,。！？!?；;、…—“”\"'（）()《》【】:：. \t\n"

def _tokens_with_span(text):
    """把文本切成与 FunASR timestamp 一一对应的 token。
    实测规则：中文一字一个 token，连续英文字母算一个 token，连续数字算一个 token，
    标点不占 token。差值验证：'the' 3 个字符只占 1 项，差 2，与实测完全吻合。
    按字符对齐会让时间轴整体错位，越往后偏得越多。"""
    toks, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in PUNC_SET:
            toks.append((ch, False)); i += 1
        elif ch.isascii() and (ch.isalpha() or ch == "'"):
            j = i
            while j < n and text[j].isascii() and (text[j].isalpha() or text[j] == "'"):
                j += 1
            toks.append((text[i:j], True)); i = j
        elif ch.isdigit():
            j = i
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            toks.append((text[i:j], True)); i = j
        else:
            toks.append((ch, True)); i += 1
    return toks

def _segs_from_word_timestamps(text, ts):
    """按标点切句，每句的起止时间取自该句首尾 token 的时间戳。"""
    segs, buf, first, last, ti = [], [], None, None, 0
    for tok, counts in _tokens_with_span(text):
        if counts:
            if ti < len(ts):
                st, en = ts[ti][0] / 1000.0, ts[ti][1] / 1000.0
                if first is None:
                    first = st
                last = en
            ti += 1
        buf.append(tok)
        if tok in SENT_END and buf:
            t = "".join(buf).strip()
            if t:
                segs.append((first if first is not None else 0.0,
                             last if last is not None else 0.0, t))
            buf, first, last = [], None, None
    if buf:
        t = "".join(buf).strip()
        if t:
            segs.append((first if first is not None else 0.0,
                         last if last is not None else 0.0, t))
    return segs

def _split_long(segs, max_sec=12.0, max_chars=45):
    """句号切完还是有超长句（口播不断句很常见）。按逗号顿号再切一层，
    并按字数比例线性分配时间。字幕一条超过十几秒就没法用来定位了。"""
    out = []
    for st, en, tx in segs:
        if (en - st) <= max_sec and len(tx) <= max_chars:
            out.append((st, en, tx)); continue
        parts, buf = [], []
        for ch in tx:
            buf.append(ch)
            if ch in "，,、；;" and len("".join(buf)) >= max_chars // 3:
                parts.append("".join(buf)); buf = []
        if buf:
            parts.append("".join(buf))
        if len(parts) <= 1:
            out.append((st, en, tx)); continue
        total = sum(len(x) for x in parts) or 1
        cur = st
        for x in parts:
            span = (en - st) * len(x) / total
            out.append((cur, min(cur + span, en), x))
            cur += span
    return out

def asr_funasr(wav):
    from funasr import AutoModel
    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                      punc_model="ct-punc", disable_update=True, device="cpu")
    res = model.generate(input=str(wav), batch_size_s=300, sentence_timestamp=True)
    if not res:
        return []
    r0 = res[0]
    ts = r0.get("timestamp")
    text = r0.get("text") or ""

    # 路线一（主路径）：用字级时间戳按标点自己切句。
    # 为什么不优先用 sentence_info：实测 funasr 1.4.13 对一条 143 秒的视频
    # 只返回了 1 个 sentence_info 元素，等于整段一句话，时间戳存在但无法定位。
    # 字级 timestamp 是逐字对齐的，切出来的粒度可控。
    if ts and text:
        segs = _segs_from_word_timestamps(text, ts)
        if segs:
            segs = _split_long(segs)
            log(f"按标点切出 {len(segs)} 句（字级时间戳对齐）")
            return segs

    # 路线二：退回模型给的句级信息
    segs = []
    for s in (r0.get("sentence_info") or []):
        st = s.get("start"); en = s.get("end"); tx = s.get("text") or s.get("sentence")
        if tx is not None and st is not None:
            segs.append((st / 1000.0, (en or st) / 1000.0, tx))
    if segs:
        log(f"用模型给的 sentence_info，共 {len(segs)} 段")
        return segs

    # 路线三：真的什么都没有。整篇一条，但要明确警告，不能让它悄悄混进正式材料。
    if text:
        log("警告：这次转写拿不到任何时间戳，输出的是无时间轴全文。"
            "不要用于需要定位的场合。返回字段：" + ",".join(sorted(r0.keys())), "!")
        return [(0.0, 0.0, text)]
    return []

def asr_parakeet(wav):
    if os.name == "nt":
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        rows, _ = model.transcribe(str(wav), language="en", vad_filter=True)
        return [(float(s.start), float(s.end), s.text) for s in rows]
    from parakeet_mlx import from_pretrained
    model = from_pretrained("mlx-community/parakeet-tdt-0.6b-v2")
    res = model.transcribe(str(wav))
    segs = []
    for s in getattr(res, "sentences", []) or []:
        segs.append((float(s.start), float(s.end), s.text))
    if not segs and getattr(res, "text", None):
        segs = [(0.0, 0.0, res.text)]
    return segs

def speech_quality(segs, duration_sec):
    """判断这次转写有没有拿到真东西。

    第一版用"不同字符数 / 总字符数"当重复度，是错的：英文只有 26 个字母，
    几千字符的正常英文算出来是 0.00；正常中文口播也只有 0.28，全被误判。
    真正的"在识别背景音"特征不是用字种类少，而是少数字符高频重复——
    实测那条无口播视频里"嗯"一个字占了六成，而正常中文最高频的"的"约占 4%。
    所以改用最高频字符占比，跨语种都成立。"""
    from collections import Counter
    text = "".join(t for _, _, t in segs)
    core = "".join(c for c in text if c not in PUNC_SET)
    cps = len(core) / max(duration_sec or 1, 1)
    top = 0.0
    if core:
        top = Counter(core).most_common(1)[0][1] / len(core)
    problems = []
    if cps < 0.8:
        problems.append(f"语速仅 {cps:.2f} 字/秒（正常口播 3～6）")
    if len(core) >= 20 and top > 0.35:
        problems.append(f"单个字符占了 {top:.0%}，像是在识别背景音")
    return cps, top, problems

def transcribe(wav, lang, engine):
    if engine == "smartsub":
        die("--engine smartsub 是人工档：请把 media/ 里的视频拖进 SmartSub，"
            "转好后把 srt 放进 subs/ 再重跑本条（会自动跳过已完成步骤）")
    if engine == "auto":
        engine = "funasr" if lang == "zh" else "parakeet"
    log(f"转写引擎 {engine}（语种 {lang}），首次运行要下模型，请等")
    t0 = time.time()
    segs = asr_funasr(wav) if engine == "funasr" else asr_parakeet(wav)
    dur = time.time() - t0
    has_ts = any(e > 0 for _, e, _ in segs)
    log(f"转写完成 {len(segs)} 段，用时 {dur:.0f}s，时间戳：{'有' if has_ts else '无'}")
    return segs, ("faster-whisper" if os.name == "nt" and engine == "parakeet" else engine)

# ---------------------------------------------------------------- 抽帧

def extract_frames(video, fdir, interval=15, scene=0.30):
    fdir.mkdir(parents=True, exist_ok=True)
    tmp = fdir / "_tmp"; tmp.mkdir(exist_ok=True)
    times = {}
    # 第一趟：场景切换。用 metadata=print 把每帧的 pts_time 落到文件里，
    # 否则只有序号，对不回时间轴。
    meta_txt = tmp / "scenes.txt"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-vf", f"select='gt(scene,{scene})',metadata=print:file={meta_txt}",
         "-vsync", "vfr", str(tmp / "sc_%05d.jpg")])
    pts = []
    if meta_txt.exists():
        for line in meta_txt.read_text(errors="ignore").splitlines():
            m = re.search(r"pts_time:([\d.]+)", line)
            if m:
                pts.append(float(m.group(1)))
    for i, f in enumerate(sorted(tmp.glob("sc_*.jpg"))):
        t = pts[i] if i < len(pts) else i * interval
        times[round(t)] = ("scene", f)
    # 第二趟：固定间隔保底，防止长镜头静态画面整段漏掉
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-vf", f"fps=1/{interval}", "-vsync", "vfr", str(tmp / "iv_%05d.jpg")])
    for i, f in enumerate(sorted(tmp.glob("iv_*.jpg"))):
        t = round(i * interval)
        times.setdefault(t, ("interval", f))
    if not times:
        first = tmp / "first.jpg"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
             "-frames:v", "1", str(first)])
        if first.exists():
            times[0] = ("first", first)
    out = []
    for t in sorted(times):
        kind, src = times[t]
        dst = fdir / f"t{t:06d}_{kind}.jpg"
        shutil.move(str(src), str(dst)); out.append((t, dst))
    shutil.rmtree(tmp, ignore_errors=True)
    return out

# ---------------------------------------------------------------- 硬字幕 OCR

DEFAULT_OCR_ROI = "0,0,1,0.30"   # Vision 原点在左下角，这是底部 30% 的字幕条
HARDSUB_MIN_CHARS = 4            # 一帧的文字够这么长才算「有字幕」

def _ocr_too_thin(rows):
    """这批 OCR 结果是不是薄到没有意义。

    判据用「有没有任何一帧够得上 HARDSUB_MIN_CHARS」，
    而不是「总字数是不是 0」——实测一条快手视频，底部 ROI 把竖排贴纸大字
    从中间切断，每组只捞到最下面一个字，结果是「袋 / 啵 / 的 / 甜」四个孤立单字。
    总字数不是 0，但和 0 一样没用，只会污染互校报告。
    这个阈值和 has_hardsub() 用的是同一个，别改成两套。"""
    return max((len(t) for _, t in rows), default=0) < HARDSUB_MIN_CHARS

def _ocr_pass(frames, roi):
    """跑一遍 OCR，返回 [(秒, 文字)]。失败原因往上抛，不吞。"""
    out = []
    B = 40
    for i in range(0, len(frames), B):
        batch = frames[i:i + B]
        r = run(([sys.executable, "-X", "utf8", "-B"] if os.name == "nt" else []) + [str(VISIONOCR), "--roi", roi] + [str(p) for _, p in batch])
        if r.returncode != 0:
            err = (r.stderr or "").strip().splitlines()
            log(f"Vision OCR 退出码 {r.returncode}" + (f"：{err[-1][:120]}" if err else ""), "!")
            return None
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            log("Vision OCR 输出不是合法 JSON，这一批跳过", "!")
            return None
        if (not isinstance(data, list) or any(not isinstance(d, dict) or not isinstance(d.get("file"), str)
                or not isinstance(d.get("lines"), list) or any(not isinstance(line, dict)
                or not isinstance(line.get("text"), str) for line in d["lines"]) for d in data)):
            log("Vision OCR 返回结构无效，未完成识别", "!")
            return None
        by_file = {d["file"]: d for d in data}
        if any(str(p) not in by_file for _, p in batch):
            log("Vision OCR 缺少部分帧的结果，未完成识别", "!")
            return None
        for t, p in batch:
            d = by_file.get(str(p)) or {}
            txt = " ".join(l["text"] for l in (d.get("lines") or []))
            out.append((t, txt.strip()))
    return out


def ocr_frames(frames, roi=None):
    """对帧跑 Vision OCR。注意 ROI 模式下 Vision 返回的坐标是相对 ROI 的，
    不是相对整图——这里只用文字不用坐标，所以不做反向映射。

    默认只扫底部 30%（字幕条），扫全图会把画面里的路牌、商品包装、
    弹幕都当成字幕，噪声很大。但中文短视频的贴纸式大字常打在画面中部，
    不在字幕条里——实测一条快手视频，「菜包」两个大字在从底部往上
    31%～41% 处，刚好擦着默认 ROI 出去，于是 OCR 返回 0 字。

    所以：默认 ROI 一无所获时，**自动用全图重扫一次**，并说明扫的是全图。
    宁可多噪声也不要静默返回空——「没有字」和「没扫到字」必须区分得开。"""
    if not VISIONOCR.exists():
        log(f"没有 Vision OCR 程序（{VISIONOCR}），跳过 OCR。", "!")
        log("要用硬字幕互校，先跑 scripts/04_build_visionocr.sh 编译它。", "!")
        return None
    explicit = roi is not None
    roi = roi or DEFAULT_OCR_ROI
    out = _ocr_pass(frames, roi)
    if out is None: return None
    if not explicit and _ocr_too_thin(out):
        best = max((len(t) for _, t in out), default=0)
        log(f"字幕条（ROI {roi}）里最长只有 {best} 个字，改扫全图重试一次", "↻")
        wide = _ocr_pass(frames, "0,0,1,1")
        if wide is None: return None
        if sum(len(t) for _, t in wide) > sum(len(t) for _, t in out):
            log("全图扫到更多文字——字不在字幕条位置（竖排贴纸大字常见）", "!")
            log("全图会混入画面里本来就有的字（路牌、包装、水印），需人工核对", "!")
            return wide
        log("全图也未识别出更多有效文字；不能据此断定画面没有文字", "!")
    return out

def has_hardsub(ocr_rows, min_ratio=0.5):
    if not ocr_rows:
        return False
    hit = sum(1 for _, t in ocr_rows if len(t) >= HARDSUB_MIN_CHARS)
    return hit / max(len(ocr_rows), 1) >= min_ratio

def merge_ocr(ocr_rows):
    """连续相同文字合并成一段，得到近似的硬字幕时间轴。"""
    segs, cur, start, last = [], None, None, None
    for t, txt in ocr_rows:
        if txt != cur:
            if cur:
                segs.append((start, t, cur))
            cur, start = (txt or None), t
        last = t
    if cur:
        segs.append((start, last, cur))
    return [s for s in segs if s[2]]

def dual_report(asr_segs, ocr_segs, path):
    import difflib
    a = re.sub(r"\s+", "", "".join(s[2] for s in asr_segs))
    o = re.sub(r"\s+", "", "".join(s[2] for s in ocr_segs))
    ratio = difflib.SequenceMatcher(None, a, o).ratio() if a and o else 0.0
    lines = [
        "# 双路互校报告", "",
        f"ASR 字符数：{len(a)}", f"OCR 字符数：{len(o)}",
        f"整体相似度：{ratio:.3f}", "",
        "相似度低于 0.6 时，多半是硬字幕只覆盖了部分口播，或 OCR 漏读。",
        "型号、数字、专有名词以 OCR 为准（博主自己打的字）；",
        "完整语流以 ASR 为准（覆盖画面上没写的内容）。冲突处人工判。", "",
        "## OCR 逐段（时间 秒）", "",
    ]
    for st, en, tx in ocr_segs:
        lines.append(f"[{st:>5}–{en:>5}] {tx}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return ratio

# ---------------------------------------------------------------- 总表

def append_index(lib, meta, outdir):
    """按 slug 去重写入。--force 重跑时如果只是追加，同一条会在总表里出现多次，
    而总表是要拿去做批量分析的，重复行会污染统计。"""
    idx = lib / "index.csv"
    row = {
        "slug": outdir.name, "platform": meta["platform"], "video_id": meta["video_id"],
        "title": meta["title"], "author": (meta["author"] or {}).get("name"),
        "published_at": meta["published_at"], "duration_sec": meta["duration_sec"],
        "play": (meta["stats"] or {}).get("play"), "like": (meta["stats"] or {}).get("like"),
        "text_source": (meta["text"] or {}).get("source"),
        "primary": (meta["text"] or {}).get("primary") or (meta["text"] or {}).get("source"),
        "sub_kind": (meta["text"] or {}).get("sub_kind"),
        "sub_lang": (meta["text"] or {}).get("sub_lang"),
        "translated": (meta["text"] or {}).get("translated"),
        "engine": (meta["text"] or {}).get("engine"),
        "quality": (meta["text"] or {}).get("quality"),
        "chars_per_sec": (meta["text"] or {}).get("chars_per_sec"),
        "dual_check": (meta["text"] or {}).get("dual_check"),
        "evidence": (meta["capture"] or {}).get("evidence"),
        "captured_at": (meta["capture"] or {}).get("at"), "url": meta["url"],
    }
    rows = []
    if idx.exists():
        with open(idx, newline="", encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r.get("slug") != row["slug"]]
    rows.append(row)
    fields = list(row)
    with open(idx, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

# ------------------------------------------------- 平台专用解析（yt-dlp 补不上的）

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

def http_get(url, referer=None, timeout=25, mobile=False, xhr=False):
    import urllib.request
    h = {"User-Agent": MOBILE_UA if mobile else UA,
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if xhr:
        h["X-Requested-With"] = "XMLHttpRequest"
        h["MWeibo-Pwa"] = "1"
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

def enrich_xhs(meta, url):
    """小红书：yt-dlp 给得出标题，给不出作者和发布日期。

    页面里有 __INITIAL_STATE__，公开笔记不登录也能拿到。补不上就保持 null，
    不编造——目录名里缺一段总好过写个假作者。"""
    try:
        raw = http_get(url, referer="https://www.xiaohongshu.com/")
    except Exception as e:
        log(f"补小红书元数据失败（{type(e).__name__}），作者和日期留空", "!")
        return
    m = re.search(r'"nickname"\s*:\s*"([^"]{1,40})"', raw)
    if m and not (meta["author"] or {}).get("name"):
        meta["author"]["name"] = m.group(1)
    m = re.search(r'"userId"\s*:\s*"([0-9a-f]{8,})"', raw)
    if m and not (meta["author"] or {}).get("id"):
        meta["author"]["id"] = m.group(1)
    m = re.search(r'"time"\s*:\s*(\d{13})', raw)
    if m and not meta.get("published_at"):
        meta["published_at"] = datetime.fromtimestamp(int(m.group(1)) / 1000).strftime("%Y%m%d")
    for k, f in (("likedCount", "like"), ("commentCount", "comment"), ("shareCount", "share")):
        mm = re.search(r'"%s"\s*:\s*"?(\d+)"?' % k, raw)
        if mm and meta["stats"].get(f) is None:
            meta["stats"][f] = int(mm.group(1))
    got = [x for x in ((meta["author"] or {}).get("name"), meta.get("published_at")) if x]
    if got:
        log(f"从页面补到小红书元数据：{' / '.join(got)}")

def fetch_weibo_meta(url):
    """微博：yt-dlp 的 extractor 和微博当前页面对不上（KeyError / JSONDecodeError），
    而且已经是最新版，属于上游问题。

    绕过去的办法是走移动端接口 m.weibo.cn/statuses/show?id=<mid>，
    它返回结构稳定的 JSON，公开微博不需要登录。
    这里只解决元数据；视频文件仍要由 yt-dlp 或嗅探拿。"""
    m = re.search(r"[?&]mid=(\d+)", url) or re.search(r"weibo\.com/\d+/(\w+)", url) \
        or re.search(r"(?:fid|show/)[=/]?1034:(\d+)", url)
    if not m:
        return None, "从链接里认不出微博的 mid"
    mid = m.group(1)
    # m.weibo.cn/statuses/show 这个端点现在对未登录返回 HTML 而不是 JSON。
    # 改走 m.weibo.cn/detail/<mid>，它是普通网页，里面内嵌 $render_data。
    d = {}
    try:
        html = http_get(f"https://m.weibo.cn/detail/{mid}",
                        referer="https://m.weibo.cn/",
                        mobile=True)
        m2 = re.search(r"\$render_data\s*=\s*(\[.*?\])\s*\|\|", html, re.S)
        if m2:
            arr = json.loads(m2.group(1))
            d = (arr[0] if arr else {}).get("status") or {}
    except Exception as e:
        return None, f"detail 页取不到（{type(e).__name__}: {e}）"
    if not d:
        try:
            j = json.loads(http_get(f"https://m.weibo.cn/statuses/show?id={mid}",
                                    referer="https://m.weibo.cn/", mobile=True, xhr=True))
            d = (j or {}).get("data") or {}
        except Exception:
            pass
    if not d:
        return None, "两个移动端入口都拿不到，这条微博可能需要登录或已删除"
    pi = d.get("page_info") or {}
    mi = pi.get("media_info") or {}
    urls = pi.get("urls") or {}
    play = (mi.get("stream_url_hd") or mi.get("stream_url")
            or urls.get("mp4_hd_mp4") or urls.get("mp4_ld_mp4"))
    created = d.get("created_at") or ""
    published = None
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S"):
        try:
            published = datetime.strptime(created, fmt).strftime("%Y%m%d"); break
        except Exception:
            pass
    text = re.sub(r"<[^>]+>", "", d.get("text") or "").strip()
    return {
        "id": str(d.get("id") or mid),
        "title": (pi.get("title") or text or "")[:120] or None,
        "uploader": ((d.get("user") or {}).get("screen_name")),
        "uploader_id": str((d.get("user") or {}).get("id") or "") or None,
        "upload_date": published,
        "duration": mi.get("duration") or pi.get("media_info", {}).get("duration"),
        "view_count": (mi.get("online_users_number") or None),
        "like_count": d.get("attitudes_count"),
        "comment_count": d.get("comments_count"),
        "repost_count": d.get("reposts_count"),
        "language": "zh",
        "_vx_play_url": play,
        "extractor": "weibo-mobile-api",
    }, None

# ---------------------------------------------------------------- 公众号文章

def fetch_wx_article(url, outdir):
    """微信公众号文章：正文本来就是文字，不涉及下载和转写。

    表一里这一行写着"网页正文直接是文字"，但先前的实现完全没有这条路径——
    喂进来的 mp.weixin 链接会被当成视频交给 yt-dlp，然后失败。
    页面是服务端渲染的，正文在 #js_content 里，公开文章不需要登录。
    """
    import html as _html
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode("utf-8", "ignore")

    def pick(*pats):
        """逐个模式试，跳过空值和明显匹配歪了的结果。

        公众号页面里 var author = "" 通常就是空的，第一版直接返回了空串后面
        贪进去的一截 JS，作者字段变成了 '"; var author_id ='，目录名跟着报废。
        真正的公众号名在 nickname 或 #js_name 里。"""
        for pat in pats:
            m = re.search(pat, raw, re.S)
            if not m:
                continue
            v = _html.unescape(m.group(1)).strip()
            if not v or len(v) > 60:
                continue
            if any(bad in v for bad in ("var ", ";", "=", "{", "}", "<", ">")):
                continue
            return v
        return None

    title = pick(r'var\s+msg_title\s*=\s*[\'"](.+?)[\'"]',
                 r'<h1[^>]*rich_media_title[^>]*>(.*?)</h1>',
                 r'<meta[^>]+property="og:title"[^>]+content="(.*?)"')
    # nickname 才是公众号名；author 那个字段多数文章是空的
    author = pick(r'var\s+nickname\s*=\s*[\'"](.+?)[\'"]',
                  r'id="js_name"[^>]*>\s*([^<]{1,40}?)\s*<',
                  r'var\s+author\s*=\s*[\'"]([^\'"]{1,40})[\'"]',
                  r'<meta[^>]+name="author"[^>]+content="([^"]{1,40})"')
    ts = pick(r'var\s+ct\s*=\s*"(\d+)"', r'var\s+createTime\s*=\s*[\'"](.+?)[\'"]')
    published = None
    if ts and ts.isdigit():
        published = datetime.fromtimestamp(int(ts)).strftime("%Y%m%d")
    sid = pick(r'/s\?__biz=[^"&]+&(?:amp;)?mid=(\d+)') or (url.rstrip("/").split("/")[-1][:24])

    m = re.search(r'<div[^>]+id="js_content".*?>(.*?)</div>\s*(?:<script|</div>)', raw, re.S)
    body_html = m.group(1) if m else ""
    body = re.sub(r"<br\s*/?>", "\n", body_html)
    body = re.sub(r"</p>|</section>|</h\d>", "\n", body)
    body = re.sub(r"<[^>]+>", "", body)
    body = _html.unescape(body)
    body = re.sub(r"[ \t\xa0]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    if not body:
        return None, "正文为空——文章可能已删除、需要登录，或页面结构变了"

    (outdir / "subs").mkdir(parents=True, exist_ok=True)
    out = outdir / "subs" / "article.md"
    out.write_text(f"# {title or '(无标题)'}\n\n{body}\n", encoding="utf-8")
    return {"title": title, "author": author, "published": published,
            "id": sid, "chars": len(body), "path": out}, None

def process_wx_article(url, args, lib):
    log("公众号文章：正文直接是文字，不下载不转写")
    tmp = lib / "_wx_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    info, err = fetch_wx_article(url, tmp)
    if info is None:
        log(f"抓取失败：{err}", "✗")
        shutil.rmtree(tmp, ignore_errors=True)
        return "failed"
    slug = f"wxarticle_{safe(info['author'])}_{info['published'] or 'nodate'}_{safe(info['id'], 30)}"
    outdir = lib / slug
    for sub in ("subs", "notes"):
        (outdir / sub).mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp / "subs" / "article.md"), str(outdir / "subs" / "article.md"))
    shutil.rmtree(tmp, ignore_errors=True)
    meta = {
        "url": url, "platform": "wxarticle", "video_id": info["id"],
        "title": info["title"], "language": "zh",
        "author": {"name": info["author"], "id": None, "url": None},
        "published_at": info["published"], "duration_sec": None,
        "stats": {"play": None, "like": None, "comment": None, "share": None},
        "capture": {"channel": "网页解析", "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                    "tool": "vx", "evidence": "一手"},
        "text": {"source": "webpage", "engine": None, "has_timestamps": False,
                 "dual_check": False, "quality": "ok", "chars": info["chars"]},
        "notes": "公众号文章正文，无时间戳（文字稿本来就没有时间轴）。",
    }
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    append_index(lib, meta, outdir)
    (outdir / ".done").write_text(datetime.now().isoformat(), encoding="utf-8")
    log(f"正文 {info['chars']} 字 → {outdir}", "✓")
    return "ok"

def retire_outputs(outdir, names):
    """从当前结果撤下过期派生文件，保留可恢复副本。"""
    existing = [outdir / name for name in names if (outdir / name).is_file()]
    if not existing: return
    backup = outdir / "notes" / "_superseded" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup.mkdir(parents=True, exist_ok=False)
    for path in existing:
        path.rename(backup / path.name)
    log(f"旧派生结果已备份到 {backup.relative_to(outdir)}", "↻")


def ocr_status(rows):
    if rows is None: return "failed"
    if not rows or not any(text for _, text in rows): return "empty"
    return "too_thin" if _ocr_too_thin(rows) else "recognized"


def finish_visual_pipeline(meta, outdir, video, args, lib, reason):
    """无音轨/无转写结果也保留可审阅画面，不伪造口播文本。"""
    log(reason + "，转入画面/OCR 处理", "!")
    if args.force and not args.no_frames:
        # 帧是派生数据，重抽几乎不花钱。不清掉的话 --interval 在重跑时
        # 完全不生效——实测同一条视频前后两次 --dual，一次 9 帧一次 1 帧，
        # OCR 结果天差地别，而输出里没有任何迹象表明帧没重抽。
        old_frames = sorted((outdir / "frames").glob("t*.jpg"))
        if old_frames:
            log(f"--force：清掉旧的 {len(old_frames)} 帧重抽（间隔 {args.interval}s）", "↻")
            for f in old_frames:
                f.unlink()
    frames = sorted((outdir / "frames").glob("t*.jpg"))
    if not frames and not args.no_frames:
        frames = [p for _, p in extract_frames(video, outdir / "frames", interval=args.interval)]
    pairs = [(int(re.search(r"t(\d+)_", p.name).group(1)), p) for p in frames]
    rows = ocr_frames(pairs, getattr(args, "ocr_roi", None)) if pairs else None
    status = ocr_status(rows) if pairs else "not_run"
    segs = merge_ocr(rows) if status == "recognized" else []
    meta["text"]["ocr_status"] = status
    if not segs:
        retire_outputs(outdir, ["subs/transcript_ocr.srt", "subs/transcript.srt"])
        log(f"OCR 状态：{status}，未产出有效字幕", "!")
    meta["text"].update(source="ocr" if segs else "none", engine="macOS Vision" if segs else None,
                        primary="ocr" if segs else None, quality="unreviewed" if segs else "unavailable",
                        has_timestamps=bool(segs), ocr_chars=sum(len(t) for _, _, t in segs))
    if segs:
        write_srt(segs, outdir / "subs" / "transcript_ocr.srt")
        write_srt(segs, outdir / "subs" / "transcript.srt")
    meta["capture"]["evidence"] = "待核对"
    meta["notes"] = (meta.get("notes", "") + " " + reason +
        "。OCR 来自抽样画面，时间戳是采样位置，不能代表逐字字幕或完整内容；需对照视频核对。").strip()
    (outdir / "notes" / "content_status.md").write_text(meta["notes"], encoding="utf-8")
    (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    append_index(lib, meta, outdir)
    (outdir / ".done").write_text(datetime.now().isoformat(), encoding="utf-8")
    log(f"媒体归档完成，OCR {len(segs)} 段、画面 {len(frames)} 张 → {outdir}", "✓")
    return "ok"


def finish_pipeline(url, meta, outdir, video, args, lib):
    """有了媒体文件之后的通用流程：字幕/转写 → 抽帧 → 硬字幕 → 落盘。

    抽出来是为了让三种入口共用：网络链接、本地文件、抓流拿到的直链。
    快手和视频号最终都落到"本地文件"这一路，如果只有 process() 里有这段，
    那两条链路就永远拼不完整。"""
    log(f"媒体 {video.name}（{video.stat().st_size/1048576:.1f} MB）")
    if getattr(args, "download_only", False):
        check = run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:v:0",
                     "-frames:v", "1", "-f", "null", "-"])
        if check.returncode:
            log("视频解码检查失败，未标记下载完成", "✗")
            return "failed"
        if not meta.get("duration_sec"):
            meta["duration_sec"], _ = probe_local(video)
        meta["text"].update(source="none", quality="not_requested", verification="not_requested")
        meta["notes"] = (meta.get("notes", "") + " 仅下载，未请求转写或 OCR。").strip()
        (outdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        append_index(lib, meta, outdir)
        (outdir / ".downloaded").write_text(datetime.now().isoformat(), encoding="utf-8")
        log(f"下载完成 → {outdir}", "✓")
        return "ok"


    if not meta.get("duration_sec"):
        meta["duration_sec"], _ = probe_local(video)

    # 文本：官方字幕优先
    final_srt = outdir / "subs" / "transcript.srt"
    if not final_srt.exists():
        prefer = guess_lang(meta, args.lang)
        off, sub_kind, sub_lang, is_tr = find_official_srt(outdir, prefer)
        if off and not args.force_asr:
            shutil.copy(off, final_srt)
            extra = copy_extra_subs(outdir)
            meta["text"].update(source="official", sub_kind=sub_kind,
                                sub_lang=sub_lang, translated=is_tr,
                                extra_subs=extra, engine=None, has_timestamps=True)
            if len(extra) > 1:
                log(f"另存 {len(extra)} 条字幕轨到 subs/：{', '.join(extra)}")
            if sub_kind == "auto":
                # 自动轨仍是平台产出，算一手，但错字率明显高于人工轨，要标出来
                meta["notes"] = (meta["notes"] +
                    " 用的是平台自动生成字幕，非人工轨，专有名词可能有听写错误。").strip()
                log(f"用自动字幕轨 {off.name}（无人工轨），不跑 ASR", "!")
            else:
                log(f"用人工字幕轨 {off.name}，不跑 ASR", "✓")
        else:
            audio_probe = run(["ffprobe", "-v", "error", "-select_streams", "a",
                               "-show_entries", "stream=index", "-of", "csv=p=0", str(video)])
            if audio_probe.returncode == 0 and not audio_probe.stdout.strip():
                return finish_visual_pipeline(meta, outdir, video, args, lib, "下载的媒体没有音轨（原内容可能静音，或平台未提供音轨）")
            wav = outdir / "media" / "audio.wav"
            if not wav.exists() and not extract_wav(video, wav):
                log("提取音轨失败", "✗")
                return "failed"
            lang = guess_lang(meta, args.lang)
            segs, eng = transcribe(wav, lang, args.engine)
            if not segs:
                return finish_visual_pipeline(meta, outdir, video, args, lib, "ASR 没有产出文本")
            cps, uniq, problems = speech_quality(segs, meta.get("duration_sec"))
            write_srt(segs, final_srt)
            has_ts = any(e > 0 for _, e, _ in segs)
            meta["text"].update(source="asr", engine=eng, has_timestamps=has_ts)
            if problems:
                warn = "；".join(problems)
                log(f"转写质量存疑：{warn}", "!")
                log("这条多半没有口播解说（纯 BGM 或纯字幕），文本不可当一手材料用。"
                    "建议改走硬字幕 OCR：加 --dual", "!")
                meta["text"]["quality"] = "suspect"
                meta["capture"]["evidence"] = "存疑"
                meta["notes"] = (meta["notes"] + f" ASR 质量存疑：{warn}。").strip()
            else:
                meta["text"]["quality"] = "ok"
            meta["text"]["chars_per_sec"] = round(cps, 2)
    else:
        # 只是跳过转写，不代表 meta 不用填。上一版这里什么都没写，
        # 结果 index.csv 里 81 条字幕的抖音视频 text_source 是空的。
        n = len([l for l in final_srt.read_text(encoding="utf-8").splitlines() if "-->" in l])
        off, sub_kind, sub_lang, is_tr = find_official_srt(
            outdir, guess_lang(meta, args.lang))
        src = "official" if (off and not args.force_asr) else "asr"
        meta["text"]["source"] = src
        meta["text"]["has_timestamps"] = True
        if src == "official":
            meta["text"].update(sub_kind=sub_kind, sub_lang=sub_lang, translated=is_tr)
        else:
            # 这里必须直接赋值。用 setdefault 的话，键已经存在且为 None，
            # 不会被覆盖——上一轮抖音那条 engine 就是这么变空的。
            meta["text"]["engine"] = ("funasr"
                if guess_lang(meta, args.lang) == "zh" else ("faster-whisper" if os.name == "nt" else "parakeet"))
        # 跳过转写不等于跳过质检。已有字幕同样要过闸门，
        # 否则一份垃圾字幕只要落了盘就再也不会被复查。
        segs_existing = []
        for blk in final_srt.read_text(encoding="utf-8").split("\n\n"):
            ls = [x for x in blk.strip().splitlines() if x]
            if len(ls) >= 3:
                segs_existing.append((0.0, 0.0, " ".join(ls[2:])))
        if segs_existing:
            cps, uniq, problems = speech_quality(segs_existing, meta.get("duration_sec"))
            meta["text"]["chars_per_sec"] = round(cps, 2)
            meta["text"]["quality"] = "suspect" if problems else "ok"
            if problems:
                log("已有字幕质量存疑：" + "；".join(problems), "!")
                meta["capture"]["evidence"] = "存疑"
        log(f"字幕已存在（{n} 条），跳过转写", "↷")

    # 抽帧
    if args.force and not args.no_frames:
        # 帧是派生数据，重抽几乎不花钱。不清掉的话 --interval 在重跑时
        # 完全不生效——实测同一条视频前后两次 --dual，一次 9 帧一次 1 帧，
        # OCR 结果天差地别，而输出里没有任何迹象表明帧没重抽。
        old_frames = sorted((outdir / "frames").glob("t*.jpg"))
        if old_frames:
            log(f"--force：清掉旧的 {len(old_frames)} 帧重抽（间隔 {args.interval}s）", "↻")
            for f in old_frames:
                f.unlink()
    frames = sorted((outdir / "frames").glob("t*.jpg"))
    if not frames and not args.no_frames:
        log("抽帧中（场景切换 + 固定间隔保底）…")
        fr = extract_frames(video, outdir / "frames", interval=args.interval)
        frames = [p for _, p in fr]
        log(f"抽出 {len(frames)} 帧")
    frame_pairs = [(int(re.search(r"t(\d+)_", p.name).group(1)), p) for p in frames]

    # 只有有效的两路文本才做互校；识别失败、空结果和零散文字分别记录。
    if args.dual:
        rows = ocr_frames(frame_pairs, getattr(args, "ocr_roi", None)) if frame_pairs else None
        status = ocr_status(rows) if frame_pairs else "not_run"
        meta["text"]["ocr_status"] = status
        meta["text"]["ocr_chars"] = sum(len(t) for _, t in (rows or []))
        meta["text"]["dual_check"] = False
        if status != "recognized":
            retire_outputs(outdir, ["subs/transcript_ocr.srt", "notes/dual_check.md"])
            log(f"OCR 状态：{status}，未完成双路互校，未产出硬字幕", "!")
            (outdir / "notes" / "dual_check.md").write_text(
                f"# 双路互校未完成\n\nOCR 状态：{status}。不可把未识别解释为画面没有文字。\n", encoding="utf-8")
            if meta["text"].get("primary") == "ocr": meta["text"].pop("primary", None)
        else:
            ocr_segs = merge_ocr(rows)
            asr_segs = []
            for blk in final_srt.read_text(encoding="utf-8").split("\n\n"):
                ls = blk.strip().splitlines()
                if len(ls) >= 3: asr_segs.append((0, 0, " ".join(ls[2:])))
            if asr_segs:
                ratio = dual_report(asr_segs, ocr_segs, outdir / "notes" / "dual_check.md")
                meta["text"]["dual_check"] = True
                log(f"互校完成，相似度 {ratio:.3f}，报告在 notes/dual_check.md", "✓")
            else:
                retire_outputs(outdir, ["notes/dual_check.md"])
                log("没有可比较的字幕/转写，仅保存 OCR；未完成互校", "!")
            write_srt(ocr_segs, outdir / "subs" / "transcript_ocr.srt")
            if meta["text"].get("quality") == "suspect":
                meta["text"]["primary"] = "ocr"
                meta["capture"]["evidence"] = "待核对"
                meta["notes"] = (meta["notes"] + " 抽样 OCR 作为备选文本，需人工核对。").strip()
    elif frame_pairs:
        probe = frame_pairs[:: max(1, len(frame_pairs) // 8)][:8]
        rows = ocr_frames(probe, getattr(args, "ocr_roi", None))
        if has_hardsub(rows):
            log("检测到画面里有硬字幕。要进正式材料的话，加 --dual 跑 OCR＋ASR 互校", "!")
            meta["notes"] = (meta["notes"] + " 检测到硬字幕，未做互校。").strip()

    if meta["text"].get("source") in ("asr", "ocr"):
        meta["text"]["verification"] = "unreviewed"
        if meta["capture"].get("evidence") == "一手":
            meta["capture"]["evidence"] = "原始媒体一手；机器文本待核对"
    (outdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    append_index(lib, meta, outdir)
    (outdir / ".done").write_text(datetime.now().isoformat(), encoding="utf-8")
    log(f"完成 → {outdir}", "✓")
    return "ok"



def probe_local(path):
    """探本地文件：时长、有没有内嵌的软字幕轨。"""
    r = run(["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", str(path)])
    try:
        j = json.loads(r.stdout)
    except Exception:
        return None, []
    dur = None
    try:
        dur = float((j.get("format") or {}).get("duration"))
    except Exception:
        pass
    subs = [st for st in (j.get("streams") or []) if st.get("codec_type") == "subtitle"]
    return dur, subs

def extract_embedded_subs(path, outdir, subs):
    """把内嵌软字幕轨导成 srt。有软字幕就不必跑 ASR——
    这是本地文件相对网络视频唯一的额外机会，别浪费。"""
    got = []
    for i, st in enumerate(subs):
        lang = ((st.get("tags") or {}).get("language") or f"und{i}")
        dst = outdir / "media" / "subs_manual" / f"local.{lang}.srt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path),
                 "-map", f"0:s:{i}", str(dst)])
        if dst.exists() and dst.stat().st_size > 50:
            got.append(dst.name)
        else:
            dst.unlink(missing_ok=True)
    return got

def process_local(path, args, lib):
    """本地文件档。

    快手和视频号最终都走这一路：抓流工具把文件下到本地，再交给 vx。
    也用于录屏、别处下来的素材、以及任何工具拿不到但你手上已有的视频。"""
    src = Path(path).expanduser().resolve()
    if not src.exists():
        log(f"文件不存在：{src}", "✗")
        return "failed"
    print(f"\n\033[1m▶ {src.name}\033[0m")

    dur, subs = probe_local(src)
    stat = src.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime)
    vid = hashlib.sha1(f"{src.name}{stat.st_size}".encode()).hexdigest()[:12]

    platform = args.as_platform or "local"
    parts = [platform]
    if args.author:
        parts.append(safe(args.author))
    if args.published:
        parts.append(args.published)
    elif not args.media_url and platform == "local":
        # 文件 mtime 只对真·本地文件有意义。给了 --as <平台> 的，
        # mtime 是「我什么时候下的」，不是「它什么时候发的」，
        # 拿它冒充发布日期既失真，又让同一条视频从不同入口进来时
        # 落到不同目录：抓流进的是 kuaishou_3xm4y…，
        # 本地文件重跑进的是 kuaishou_20260907_3xm4y…，
        # 于是「重新处理已有条目」永远做不到。
        parts.append(mtime.strftime("%Y%m%d"))
    parts.append(safe(src.stem, 30) or vid)
    outdir = lib / "_".join(parts)
    for sub in ("media", "subs", "frames", "notes"):
        (outdir / sub).mkdir(parents=True, exist_ok=True)

    if (outdir / ".done").exists() and not args.force and not getattr(args, "redownload", False):
        log(f"已完成过，跳过：{outdir.name}（要重跑加 --force）", "↷")
        return "skipped"

    dst = outdir / "media" / src.name
    if getattr(args, "redownload", False) and src != dst.resolve():
        moved = stash_media(outdir)
        if moved: log(f"旧媒体已备份到 {moved.relative_to(outdir)}", "↻")
    if not dst.exists():
        # 复制而不是移动：原文件是你的，不动它
        log(f"复制进媒体库（{stat.st_size/1048576:.1f} MB）…")
        shutil.copy2(src, dst)

    if subs and not getattr(args, "download_only", False):
        got = extract_embedded_subs(src, outdir, subs)
        if got:
            log(f"文件里有内嵌字幕轨，已导出 {len(got)} 条：{', '.join(got)}")

    meta = {
        "url": args.source_url or args.media_url or f"file://{src}",
        "platform": platform,
        "video_id": vid,
        "title": args.title or src.stem,
        "language": args.lang,
        "author": {"name": args.author, "id": getattr(args, "author_id", None),
                   "url": None},
        "published_at": args.published,
        "duration_sec": dur,
        "stats": {"play": None, "like": None, "comment": None, "share": None},
        "capture": {
            "channel": args.channel or "本地文件",
            "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "tool": args.tool or "手工",
            "evidence": "一手",
        },
        "text": {"source": None, "engine": None, "has_timestamps": None,
                 "dual_check": False, "available_subs": [], "available_auto_subs_count": 0},
        "notes": args.note or "",
    }
    if platform in ("kuaishou", "wxchannel") and not args.published:
        missing = "发布时间/播放量" if meta["author"]["id"] else "发布时间/播放量/作者ID"
        meta["notes"] = (meta["notes"] +
            f" 元数据（{missing}）工具给不了，需人工补录并附带系统时间的截图。").strip()
    log(f"目录 {outdir.name}")
    return finish_pipeline(meta["url"], meta, outdir, dst, args, lib)

def ids_from_capture(media_url, referer, platform):
    """从抓流记下的媒体地址和 referer 里挖出平台自己的作品 ID 和作者 ID。

    为什么值得做：抓流档的文件名原本是 grab_<sha 前20位>，
    目录名就成了 kuaishou_grab_e69696266d…——一个跟平台毫无关系的哈希，
    既回不到原页面，也没法跟同一作者的其他作品对上号。
    而 Surge 抓到的 referer 里本来就带着这两个 ID：
      https://www.kuaishou.com/short-video/3xm4y3b94veigzi?authorId=3xhafyhtrk29exg
    只是之前只当 source_url 原样存着，没解析。

    作品 ID 有两个来源，媒体地址那个更可靠：
      媒体地址  ...&clientCacheKey=3xm4y3b94veigzi_b.mp4
      referer   .../short-video/3xm4y3b94veigzi?authorId=3xhafyhtrk29exg

    **优先用 clientCacheKey**：从首页/推荐流播的 referer 只有
    https://www.kuaishou.com/，挖不出作品 ID，但媒体地址里那个一直在。
    实测两条对照过，两个来源给出的 ID 完全一致。
    authorId 只有 referer 有，所以从作品页播仍然更划算。

    都挖不到时返回 (None, None)，调用方回落到 sha 命名——不是失败。"""
    if platform != "kuaishou":
        return None, None
    vid = None
    m = re.search(r"[?&]clientCacheKey=([A-Za-z0-9]+?)(?:_[a-z]+)?\.mp4", media_url or "")
    if m:
        vid = m.group(1)
    if not vid:
        m = re.search(r"/short-video/([A-Za-z0-9_-]+)", referer or "")
        vid = m.group(1) if m else None
    m2 = re.search(r"[?&]authorId=([A-Za-z0-9_-]+)", referer or "")
    return vid, (m2.group(1) if m2 else None)


def process_media_url(args, lib):
    """直链档：Surge 脚本抓到的媒体地址直接进来。

    快手网页是空壳、视频号只在端内，两者都拿不到可解析的页面，
    但抓流能拿到真实媒体地址——从那里接上，后面的流程和别的平台完全一样。"""
    mu = args.media_url
    platform = args.as_platform or ("wxchannel" if "qq.com" in mu else
                                    "kuaishou" if "kwai" in mu or "kuaishou" in mu else "local")
    print(f"\n\033[1m▶ 直链 {mu[:90]}\033[0m")
    if args.dry_run:
        log("dry-run：直链不下载；尚未验证媒体内容", "✓")
        return "dry"
    lib.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vx-grab-", dir=lib) as td:
        dest = Path(td) / "download.mp4"
        log("下载中…")
        okd, why = download_direct(mu, dest, referer=args.source_url,
                                   user_agent=args.user_agent)
        if not okd:
            log(f"直链下载失败：{why}。重新播放以刷新地址。", "✗")
            return "failed"
        dur, _ = probe_local(dest)
        if dur is None or dur <= 0:
            log("下载内容不是可解码媒体，可能是播放列表、错误页或加密流。", "✗")
            return "failed"
        digest = hashlib.sha256()
        with dest.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        vid, aid = ids_from_capture(mu, args.source_url, platform)
        if vid:
            log(f"从 referer 认出平台作品 ID：{vid}" + (f"（作者 {aid}）" if aid else ""))
        stable = dest.with_name((vid or "grab_" + digest.hexdigest()[:20]) + ".mp4")
        dest.rename(stable)
        log(f"下载完成 {stable.stat().st_size/1048576:.1f} MB")
        if aid:
            args.author_id = aid
        args.as_platform = platform
        args.channel = args.channel or "Surge 抓流"
        args.tool = args.tool or "surge"
        return process_local(stable, args, lib)

# ---------------------------------------------------------------- 单条主流程

def process(url, args):
    lib = Path(args.lib).expanduser()
    # 本地文件先认出来。之前这里直接当 URL 解析，
    # 于是 vx <本地文件> 永远失败——而快手和视频号恰恰以本地文件为终点。
    if not re.match(r"^[a-z]+://", url) and Path(url).expanduser().exists():
        return process_local(url, args, lib)
    print(f"\n\033[1m▶ {url}\033[0m")
    platform = platform_of(url)

    if platform == "wxarticle":
        return process_wx_article(url, args, lib)

    if platform == "wxchannel":
        from vx_wxchannels import process_share
        from types import SimpleNamespace
        context = SimpleNamespace(log=log, download_direct=download_direct, run=run,
                                  probe_local=probe_local, process_local=process_local)
        return process_share(url, args, lib, context)

    backend = getattr(args, "tiktok_backend", "direct")
    if platform == "kuaishou":
        try:
            from vx_kuaishou import fetch_kuaishou
            log("解析快手公开作品页面（不读取浏览器 Cookie）")
            log("快手使用页面默认画质，画质上限不控制此直链", "!")
            raw, err = fetch_kuaishou(url), None
        except Exception as e:
            raw, err = None, f"快手页面解析失败：{e}"
    elif platform == "tiktok" and backend == "tikwm":
        raw, err = None, None
    else:
        raw, err = fetch_meta_cached(url, args.cookies, lib, refresh=args.refresh_meta)
    if platform == "tiktok" and raw is None and backend in ("tikwm", "auto"):
        log("使用 TikWM 第三方解析：只发送作品链接，不发送浏览器 Cookie", "↻")
        try:
            from vx_tiktok import fetch_tikwm
            raw = fetch_tikwm(url)
            err = None
        except Exception as e:
            err = f"TikWM 解析失败：{type(e).__name__}: {e}"

    if raw is None and platform == "weibo":
        log("yt-dlp 解析不了这条微博，改走移动端接口", "↻")
        raw, err2 = fetch_weibo_meta(url)
        if raw is None:
            log(f"移动端接口也不行：{err2}", "✗")
    if raw is None and platform == "kuaishou":
        log("快手公开页面解析未通过，请在浏览器确认作品仍可播放。", "!")
    if raw is None:
        log(f"元数据解析失败：{err}", "✗")
        if "fresh cookies" in (err or "").lower():
            # 抖音／TikTok 这条报错的原文是
            #   "Fresh cookies (not necessarily logged in) are needed"
            # 它明说了跟登没登录无关，要的是**新鲜**。原来这里统一提示
            # 「确认登录了该平台」，会把人引到完全没用的方向去。
            # 实测：同一条抖音链接 02:20 能解析，18:41 就报这个，中间什么都没改——
            # 是浏览器里的 cookie 放久了失效，不是账号问题。
            log("平台要求「新鲜」cookie；这不一定是未登录，已登录也可能需要刷新。", "!")
            log(f"去浏览器里打开一次 {platform} 的网站、等页面加载完，再重跑这条。", "!")
        elif "cookies" in (err or "").lower():
            log("多半是 cookie 问题。确认浏览器里登录了该平台，或换 --cookies safari", "!")
        elif "412" in (err or "") or "429" in (err or ""):
            log("这是平台限速，不是链路问题。隔几分钟再跑，或批量时把 --sleep 调大", "!")
        elif platform == "tiktok" and backend == "direct":
            # 实测：同一批里 @hankgreen1 那条直连成功（yt-dlp 会自己解 JS challenge），
            # @patroxofficial 那条报 "Unable to extract universal data for rehydration"。
            # 也就是说 extractor 本身没坏，是这一条的页面结构 yt-dlp 跟不上。
            # 不自动降级到 TikWM：那是第三方服务，等于把链接发给别人，
            # 要不要发是用户的选择，不是默认值。但得让用户知道有这条路。
            log("TikTok 直连解析不了这一条。备用路径：--tiktok-backend auto", "!")
            log("注意 auto 会把链接发给第三方 TikWM 解析（不发 cookie）。不想外发就跳过这条。", "!")
        elif platform == "xiaohongshu" and "No video formats" in (err or ""):
            log("小红书链接里的 xsec_token 是有时效的，过期后同一条链接就取不到了。", "!")
            log("重新从小红书复制一次链接（必须带 xsec_token 那一整串）。", "!")
            log("批量档因此不能提前很久备链接清单——攒好就尽快跑。", "!")
        elif platform in ("tencent", "iqiyi", "youku"):
            log("长视频平台的正片有 DRM，工具拿不到，这是版权限制不是技术问题。", "!")
            log("确实需要的话只能录屏，再用 vx <录屏文件> 走本地档做 OCR/ASR。", "!")
        elif "extractor error" in (err or "").lower() or "KeyError" in (err or ""):
            log("yt-dlp 的解析器和该平台当前页面结构对不上（平台改版了）。", "!")
            log("先试 yt-dlp -U 升级；仍不行就换一种链接形式，或走浏览器嗅探兜底。", "!")
        return "failed"

    if raw.get("_type") in ("playlist", "multi_video") or raw.get("entries"):
        log("该链接包含多个作品或轮播视频。请将各条视频链接放入 -f 清单逐条处理。", "!")
        return "unsupported_collection"

    meta = build_meta(url, raw, platform,
                      channel=("移动端接口" if raw.get("extractor") == "weibo-mobile-api" else "TikWM 第三方解析" if raw.get("extractor") == "tikwm" else "yt-dlp"))
    if raw.get("extractor") == "tikwm":
        meta["capture"]["tool"] = "TikWM API (adapter researched from JoeanAmier/TikTokDownloader)"
        meta["capture"]["evidence"] = "第三方转存媒体；来源待核对"
        meta["notes"] = (meta.get("notes", "") + " 媒体通过 TikWM 获取，非直接从 TikTok 取得。").strip()
    if raw.get("extractor") == "kuaishou-public-page":
        meta["capture"].update(channel="快手公开作品页面", tool="拾影快手页面解析")
        meta["notes"] = "使用页面默认媒体画质；画质上限不控制此直链。"
    if platform == "xiaohongshu":
        enrich_xhs(meta, url)
    # 有些平台的 extractor 不给作者和日期（实测小红书就是），
    # 硬拼成 xiaohongshu_unknown_nodate_xxx 既难看也不利于检索，
    # 缺哪段就省哪段，ID 一定在，唯一性不受影响。
    parts = [platform]
    an = (meta["author"] or {}).get("name")
    if an:
        parts.append(safe(an))
    if meta["published_at"]:
        parts.append(str(meta["published_at"]))
    parts.append(safe(meta["video_id"], 30))
    slug = "_".join(parts)
    outdir = lib / slug
    for sub in ("media", "subs", "frames", "notes"):
        (outdir / sub).mkdir(parents=True, exist_ok=True)

    if (outdir / ".done").exists() and not args.force and not getattr(args, "redownload", False) and not args.dry_run:
        log(f"已完成过，跳过：{slug}（要重跑加 --force）", "↷")
        return "skipped"

    log(f"目录 {slug}")
    log(f"标题 {meta['title']}")

    if args.dry_run:
        (outdir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log("dry-run：只写了 meta.json，未下载", "✓")
        return "dry"

    if getattr(args, "redownload", False):
        moved = stash_media(outdir)
        if moved:
            log(f"旧媒体已挪到 {moved.relative_to(outdir)}，将重新下载", "↻")
            log("确认新文件没问题之后，_replaced 目录可以自己删掉", "!")
    elif args.force and find_media(outdir) is not None:
        # --force 只是忽略 .done，它不刷元数据也不重下媒体。
        # 字面意思没错，但谁看了都会理解成"重新跑一遍"，
        # 结果是批量复跑时以为压了网络，其实一条都没走——说清楚。
        log("媒体已在本地，--force 不会重下（要重下加 --redownload）", "!")

    # 下载
    # 元数据是用哪个浏览器的 cookie 拿到的，下载和字幕就沿用哪个
    br = raw.get("_vx_browser") or browser_list(args.cookies)[0]
    # 元数据是靠强行带 cookie 才拿到的，下载和字幕必须沿用同样的姿势，
    # 否则 needs_cookies() 会在下一步把 cookie 又剥掉，白试一遍。
    force_ck = bool(raw.get("_vx_force_cookies"))
    if getattr(args, "download_only", False):
        pass
    elif platform in ("instagram", "tiktok", "kuaishou") and not raw.get("subtitles") and not raw.get("automatic_captions"):
        (outdir / "media" / ".subs_fetched").write_text("metadata: no subtitle tracks", encoding="utf-8")
        log("元数据未列出字幕轨，下载后使用本地转写")
    else:
        ensure_subs(url, outdir, br, force_cookies=force_ck)
    video = find_media(outdir)
    if video is not None:
        log("复用已有媒体；本次不重新下载", "↷")
    if video is None:
        direct = raw.get("_vx_play_url")
        if direct:
            log("用接口给的直链下载（yt-dlp 解析不了这条）…")
            dest = outdir / "media" / f"{meta['video_id']}.mp4"
            okd, why = download_direct(direct, dest, referer=raw.get("_vx_referer") or url, user_agent=raw.get("_vx_user_agent"))
            if okd:
                log(f"直链下载完成 {dest.name}")
            else:
                log(f"直链下载失败：{why}", "!")
                if raw.get("extractor") in ("tikwm", "kuaishou-public-page"):
                    return "failed"
                log("改试 yt-dlp", "↻")
        if find_media(outdir) is None:
            log("下载中…")
            if not download(url, outdir, br, want_subs=not getattr(args, "download_only", False), max_res=getattr(args, "max_res", 1080), force_cookies=force_ck):
                log("下载失败", "✗")
                return "failed"
        video = find_media(outdir)
    if video is None:
        log("下载后找不到媒体文件", "✗")
        return "failed"
    return finish_pipeline(url, meta, outdir, video, args, lib)

# ---------------------------------------------------------------- 入口

def parse_target_list(text):
    # 仅空白后的 # 是行内注释；URL 自身的 fragment 保留。
    return [re.split(r"\s+#", line.strip(), maxsplit=1)[0].rstrip()
            for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def main():
    ap = argparse.ArgumentParser(
        prog="vx", description="全平台视频内容提取",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例子：
  vx https://www.bilibili.com/video/BVxxxx        标准档，单条走全流程
  vx -f links.txt                                 批量档，逐行读链接，可断点续跑
  vx <链接> --dual                                进正式材料：OCR＋ASR 双路互校
  vx <链接> --dry-run                             只探元数据，不下载
  vx ~/Movies/a.mp4                               本地文件档
""")
    ap.add_argument("targets", nargs="*", help="链接或本地文件")
    ap.add_argument("-f", "--file", help="链接清单文件，一行一条")
    ap.add_argument("--lib", default=str(DEFAULT_LIB), help=f"媒体库根目录（默认 {DEFAULT_LIB}）")
    ap.add_argument("--cookies", default="chrome,edge",
                    help="cookie 来源浏览器，可给多个用逗号分隔按序尝试；none 为不带")
    ap.add_argument("--tiktok-backend", choices=["direct", "auto", "tikwm"], default="direct",
                    help="TikTok 路径：direct 直连；auto 失败后将链接交给第三方 TikWM；tikwm 直接使用第三方")
    ap.add_argument("--engine", default="auto", choices=["auto", "funasr", "parakeet", "smartsub"])
    ap.add_argument("--lang", choices=["zh", "en"], help="强制语种，默认按平台和字幕轨猜")
    ap.add_argument("--download-only", action="store_true", help="只下载并验证媒体，不转写、不抽帧；后续可继续提取")
    ap.add_argument("--ocr-roi", metavar="x,y,w,h",
                    help="OCR 扫描区域，Vision 坐标（原点左下角，归一化）。"
                         f"默认 {DEFAULT_OCR_ROI}（底部字幕条），空手而归时自动改扫全图。"
                         "显式给了就只扫这一块，不再自动放宽。全图是 0,0,1,1")
    ap.add_argument("--redownload", action="store_true",
                    help="把已有媒体挪进 media/_replaced/ 后重新下载（换画质策略后用），不删文件")
    ap.add_argument("--max-res", type=int, default=1080, metavar="N",
                    help="画质上限，默认 1080。要原画存档就 --max-res 2160")
    ap.add_argument("--dual", action="store_true", help="开启 OCR＋ASR 双路互校")
    ap.add_argument("--force-asr", action="store_true", help="有官方字幕也跑 ASR")
    ap.add_argument("--no-frames", action="store_true", help="不抽帧")
    ap.add_argument("--interval", type=int, default=15, help="固定间隔抽帧秒数，默认 15")
    ap.add_argument("--force", action="store_true",
                    help="忽略 .done 标记重跑。注意：不刷新元数据也不重下已有媒体，"
                         "要那样得配 --refresh-meta / --redownload")
    ap.add_argument("--youtube-cookies", action="store_true",
                    help="对 YouTube 也带 cookie（默认先不带；遇登录校验时会用所选浏览器重试，--cookies none 可禁用）")
    ap.add_argument("--refresh-meta", action="store_true", help="忽略缓存，强制重新联网取元数据")
    ap.add_argument("--user-agent", help="抓流请求的 User-Agent，vx-grab 自动传入")
    ap.add_argument("--media-url", help="直接给媒体直链（Surge 抓流拿到的地址）")
    ap.add_argument("--as", dest="as_platform", help="标记平台，如 kuaishou / wxchannel")
    ap.add_argument("--source-url", help="原始页面地址，写进 meta 供追溯")
    ap.add_argument("--title", help="人工指定标题")
    ap.add_argument("--author", help="人工指定作者")
    ap.add_argument("--published", help="人工指定发布日期，形如 20260904")
    ap.add_argument("--note", help="写进 meta.notes 的备注")
    ap.add_argument("--channel", help="采集通道，写进 meta.capture.channel")
    ap.add_argument("--tool", help="采集工具，写进 meta.capture.tool")
    ap.add_argument("--sleep", type=float, default=3, help="批量条目之间的等待秒数，默认 3")
    ap.add_argument("--dry-run", action="store_true", help="只探元数据不下载")
    args = ap.parse_args()
    global YOUTUBE_COOKIES
    YOUTUBE_COOKIES = bool(getattr(args, "youtube_cookies", False))
    if args.max_res < 1:
        ap.error("--max-res 必须为正整数")
    if args.sleep < 0 or args.interval < 1:
        ap.error("--sleep 必须非负，--interval 必须为正整数")

    urls = list(args.targets)
    if args.file:
        urls += parse_target_list(Path(args.file).read_text(encoding="utf-8"))
    if args.media_url:
        lib = Path(args.lib).expanduser(); lib.mkdir(parents=True, exist_ok=True)
        r = process_media_url(args, lib)
        print(f"\n\033[1m── 小结 ──\033[0m\n  {r}")
        raise SystemExit(0 if r in ("ok", "skipped", "dry") else 1)
    if not urls:
        ap.print_help(); raise SystemExit(0)

    Path(args.lib).expanduser().mkdir(parents=True, exist_ok=True)
    urls = list(dict.fromkeys(urls))
    tally = {}
    results = []
    for i, u in enumerate(urls):
        if i and args.sleep:
            time.sleep(args.sleep)
        try:
            r = process(u, args)
        except KeyboardInterrupt:
            print("\n中断。已完成的条目下次会自动跳过。"); raise SystemExit(130)
        except Exception as e:
            log(f"未预期的错误：{type(e).__name__}: {e}", "✗")
            r = "failed"
        tally[r] = tally.get(r, 0) + 1
        results.append({"url": u, "result": r})

    print("\n\033[1m── 小结 ──\033[0m")
    for k, v in tally.items():
        print(f"  {k}: {v}")
    print(f"  总表：{Path(args.lib).expanduser()/'index.csv'}")
    run_dir = Path(args.lib).expanduser() / ".runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    report = run_dir / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
    report.write_text(json.dumps({"tally": tally, "items": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(1 if any(r["result"] not in ("ok", "skipped", "dry") for r in results) else 0)

if __name__ == "__main__":
    main()
