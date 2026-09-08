"""Read public Kuaishou SSR metadata; no login, private API or cookie export."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'


def page_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname not in ('www.kuaishou.com', 'kuaishou.com', 'v.kuaishou.com') or p.port not in (None, 443) or p.username:
        raise ValueError('快手跳转地址不受支持')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        page_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_page(text, photo_id):
    marker = re.search(r'window\.__APOLLO_STATE__\s*=\s*', text)
    if not marker:
        raise ValueError('快手未返回作品数据，可能触发验证或作品不可访问；请在浏览器核对后再试')
    state, _ = json.JSONDecoder().raw_decode(text[marker.end():])
    db = state['defaultClient']
    photo = db.get('VisionVideoDetailPhoto:' + photo_id)
    if not isinstance(photo, dict) or photo.get('id') != photo_id:
        raise ValueError('页面作品 ID 与链接不符，停止下载')
    detail = next((v for v in db.values() if isinstance(v, dict) and isinstance(v.get('photo'), dict) and v['photo'].get('id') == 'VisionVideoDetailPhoto:' + photo_id), {})
    author = db.get((detail.get('author') or {}).get('id'), {})
    media = photo.get('photoUrl') or ''
    p = urlsplit(media)
    domains = ('oskwai.com', 'kwaicdn.com', 'kwimgs.com', 'yximgs.com', 'gifshow.com')
    if p.scheme != 'https' or not any(p.hostname == d or (p.hostname or '').endswith('.' + d) for d in domains) or p.username or p.port not in (None,443):
        raise ValueError('快手页面没有受支持的视频地址')
    ts = photo.get('timestamp')
    return {'id':photo_id, 'title':photo.get('caption') or photo_id,
            'uploader':author.get('name'), 'uploader_id':author.get('id'),
            'duration':float(photo.get('duration') or 0)/1000,
            'upload_date':datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y%m%d') if isinstance(ts,(int,float)) else None,
            'like_count':photo.get('realLikeCount'), 'extractor':'kuaishou-public-page',
            '_vx_play_url':media, '_vx_user_agent':UA,
            '_vx_referer':'https://www.kuaishou.com/short-video/' + photo_id}


def fetch_kuaishou(url):
    opener = build_opener(Redirects())
    def read(target):
        with opener.open(Request(page_url(target), headers={'User-Agent':UA}), timeout=25) as r:
            data = r.read(4*1024*1024+1)
            if len(data)>4*1024*1024:
                raise ValueError('快手页面超过大小限制')
            return r.geturl(), data.decode('utf-8')
    final, text = read(url)
    match = re.fullmatch(r'/short-video/([A-Za-z0-9_-]+)', urlsplit(final).path)
    if not match:
        raise ValueError('请提供快手单条作品链接或分享短链接')
    canonical = 'https://www.kuaishou.com/short-video/' + match[1]
    if final != canonical:
        _, text = read(canonical)
    return parse_page(text, match[1])
