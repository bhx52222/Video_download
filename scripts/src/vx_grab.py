#!/usr/bin/env python3
"""从抓流候选里挑一条，交给 vx 走全流程。

不带参数就列清单；带序号就处理那一条。
默认按体积倒序，因为一条视频的主流一定比它的封面、预览、分片都大。
"""
import json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vx_runtime

# 候选清单是可写状态，命令入口是运行时。一体化包里这两者不在同一处。
STORE = vx_runtime.state_home() / "captures.jsonl"
VX = Path(vx_runtime.tool("vx"))

def load():
    if not STORE.exists():
        return []
    rows = [json.loads(l) for l in STORE.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows.sort(key=lambda r: (-r.get("size", 0), r.get("at", "")))
    return rows[:20]

def main():
    args = sys.argv[1:]
    rows = load()
    if not rows:
        print("还没有捕获到任何媒体。")
        print("  确认接收端在跑：vx-capture status")
        print("  然后在浏览器或微信里把那条视频播起来。")
        return 1
    if not args or args[0] in ("-l", "list"):
        print(f"\n抓流候选（{len(rows)} 条，按体积倒序）\n")
        for i, r in enumerate(rows, 1):
            print(f"  [{i:2d}] {r['size']/1048576:7.1f} MB  {r.get('ctype','')[:20]:20s} {r.get('at','')}")
            print(f"       {r['url'][:100]}")
            if r.get("encrypted"):
                print("       [加密媒体：缺少解码信息，不能直接提取]")
            if r.get("referer"):
                print(f"       来自 {r['referer'][:90]}")
        print("\n处理其中一条：vx-grab 1 [--as kuaishou] [--title '...'] [--author '...']")
        return 0
    try:
        idx = int(args[0]) - 1
        if idx < 0:
            raise IndexError
        row = rows[idx]
    except (ValueError, IndexError):
        print(f"没有第 {args[0]} 条"); return 1
    cmd = [str(VX), "--media-url", row["url"]]
    if row.get("referer"):
        cmd += ["--source-url", row["referer"]]
    if row.get("ua"):
        cmd += ["--user-agent", row["ua"]]
    cmd += args[1:]
    print("→ " + " ".join(cmd[:4]) + " …")
    return subprocess.call(cmd)

if __name__ == "__main__":
    sys.exit(main())
