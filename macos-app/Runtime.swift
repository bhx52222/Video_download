import Foundation

/// 运行时定位。与 backend/vx_runtime.py 是同一套规则的两端，改一边要改另一边。
///
/// 一体化包把 Python、ffmpeg、yt-dlp 等放在 .app/Contents/Resources/runtime/，
/// 这时用包内那份并通过 VX_RUNTIME 告诉内核；包内没有就回退 ~/.vx，
/// 行为与依赖本机环境的版本完全相同。
enum Runtime {
    static let home = FileManager.default.homeDirectoryForCurrentUser

    /// .app 内自带的运行时目录；没打包进去就是 nil。
    static var bundled: URL? {
        guard let resources = Bundle.main.resourceURL else {return nil}
        let root = resources.appendingPathComponent("runtime")
        // 光有目录不算数——必须真的有个能执行的 Python，否则宁可回退。
        let python = root.appendingPathComponent("python/bin/python3")
        return FileManager.default.isExecutableFile(atPath: python.path) ? root : nil
    }

    /// 跑内核用的 Python。包内优先，否则 ~/.vx/venv/bin/python。
    static var python: URL {
        if let root = bundled {return root.appendingPathComponent("python/bin/python3")}
        return home.appendingPathComponent(".vx/venv/bin/python")
    }

    static var isAvailable: Bool {
        return FileManager.default.isExecutableFile(atPath: python.path)
    }

    /// 运行环境不可用时给用户看的话。两种情况的处理方式不同，不能混成一句。
    static var unavailableMessage: String {
        if bundled != nil {
            return "应用自带的运行环境不完整，可能是安装包损坏。请重新下载安装。"
        }
        return "此版本需要本机已安装的 ~/.vx 运行环境。请按环境配置说明安装后重试。"
    }

    /// 子进程环境变量。
    ///
    /// VX_RUNTIME 让内核去包内找 ffmpeg/yt-dlp/visionocr；
    /// 不设 VX_STATE，可写状态照旧留在 ~/.vx——.app 内部不可写，
    /// 而且重装应用不该丢掉用户的抓流候选清单。
    static func environment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        var search = [String]()
        if let root = bundled {
            env["VX_RUNTIME"] = root.path
            search.append(root.appendingPathComponent("bin").path)
        }
        search += ["\(home.path)/.vx/bin", "\(home.path)/.local/bin",
                   "/opt/homebrew/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        env["PATH"] = search.joined(separator: ":")
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["LANG"] = "en_US.UTF-8"
        return env
    }
}
