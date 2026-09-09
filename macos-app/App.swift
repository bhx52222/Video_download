import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    let input = NSTextView(), logView = NSTextView()
    let mode = NSPopUpButton(), cookie = NSPopUpButton(), language = NSPopUpButton(), quality = NSPopUpButton()
    let youtubeBackend = NSPopUpButton()
    var wxPanel: WxPanel?
    var handoffToken = ""
    let youtubeCookies = NSButton(checkboxWithTitle:"YouTube 优先使用登录态",target:nil,action:nil)
    let redownload = NSButton(checkboxWithTitle:"重新下载媒体（旧文件备份）",target:nil,action:nil)
    let collect = NSButton(checkboxWithTitle:"收集复制的链接（不自动下载）",target:nil,action:nil)
    var clipboardTimer: Timer?
    var clipboardChange = 0
    let fallback = NSButton(checkboxWithTitle: "TikTok 使用备用解析（TikWM，只发送链接）", target: nil, action: nil)
    let force = NSButton(checkboxWithTitle: "重新处理已有结果", target: nil, action: nil)
    let folderLabel = NSTextField(labelWithString: "")
    let status = NSTextField(labelWithString: "准备就绪")
    let start = NSButton(title: "开始下载", target: nil, action: nil)
    let cancel = NSButton(title: "取消任务", target: nil, action: nil)
    let progress = NSProgressIndicator()
    var folder = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("VideoExtract")
    var task: Process?
    var outputPipe: Pipe?
    var cancelRequested = false
    var pendingOutput = Data()

    func label(_ text: String, size: CGFloat = 13, bold: Bool = false) -> NSTextField {
        let v = NSTextField(labelWithString: text)
        v.font = bold ? .systemFont(ofSize: size, weight: .semibold) : .systemFont(ofSize: size)
        v.lineBreakMode = .byTruncatingMiddle
        return v
    }
    func row(_ views: [NSView]) -> NSStackView {
        let s=NSStackView(views:views); s.orientation = .horizontal; s.spacing=10; s.alignment = .centerY
        return s
    }
    func button(_ title: String, _ action: Selector) -> NSButton {
        let b=NSButton(title:title,target:self,action:action);b.bezelStyle = .rounded;return b
    }
    func scroll(_ text: NSTextView, editable: Bool, height: CGFloat) -> NSScrollView {
        let s=NSScrollView();s.hasVerticalScroller=true;s.borderType = .bezelBorder
        text.isEditable=editable;text.isRichText=false;text.isAutomaticQuoteSubstitutionEnabled=false
        text.isAutomaticDashSubstitutionEnabled=false;text.font = .monospacedSystemFont(ofSize:12,weight:.regular)
        text.textContainerInset=NSSize(width:12,height:12);text.autoresizingMask = [.width]
        text.isVerticallyResizable=true;text.isHorizontallyResizable=false
        text.textContainer?.widthTracksTextView=true;s.documentView=text
        s.heightAnchor.constraint(equalToConstant:height).isActive=true
        return s
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        if let saved=UserDefaults.standard.string(forKey:"outputFolder") {folder=URL(fileURLWithPath:saved)}
        window=NSWindow(contentRect:NSRect(x:0,y:0,width:900,height:880),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.title="拾影 · 视频下载器";window.minSize=NSSize(width:790,height:880);window.delegate=self
        let root=NSStackView();root.orientation = .vertical;root.alignment = .leading;root.spacing=10;root.translatesAutoresizingMaskIntoConstraints=false
        window.contentView!.addSubview(root)
        NSLayoutConstraint.activate([root.leadingAnchor.constraint(equalTo:window.contentView!.leadingAnchor,constant:26),root.trailingAnchor.constraint(equalTo:window.contentView!.trailingAnchor,constant:-26),root.topAnchor.constraint(equalTo:window.contentView!.topAnchor,constant:22)])
        let title=label("拾影",size:29,bold:true)
        let subtitle=label("把视频存下来，把内容留下来。",size:14);subtitle.textColor = .secondaryLabelColor
        root.addArrangedSubview(row([title,subtitle]))
        root.addArrangedSubview(label("粘贴视频或文章链接，可多行批量下载，也可添加本地视频。"))
        let inputScroll=scroll(input,editable:true,height:110);root.addArrangedSubview(inputScroll)
        root.addArrangedSubview(row([button("粘贴链接",#selector(pasteLinks)),button("添加本地视频",#selector(addFiles)),button("清空输入",#selector(clearInput)),button("平台与帮助",#selector(help)),button("视频号采集…",#selector(showWx))]))
        mode.addItems(withTitles:["仅下载","下载并转写","下载、转写和 OCR"])
        cookie.addItems(withTitles:["Edge → Chrome","Chrome → Edge","仅 Edge","仅 Chrome","不使用 Cookie"])
        language.addItems(withTitles:["自动语种","中文","英文"])
        root.addArrangedSubview(row([label("处理方式"),mode,label("登录浏览器"),cookie,label("语种"),language]))
        quality.addItems(withTitles:["1080p","720p","2160p / 4K"])
        root.addArrangedSubview(row([label("画质上限"),quality,youtubeCookies]))
        collect.target=self;collect.action=#selector(toggleCollection)
        root.addArrangedSubview(row([fallback,force]))
        youtubeBackend.addItems(withTitles:["内核下载","失败后用 Downie 4","直接用 Downie 4"])
        root.addArrangedSubview(row([redownload,label("YouTube"),youtubeBackend]))
        root.addArrangedSubview(row([collect,label("复制支持平台的链接 → 自动加入输入区",size:12)]))
        let note=label("视频号需分享链接与元宝登录态；快手支持公开作品链接。机器文字需核对。",size:12);note.textColor = .secondaryLabelColor;root.addArrangedSubview(note)
        folderLabel.stringValue=folder.path;folderLabel.lineBreakMode = .byTruncatingMiddle
        let folderRow=row([label("保存到"),folderLabel,button("更改…",#selector(chooseFolder)),button("打开目录",#selector(openFolder))]);root.addArrangedSubview(folderRow)
        folderLabel.setContentCompressionResistancePriority(.defaultLow,for:.horizontal)
        start.target=self;start.action=#selector(runTask);start.bezelStyle = .rounded;start.keyEquivalent="\r";start.bezelColor = .systemBlue
        cancel.target=self;cancel.action=#selector(cancelTask);cancel.bezelStyle = .rounded;cancel.isEnabled=false
        progress.style = .spinning;progress.controlSize = .small;progress.isDisplayedWhenStopped=false
        root.addArrangedSubview(row([start,cancel,progress,status]))
        let logScroll=scroll(logView,editable:false,height:175);root.addArrangedSubview(logScroll)
        for v in [inputScroll,folderRow,logScroll] {v.widthAnchor.constraint(equalTo:root.widthAnchor).isActive=true}
        let bottom=label("原生 macOS 应用 · 本机处理 · 文件保存在你选择的目录",size:11);bottom.textColor = .tertiaryLabelColor;root.addArrangedSubview(bottom)
        let menu=NSMenu();let appItem=NSMenuItem();menu.addItem(appItem);let appMenu=NSMenu();appItem.submenu=appMenu
        appMenu.addItem(withTitle:"关于拾影",action:#selector(about),keyEquivalent:"").target=self
        appMenu.addItem(.separator());appMenu.addItem(withTitle:"退出拾影",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q")
        let editItem=NSMenuItem();editItem.title="编辑";menu.addItem(editItem);let edit=NSMenu(title:"编辑");editItem.submenu=edit
        for (name,action,key) in [("撤销","undo:","z"),("剪切","cut:","x"),("复制","copy:","c"),("粘贴","paste:","v"),("全选","selectAll:","a")] {edit.addItem(withTitle:name,action:Selector(action),keyEquivalent:key)}
        NSApp.mainMenu=menu;window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
        append("粘贴链接后点击“开始下载”。\nTikTok 直接路径失败时，可勾选备用解析再试。\n")
    }
    func consume(_ data: Data, final: Bool = false) {
        pendingOutput.append(data)
        if final {append(String(decoding:pendingOutput,as:UTF8.self));pendingOutput.removeAll();return}
        if let last=pendingOutput.lastIndex(of:10) {
            let end=pendingOutput.index(after:last)
            append(String(decoding:pendingOutput[..<end],as:UTF8.self));pendingOutput.removeSubrange(..<end)
        }
    }
    func append(_ text: String) {
        if text.hasPrefix("@@VX_DOWNIE@@"), let data=String(text.dropFirst(13)).data(using:.utf8),
           let job=try? JSONSerialization.jsonObject(with:data) as? [String:String],job["token"]==handoffToken,
           let source=job["url"],let destination=job["destination"],
           let u=URL(string:source),u.scheme=="https",let host=u.host,
           (host=="youtu.be" || host=="youtube.com" || host.hasSuffix(".youtube.com")),
           destination.hasPrefix(folder.appendingPathComponent(".external-downie").path+"/") {
            var c=URLComponents();c.scheme="downie";c.host="XUOpenURL"
            c.queryItems=[URLQueryItem(name:"url",value:source),URLQueryItem(name:"destination",value:destination),URLQueryItem(name:"postprocessing",value:"mp4")]
            let allowed=CharacterSet(charactersIn:"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
            c.percentEncodedQuery=c.queryItems?.map { "\($0.name)=\(($0.value ?? "").addingPercentEncoding(withAllowedCharacters:allowed) ?? "")" }.joined(separator:"&")
            if let link=c.url, let application=NSWorkspace.shared.urlForApplication(toOpen:link),
               Bundle(url:application)?.bundleIdentifier == "com.charliemonroe.Downie-4" {
                if NSWorkspace.shared.open(link) {append("已向 Downie 4 发送请求；等待实际视频后才计为完成。\n")}
                else {append("Downie 未接受打开请求，请取消等待。\n")}
            }else{append("downie:// 当前未关联到 Downie 4，请取消等待并检查应用关联。\n")}
            return
        }
        let trimmed=text.replacingOccurrences(of:"\r",with:"\n")
        logView.textStorage?.append(NSAttributedString(string:trimmed,attributes:[.font:NSFont.monospacedSystemFont(ofSize:11,weight:.regular),.foregroundColor:NSColor.labelColor]))
        if let storage=logView.textStorage, storage.length>120000 {storage.deleteCharacters(in:NSRange(location:0,length:storage.length-100000))}
        logView.scrollToEndOfDocument(nil)
    }
    func alert(_ title: String, _ body: String) {let a=NSAlert();a.messageText=title;a.informativeText=body;a.runModal()}
    func clipboardText() -> String {
        let p=NSPasteboard.general
        return [p.string(forType:.string),p.string(forType:.URL),p.string(forType:.html)].compactMap{$0}.joined(separator:"\n")
    }
    func addLinks(_ links:[String]) {
        let existing=Set(LinkTools.extractAny(input.string));let fresh=links.filter{!existing.contains($0)}
        if !fresh.isEmpty {input.string += (input.string.isEmpty ? "" : "\n")+fresh.joined(separator:"\n");append("已加入 \(fresh.count) 条链接；点击开始下载时处理。\n")}
    }
    @objc func pasteLinks() {
        let links=LinkTools.extractAny(clipboardText())
        if links.isEmpty {alert("剪贴板里没有网址","视频号卡片或 #视频号 口令不等于分享网址。请在视频的分享菜单寻找“复制链接”；如果当前版本没有该选项，不能仅凭标题生成下载链接。");return}
        addLinks(links)
        let unknown=LinkTools.unknownPlatform(links)
        if !unknown.isEmpty {append("其中 \(unknown.count) 条不在已知平台列表内，将交给内核通用解析尝试，未必成功。\n")}
    }
    @objc func toggleCollection() {
        clipboardTimer?.invalidate();clipboardTimer=nil
        if collect.state == .on {
            clipboardChange=NSPasteboard.general.changeCount
            clipboardTimer=Timer.scheduledTimer(withTimeInterval:1,repeats:true){_ in
                let count=NSPasteboard.general.changeCount
                if count != self.clipboardChange {self.clipboardChange=count;self.addLinks(LinkTools.extract(self.clipboardText()))}
            }
            append("已开启链接收集：仅加入支持平台的网址，其他剪贴板内容不保存；不会自动下载。\n")
            // 先复制链接、再勾选是常见顺序；只等下一次变化会让这一条永远收不到。
            addLinks(LinkTools.extract(clipboardText()))
        } else {
            append("已停止链接收集。\n")
        }
    }
    @objc func clearInput() {input.string=""}
    @objc func addFiles() {
        let panel=NSOpenPanel();panel.allowsMultipleSelection=true;panel.canChooseDirectories=false
        panel.beginSheetModal(for:window) {response in if response == .OK {self.input.string += (self.input.string.isEmpty ? "" : "\n")+panel.urls.map(\.path).joined(separator:"\n")}}
    }
    @objc func chooseFolder() {
        let p=NSOpenPanel();p.canChooseFiles=false;p.canChooseDirectories=true;p.canCreateDirectories=true;p.directoryURL=folder
        p.beginSheetModal(for:window) {r in if r == .OK,let u=p.url {self.folder=u;self.folderLabel.stringValue=u.path;UserDefaults.standard.set(u.path,forKey:"outputFolder")}}
    }
    @objc func openFolder() {do {try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true);NSWorkspace.shared.open(folder)}catch{alert("无法打开目录",error.localizedDescription)}}
    @objc func help() {if let u=Bundle.main.url(forResource:"使用说明",withExtension:"html") {NSWorkspace.shared.open(u)}}
    @objc func showWx() {
        if wxPanel == nil {wxPanel=WxPanel(onLink:{[weak self] link in self?.addLinks([link])})}
        wxPanel?.show()
    }
    @objc func about() {alert("拾影 · 视频下载器 1.5 测试版","为这台 Mac 构建，内置独立运行环境。支持链接队列、下载、转写与 OCR。\n第三方代码来源及许可见应用帮助。")}
    @objc func runTask() {
        guard task == nil else {return}
        guard !input.string.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else {alert("请先添加链接","也可以选择一个本地视频。");return}
        let python=Bundle.main.resourceURL!.appendingPathComponent("runtime/bin/python3")
        guard FileManager.default.isExecutableFile(atPath:python.path),let runner=Bundle.main.url(forResource:"runner",withExtension:"py") else {alert("处理环境不可用","安装包内运行环境缺失，请重新下载完整安装包。");return}
        let cookies=["edge,chrome","chrome,edge","edge","chrome","none"]
        handoffToken=UUID().uuidString
        let payload:[String:Any]=["youtube_backend":["core","auto","downie"][youtubeBackend.indexOfSelectedItem],"handoff_token":handoffToken,"text":input.string,"folder":folder.path,"mode":mode.indexOfSelectedItem,"cookies":cookies[cookie.indexOfSelectedItem],"language":["auto","zh","en"][language.indexOfSelectedItem],"tiktok":fallback.state == .on ? "tikwm" : "direct","force":force.state == .on,"redownload":redownload.state == .on,"max_res":[1080,720,2160][quality.indexOfSelectedItem],"youtube_cookies":youtubeCookies.state == .on]
        let p=Process(), stdin=Pipe(), stdout=Pipe();p.executableURL=python;p.arguments=["-B","-u",runner.path]
        var env=ProcessInfo.processInfo.environment;let home=FileManager.default.homeDirectoryForCurrentUser.path
        env["PATH"]="/usr/bin:/bin:/usr/sbin:/sbin";env["PYTHONUNBUFFERED"]="1";env["PYTHONDONTWRITEBYTECODE"]="1";env["LANG"]="en_US.UTF-8"
        p.environment=env;p.standardInput=stdin;p.standardOutput=stdout;p.standardError=stdout
        outputPipe=stdout;cancelRequested=false;logView.string="";pendingOutput.removeAll()
        stdout.fileHandleForReading.readabilityHandler={handle in let data=handle.availableData;if !data.isEmpty {DispatchQueue.main.async {self.consume(data)}}}
        p.terminationHandler={process in
            stdout.fileHandleForReading.readabilityHandler=nil
            let remaining=stdout.fileHandleForReading.readDataToEndOfFile()
            DispatchQueue.main.async {
                self.consume(remaining,final:true)
                self.task=nil;self.outputPipe=nil;self.start.isEnabled=true;self.cancel.isEnabled=false;self.progress.stopAnimation(nil)
                self.status.stringValue=self.cancelRequested ? "已取消" : (process.terminationStatus == 0 ? "处理完成" : "部分任务失败，请查看日志")
            }
        }
        do {
            task=p;try p.run();start.isEnabled=false;cancel.isEnabled=true;progress.startAnimation(nil);status.stringValue="正在处理…"
            let data=try JSONSerialization.data(withJSONObject:payload);stdin.fileHandleForWriting.write(data);try stdin.fileHandleForWriting.close()
        }catch{task=nil;stdout.fileHandleForReading.readabilityHandler=nil;alert("无法启动",error.localizedDescription)}
    }
    @objc func cancelTask() {guard let p=task else{return};cancelRequested=true;cancel.isEnabled=false;status.stringValue="正在取消…";p.terminate()}
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        wxPanel?.shutdown()
        if let p=task {cancelRequested=true;p.terminate()};return .terminateNow
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{return true}
}
@main
struct Main {
    static func main() {
let app=NSApplication.shared
app.setActivationPolicy(.regular)
let delegate=AppDelegate();app.delegate=delegate;app.run()

    }
}
