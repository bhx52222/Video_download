"""Internal subprocess helper; stdout is captured in memory, never logged or saved."""
import sys
from yt_dlp.cookies import extract_cookies_from_browser
class Quiet:
    def debug(self,*a,**k): pass
    def info(self,*a,**k): pass
    def warning(self,*a,**k): pass
    def error(self,*a,**k): pass
if __name__ == '__main__':
    try:
        jar = extract_cookies_from_browser(sys.argv[1], logger=Quiet())
        value = jar.get_cookie_header('https://yuanbao.tencent.com/api/weixin/get_parse_result') or ''
        if '--check' in sys.argv:
            sys.exit(0 if value else 1)
        print(value)
    except Exception:
        sys.exit(1)
