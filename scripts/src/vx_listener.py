#!/usr/bin/env python3
"""vx 抓流接收端：接住 Surge 脚本推来的媒体地址，验证后存成候选清单。

设计上只做"收集和甄别"，不自动下载。播一条视频会产生几十上百个分片请求，
全自动下载只会灌一堆垃圾进媒体库。让它攒候选，由 vx-grab 挑一条再走全流程。
"""
import json, os, re, sys, threading, time, urllib.request, urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
# truststore 走系统钥匙串的根证书；缺了就退回默认信任库。
# 接收端只用它做 HEAD/Range 校验，不该因为这个包没装就整个起不来。
try:
    import truststore
    TLS_CONTEXT = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    HAS_TRUSTSTORE = True
except Exception:
    TLS_CONTEXT = ssl.create_default_context()
    HAS_TRUSTSTORE = False

VXHOME = Path.home() / ".vx"
STORE = VXHOME / "captures.jsonl"
PORT = int(os.environ.get("VX_CAPTURE_PORT", "18787"))
MIN_BYTES = int(os.environ.get("VX_CAPTURE_MIN", str(300 * 1024)))
KEEP = 200

_seen = set()
_lock = threading.Lock()

def head(url, ua, referer, details=None):
    """HEAD 验证：确认是媒体、且够大。抓流会混进大量图片和接口请求。"""
    headers = {"User-Agent": ua or "Mozilla/5.0", "X-VX-Probe": "1", "Connection": "close"}
    if referer:
        headers["Referer"] = referer
    methods = ("GET",) if urllib.parse.urlsplit(url).hostname == "finder.video.qq.com" else ("HEAD", "GET")
    for method in methods:
        try:
            h = dict(headers)
            if method == "GET":
                h["Range"] = "bytes=0-1"
            req = urllib.request.Request(url, method=method, headers=h)
            with urllib.request.urlopen(req, timeout=12, context=TLS_CONTEXT) as r:
                if details is not None:
                    details["encrypted"] = r.headers.get("X-encflag") == "1"
                ct = (r.headers.get("Content-Type") or "").lower()
                total = (r.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
                cl = int(total if total.isdigit() else r.headers.get("Content-Length") or 0)
                if cl >= MIN_BYTES or method == "GET":
                    return ct, cl
        except Exception:
            continue
    return "", 0

def dedup_key(url, size):
    # 媒体地址普遍带时效签名，同一条视频每次播都不一样，
    # 所以按 host+path+大小 去重，不能按完整 URL。
    m = re.match(r"https?://([^/]+)(/[^?]*)", url)
    return (m.group(1), m.group(2), size) if m else (url, "", size)

def record(item):
    details = {}
    ct, cl = head(item["url"], item.get("ua"), item.get("referer"), details)
    item.update(details)
    if cl < MIN_BYTES:
        return
    if not (ct.startswith("video/") or ct.startswith("audio/")
            or "mpegurl" in ct or "octet-stream" in ct):
        return
    key = dedup_key(item["url"], cl)
    with _lock:
        # 重新播放刷新签名；从磁盘读取，重启和 clear 后行为一致。
        rows = []
        if STORE.exists():
            for line in STORE.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    if dedup_key(row["url"], row.get("size", 0)) != key:
                        rows.append(row)
                except (ValueError, KeyError, TypeError):
                    continue
        item.update(size=cl, ctype=ct,
                    at=datetime.now().isoformat(timespec="seconds"))
        rows.append(item)
        STORE.parent.mkdir(parents=True, exist_ok=True)
        temp = STORE.with_suffix(".tmp")
        temp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[-KEEP:]), encoding="utf-8")
        temp.chmod(0o600)
        temp.replace(STORE)
    print(f"[捕获] {cl/1048576:6.1f} MB  {ct:24s} {item['url'][:70]}", flush=True)

class Server(ThreadingHTTPServer):
    # 不加这个，进程刚退出时端口还在 TIME_WAIT，重启会 Address already in use
    allow_reuse_address = True
    daemon_threads = True

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, body=b"ok", ctype="text/plain"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/metadata":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 < n <= 65536:
                    self.send_error(400); return
                rows = json.loads(self.rfile.read(n))
                valid = []
                if not isinstance(rows, list):
                    self.send_error(400); return
                for row in rows[:20]:
                    if not isinstance(row, dict): continue
                    url, key = row.get("url", ""), row.get("decode_key", "")
                    if (isinstance(url, str) and urllib.parse.urlsplit(url).hostname == "finder.video.qq.com"
                            and isinstance(key, str) and key.isdigit() and 0 <= int(key) < 2**64):
                        valid.append({"url": url, "decode_key": key, "at": datetime.now().isoformat(timespec="seconds")})
                if valid:
                    target = VXHOME / "wx_metadata.jsonl"
                    with _lock:
                        old = []
                        if target.exists():
                            for line in target.read_text().splitlines():
                                try: old.append(json.loads(line))
                                except ValueError: pass
                        temp = target.with_suffix(".tmp")
                        temp.write_text("".join(json.dumps(r) + "\n" for r in (old + valid)[-KEEP:]))
                        temp.chmod(0o600); temp.replace(target)
                    print(f"[元数据] 收到 {len(valid)} 条媒体解码参数", flush=True)
                self._ok(); return
            except (ValueError, TypeError):
                self.send_error(400); return
        if self.path != "/capture":
            self._ok(b"?"); return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        self._ok()   # 立刻回，别拖住 Surge
        try:
            item = json.loads(raw)
        except Exception:
            return
        if isinstance(item, dict) and isinstance(item.get("url"), str) and item["url"].startswith(("http://", "https://")):
            threading.Thread(target=record, args=(item,), daemon=True).start()

    def do_GET(self):
        if self.path == "/health":
            self._ok(b"vx-capture-v1"); return
        if self.path == "/list":
            rows = []
            if STORE.exists():
                rows = [json.loads(l) for l in STORE.read_text(encoding="utf-8").splitlines() if l.strip()]
            body = json.dumps(rows[-KEEP:], ensure_ascii=False, indent=2).encode()
            self._ok(body, "application/json"); return
        self._ok(b"vx capture listener")

if __name__ == "__main__":
    print(f"vx 抓流接收端启动：http://127.0.0.1:{PORT}")
    print(f"  候选清单：{STORE}")
    print(f"  只收 {MIN_BYTES//1024} KB 以上的音视频请求，其余丢弃")
    try:
        Server(("127.0.0.1", PORT), H).serve_forever()
    except OSError as e:
        print(f"端口 {PORT} 起不来：{e}")
        print("多半是已经有一个接收端在跑了。vx-capture status 看看。")
        sys.exit(1)
