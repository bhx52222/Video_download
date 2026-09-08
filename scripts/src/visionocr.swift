// visionocr —— 用 macOS 自带的 Vision 框架做图片文字识别
// 用途：抽帧后的硬字幕 OCR、画面内文字提取
// 用法：visionocr [--langs zh-Hans,en-US] [--roi x,y,w,h] <图片> [图片…]
//   --roi 用归一化坐标（0~1），原点在左下角。只识别字幕条时可传 --roi 0,0,1,0.25
// 输出：JSON 数组，每个元素含 file / lines[]，每行含 text、conf、box(归一化 x,y,w,h)

import Foundation
import Vision
import AppKit

struct Line: Codable { let text: String; let conf: Float; let box: [Double] }
struct Item: Codable { let file: String; let lines: [Line]; let error: String? }

func loadCGImage(_ path: String) -> CGImage? {
    guard let img = NSImage(contentsOfFile: path) else { return nil }
    var rect = CGRect(x: 0, y: 0, width: img.size.width, height: img.size.height)
    return img.cgImage(forProposedRect: &rect, context: nil, hints: nil)
}

var argv = Array(CommandLine.arguments.dropFirst())
var roi: CGRect? = nil
var langs = ["zh-Hans", "en-US"]
var files: [String] = []
var i = 0
while i < argv.count {
    switch argv[i] {
    case "--roi":
        i += 1
        if i < argv.count {
            let p = argv[i].split(separator: ",").compactMap { Double($0) }
            if p.count == 4 { roi = CGRect(x: p[0], y: p[1], width: p[2], height: p[3]) }
        }
    case "--langs":
        i += 1
        if i < argv.count { langs = argv[i].split(separator: ",").map(String.init) }
    case "-h", "--help":
        FileHandle.standardError.write("用法: visionocr [--langs zh-Hans,en-US] [--roi x,y,w,h] <图片>…\n".data(using: .utf8)!)
        exit(0)
    default:
        files.append(argv[i])
    }
    i += 1
}

if files.isEmpty {
    FileHandle.standardError.write("错误：没有给图片路径。用 --help 看用法。\n".data(using: .utf8)!)
    exit(2)
}

var out: [Item] = []
for f in files {
    guard let cg = loadCGImage(f) else {
        out.append(Item(file: f, lines: [], error: "无法读取图片"))
        continue
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = langs
    if let r = roi { req.regionOfInterest = r }

    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        let obs = req.results ?? []
        let lines: [Line] = obs.compactMap { o in
            guard let c = o.topCandidates(1).first else { return nil }
            let b = o.boundingBox
            return Line(text: c.string, conf: c.confidence,
                        box: [b.origin.x, b.origin.y, b.size.width, b.size.height])
        }
        out.append(Item(file: f, lines: lines, error: nil))
    } catch {
        out.append(Item(file: f, lines: [], error: "\(error)"))
    }
}

let enc = JSONEncoder()
enc.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes, .sortedKeys]
if let d = try? enc.encode(out) { FileHandle.standardOutput.write(d); print() }
