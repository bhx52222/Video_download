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
subprocess.run(['xcrun','swiftc','-swift-version','5','-target','arm64-apple-macos14.0','-O','-framework','AppKit',str(ROOT/'App.swift'),str(ROOT/'LinkTools.swift'),str(ROOT/'Runtime.swift'),str(ROOT/'WxPanel.swift'),'-o',str(mac/'Shiying')],check=True)
shutil.copy(ROOT/'runner.py',resources/'runner.py')
shutil.copy(ROOT/'downie_bridge.py',resources/'downie_bridge.py')
shutil.copy(ROOT/'wx_bridge.py',resources/'wx_bridge.py')
shutil.copy(ROOT/'视频号连接说明.html',resources/'视频号连接说明.html')
shutil.copytree(ROOT/'external',resources/'external',dirs_exist_ok=True)
for name in ('vx.py','vx_link.py','vx_runtime.py','vx_process.py','vx_tiktok.py','vx_wxchannels.py','vx_browser_cookie.py','vx_kuaishou.py'):
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
# 自带运行时（一体化包）。没组装过就照旧出依赖本机 ~/.vx 的版本，
# 不因此让构建失败——两种包都要能出。Runtime.swift 按包内有没有
# python/bin/python3 自行判断走哪条路。
runtime=ROOT.parent/'work/runtime'
bundled=(runtime/'python/bin/python3').is_file()
# 先清干净。上一次构建留下的 runtime/ 不删，会出两种错：切回依赖环境的版本时
# 包里还带着旧运行时，以及重新组装后被删掉的文件仍留在包内。
if (resources/'runtime').exists():
 shutil.rmtree(resources/'runtime')
if bundled:
 # symlinks=True 必须带：Python 发行版里 python3 → python3.12 之类是符号链接，
 # 实体化会让体积翻倍，还可能让相对定位失效。
 shutil.copytree(runtime,resources/'runtime',symlinks=True)
info={'CFBundleExecutable':'Shiying','CFBundleIdentifier':'local.beibei.shiying.preview','CFBundleName':'拾影视频下载器','CFBundleDisplayName':'拾影视频下载器','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.4.1','CFBundleVersion':'6','CFBundleIconFile':'App','LSMinimumSystemVersion':'14.0','NSHighResolutionCapable':True,'NSPrincipalClass':'NSApplication'}
with (contents/'Info.plist').open('wb') as f:plistlib.dump(info,f)
# 只清我们自己代码产生的缓存。runtime/ 里 site-packages 的 __pycache__ 是
# 上游装出来的，删了只会让首次启动变慢，而且那底下有上万个文件，遍历很费时。
for folder in (resources,resources/'backend'):
 for cache in folder.glob('__pycache__'):
  shutil.rmtree(cache)
subprocess.run(['codesign','--force','--deep','--sign','-',str(APP)],check=True)
print(APP)
if bundled:
 manifest=json.loads((runtime/'manifest.json').read_text())
 total=sum(f.stat().st_size for f in APP.rglob('*') if f.is_file())
 print(f"一体化包：自带 Python {manifest['python']}、yt-dlp {manifest['yt_dlp']}、"
       f"ffmpeg 及 {len(manifest['ffmpeg_libs'])} 个依赖库，共 {total/1024/1024:.0f} MB")
 print('验证：python3 scripts/verify_bundle.py')
else:
 print('依赖本机 ~/.vx 的版本。要出一体化包先跑 python3 scripts/bundle_runtime.py')
