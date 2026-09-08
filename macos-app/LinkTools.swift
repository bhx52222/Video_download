import Foundation

/// 剪贴板文本 → 链接。规则与 backend/vx_link.py 保持一致，
/// 两处一旦不同，就会出现「CLI 认得、App 不认」这类只在 App 里复现的失败。
enum LinkTools {
    /// 与 vx_link.py 的 TRAILING 一致：这些是中文文案带的尾部标点，不属于 URL。
    /// 原来只剥 "，。；！、）)]}"，粘贴 "…BV15PtJ6JEBh？" 会把 ？ 一起送进内核。
    static let trailing = "，。；！？、）)]}】》」』…,.;!?"

    /// 与 vx_link.py 的 PLATFORM_HOSTS 一致。剪贴板自动收集只认这些域名，
    /// 其余剪贴板内容不进输入区——这是「不保存其他剪贴板内容」的承诺所在。
    static let platformDomains = ["youtube.com", "youtu.be", "bilibili.com", "b23.tv",
        "douyin.com", "iesdouyin.com", "xiaohongshu.com", "xhslink.com",
        "weibo.com", "weibo.cn", "t.cn", "kuaishou.com", "kwai.com", "kwaicdn.com",
        "tiktok.com", "tiktokv.com", "instagram.com", "x.com", "twitter.com",
        "mp.weixin.qq.com", "channels.weixin.qq.com", "weixin.qq.com"]

    static func isPlatform(_ host: String) -> Bool {
        return platformDomains.contains { host == $0 || host.hasSuffix("." + $0) }
    }

    /// 捞出文本里所有形态合法的网址，连同小写主机名一起返回。
    private static func candidates(_ text: String) -> [(url: String, host: String)] {
        let clean = text.replacingOccurrences(of: "&amp;", with: "&").replacingOccurrences(of: "&#38;", with: "&")
        guard let re = try? NSRegularExpression(pattern: "https?://[^\\s<>\"“”【】（）]+") else {return []}
        let ns = clean as NSString
        var out = [(url: String, host: String)]()
        for match in re.matches(in: clean, range: NSRange(location: 0, length: ns.length)) {
            var value = ns.substring(with: match.range)
            while let last = value.last, trailing.contains(last) {value.removeLast()}
            guard let u = URLComponents(string: value), let host = u.host?.lowercased(),
                  !host.isEmpty, u.user == nil, u.password == nil else {continue}
            // 视频号只认 /sph/ 分享链接；weixin.qq.com 下的其他路径不是作品地址。
            if host == "weixin.qq.com" && !u.path.hasPrefix("/sph/") {continue}
            out.append((url: value, host: host))
        }
        return out
    }

    /// 剪贴板自动收集用：只认已知平台。
    static func extract(_ text: String) -> [String] {
        var result = [String]()
        for item in candidates(text) where isPlatform(item.host) {
            if !result.contains(item.url) {result.append(item.url)}
        }
        return result
    }

    /// 手动「粘贴链接」用：用户已经明确要处理这段文本，未知站点也收下，
    /// 交给内核的 yt-dlp 通用兜底去试，而不是当场丢掉再报「没有可识别的链接」。
    static func extractAny(_ text: String) -> [String] {
        var result = [String]()
        for item in candidates(text) {
            if !result.contains(item.url) {result.append(item.url)}
        }
        return result
    }

    /// 这批链接里不在已知平台表内的部分，用于提示走的是兜底路径。
    static func unknownPlatform(_ links: [String]) -> [String] {
        return links.filter { link in
            guard let host = URLComponents(string: link)?.host?.lowercased() else {return true}
            return !isPlatform(host)
        }
    }
}
