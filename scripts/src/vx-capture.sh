#!/bin/bash
set -eu
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VXHOME="$HOME/.vx"
BASE=http://127.0.0.1:18787
LABEL=local.vx.capture
healthy() { [ "$(curl -fsS -m 3 "$BASE/health" 2>/dev/null)" = vx-capture-v1 ]; }
case "${1:-status}" in
 start)
  if healthy; then echo 'vx 接收端在跑（18787）'; exit 0; fi
  if lsof -tiTCP:18787 -sTCP:LISTEN >/dev/null 2>&1; then echo '18787 被其他服务占用，未修改该服务'; exit 1; fi
  launchctl remove "$LABEL" 2>/dev/null || true
  launchctl submit -l "$LABEL" -o "$VXHOME/capture.log" -e "$VXHOME/capture-error.log" -- "$VXHOME/venv/bin/python" -u "$SRC/vx_listener.py"
  for n in 1 2 3 4 5; do if healthy; then echo 'vx 接收端启动成功（18787，launchd 托管）'; exit 0; fi; sleep 1; done
  echo '启动失败：检查 ~/.vx/capture-error.log'; exit 1 ;;
 stop) launchctl remove "$LABEL"; echo 'vx 接收端已停止' ;;
 status) if healthy; then echo "vx 接收端在跑（18787），候选 $(wc -l < "$VXHOME/captures.jsonl" 2>/dev/null || echo 0) 条"; else echo 'vx 接收端未运行'; exit 1; fi ;;
 log) tail -30 "$VXHOME/capture.log" "$VXHOME/capture-error.log" ;;
 clear) if [ -f "$VXHOME/captures.jsonl" ]; then mv "$VXHOME/captures.jsonl" "$VXHOME/captures.$(date +%s).bak"; fi; echo '候选已清空，旧清单保留为 .bak' ;;
 test|doctor)
  healthy || { echo '请先 vx-capture start'; exit 1; }
  "$VXHOME/venv/bin/python" - <<'PY'
import urllib.request,json,time
url='https://www.w3schools.com/html/mov_bbb.mp4'
started=time.time()
payload=json.dumps({'url':url,'ua':'Mozilla/5.0','referer':'vx-selftest','ts':started}).encode()
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18787/capture',data=payload,headers={'Content-Type':'application/json'}),timeout=5) as r:
 assert r.status==200
for _ in range(20):
 with urllib.request.urlopen('http://127.0.0.1:18787/list',timeout=5) as r: rows=json.load(r)
 if any(r.get('ts')==started for r in rows): print('本次推送已验证并入库（不是旧记录）');break
 time.sleep(1)
else: raise SystemExit('本次测试失败，未发现新候选')
PY
 ;;
 *) echo '用法：vx-capture start|stop|status|test|clear|log'; exit 2 ;;
esac
