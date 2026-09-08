"""Opt-in TikWM adapter, API approach researched in JoeanAmier/TikTokDownloader.
Independent implementation: TLS verification stays on; no browser cookies sent.
"""
from datetime import datetime, timezone
import json
import re
import ssl
import urllib.request
from urllib.parse import urlencode, urlsplit
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

TIKTOK_CONTEXT = (truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                  if HAS_TRUSTSTORE else ssl.create_default_context())


def fetch_tikwm(url):
    host = (urlsplit(url).hostname or '').lower()
    if not (host == 'tiktok.com' or host.endswith('.tiktok.com')):
        raise ValueError('TikWM 仅接受 TikTok 链接')
    endpoint = 'https://www.tikwm.com/api/?' + urlencode({'url': url, 'hd': '1'})
    request = urllib.request.Request(endpoint, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=40,
            context=TIKTOK_CONTEXT) as response:
        raw = json.loads(response.read(4 * 1024 * 1024))
    if raw.get('code') != 0 or not isinstance(raw.get('data'), dict):
        raise ValueError('TikWM 未返回成功的视频结果')
    data = raw['data']
    video_id = str(data.get('id') or '')
    expected = re.search(r'/video/(\d+)', urlsplit(url).path)
    if not video_id.isdigit() or (expected and expected.group(1) != video_id):
        raise ValueError('TikWM 返回作品 ID 与请求不一致')
    if data.get('images'):
        raise ValueError('暂不支持 TikTok 图集，请使用单条视频')
    media = data.get('hdplay') or data.get('play')
    parsed = urlsplit(media or '')
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username:
        raise ValueError('TikWM 未提供有效 HTTPS 媒体地址')
    author = data.get('author') or {}
    return {'id': video_id, 'title': data.get('title') or video_id,
            'uploader': author.get('nickname'), 'uploader_id': author.get('unique_id'),
            'timestamp': data.get('create_time'),
            'upload_date': datetime.fromtimestamp(int(data['create_time']), timezone.utc).strftime('%Y%m%d') if data.get('create_time') else None,
            'duration': data.get('duration'),
            'view_count': data.get('play_count'), 'like_count': data.get('digg_count'),
            'comment_count': data.get('comment_count'), 'repost_count': data.get('share_count'),
            'extractor': 'tikwm', '_vx_play_url': media, '_vx_browser': 'none'}
