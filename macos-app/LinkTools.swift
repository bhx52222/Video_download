import Foundation

enum LinkTools {
    static func extract(_ text: String) -> [String] {
        let clean=text.replacingOccurrences(of:"&amp;",with:"&").replacingOccurrences(of:"&#38;",with:"&")
        guard let re=try? NSRegularExpression(pattern:"https?://[^\\s<>\"“”]+") else {return []}
        let ns=clean as NSString
        let domains=["youtube.com","youtu.be","bilibili.com","b23.tv","douyin.com","weibo.com","weibo.cn","instagram.com","tiktok.com","tiktokv.com","mp.weixin.qq.com","channels.weixin.qq.com","weixin.qq.com","xiaohongshu.com","xhslink.com","kuaishou.com"]
        var result=[String]()
        for match in re.matches(in:clean,range:NSRange(location:0,length:ns.length)) {
            var value=ns.substring(with:match.range)
            while let last=value.last,"，。；！、）)]}".contains(last) {value.removeLast()}
            guard let u=URLComponents(string:value),let host=u.host?.lowercased(),u.user==nil,
                  domains.contains(where:{host == $0 || host.hasSuffix("."+$0)}) else {continue}
            if host == "weixin.qq.com" && !u.path.hasPrefix("/sph/") {continue}
            if !result.contains(value) {result.append(value)}
        }
        return result
    }
}
