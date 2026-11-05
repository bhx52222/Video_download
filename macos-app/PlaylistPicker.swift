import AppKit

/// 识别到播放列表或合集后，由用户决定：只下当前这一个 / 下整个列表 / 勾选部分。
final class PlaylistPicker: NSObject, NSTableViewDataSource, NSTableViewDelegate {
    enum Choice {case single, all, some}
    static let batchThreshold = 5   // 与 vx_playlist.BATCH_THRESHOLD 一致

    let info: [String:Any]
    let entries: [[String:Any]]
    var checked = Set<Int>()
    var choice = Choice.all
    let countLabel = NSTextField(labelWithString: "")
    let table = NSTableView()
    lazy var currentRadio = NSButton(radioButtonWithTitle: "只下当前这一个", target: self, action: #selector(choose(_:)))
    lazy var allRadio = NSButton(radioButtonWithTitle: "下整个列表", target: self, action: #selector(choose(_:)))
    lazy var someRadio = NSButton(radioButtonWithTitle: "勾选部分", target: self, action: #selector(choose(_:)))

    init(_ info: [String:Any]) {
        self.info = info
        entries = info["entries"] as? [[String:Any]] ?? []
        for e in entries where (e["unavailable"] as? Bool) != true {
            if let i = e["index"] as? Int {checked.insert(i)}
        }
        super.init()
    }

    /// 选中的序号。纯逻辑，便于单独测试。
    static func selected(_ choice: Choice, entries: [[String:Any]], checked: Set<Int>) -> [Int] {
        let all = entries.compactMap {$0["index"] as? Int}
        switch choice {
        case .single: return []
        case .all: return all
        case .some: return all.filter {checked.contains($0)}
        }
    }

    /// 发回 runner 的内容：原清单加上用户的选择。返回 nil 表示取消本次任务。
    static func ask(_ info: [String:Any], window: NSWindow?) -> [String:Any]? {
        let picker = PlaylistPicker(info)
        return picker.run()
    }

    private func hasCurrent() -> Bool {return info["current_url"] is String}

    func run() -> [String:Any]? {
        // 链接指向某一条时默认只下那一条，避免顺手一按回车就下几百条。
        choice = hasCurrent() ? .single : .all
        let alert = NSAlert()
        let count = entries.count
        alert.messageText = "这是一个列表，共 \(count) 条"
        alert.informativeText = [info["title"] as? String, info["uploader"] as? String].compactMap {$0}.joined(separator: " · ")
            + ((info["truncated"] as? Bool) == true ? "\n列表太长，这里只列出前 \(count) 条。" : "")
            + ((info["generated_mix"] as? Bool) == true ? "\n这是 YouTube 按当前视频自动生成的合辑，不是作者编排的列表。" : "")
        alert.accessoryView = buildView()
        alert.addButton(withTitle: "开始下载")
        alert.addButton(withTitle: "取消")
        refresh()
        while alert.runModal() == .alertFirstButtonReturn {
            let picked = Self.selected(choice, entries: entries, checked: checked)
            if choice != .single && picked.isEmpty {
                let warn = NSAlert();warn.messageText = "还没有勾选任何条目";warn.runModal();continue
            }
            var result = info
            result["choice"] = choice == .single ? "single" : (choice == .all ? "all" : "some")
            result["selected"] = picked
            return result
        }
        return nil
    }

    func buildView() -> NSView {
        currentRadio.isEnabled = hasCurrent()
        if !hasCurrent() {currentRadio.title = "只下当前这一个（这个链接没有指向具体视频）"}
        let radios = NSStackView(views: [currentRadio, allRadio, someRadio])
        radios.orientation = .horizontal;radios.spacing = 16
        for (id, title, width) in [("check", "", 28.0), ("index", "序号", 40.0), ("title", "标题", 420.0), ("duration", "时长", 60.0)] {
            let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier(id))
            column.title = title;column.width = CGFloat(width)
            table.addTableColumn(column)
        }
        table.dataSource = self;table.delegate = self;table.rowHeight = 22;table.selectionHighlightStyle = .none
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 620, height: 300))
        scroll.documentView = table;scroll.hasVerticalScroller = true;scroll.borderType = .bezelBorder
        scroll.translatesAutoresizingMaskIntoConstraints = false
        countLabel.font = .systemFont(ofSize: 12);countLabel.textColor = .secondaryLabelColor
        let stack = NSStackView(views: [radios, scroll, countLabel])
        stack.orientation = .vertical;stack.alignment = .leading;stack.spacing = 8
        stack.frame = NSRect(x: 0, y: 0, width: 620, height: 370)
        NSLayoutConstraint.activate([scroll.widthAnchor.constraint(equalToConstant: 620), scroll.heightAnchor.constraint(equalToConstant: 300)])
        return stack
    }

    @objc func choose(_ sender: NSButton) {
        choice = sender === currentRadio ? .single : (sender === allRadio ? .all : .some)
        refresh()
    }

    func refresh() {
        currentRadio.state = choice == .single ? .on : .off
        allRadio.state = choice == .all ? .on : .off
        someRadio.state = choice == .some ? .on : .off
        table.reloadData()
        let n = choice == .single ? 1 : Self.selected(choice, entries: entries, checked: checked).count
        countLabel.stringValue = choice == .single ? "只下载当前这 1 条，按普通单条处理。"
            : "已选 \(n) 条。文件名带序号，生成 index.csv，可断点续跑，单条失败不影响其他条目"
              + (n >= Self.batchThreshold ? "；已达 \(Self.batchThreshold) 条，走批量档。" : "。")
    }

    func numberOfRows(in tableView: NSTableView) -> Int {return entries.count}

    func tableView(_ tableView: NSTableView, viewFor column: NSTableColumn?, row: Int) -> NSView? {
        let entry = entries[row]
        let index = entry["index"] as? Int ?? row + 1
        switch column?.identifier.rawValue {
        case "check":
            let box = NSButton(checkboxWithTitle: "", target: self, action: #selector(toggle(_:)))
            box.tag = index
            box.isEnabled = choice == .some
            box.state = choice == .single ? ((info["current_index"] as? Int) == index ? .on : .off)
                : (choice == .all || checked.contains(index) ? .on : .off)
            return box
        case "index":
            let current = (info["current_index"] as? Int) == index
            return NSTextField(labelWithString: (current ? "▶ " : "") + String(index))
        case "duration":
            guard let seconds = (entry["duration"] as? NSNumber)?.intValue else {return NSTextField(labelWithString: "—")}
            return NSTextField(labelWithString: String(format: "%d:%02d", seconds / 60, seconds % 60))
        default:
            let label = NSTextField(labelWithString: (entry["title"] as? String ?? "")
                + ((entry["unavailable"] as? Bool) == true ? "（不可用）" : ""))
            label.lineBreakMode = .byTruncatingTail
            return label
        }
    }

    @objc func toggle(_ sender: NSButton) {
        if sender.state == .on {checked.insert(sender.tag)} else {checked.remove(sender.tag)}
        refresh()
    }
}
