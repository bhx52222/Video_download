#!/bin/bash
# 普查一个频道的每条视频：发布日期、字幕轨情况、章节数。
#
# 为什么要单独一步：--flat-playlist 为了快不取每条的详细元数据，
# upload_date 全是 NA。而对宏观/预测类频道，日期是刚需——
# 「他哪年哪月说了什么、后来发生了什么」是这类内容唯一的检验方式。
#
# 同时普查字幕：先知道谁有字幕再去抓，能省掉大量在无字幕视频上的空跑。
# 字幕缺失如果集中在某个时期，本身就是发现（制作投入下降）。
#
# 增量写入：每条立即落盘并 flush，中断了不用重来，重跑会跳过已有的。
# 858 条按每条约 1.5 秒算，大概 20 分钟。
#
# 用法：bash 21_channel_survey.sh <目录目录>        例如 ~/VideoExtract/_catalog/@HongAcademy
set -u
D="${1:-}"
[ -z "$D" ] && { echo "用法：bash 21_channel_survey.sh <catalog 目录>"; exit 2; }
D="${D%/}"
IN="$D/videos.tsv"
OUT="$D/survey.tsv"
[ -f "$IN" ] || { echo "找不到 $IN，先跑 20_channel_catalog.sh"; exit 1; }

python3 - "$IN" "$OUT" <<'PY'
import json, subprocess, sys, time, io, os

src, dst = sys.argv[1], sys.argv[2]

ids = []
for line in io.open(src, encoding='utf-8'):
    line = line.rstrip('\n')
    if not line.strip():
        continue
    # yt-dlp 的 --print 没把 \t 解释成制表符，输出里是字面的两个字符
    parts = line.split('\\t')
    if parts and parts[0]:
        ids.append((parts[0], parts[1] if len(parts) > 1 else ''))

# 只把「成功过」的算作已完成。ERROR 行必须重试——
# 第一版把 ERROR 也加进 done，结果重跑恰好跳过了所有需要重试的条目，
# 而输出看起来一切正常。这就是 HANDOFF 坑 44 那个病根在续跑逻辑里的翻版：
# 跳过和失败长得一样。
done = set()
seen_err = set()
if os.path.exists(dst):
    for line in io.open(dst, encoding='utf-8'):
        f = line.rstrip('\n').split('\t')
        if not f or not f[0] or f[0] == 'id':
            continue
        if len(f) > 1 and f[1] == 'ERROR':
            seen_err.add(f[0])
        else:
            done.add(f[0])
    seen_err -= done
    print(f"已成功 {len(done)} 条，其中 {len(seen_err)} 条上次失败需重试")

todo = [(v, t) for v, t in ids if v not in done]
print(f"待普查 {len(todo)} / 共 {len(ids)}")

# 重写文件：只保留成功行（每个 id 一条）。这样重跑不会让 ERROR 行和
# 重复行越积越多——实测第一轮跑完 858 条，文件里有 1146 行、288 个 id 重复。
if os.path.exists(dst):
    keep, seen = [], set()
    for line in io.open(dst, encoding='utf-8'):
        f = line.rstrip('\n').split('\t')
        if not f or not f[0] or f[0] == 'id':
            continue
        if len(f) > 1 and f[1] != 'ERROR' and f[0] not in seen:
            seen.add(f[0]); keep.append(line)
    with io.open(dst, 'w', encoding='utf-8') as w:
        w.write("id\tupload_date\tduration\tviews\tlikes\tcomments\tmanual_subs\tauto_subs\tchapters\ttitle\n")
        w.writelines(keep)
    print(f"已整理：保留 {len(keep)} 条成功记录，清掉重复行和 ERROR 行")

out = io.open(dst, 'a', encoding='utf-8')
if not os.path.exists(dst) or os.path.getsize(dst) == 0:
    out.write("id\tupload_date\tduration\tviews\tlikes\tcomments\tmanual_subs\tauto_subs\tchapters\ttitle\n")
    out.flush()

ok = fail = 0
t0 = time.time()
for i, (vid, title) in enumerate(todo, 1):
    cmd = ["yt-dlp", "--skip-download", "--dump-single-json", "--no-warnings",
           "--socket-timeout", "20", f"https://www.youtube.com/watch?v={vid}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        d = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        d = None
    if d is None:
        fail += 1
        out.write(f"{vid}\tERROR\t\t\t\t\t\t\t\t{title}\n")
    else:
        ok += 1
        man = ",".join(sorted((d.get("subtitles") or {}).keys())) or "-"
        auto = len(d.get("automatic_captions") or {})
        out.write("\t".join(str(x) for x in [
            vid, d.get("upload_date") or "", d.get("duration") or "",
            d.get("view_count") or "", d.get("like_count") or "",
            d.get("comment_count") or "", man, auto,
            len(d.get("chapters") or []), (d.get("title") or title).replace("\t", " "),
        ]) + "\n")
    out.flush()
    if i % 25 == 0 or i == len(todo):
        el = time.time() - t0
        eta = el / i * (len(todo) - i)
        print(f"  {i}/{len(todo)}  成功 {ok} 失败 {fail}  已用 {el/60:.1f} 分  预计还要 {eta/60:.1f} 分",
              flush=True)
    time.sleep(1.2)   # 给 YouTube 留间隔，理由见 HANDOFF 坑 37
out.close()
print(f"\n完成：成功 {ok}，失败 {fail} → {dst}")
PY
