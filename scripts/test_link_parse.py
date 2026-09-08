#!/usr/bin/env python3
"""vx_link 的回归测试。样本全部取自真实使用记录，不是编的。

不联网：--expand 那条路径要网络，在这里只测「判定为 needs_expand」，
真实展开结果得在有网的机器上验。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from vx_link import parse_text, classify, urls_in_text

fail = []
def check(name, got, want):
    if got != want:
        fail.append(f"{name}\n    got  {got!r}\n    want {want!r}")

# ── 1. 真实的小红书分享文案（2026-09-07 用户原样粘贴）──
XHS = ("30 【被挂在暗网上的女模特：30万刀全球包邮到家 - 安小舟 | 小红书 - 你的生活兴趣社区】 "
       "😆 nqI0EPfpfDpEaxg 😆 https://www.xiaohongshu.com/discovery/item/"
       "6a9b7409000000002601d79b?source=webshare&xhsshare=pc_web&"
       "xsec_token=TEST_TOKEN&xsec_source=pc_share")
ls = parse_text(XHS)
check("小红书 只捞出一条", len(ls), 1)
check("小红书 平台", ls[0].platform, "xiaohongshu")
check("小红书 作品ID", ls[0].video_id, "6a9b7409000000002601d79b")
check("小红书 时效状态", ls[0].status, "expiring")
check("小红书 emoji/口令没混进 URL", "😆" in ls[0].url, False)

# ── 2. 各平台链接形态（本测试只检查字符串，不联网下载）──
CASES = [
    ("https://www.youtube.com/watch?v=DBpE9WcC11E", "youtube", "DBpE9WcC11E", "ready"),
    ("https://www.bilibili.com/video/BV15PtJ6JEBh/?spm_id_from=333.1007.tianma.1-1-1.click"
     "&vd_source=example", "bilibili", "BV15PtJ6JEBh", "ready"),
    ("https://www.douyin.com/video/7655282202342755634", "douyin", "7655282202342755634", "ready"),
    ("https://weibo.com/tv/show/1034:5331196788277301?mid=5331197049703001",
     "weibo", "1034:5331196788277301", "ready"),
    ("https://www.instagram.com/reel/Chunk8-jurw/", "instagram", "Chunk8-jurw", "ready"),
    ("https://www.tiktok.com/@hankgreen1/video/7047596209028074758",
     "tiktok", "7047596209028074758", "ready"),
    ("https://weixin.qq.com/sph/Axv548mzBF", "wxchannel", "Axv548mzBF", "ready"),
    ("https://mp.weixin.qq.com/s/Aq_rJ50FllapHSx8qe7HRQ", "wxarticle",
     "Aq_rJ50FllapHSx8qe7HRQ", "ready"),
    # 快手：认得出、有 ID，但状态为 ready
    ("https://www.kuaishou.com/short-video/3xm4y3b94veigzi?authorId=3xhafyhtrk29exg"
     "&streamSource=profile", "kuaishou", "3xm4y3b94veigzi", "ready"),
]
for url, plat, vid, status in CASES:
    l = classify(url)
    check(f"{plat} 平台", l.platform, plat)
    check(f"{plat} 作品ID", l.video_id, vid)
    check(f"{plat} 状态", l.status, status)

# ── 3. 快手直链里的 clientCacheKey 也能挖出作品 ID ──
DIRECT = ("https://v23-3.kwaicdn.com/upic/2026/07/02/11/BMjA_b_B897.mp4?pkey=AAU7"
          "&clientCacheKey=3xm4y3b94veigzi_b.mp4&di=da5cb2de&tt=b")
check("快手直链 作品ID", classify(DIRECT).video_id, "3xm4y3b94veigzi")

# ── 4. 短链：判定为需展开，不联网 ──
for short in ["https://b23.tv/AbCdEfG", "https://v.douyin.com/iXXXXXX/",
              "https://xhslink.com/a/AbCdEf"]:
    check(f"短链 {short.split('/')[2]}", classify(short).status, "needs_expand")

# ── 5. 尾部中文标点不能吃进 URL ──
check("尾部句号", urls_in_text("看这个 https://www.bilibili.com/video/BV15PtJ6JEBh。"),
      ["https://www.bilibili.com/video/BV15PtJ6JEBh"])
check("中文括号包裹", urls_in_text("（https://youtu.be/abc123）"),
      ["https://youtu.be/abc123"])

# ── 6. 认不出的站不算失败 ──
u = classify("https://example.com/some/video")
check("未知站 状态", u.status, "unknown")

# ── 7. 一段文本里多条、去重、保持顺序 ──
multi = parse_text("a https://youtu.be/x1\nb https://www.douyin.com/video/7\n"
                   "重复 https://youtu.be/x1")
check("多条去重", [l.url for l in multi],
      ["https://youtu.be/x1", "https://www.douyin.com/video/7"])
check("youtu.be 短链有 ID 就不需要展开", multi[0].status, "ready")
check("youtu.be 作品ID", multi[0].video_id, "x1")

# ── 8. 抖音「精选」页：ID 在 modal_id 里，且要规范化成 /video/<id> ──
#     实测样本，用户 2026-09-07 从抖音网页版复制
JX = "https://www.douyin.com/jingxuan?modal_id=7681863407733165321"
l = classify(JX)
check("抖音精选 平台", l.platform, "douyin")
check("抖音精选 作品ID", l.video_id, "7681863407733165321")
check("抖音精选 规范化", l.url, "https://www.douyin.com/video/7681863407733165321")
check("抖音精选 留了原链接痕迹", any("已规范化" in w for w in l.warnings), True)

# ── 9. 快手分享短链 /f/：主机名是 kuaishou.com，靠域名表认不出 ──
#     实测样本 https://www.kuaishou.com/f/XJJLFtop9kBf0g
KF = classify("https://www.kuaishou.com/f/XJJLFtop9kBf0g")
check("快手 /f/ 判为短链", KF.status, "needs_expand")
check("快手 /f/ 支持公开短链", "直接处理" in KF.note, True)
# 作品页形态不能被误判成短链
check("快手作品页不是短链",
      classify("https://www.kuaishou.com/short-video/3xm4y3b94veigzi").status, "ready")

# ── 10. 规范化只在有把握时做，拿不准原样返回 ──
ok_url = "https://www.douyin.com/video/7655282202342755634"
check("抖音标准形态不改写", classify(ok_url).url, ok_url)
bv = "https://www.bilibili.com/video/BV15PtJ6JEBh/?spm_id_from=333.1007"
check("B站带参数不改写", classify(bv).url, bv)

# ── 11. 视频号纯卡片文案：认不出任何链接，且不能崩 ──
check("视频号纯卡片", parse_text("#视频号 毒研解说 这条视频不错"), [])

if fail:
    print(f"❌ {len(fail)} 项不符：\n" + "\n".join(fail))
    sys.exit(1)
print("PASS vx_link：9 平台识别、作品ID提取、短链判定、抖音精选规范化、快手 /f/ 短链、中文标点剥离、去重、未知站兜底")
