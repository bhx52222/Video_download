#!/bin/bash
# 抓一个 YouTube 频道的全量作品目录，三个标签页分开统计。
#
# 为什么分开：平台显示的「N 个视频」通常把 Shorts 和直播回放算在里面，
# 三者的可获取性和分析价值完全不同——Shorts 通常没有实质内容，
# 直播回放动辄几小时且多是重复口播。混在一起统计会让后面的判断全歪。
#
# 不用浏览器接口：yt-dlp 的 --flat-playlist 一条命令就够，
# 不必去踩 innertube 分页 token 那些坑。
#
# 用法：bash 20_channel_catalog.sh <频道URL或@handle> [输出目录]
set -u
CH="${1:-}"
[ -z "$CH" ] && { echo "用法：bash 20_channel_catalog.sh <频道URL或@handle> [输出目录]"; exit 2; }
case "$CH" in
  @*) CH="https://www.youtube.com/$CH" ;;
  http*) : ;;
  *) CH="https://www.youtube.com/@$CH" ;;
esac
CH="${CH%/}"; CH="${CH%/videos}"; CH="${CH%/shorts}"; CH="${CH%/streams}"

# grep -c 在没匹配到时退出码是 1，写成 `grep -c ... || echo 0` 会输出两行 0，
# 后面的算术就炸。用函数统一处理，永远只输出一个整数。
count_lines() { [ -f "$1" ] || { echo 0; return; }; awk 'NF' "$1" | wc -l | tr -d " "; }

OUT="${2:-$HOME/VideoExtract/_catalog/$(basename "$CH")}"
mkdir -p "$OUT"
echo "频道：$CH"
echo "输出：$OUT"

# 字段用 tab 分隔。标题里可能有逗号，CSV 会乱；tab 在标题里几乎不出现。
FMT='%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(upload_date)s\t%(timestamp)s'

for tab in videos shorts streams; do
  f="$OUT/$tab.tsv"
  printf '\n\033[1m== %s ==\033[0m\n' "$tab"
  # 不带 cookie：实测 YouTube 带登录态反而会返回残缺数据（见 HANDOFF 坑 34）
  if yt-dlp --flat-playlist --ignore-errors --no-warnings \
       --print "$FMT" "$CH/$tab" > "$f" 2>"$OUT/$tab.err"; then
    n=$(count_lines "$f")
    echo "  $n 条 → $tab.tsv"
  else
    n=$(count_lines "$f")
    if [ "$n" -gt 0 ]; then
      echo "  $n 条（中途有报错，见 $tab.err）"
    else
      echo "  取不到。报错："; head -3 "$OUT/$tab.err" | sed 's/^/     /'
    fi
  fi
done

printf '\n\033[1m== 小结 ==\033[0m\n'
tot=0
for tab in videos shorts streams; do
  n=$(count_lines "$OUT/$tab.tsv")
  printf '  %-8s %5s 条\n' "$tab" "$n"
  tot=$((tot+n))
done
echo "  合计     $tot 条"
echo
echo "文件在 $OUT"
