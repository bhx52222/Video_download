#!/usr/bin/env python3
"""从任意文本里认出视频链接，判断它能不能跑、该走哪条路。

为什么单独一个模块：链接解析原来散在两处——app 的 runner.py 里一份
（处理分享文案、.webloc、HTML 转义），vx.py 里一份（平台映射、alt_urls），
两边逻辑不一致，也没法单独测。这里收成一处，CLI 和 app 都调它。

设计边界：
  · 纯解析不联网。展开短链要联网，是单独一步（expand=True 才做）。
  · 不下载、不解析页面。只回答「这是什么、能不能跑、下一步做什么」。
  · 认不出来不算失败——返回 status=unknown，交给 yt-dlp 通用兜底去试。

用法：
    from vx_link import parse_text
    for link in parse_text(分享文案): print(link.platform, link.status)

    python3 vx_link.py "30 【…】 😆 https://www.xiaohongshu.com/…"
    python3 vx_link.py --json --expand links.txt
"""
from dataclasses import dataclass, asdict, field
import html
import json
import plistlib
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

# ---------------------------------------------------------------- 平台

# 域名 → 平台。用后缀匹配，所以 m.weibo.cn 和 weibo.com 都能中。
PLATFORM_HOSTS = {
    "youtube.com": "youtube", "youtu.be": "youtube",
    "bilibili.com": "bilibili", "b23.tv": "bilibili",
    "douyin.com": "douyin", "iesdouyin.com": "douyin",
    "xiaohongshu.com": "xiaohongshu", "xhslink.com": "xiaohongshu",
    "weibo.com": "weibo", "weibo.cn": "weibo",
    "kuaishou.com": "kuaishou", "kwaicdn.com": "kuaishou", "kwai.com": "kuaishou",
    "tiktok.com": "tiktok", "tiktokv.com": "tiktok",
    "instagram.com": "instagram",
    "t.cn": "weibo",
}

# 短链域名：主机名本身不含作品信息，必须跟一次跳转才知道是什么。
SHORT_HOSTS = {"b23.tv", "v.douyin.com", "xhslink.com", "t.cn",
               "v.kuaishou.com", "youtu.be", "vt.tiktok.com", "vm.tiktok.com"}

# 每个平台怎么跑。这张表是给用户看的，不是给代码分支用的。
ROUTE = {
    "youtube":     "yt-dlp 直接跑",
    "bilibili":    "yt-dlp 直接跑",
    "douyin":      "yt-dlp 直接跑",
    "xiaohongshu": "yt-dlp 直接跑",
    "weibo":       "yt-dlp 解析器已失效，走 m.weibo.cn 移动端接口",
    "instagram":   "yt-dlp 直接跑",
    "tiktok":      "yt-dlp 直连；失败可加 --tiktok-backend auto 走第三方 TikWM",
    "wxchannel":   "元宝解析接口（需浏览器里有元宝登录态）",
    "wxarticle":   "解析文章正文，不下载不转写",
    "kuaishou":    "公开作品页由拾影快手页面解析器下载；风控或不可访问作品可能失败",
}


@dataclass
class Link:
    raw: str                      # 原始串（展开前）
    url: str                      # 规范化之后的 URL
    platform: str                 # 平台，认不出是 "unknown"
    video_id: str | None = None   # 平台自己的作品 ID
    status: str = "ready"         # 见下面 STATUS
    note: str = ""                # 给人看的一句话
    route: str = ""               # 该走哪条路
    expanded_from: str | None = None
    warnings: list = field(default_factory=list)


# ready         能直接跑
# needs_expand  短链，要联网跟一次跳转才知道是什么
# needs_capture 快手，必须走 Surge 抓流
# expiring      能跑，但链接里的令牌有时效
# unknown       认不出平台，交给 yt-dlp 通用兜底试
STATUS_LABEL = {
    "ready": "可直接处理",
    "needs_expand": "短链，需展开",
    "needs_capture": "需走抓流",
    "expiring": "可处理（链接有时效）",
    "unknown": "平台未知，可交给 yt-dlp 兜底试",
}


def platform_of(url):
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return "unknown"
    # 微信两条路完全不同，先分开：/sph/ 是视频号，/s/ 是公众号文章
    if host.endswith("weixin.qq.com") or host.endswith("qq.com"):
        path = urlsplit(url).path
        if path.startswith("/sph/"):
            return "wxchannel"
        if path.startswith("/s/") or host.startswith("mp."):
            return "wxarticle"
    for suffix, name in PLATFORM_HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return "unknown"


def is_short(url):
    """短链＝主机名或路径本身不含作品信息，必须跟一次跳转。

    除了独立短链域名，还有一类是主站下的分享短路径：
    实测 https://www.kuaishou.com/f/XJJLFtop9kBf0g 就是这种，
    主机名是 kuaishou.com，靠域名表认不出来。"""
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host in SHORT_HOSTS:
        return True
    if host.endswith("kuaishou.com") and re.match(r"^/f/[A-Za-z0-9]+/?$", u.path):
        return True
    return False


# ---------------------------------------------------------------- 作品 ID

def video_id_of(url, platform):
    """挖平台自己的作品 ID。挖不到返回 None，不是错误——
    有些形态（频道页、短链未展开）本来就没有。"""
    u = urlsplit(url)
    path, qs = u.path, parse_qs(u.query)
    if platform == "youtube":
        if (u.hostname or "").endswith("youtu.be"):
            return path.strip("/").split("/")[0] or None
        return (qs.get("v") or [None])[0]
    if platform == "bilibili":
        m = re.search(r"/(BV[0-9A-Za-z]{10})", path)
        return m.group(1) if m else None
    if platform == "douyin":
        m = re.search(r"/video/(\d+)", path)
        if m:
            return m.group(1)
        # 「精选」页的形态：/jingxuan?modal_id=7681863407733165321
        # 实测用户从抖音网页版复制出来就是这个样子。
        return (qs.get("modal_id") or [None])[0]
    if platform == "xiaohongshu":
        m = re.search(r"/(?:explore|discovery/item)/([0-9a-f]{16,32})", path)
        return m.group(1) if m else None
    if platform == "weibo":
        m = re.search(r"/tv/show/([\d:]+)", path) or re.search(r"/detail/(\d+)", path)
        if m:
            return m.group(1)
        return (qs.get("fid") or qs.get("mid") or [None])[0]
    if platform == "kuaishou":
        # 作品页 /short-video/<id>；直链里 clientCacheKey=<id>_b.mp4 也带
        m = re.search(r"/short-video/([A-Za-z0-9_-]+)", path)
        if m:
            return m.group(1)
        ck = (qs.get("clientCacheKey") or [""])[0]
        m = re.match(r"([A-Za-z0-9]+?)(?:_[a-z]+)?\.mp4$", ck)
        return m.group(1) if m else None
    if platform == "tiktok":
        m = re.search(r"/video/(\d+)", path)
        return m.group(1) if m else None
    if platform == "instagram":
        m = re.search(r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", path)
        return m.group(1) if m else None
    if platform == "wxchannel":
        m = re.search(r"/sph/([A-Za-z0-9]+)", path)
        return m.group(1) if m else None
    if platform == "wxarticle":
        m = re.search(r"/s/([A-Za-z0-9_-]+)", path)
        return m.group(1) if m else None
    return None


def canonical_url(url, platform, video_id):
    """还原成平台自己（和 yt-dlp）最认的那种形态。

    只做有把握的改写，拿不准就原样返回——**规范化错了比不规范化更糟**，
    会把一条本来能跑的链接改成跑不通的。

    实测需要改写的：抖音「精选」页 /jingxuan?modal_id=<id>
    yt-dlp 的 extractor 匹配的是 /video/<id>，精选页那种形态它不认。

    这条有实测对照（2026-09-07）：
      /jingxuan?modal_id=7681863407733165321 → ERROR: Unsupported URL
      /video/7681863407733165321             → 进了 Douyin extractor
    也就是说规范化把「这个 URL 我不处理」变成了「我认得，但取不到」——
    后者才是能继续诊断的状态。"""
    if not video_id:
        return url
    if platform == "douyin" and "/video/" not in urlsplit(url).path:
        return f"https://www.douyin.com/video/{video_id}"
    return url


def author_id_of(url, platform):
    if platform == "kuaishou":
        return (parse_qs(urlsplit(url).query).get("authorId") or [None])[0]
    return None


# ---------------------------------------------------------------- 从文本里捞 URL

# 尾部这些字符不是 URL 的一部分，是中文文案带的。
TRAILING = "，。；！？、）)]}】》」』…,.;!?"

URL_RE = re.compile(r'https?://[^\s<>"“”【】（）]+')


def urls_in_text(text):
    """从一段文本里把 URL 都捞出来，按出现顺序去重。

    实测样本（小红书分享文案）：
      30 【被挂在暗网上的女模特…- 安小舟 | 小红书…】 😆 nqI0EPfpfDpEaxg 😆 https://www.xiaohongshu.com/…
    要处理的：前面的数字和方括号标题、中间的 emoji 和口令、尾部的中文标点。
    """
    out = []
    for raw in URL_RE.findall(html.unescape(text or "")):
        u = raw.rstrip(TRAILING)
        # 括号成对时不该剥：…/watch?v=x(注) 这种少见，但 (x) 结尾的更少见
        if u not in out:
            out.append(u)
    return out


def read_file_link(path):
    """.webloc（plist）和 .url（ini）里存的是一个 URL，不是媒体本身。"""
    p = Path(path).expanduser()
    if p.suffix.lower() == ".webloc":
        try:
            u = plistlib.loads(p.read_bytes()).get("URL", "")
            return u if u.startswith(("http://", "https://")) else None
        except Exception:
            return None
    if p.suffix.lower() == ".url":
        for line in p.read_text(errors="replace").splitlines():
            if line.upper().startswith("URL=") and line[4:].startswith(("http://", "https://")):
                return line[4:]
    return None


# ---------------------------------------------------------------- 判定

def classify(url, expanded_from=None):
    platform = platform_of(url)
    link = Link(raw=expanded_from or url, url=url, platform=platform,
                expanded_from=expanded_from)
    link.video_id = video_id_of(url, platform)
    canon = canonical_url(url, platform, link.video_id)
    if canon != url:
        link.warnings.append(f"已规范化：原链接是 {url[:70]}")
        link.url = canon
    link.route = ROUTE.get(platform, "交给 yt-dlp 通用兜底试一下")

    if is_short(url) and link.video_id is None:
        link.status = "needs_expand"
        link.note = "短链，展开之前不知道是哪条作品。加 --expand 跟一次跳转。"
        if platform == "kuaishou":
            link.note += "（拾影下载器也可直接处理公开作品分享短链）"
        return link

    if platform == "unknown":
        link.status = "unknown"
        link.note = "认不出平台。yt-dlp 支持上千个站，值得直接试一次。"
        return link

    if platform == "kuaishou":
        link.status = "ready" if "/short-video/" in url and link.video_id else "needs_capture"
        link.note = "公开作品页使用页面默认画质；媒体直链可通过 --media-url 导入。"
        return link

    if platform == "xiaohongshu" and "xsec_token" in url:
        link.status = "expiring"
        link.note = "链接里的 xsec_token 约一小时过期，过期后同一条链接取不到，要重新复制。"
        return link

    if platform == "xiaohongshu" and "xsec_token" not in url:
        link.warnings.append("没有 xsec_token，小红书多半会拒绝。从 App 分享出来的链接才带。")

    if platform == "wxchannel":
        link.note = "需要浏览器里有元宝登录态。纯卡片、#视频号 和作者名都不是网址，转不出来。"

    if platform == "wxarticle":
        link.note = "公众号文章：正文直接是文字，不下载不转写。"

    link.status = "ready"
    return link


def parse_text(text, expand=False, timeout=10):
    """入口。文本进，Link 列表出。

    text 也可以是一行一条的清单，或者 .webloc / .url 文件的路径。
    expand=True 才联网跟短链跳转。
    """
    items = []
    for line in (text or "").splitlines():
        line = line.strip().strip('"')
        if not line or line.startswith("#"):
            continue
        p = Path(line).expanduser()
        try:
            is_file = p.is_file()
        except OSError:
            is_file = False
        if is_file:
            u = read_file_link(p)
            if u:
                items.append(u)
            continue
        items.extend(urls_in_text(line))

    seen, links = set(), []
    for u in items:
        if u in seen:
            continue
        seen.add(u)
        link = classify(u)
        if expand and link.status == "needs_expand":
            target = expand_short(u, timeout=timeout)
            if target and target != u:
                link = classify(target, expanded_from=u)
            else:
                link.warnings.append("展开失败，可能是网络不通或短链已失效。")
        links.append(link)
    return links


def expand_short(url, timeout=10):
    """跟一次跳转拿到真实地址。

    只在 expand=True 时调用——这是唯一联网的地方，且只发 HEAD/GET，
    不带任何 cookie。短链服务不需要登录态。
    """
    import urllib.request
    import urllib.error
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.url
    except urllib.error.HTTPError as e:
        # 有些短链对 HEAD/GET 返回 4xx，但 Location 已经在响应头里
        loc = e.headers.get("Location") if e.headers else None
        return loc
    except Exception:
        return None


# ---------------------------------------------------------------- CLI

def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    as_json = "--json" in argv
    expand = "--expand" in argv
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("用法：vx_link.py [--json] [--expand] <文本 | 文件路径>")
        return 2
    text = " ".join(args)
    p = Path(text).expanduser()
    if p.is_file() and p.suffix.lower() not in (".webloc", ".url"):
        text = p.read_text(encoding="utf-8", errors="replace")
    links = parse_text(text, expand=expand)
    if as_json:
        print(json.dumps([asdict(l) for l in links], ensure_ascii=False, indent=2))
        return 0
    if not links:
        print("没认出任何链接。")
        print("视频号的纯卡片、#话题、作者名都不是网址——要在分享菜单里选「复制链接」。")
        return 1
    for i, l in enumerate(links, 1):
        print(f"\n[{i}] {STATUS_LABEL.get(l.status, l.status)}")
        print(f"    平台     {l.platform}")
        if l.video_id:
            print(f"    作品 ID  {l.video_id}")
        print(f"    链接     {l.url[:110]}")
        if l.expanded_from:
            print(f"    展开自   {l.expanded_from}")
        print(f"    路径     {l.route}")
        if l.note:
            print(f"    说明     {l.note}")
        for w in l.warnings:
            print(f"    ⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
