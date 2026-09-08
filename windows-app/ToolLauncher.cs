using System;using System.IO;using System.Text;using System.Diagnostics;
class ToolLauncher {
 static string Q(string v){var b=new StringBuilder();b.Append('"');int n=0;foreach(char c in v){if(c=='\\'){n++;continue;}if(c=='"'){b.Append('\\',2*n+1);b.Append(c);n=0;continue;}b.Append('\\',n);n=0;b.Append(c);}b.Append('\\',n*2);b.Append('"');return b.ToString();}
 static int Main(string[] args){string root=Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,".."));var b=new StringBuilder("-B -m yt_dlp");foreach(string a in args)b.Append(" "+Q(a));using(var p=Process.Start(new ProcessStartInfo(Path.Combine(root,"runtime","python.exe"),b.ToString()){UseShellExecute=false})){p.WaitForExit();return p.ExitCode;}}
}
