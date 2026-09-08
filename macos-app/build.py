from pathlib import Path
import plistlib,shutil,subprocess,json,hashlib
from check_backend import require_current
require_current()  # Fail before any bundle writes if Claude's source has drifted.
ROOT=Path(__file__).resolve().parent
BACKEND=ROOT/'backend'
helper=ROOT/'external/wx_channels_download'
manifest=json.loads((helper/'provenance.json').read_text())
if not (helper/'wx_video_download').is_file():
 raise RuntimeError('先运行 python3 scripts/fetch_wx_helper.py 获取固定版本连接组件')
if hashlib.sha256((helper/'wx_video_download').read_bytes()).hexdigest()!=manifest['binary_sha256']:
 raise RuntimeError('视频号连接组件哈希不符，停止构建')
APP=ROOT.parent/'outputs/拾影视频下载器-1.4.1测试版.app'
contents=APP/'Contents'; resources=contents/'Resources'; mac=contents/'MacOS'
for p in (resources/'backend',mac):p.mkdir(parents=True,exist_ok=True)
subprocess.run(['xcrun','swiftc','-swift-version','5','-target','arm64-apple-macos14.0','-O','-framework','AppKit',str(ROOT/'App.swift'),str(ROOT/'LinkTools.swift'),str(ROOT/'WxPanel.swift'),'-o',str(mac/'Shiying')],check=True)
shutil.copy(ROOT/'runner.py',resources/'runner.py')
shutil.copy(ROOT/'downie_bridge.py',resources/'downie_bridge.py')
shutil.copy(ROOT/'wx_bridge.py',resources/'wx_bridge.py')
shutil.copy(ROOT/'视频号连接说明.html',resources/'视频号连接说明.html')
shutil.copytree(ROOT/'external',resources/'external',dirs_exist_ok=True)
for name in ('vx.py','vx_tiktok.py','vx_wxchannels.py','vx_browser_cookie.py','vx_kuaishou.py'):
 shutil.copy(BACKEND/name,resources/'backend'/name)
shutil.copytree(BACKEND/'vendor',resources/'backend/vendor',dirs_exist_ok=True)
iconWork=ROOT.parent/'work/macos-app'
iconWork.mkdir(parents=True,exist_ok=True)
if not (iconWork/'App.icns').exists():
 subprocess.run(['xcrun','swiftc','-swift-version','5','-framework','AppKit',str(ROOT/'Icon.swift'),'-o',str(iconWork/'icon-builder')],check=True)
 subprocess.run([str(iconWork/'icon-builder'),str(iconWork/'App.iconset')],check=True)
 subprocess.run(['iconutil','-c','icns',str(iconWork/'App.iconset'),'-o',str(iconWork/'App.icns')],check=True)
shutil.copy(iconWork/'App.icns',resources/'App.icns')
shutil.copy(ROOT/'使用说明.html',resources/'使用说明.html')
info={'CFBundleExecutable':'Shiying','CFBundleIdentifier':'local.beibei.shiying.preview','CFBundleName':'拾影视频下载器','CFBundleDisplayName':'拾影视频下载器','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.4.1','CFBundleVersion':'6','CFBundleIconFile':'App','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication'}
with (contents/'Info.plist').open('wb') as f:plistlib.dump(info,f)
for cache in resources.rglob('__pycache__'):
 shutil.rmtree(cache)
subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
print(APP)
