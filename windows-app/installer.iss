#define AppVersion "1.5.0"
#ifndef BundleRoot
#define BundleRoot "..\outputs\Shiying-Windows"
#endif
[Setup]
AppId=Shiying.VideoDownloader
AppName=拾影视频下载器
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Shiying
DefaultGroupName=拾影视频下载器
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\outputs
OutputBaseFilename=Shiying-1.5-Windows-x64-Setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Shiying.exe
[Files]
Source: "{#BundleRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\拾影视频下载器"; Filename: "{app}\Shiying.exe"
Name: "{autodesktop}\拾影视频下载器"; Filename: "{app}\Shiying.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; Flags: unchecked
[Run]
Filename: "{app}\Shiying.exe"; Description: "打开拾影视频下载器"; Flags: nowait postinstall skipifsilent
