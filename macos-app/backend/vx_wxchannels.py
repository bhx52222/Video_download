import os
"""Share URL adapter based on researched Tencent API flows in:
ltaoo/wx_channels_download pkg/scraper/wxchannels/yuanbao.go,
oliver-zch/wx-video-channel-download internal/service/sph.go.
No MITM or service. Cookies stay in memory and only go to yuanbao.tencent.com.
"""
import argparse
import copy
import json
import re
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
# truststore 让 Python 走系统钥匙串里的根证书。装了 Surge 的 MITM CA 之后，
# 抓流拿到的直链才验得过。但它只服务于少数几个下载路径，
# 没有理由因为它缺席就让整个程序起不来——上一版是顶层裸 import，
# 结果 venv 里没装的时候，vx 的每一条命令都 ImportError。
try:
    import truststore
    HAS_TRUSTSTORE = True
except ImportError:
    truststore = None
    HAS_TRUSTSTORE = False

SRC = Path(__file__).resolve().parent
CONTEXT = (truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
           if HAS_TRUSTSTORE else ssl.create_default_context())
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'


def is_share_url(url):
    u = urlsplit(url)
    return u.scheme == 'https' and not u.username and (
        (u.hostname == 'weixin.qq.com' and bool(re.fullmatch(r'/sph/[A-Za-z0-9_-]+/?', u.path))) or
        (u.hostname == 'channels.weixin.qq.com' and u.path in
         ('/finder-preview/pages/sph', '/finder-preview/pages/feed', '/web/pages/feed')))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_json(url, data, referer, cookie=None):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'User-Agent': UA, 'Referer': referer,
               'Origin': 'https://' + urlsplit(url).netloc}
    if cookie:
        if urlsplit(url).hostname != 'yuanbao.tencent.com':
            raise ValueError('Cookie destination rejected')
        headers['Cookie'] = cookie
    request = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=CONTEXT))
    with opener.open(request, timeout=30) as response:
        return json.loads(response.read(4 * 1024 * 1024))


def read_cookie(browser):
    if browser == 'none':
        return ''
    if browser not in ('edge', 'chrome', 'safari', 'firefox', 'chromium', 'brave'):
        raise ValueError('视频号 Cookie 暂支持浏览器名称，不支持 profile 表达式')
    python = Path.home() / '.local/share/uv/tools/yt-dlp/bin/python'
    if not python.exists():
        raise ValueError('缺少 uv 安装的 yt-dlp Python 运行环境')
    result = subprocess.run([str(python), str(SRC / 'vx_browser_cookie.py'), browser],
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise ValueError(f'无法读取 {browser} 的元宝登录态')
    return result.stdout.strip()


def fetch_profile(url, browsers='edge,chrome'):
    if not is_share_url(url):
        raise ValueError('请提供 https://weixin.qq.com/sph/… 视频号分享链接')
    query = parse_qs(urlsplit(url).query)
    eid, token = query.get('eid', [''])[0], query.get('token', [''])[0]
    if not (eid and token and urlsplit(url).hostname == 'channels.weixin.qq.com'):
        errors = []
        for browser in dict.fromkeys((browsers or 'edge,chrome').split(',')):
            browser = browser.strip()
            try:
                cookie = read_cookie(browser)
                if not cookie:
                    errors.append(f'{browser}: 未找到元宝登录态')
                    continue
                parsed = post_json('https://yuanbao.tencent.com/api/weixin/get_parse_result',
                    {'type': 'video_channel_url', 'url': url, 'scene': 1},
                    'https://yuanbao.tencent.com/', cookie)
                if parsed.get('code') != 0:
                    errors.append(f'{browser}: 元宝解析失败，code={parsed.get("code")}')
                    continue
                playable = urlsplit((parsed.get('data') or {}).get('playable_url') or '')
                if playable.scheme != 'https' or playable.hostname != 'channels.weixin.qq.com':
                    errors.append(f'{browser}: 未返回视频号播放页')
                    continue
                q = parse_qs(playable.query)
                eid, token = q.get('eid', [''])[0], q.get('token', [''])[0]
                if eid and token:
                    break
                errors.append(f'{browser}: 播放页缺少必要参数')
            except Exception as exc:
                errors.append(f'{browser}: {type(exc).__name__}')
        if not (eid and token):
            raise ValueError('；'.join(errors) + '。请在 Edge 或 Chrome 登录元宝后重试。')
    payload = post_json('https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info?' +
        urlencode({'_rid': hex(int(time.time()))[2:], '_pageUrl': 'https://channels.weixin.qq.com/finder-preview/pages/feed'}),
        {'baseReq': {'generalToken': token}, 'exportId': eid},
        'https://channels.weixin.qq.com/finder-preview/pages/feed?' + urlencode({'eid': eid, 'token': token}))
    data = payload.get('data') or {}
    if payload.get('errCode', 0) != 0 or (data.get('errMsg') or {}).get('type', 0):
        raise ValueError('视频号返回不可访问/过期结果，请重新复制分享链接')
    feed = data.get('feedInfo') or {}
    if feed.get('picInfo') and not feed.get('videoUrl'):
        raise ValueError('暂不支持视频号图集')
    # Keep original signed URL and matching decodeKey; do not strip signatures or switch renditions.
    media = feed.get('videoUrl')
    u = urlsplit(media or '')
    if u.scheme != 'https' or not u.hostname or not (u.hostname == 'qq.com' or u.hostname.endswith('.qq.com')) or u.username:
        raise ValueError('视频号未提供有效腾讯 HTTPS 媒体地址')
    key = feed.get('decodeKey')
    if key is not None:
        if isinstance(key, bool) or not re.fullmatch(r'\d+', str(key)) or not 0 <= int(key) < 2**64:
            raise ValueError('无效视频号解码参数')
        key = str(key)
    return {'url': media, 'key': key, 'title': feed.get('description'),
            'author': (data.get('authorInfo') or {}).get('nickname'), 'created': feed.get('createtime')}


def decrypt_file(path, key):
    binary = Path(os.environ.get('VX_BIN', str(Path.home()/'.vx/bin'))) / ('vx-wx-decrypt.exe' if os.name == 'nt' else 'vx-wx-decrypt')
    if not binary.exists():
        raise ValueError('缺少 vx-wx-decrypt；运行 scripts/17_install_wx_share.sh')
    result = subprocess.run([str(binary)], input=json.dumps({'path': str(path), 'key': key}),
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('本地媒体解码失败')


def process_share(url, args, lib, vx):
    import tempfile
    from datetime import datetime, timezone
    try:
        profile = fetch_profile(url, args.cookies)
        vx.log('视频号分享解析成功：' + (profile['title'] or '无标题'))
        if args.dry_run:
            vx.log('dry-run：只验证解析，尚未下载或验证解码')
            return 'dry'
        lib.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.vx-wx-', dir=lib) as td:
            dest = Path(td) / 'video.mp4'
            ok, why = vx.download_direct(profile['url'], dest,
                referer='https://channels.weixin.qq.com/', allow_encrypted=True)
            if not ok:
                raise ValueError('媒体下载失败：' + str(why))
            probe = vx.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', str(dest)])
            valid = probe.returncode == 0 and any(s.get('codec_type') == 'video' for s in json.loads(probe.stdout or '{}').get('streams', []))
            decoding = '分享接口返回可直接播放的媒体'
            if not valid:
                decoding = '使用 ISAAC64 解码媒体头部'
                if profile['key'] is None:
                    raise ValueError('媒体加密且缺少 decodeKey')
                vx.log('媒体头部不可读，使用对应 decodeKey 本地解码')
                decrypt_file(dest, profile['key'])
            check = vx.run(['ffmpeg', '-v', 'error', '-i', str(dest), '-map', '0:v:0', '-frames:v', '1', '-f', 'null', '-'])
            dur, _ = vx.probe_local(dest)
            if check.returncode or dur is None or dur <= 0:
                raise ValueError('解码后的媒体未通过实际视频解码验收')
            import hashlib
            digest = hashlib.sha256()
            with dest.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b''):
                    digest.update(chunk)
            stable = dest.with_name('wx_' + digest.hexdigest()[:20] + '.mp4')
            dest.rename(stable)
            local = copy.copy(args)
            local.as_platform = 'wxchannel'; local.source_url = url
            local.note = ((getattr(args, 'note', None) or '') + ' ' + decoding + '；机器转写需核对。').strip()
            local.media_url = profile['url']; local.title = args.title or profile['title']
            local.author = args.author or profile['author']
            if not local.published and profile['created']:
                local.published = datetime.fromtimestamp(int(profile['created']), timezone.utc).strftime('%Y%m%d')
            vx.log('视频媒体解码验收通过')
            local.channel = '视频号分享链接'
            # tool 字段必须如实反映走过哪条路。原来无论有没有解密都写
            # 'Tencent share API + ISAAC64'，等于在溯源信息里撒谎：
            # 未加密的作品根本没进 decrypt_file()，却被标成用了 ISAAC64。
            # 这个项目的 evidence 分级（一手/二手/三手）依赖 meta 如实记录，
            # 记错来源比记漏更糟。
            local.tool = ('Tencent share API + ISAAC64'
                          if not valid else 'Tencent share API（媒体未加密，未解码）')
            return vx.process_local(stable, local, lib)
    except Exception as exc:
        vx.log(f'视频号提取失败：{type(exc).__name__}: {exc}', '✗')
        return 'failed'
