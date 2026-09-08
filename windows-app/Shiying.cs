using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Web.Script.Serialization;

class Shiying : Form {
    TextBox input=new TextBox(), log=new TextBox(), folder=new TextBox();
    ComboBox mode=new ComboBox(), quality=new ComboBox(), cookies=new ComboBox(), strategy=new ComboBox(), language=new ComboBox();
    CheckBox force=new CheckBox(), redownload=new CheckBox(), collect=new CheckBox(), tikwm=new CheckBox();
    Button start=new Button(), cancel=new Button(); Process running;
    string root=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"resources");
    JavaScriptSerializer json=new JavaScriptSerializer(); Timer clipboard=new Timer();string lastClipboard="";
    [STAThread] static void Main(){Application.EnableVisualStyles();Application.Run(new Shiying());}
    public Shiying(){
        Text="拾影视频下载器 1.5 · Windows 测试版";Width=930;Height=790;
        var panel=new TableLayoutPanel(){Dock=DockStyle.Fill,ColumnCount=1,RowCount=8,Padding=new Padding(12)};Controls.Add(panel);
        panel.Controls.Add(new Label(){Text="粘贴单作品链接或分享文字。运行环境已内置；语音模型首次使用自动下载。",AutoSize=true});
        input.Multiline=true;input.ScrollBars=ScrollBars.Vertical;input.Dock=DockStyle.Fill;input.Height=150;panel.Controls.Add(input);
        var buttons=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};panel.Controls.Add(buttons);
        AddButton(buttons,"粘贴链接",()=>{if(Clipboard.ContainsText())Append(Clipboard.GetText());});
        AddButton(buttons,"添加本地视频",()=>{using(var d=new OpenFileDialog(){Multiselect=true,Filter="视频/书签|*.mp4;*.mkv;*.webm;*.mov;*.webloc;*.url|所有文件|*.*"})if(d.ShowDialog()==DialogResult.OK)foreach(string f in d.FileNames)Append(f);});
        AddButton(buttons,"清空输入",()=>input.Clear());
        collect.Text="收集复制的链接";collect.AutoSize=true;buttons.Controls.Add(collect);
        clipboard.Interval=1000;clipboard.Tick+=(s,e)=>{try{if(collect.Checked && Clipboard.ContainsText()){string t=Clipboard.GetText();if(t!=lastClipboard){lastClipboard=t;foreach(string u in SafeLinks(t))Append(u);}}}catch{}};clipboard.Start();
        var path=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};panel.Controls.Add(path);folder.Width=640;folder.Text=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"VideoExtract");path.Controls.Add(folder);
        AddButton(path,"保存目录",()=>{using(var d=new FolderBrowserDialog())if(d.ShowDialog()==DialogResult.OK)folder.Text=d.SelectedPath;});
        AddButton(path,"打开结果",()=>{Directory.CreateDirectory(folder.Text);Process.Start("explorer.exe",Quote(folder.Text));});
        var opts=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};panel.Controls.Add(opts);
        Setup(opts,mode,new[]{"仅下载","下载并转写","下载、转写和 OCR"});Setup(opts,quality,new[]{"720p","1080p","2160p"});quality.SelectedIndex=1;
        Setup(opts,strategy,new[]{"内核下载","失败后用 IDM","直接用 IDM"});Setup(opts,cookies,new[]{"Edge、Chrome","Chrome、Edge","Edge","Chrome","不使用登录态"});Setup(opts,language,new[]{"自动语种","中文","英文"});
        var flags=new FlowLayoutPanel(){AutoSize=true,Dock=DockStyle.Fill};panel.Controls.Add(flags);
        force.Text="重新处理";redownload.Text="重新下载并备份旧媒体";tikwm.Text="TikWM 第三方备用";
        foreach(var c in new[]{force,redownload,tikwm}){c.AutoSize=true;flags.Controls.Add(c);}
        start.Text="开始下载";start.Click+=async(s,e)=>await Run();flags.Controls.Add(start);cancel.Text="取消";cancel.Enabled=false;cancel.Click+=(s,e)=>Stop();flags.Controls.Add(cancel);
        AddButton(flags,"视频号采集（试验）",()=>new WxWindow(root).Show());
        log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Both;log.Dock=DockStyle.Fill;panel.Controls.Add(log);
        panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,150));for(int i=0;i<4;i++)panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));panel.RowStyles.Add(new RowStyle(SizeType.Percent,100));
        panel.Controls.Add(new Label(){Text="IDM 需自行安装授权；先解析媒体再交接，发送请求不算成功。取消不取消 IDM。",AutoSize=true});
        FormClosing+=(s,e)=>{Stop();clipboard.Stop();};
    }
    static void Setup(Control p,ComboBox box,string[] items){box.DropDownStyle=ComboBoxStyle.DropDownList;box.Items.AddRange(items);box.SelectedIndex=0;box.Width=150;p.Controls.Add(box);}
    public static void AddButton(Control p,string title,Action action){var b=new Button(){Text=title,AutoSize=true};b.Click+=(s,e)=>action();p.Controls.Add(b);}
    void Append(string s){if(!Array.Exists(input.Lines,x=>x==s))input.AppendText((input.Text.Length==0?"":Environment.NewLine)+s);}
    static IEnumerable<string> SafeLinks(string text){
        foreach(System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(text,@"https?://[^\s<>""“”]+")){
            string value=m.Value.TrimEnd('，','。','；','！','、','）',')',']','}','】','》','？','!','?');Uri u;
            if(!Uri.TryCreate(value,UriKind.Absolute,out u)||u.UserInfo.Length>0)continue;
            foreach(string domain in new[]{"youtube.com","youtu.be","bilibili.com","b23.tv","douyin.com","xiaohongshu.com","xhslink.com","weibo.com","weibo.cn","kuaishou.com","instagram.com","tiktok.com","x.com","twitter.com","weixin.qq.com","channels.weixin.qq.com","mp.weixin.qq.com"})
                if(u.Host==domain||u.Host.EndsWith("."+domain)){yield return value;break;}
        }
    }
    public static string Quote(string value){
        var b=new StringBuilder();b.Append('"');int slashes=0;
        foreach(char c in value){
            if(c=='\\'){slashes++;continue;}
            if(c=='"'){b.Append('\\',slashes*2+1);b.Append(c);slashes=0;continue;}
            b.Append('\\',slashes);slashes=0;b.Append(c);
        }
        b.Append('\\',slashes*2);b.Append('"');return b.ToString();
    }
    async Task Run(){
        if(running!=null)return;log.Clear();
        var payload=new Dictionary<string,object>{{"text",input.Text},{"folder",folder.Text},{"mode",mode.SelectedIndex},{"max_res",new[]{720,1080,2160}[quality.SelectedIndex]},{"cookies",new[]{"edge,chrome","chrome,edge","edge","chrome","none"}[cookies.SelectedIndex]},{"youtube_backend",new[]{"core","auto","idm"}[strategy.SelectedIndex]},{"language",new[]{"auto","zh","en"}[language.SelectedIndex]},{"force",force.Checked},{"redownload",redownload.Checked},{"tiktok",tikwm.Checked?"auto":"direct"}};
        try{
            var psi=new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),"-X utf8 -B -u "+Quote(Path.Combine(root,"runner.py"))){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8,WorkingDirectory=root};
            psi.EnvironmentVariables["PYTHONUTF8"]="1";psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
            running=new Process(){StartInfo=psi};running.OutputDataReceived+=(s,e)=>Print(e.Data);running.ErrorDataReceived+=(s,e)=>Print(e.Data);running.Start();running.BeginOutputReadLine();running.BeginErrorReadLine();running.StandardInput.Write(json.Serialize(payload));running.StandardInput.Close();start.Enabled=false;cancel.Enabled=true;
            var proc=running;await Task.Run(()=>proc.WaitForExit());Print("任务进程退出码："+proc.ExitCode);
        }catch(Exception e){Print(e.Message);}finally{running=null;start.Enabled=true;cancel.Enabled=false;}
    }
    void Print(string s){if(s==null||IsDisposed)return;BeginInvoke(new Action(()=>log.AppendText(s+Environment.NewLine)));}
    void Stop(){if(running==null)return;try{Process.Start(new ProcessStartInfo("taskkill.exe","/PID "+running.Id+" /T /F"){UseShellExecute=false,CreateNoWindow=true}).WaitForExit();Print("已取消拾影处理，IDM 下载可能继续。");}catch{}}
}
class WxWindow:Form {
    string root;TextBox log=new TextBox();ComboBox history=new ComboBox();Process service;List<Dictionary<string,object>> items=new List<Dictionary<string,object>>();JavaScriptSerializer json=new JavaScriptSerializer();
    public WxWindow(string r){root=r;Text="视频号采集 · 试验";Width=760;Height=440;var top=new FlowLayoutPanel(){Dock=DockStyle.Top,AutoSize=true};Controls.Add(top);log.Multiline=true;log.ReadOnly=true;log.Dock=DockStyle.Fill;log.ScrollBars=ScrollBars.Vertical;Controls.Add(log);log.BringToFront();
        Shiying.AddButton(top,"启动服务",()=>{if(service!=null&&!service.HasExited)return;service=Process.Start(Info("serve --port 2022 --state "+Shiying.Quote(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Shiying","WxBridge")),false));log.Text="服务启动请求已发送。不会安装证书或修改代理；仍需检查页面连接。";});
        Shiying.AddButton(top,"停止本窗口服务",()=>{StopService();});
        Shiying.AddButton(top,"检查连接",async()=>log.Text=await Call("status --port 2022"));
        Shiying.AddButton(top,"最近观看",async()=>{string text=await Call("history --port 2022");log.Text=text;var d=json.Deserialize<Dictionary<string,object>>(text);items.Clear();history.Items.Clear();if(d.ContainsKey("items"))foreach(var o in (System.Collections.IEnumerable)d["items"]){var item=(Dictionary<string,object>)o;items.Add(item);history.Items.Add(item["author"]+" · "+item["title"]);}if(items.Count>0)history.SelectedIndex=0;});
        history.Width=450;top.Controls.Add(history);Shiying.AddButton(top,"取得并复制链接",async()=>{if(history.SelectedIndex<0)return;string text=await Call("share --port 2022 --oid "+Shiying.Quote(Convert.ToString(items[history.SelectedIndex]["id"])));log.Text=text;var d=json.Deserialize<Dictionary<string,object>>(text);if(d.ContainsKey("share_url"))Clipboard.SetText(Convert.ToString(d["share_url"]));});
        FormClosed+=(s,e)=>{StopService();};
    }
    void StopService(){if(service!=null&&!service.HasExited)Process.Start(new ProcessStartInfo("taskkill.exe","/PID "+service.Id+" /T /F"){UseShellExecute=false,CreateNoWindow=true}).WaitForExit();}
    ProcessStartInfo Info(string args,bool capture){return new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),"-X utf8 -B "+Shiying.Quote(Path.Combine(root,"wx_bridge.py"))+" "+args) {UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=capture,RedirectStandardError=capture,StandardOutputEncoding=capture?Encoding.UTF8:null,WorkingDirectory=root};}
    async Task<string> Call(string args){try{return await Task.Run(()=>{using(var p=Process.Start(Info(" "+args,true))){string s=p.StandardOutput.ReadToEnd();string e=p.StandardError.ReadToEnd();p.WaitForExit();return s.Length>0?s:e;}});}catch(Exception e){return e.Message;}}
}
