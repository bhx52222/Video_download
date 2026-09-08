import Foundation
@main struct Tests {
 static func main() {
  assert(LinkTools.extract("分享 https://weixin.qq.com/sph/abc。\nhttps://weixin.qq.com/sph/abc") == ["https://weixin.qq.com/sph/abc"])
  assert(LinkTools.extract("<a href=\"https://channels.weixin.qq.com/finder-preview/pages/feed?eid=a&amp;token=b\">打开</a>") == ["https://channels.weixin.qq.com/finder-preview/pages/feed?eid=a&token=b"])
  assert(LinkTools.extract("https://weixin.qq.com.evil.test/sph/a").isEmpty)
  assert(LinkTools.extract("#视频号：测试标题").isEmpty)
  assert(LinkTools.extract("普通剪贴板文字、密码不会保存").isEmpty)
  assert(LinkTools.extract("https://user:password@www.youtube.com/watch?v=abc").isEmpty)
  print("PASS clipboard link parsing: supported domains, dedup, HTML escaping, card/credential rejection")
 }
}
