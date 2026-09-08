import Foundation
@main struct Tests {
 static func main() {
  // ── 自动收集：只认已知平台，其他剪贴板内容不进输入区 ──
  assert(LinkTools.extract("分享 https://weixin.qq.com/sph/abc。\nhttps://weixin.qq.com/sph/abc") == ["https://weixin.qq.com/sph/abc"])
  assert(LinkTools.extract("<a href=\"https://channels.weixin.qq.com/finder-preview/pages/feed?eid=a&amp;token=b\">打开</a>") == ["https://channels.weixin.qq.com/finder-preview/pages/feed?eid=a&token=b"])
  assert(LinkTools.extract("https://weixin.qq.com.evil.test/sph/a").isEmpty)
  assert(LinkTools.extract("#视频号：测试标题").isEmpty)
  assert(LinkTools.extract("普通剪贴板文字、密码不会保存").isEmpty)
  assert(LinkTools.extract("https://user:password@www.youtube.com/watch?v=abc").isEmpty)

  // ── 尾部中文标点不能吃进 URL（与 vx_link.py 的 TRAILING 一致）──
  assert(LinkTools.extract("看这个 https://www.bilibili.com/video/BV15PtJ6JEBh？") == ["https://www.bilibili.com/video/BV15PtJ6JEBh"])
  assert(LinkTools.extract("【标题】https://www.douyin.com/video/7681863407733165321】") == ["https://www.douyin.com/video/7681863407733165321"])

  // ── 域名表与 vx_link.PLATFORM_HOSTS 对齐：X 和微博短链原来会被丢掉 ──
  assert(LinkTools.extract("https://x.com/user/status/1234567890") == ["https://x.com/user/status/1234567890"])
  assert(LinkTools.extract("https://t.cn/A6xxxxxx") == ["https://t.cn/A6xxxxxx"])

  // ── 手动粘贴：未知站点交给内核通用兜底，不再当场丢掉 ──
  assert(LinkTools.extract("https://vimeo.com/123456789").isEmpty)
  assert(LinkTools.extractAny("https://vimeo.com/123456789") == ["https://vimeo.com/123456789"])
  assert(LinkTools.extractAny("https://user:password@www.youtube.com/watch?v=abc").isEmpty)
  assert(LinkTools.extractAny("没有网址的一段话").isEmpty)
  assert(LinkTools.unknownPlatform(["https://vimeo.com/1", "https://youtu.be/x"]) == ["https://vimeo.com/1"])

  print("PASS clipboard link parsing: platform allowlist, manual-paste fallback, punctuation parity, dedup, HTML escaping, card/credential rejection")
 }
}
