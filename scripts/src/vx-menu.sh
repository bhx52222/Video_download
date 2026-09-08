#!/bin/bash
# vx-menu —— 交互菜单外壳。内核仍是 vx，这里只负责问几句、拼参数。
set -u
export PATH="$HOME/.vx/bin:$HOME/.local/bin:$PATH"
LIB="${VX_LIB:-$HOME/VideoExtract}"

echo
echo "  ╭──────────────────────────────────╮"
echo "  │   视频内容提取 · vx              │"
echo "  ╰──────────────────────────────────╯"
echo "   媒体库：$LIB"
if [ -f "$LIB/index.csv" ]; then
  echo "   已收录：$(($(wc -l < "$LIB/index.csv") - 1)) 条"
fi
echo
echo "   1) 标准档 —— 单条，走全流程"
echo "   2) 批量档 —— 从清单文件读，可断点续跑"
echo "   3) 正式材料 —— 单条 + OCR／ASR 双路互校"
echo "   4) 只探元数据 —— 不下载，判断值不值得做"
echo "   5) 本地文件 —— 已有视频，只做转写和抽帧"
echo "   6) 看总表"
echo "   7) 启动抓流（Surge）"
echo "   8) 查看并处理抓流候选"
echo "   9) TikTok 备用提取（TikWM 第三方，仅发送链接）"
echo "  10) 视频号分享链接（元宝登录态，无需抓流）"
echo "   q) 退出"
echo
read -r -p "   选：" c

case "$c" in
  1) read -r -p "   链接：" u; [ -n "$u" ] && vx "$u" ;;
  2) read -r -p "   清单文件路径（一行一条）：" f
     f="${f/#\~/$HOME}"; [ -f "$f" ] && vx -f "$f" || echo "   找不到 $f" ;;
  3) read -r -p "   链接：" u; [ -n "$u" ] && vx "$u" --dual ;;
  4) read -r -p "   链接：" u; [ -n "$u" ] && vx "$u" --dry-run ;;
  5) read -r -p "   视频文件路径：" p
     p="${p/#\~/$HOME}"; [ -f "$p" ] && vx "$p" || echo "   找不到 $p" ;;
  6) if [ -f "$LIB/index.csv" ]; then
       column -s, -t < "$LIB/index.csv" | less -S
     else echo "   总表还不存在，先跑一条"; fi ;;
  7) vx-capture start ;;
  8) vx-grab; read -r -p "   序号（直接回车返回）：" n
     if [ -n "$n" ]; then read -r -p "   平台（kuaishou/wxchannel）：" p; vx-grab "$n" --as "$p"; fi ;;
  9) read -r -p "   TikTok 链接（将交给 TikWM 解析）：" u; [ -n "$u" ] && vx "$u" --tiktok-backend tikwm --dual ;;
  10) read -r -p "   视频号分享链接：https://weixin.qq.com/sph/…：" u; [ -n "$u" ] && vx "$u" --cookies edge,chrome --dual ;;
  q|Q) exit 0 ;;
  *) echo "   没这个选项" ;;
esac
