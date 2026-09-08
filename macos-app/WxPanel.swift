import AppKit

final class WxPanel: NSObject {
    let panel = NSWindow(contentRect:NSRect(x:0,y:0,width:740,height:370),styleMask:[.titled,.closable],backing:.buffered,defer:false)
    let statusLabel = NSTextField(wrappingLabelWithString:"先在微信打开目标视频，再检查连接。首次接入见连接说明。")
    let port = NSTextField(string:"2022")
    let choices = NSPopUpButton()
    let connect = NSButton(title:"启动连接服务",target:nil,action:nil)
    let stop = NSButton(title:"停止本窗口服务",target:nil,action:nil)
    let refresh = NSButton(title:"检查连接",target:nil,action:nil)
    let recent = NSButton(title:"读取最近观看",target:nil,action:nil)
    let add = NSButton(title:"获取链接并加入队列",target:nil,action:nil)
    var items:[[String:String]]=[]
    var request:Process?
    var service:Process?
    var timer:Timer?
    let onLink:(String)->Void
    let state=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/拾影/WxBridge")
    init(onLink:@escaping (String)->Void) {
        self.onLink=onLink
        super.init()
        panel.title="视频号采集 · 试验功能";panel.isReleasedWhenClosed=false
        let root=NSStackView();root.orientation = .vertical;root.alignment = .leading;root.spacing=14;root.translatesAutoresizingMaskIntoConstraints=false
        panel.contentView!.addSubview(root)
        NSLayoutConstraint.activate([root.leadingAnchor.constraint(equalTo:panel.contentView!.leadingAnchor,constant:22),root.trailingAnchor.constraint(equalTo:panel.contentView!.trailingAnchor,constant:-22),root.topAnchor.constraint(equalTo:panel.contentView!.topAnchor,constant:22)])
        root.addArrangedSubview(NSTextField(labelWithString:"微信打开视频 → 连接页面 → 选择作品 → 获取分享链接"))
        let hint=NSTextField(wrappingLabelWithString:"首次使用仍需完成微信页面接入。连接服务本身不修改代理或证书，也不会自动下载。")
        hint.textColor = .secondaryLabelColor;root.addArrangedSubview(hint)
        port.widthAnchor.constraint(equalToConstant:70).isActive=true
        let row=NSStackView(views:[NSTextField(labelWithString:"本机 API 端口"),port,connect,stop,refresh]);row.spacing=8;root.addArrangedSubview(row)
        statusLabel.font = .systemFont(ofSize:13);root.addArrangedSubview(statusLabel)
        choices.addItem(withTitle:"尚未读取作品");choices.isEnabled=false
        root.addArrangedSubview(choices)
        let actions=NSStackView(views:[recent,add]);actions.spacing=10;root.addArrangedSubview(actions)
        let help=NSButton(title:"连接说明",target:self,action:#selector(showHelp))
        let wechat=NSButton(title:"打开微信",target:self,action:#selector(openWechat))
        let files=NSButton(title:"打开服务下载目录",target:self,action:#selector(openDownloads))
        let bottom=NSStackView(views:[wechat,help,files]);bottom.spacing=10;root.addArrangedSubview(bottom)
        for v in [hint,statusLabel,choices] {v.widthAnchor.constraint(equalTo:root.widthAnchor).isActive=true}
        for (b,action) in [(connect,#selector(startService)),(stop,#selector(stopService)),(refresh,#selector(check)),(recent,#selector(loadHistory)),(add,#selector(addSelected))] {b.target=self;b.action=action;b.bezelStyle = .rounded}
        stop.isEnabled=false;recent.isEnabled=false;add.isEnabled=false
    }
    func show() {panel.center();panel.makeKeyAndOrderFront(nil);check()}
    func selectedPort()->Int? {
        guard let n=Int(port.stringValue),n>0,n<=65535 else {statusLabel.stringValue="API 端口必须为 1–65535";return nil};return n
    }
    func launch(_ args:[String], completion:@escaping ([String:Any])->Void) {
        guard request == nil,let script=Bundle.main.url(forResource:"wx_bridge",withExtension:"py"),let n=selectedPort() else{return}
        let p=Process(),pipe=Pipe();p.executableURL=Bundle.main.resourceURL!.appendingPathComponent("runtime/bin/python3")
        p.arguments=["-B",script.path]+args+["--port",String(n)];p.standardOutput=pipe;p.standardError=FileHandle.nullDevice
        request=p;refresh.isEnabled=false;recent.isEnabled=false;add.isEnabled=false;connect.isEnabled=false;port.isEnabled=false
        statusLabel.stringValue="正在请求连接服务…"
        do {try p.run()} catch {request=nil;refresh.isEnabled=true;connect.isEnabled=service==nil;port.isEnabled=service==nil;statusLabel.stringValue="无法启动连接检查：\(error.localizedDescription)";return}
        DispatchQueue.global().async {
            let data=pipe.fileHandleForReading.readDataToEndOfFile();p.waitUntilExit()
            let result=(try? JSONSerialization.jsonObject(with:data) as? [String:Any]) ?? ["status":"failed","message":"连接组件未返回有效结果"]
            DispatchQueue.main.async {
                self.request=nil;self.refresh.isEnabled=true;self.connect.isEnabled=self.service==nil;self.port.isEnabled=self.service==nil
                self.statusLabel.stringValue=result["message"] as? String ?? "请求完成"
                completion(result)
            }
        }
    }
    @objc func check() {launch(["status"]) {r in self.recent.isEnabled=r["status"] as? String == "page_connected";self.add.isEnabled=false}}
    @objc func loadHistory() {
        launch(["history"]) {r in
            self.items=r["items"] as? [[String:String]] ?? [];self.choices.removeAllItems()
            for item in self.items {self.choices.addItem(withTitle:"\(item["author"] ?? "") · \(item["title"] ?? "")")}
            if self.items.isEmpty {self.choices.addItem(withTitle:"没有可选作品")}
            self.choices.isEnabled = !self.items.isEmpty;self.add.isEnabled = !self.items.isEmpty
            self.recent.isEnabled=(r["status"] as? String ?? "").hasPrefix("history_")
        }
    }
    @objc func addSelected() {
        let i=choices.indexOfSelectedItem;guard items.indices.contains(i),let oid=items[i]["id"] else{return}
        launch(["share","--oid",oid]) {r in
            if r["status"] as? String == "share_resolved",let link=r["share_url"] as? String {self.onLink(link);self.recent.isEnabled=true;self.add.isEnabled=true}
        }
    }
    @objc func startService() {
        guard service==nil,let n=selectedPort(),let script=Bundle.main.url(forResource:"wx_bridge",withExtension:"py") else{return}
        do {
            try FileManager.default.createDirectory(at:state,withIntermediateDirectories:true)
            let log=state.appendingPathComponent("service-\(Int(Date().timeIntervalSince1970)).log")
            FileManager.default.createFile(atPath:log.path,contents:nil)
            let output=try FileHandle(forWritingTo:log)
            let p=Process();p.executableURL=Bundle.main.resourceURL!.appendingPathComponent("runtime/bin/python3")
            p.arguments=["-B",script.path,"serve","--port",String(n),"--state",state.path];p.standardOutput=output;p.standardError=output;p.standardInput=FileHandle.nullDevice
            p.terminationHandler={proc in
                try? output.close()
                DispatchQueue.main.async {self.service=nil;self.connect.isEnabled=self.request==nil;self.port.isEnabled=self.request==nil;self.stop.isEnabled=false;self.recent.isEnabled=false;self.add.isEnabled=false;self.statusLabel.stringValue="本窗口服务已停止；如启动失败，请查看 \(log.lastPathComponent)"}
            }
            try p.run();service=p;connect.isEnabled=false;port.isEnabled=false;stop.isEnabled=true
            statusLabel.stringValue="正在启动连接服务；未修改系统代理或证书。"
            timer?.invalidate();timer=Timer.scheduledTimer(withTimeInterval:2,repeats:false){_ in self.check()}
        } catch {statusLabel.stringValue="服务启动失败：\(error.localizedDescription)"}
    }
    @objc func stopService() {timer?.invalidate();service?.terminate();stop.isEnabled=false}
    func shutdown() {timer?.invalidate();request?.terminate();service?.terminate()}
    @objc func showHelp() {if let url=Bundle.main.url(forResource:"视频号连接说明",withExtension:"html") {NSWorkspace.shared.open(url)}}
    @objc func openWechat() {if let url=NSWorkspace.shared.urlForApplication(withBundleIdentifier:"com.tencent.xinWeChat") {NSWorkspace.shared.open(url)}}
    @objc func openDownloads() {let dir=state.appendingPathComponent("downloads");try? FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true);NSWorkspace.shared.open(dir)}
}
