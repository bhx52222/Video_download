#!/usr/bin/env python3
"""播放列表 / 合集：判断要不要查、拉标题清单、按选择批量下载并可断点续跑。

CLI 和 App 共用这一份。vx_link 只做不联网的解析；这里的 probe 才会联网，
而且只对可能是列表的链接联网——普通单条链接不多发一次请求。

结果放两处：
  · 每条视频仍是媒体库里的 平台_作者_发布日期_视频ID 目录，媒体文件名带序号；
  · 列表自己的记录在 _playlists/<平台_作者_列表ID>/（index.csv、archive.txt、job.json）。
archive.txt 与 yt-dlp --download-archive 的格式相同（"平台 视频ID"）。
"""
import csv
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import vx_link

BATCH_THRESHOLD = 5        # 选中条数达到它就走批量档
BATCH_MIN_SLEEP = 3.0      # 批量档条目之间至少间隔的秒数
MAX_ENTRIES = 1000         # 频道页可能有上万条，清单只取前面这些
LIBRARY_DIR = "_playlists"
MARKER = "@@VX_PLAYLISTS@@"
INDEX_FIELDS = ["index", "video_id", "title", "duration_sec", "status", "slug", "media", "url"]
DONE_STATUSES = ("ok", "skipped")
MEDIA_SUFFIXES = (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv", ".m3u8", ".mp3", ".m4a")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


# ---------------------------------------------------------------- 要不要查

def hint(url):
    """不联网判断：explicit＝链接本身就指向列表；implicit＝可能是列表，要查了才知道；
    None＝确定按单条处理，不查。"""
    u = urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    platform = vx_link.platform_of(url)
    if platform in ("wxchannel", "wxarticle", "kuaishou"):
        return None
    path, host = u.path, u.hostname.lower()
    if platform == "youtube":
        if vx_link.playlist_id_of(url, platform) or path.rstrip("/") == "/playlist":
            return "explicit"
        if re.match(r"^/(@|channel/|c/|user/)", path):
            return "explicit"
        return None
    if platform == "bilibili":
        if host.startswith("space.") or path.startswith(("/medialist/", "/list/")):
            return "explicit"
        if path.startswith("/video/"):
            return "explicit" if "p" in parse_qs(u.query) else "implicit"
        return "implicit" if host.endswith("b23.tv") or path.startswith("/bangumi/") else None
    if platform == "instagram":
        return "implicit" if path.startswith("/p/") else None
    if path.lower().endswith(MEDIA_SUFFIXES) or vx_link.is_short(url):
        return None
    return None if vx_link.video_id_of(url, platform) else "implicit"


def to_probe(urls, implicit_limit=3):
    """一次贴很多条时，用户已经给的就是逐条清单，只查明确指向列表的链接。"""
    lone = len(urls) <= implicit_limit
    return [u for u in urls if hint(u) == "explicit" or (lone and hint(u) == "implicit")]


# ---------------------------------------------------------------- 拉清单

def _entry(index, video_id, title, duration, url):
    missing = str(title or "").strip() in ("[Deleted video]", "[Private video]")
    return {"index": index, "id": video_id, "title": title or video_id or f"第 {index} 条",
            "duration": duration, "url": url, "unavailable": missing}


def from_ytdlp(source_url, raw):
    """yt-dlp --flat-playlist 的结果 → 清单。不足两条就不算列表，返回 None。"""
    if raw.get("_type") not in ("playlist", "multi_video") or not raw.get("entries"):
        return None
    platform = vx_link.platform_of(source_url)
    entries = []
    for i, e in enumerate(raw["entries"], 1):
        if not e:
            continue
        vid = e.get("id")
        link = (f"https://www.youtube.com/watch?v={vid}" if platform == "youtube" and vid
                else e.get("webpage_url") or e.get("url"))
        if link:
            entries.append(_entry(e.get("playlist_index") or i, vid, e.get("title"), e.get("duration"), link))
    if len(entries) < 2:
        return None
    info = _info(source_url, platform, raw.get("id"), raw.get("title"),
                 raw.get("uploader") or raw.get("channel"), entries)
    info["truncated"] = len(entries) >= MAX_ENTRIES
    return info


def _info(source_url, platform, list_id, title, uploader, entries):
    list_id = str(list_id or "list")
    current = _current(source_url, platform, entries)
    return {"source_url": source_url, "platform": platform, "id": list_id,
            "title": title or list_id, "uploader": uploader, "count": len(entries),
            "entries": entries, "current_index": current["index"] if current else None,
            "current_url": current["url"] if current else None, "truncated": False,
            # YouTube Mix（RD 开头）是系统按当前视频无限生成的，不是作者编的列表。
            "generated_mix": platform == "youtube" and list_id.startswith("RD")}


def _current(source_url, platform, entries):
    query = parse_qs(urlsplit(source_url).query)
    if platform == "youtube":
        wanted = vx_link.video_id_of(source_url, platform)
    elif platform == "bilibili":
        wanted = vx_link.video_id_of(source_url, platform)
        part = (query.get("p") or [None])[0]
        for e in entries:
            if wanted and part and e["url"].endswith(f"{wanted}?p={part}"):
                return e
    else:
        return None
    return next((e for e in entries if wanted and (e["id"] == wanted or str(e["id"]).startswith(f"{wanted}_p"))), None)


def bilibili_view(bvid, timeout=15):
    request = urllib.request.Request(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    return payload.get("data") if payload.get("code") == 0 else None


def from_bilibili_view(source_url, data):
    """B 站 /video/BV… 是不是分P或合集，yt-dlp 不看合集，这里读官方公开接口。
    一个视频既是分P又在合集里时，先给分P——它才是这条链接本身的内容。"""
    bvid = data.get("bvid")
    owner = (data.get("owner") or {}).get("name")
    pages = data.get("pages") or []
    if len(pages) > 1:
        entries = [_entry(p.get("page") or i, f"{bvid}_p{p.get('page') or i}", p.get("part"), p.get("duration"),
                          f"https://www.bilibili.com/video/{bvid}?p={p.get('page') or i}")
                   for i, p in enumerate(pages, 1)]
        return _info(source_url, "bilibili", bvid, data.get("title"), owner, entries)
    season = data.get("ugc_season") or {}
    episodes = [ep for section in season.get("sections") or [] for ep in section.get("episodes") or []]
    if len(episodes) > 1:
        entries = [_entry(i, ep.get("bvid"), ep.get("title"), (ep.get("arc") or {}).get("duration"),
                          f"https://www.bilibili.com/video/{ep.get('bvid')}")
                   for i, ep in enumerate(episodes, 1)]
        return _info(source_url, "bilibili", f"season{season.get('id')}", season.get("title"),
                     owner, entries)
    return None


def probe(url, core, browser="none", timeout=120):
    """返回列表信息；是单条或查不出来都返回 None——查不出来就按原来的单条流程走。"""
    target = url
    if vx_link.is_short(url) and vx_link.platform_of(url) == "bilibili":
        target = vx_link.expand_short(url) or url
    if vx_link.platform_of(target) == "bilibili" and urlsplit(target).path.startswith("/video/"):
        bvid = vx_link.video_id_of(target, "bilibili")
        try:
            data = bilibili_view(bvid) if bvid else None
        except Exception:
            data = None
        if data is not None:
            info = from_bilibili_view(target, data)
            if info:
                info["source_url"] = url
            return info
        if hint(url) != "explicit":
            return None
    flags = ["--flat-playlist", "--yes-playlist", "--skip-download", "--dump-single-json",
             "--playlist-end", str(MAX_ENTRIES), target]

    def attempt(force):
        core["throttle"](target)
        try:
            return core["run"](core["ytdlp_base"](target, browser, force_cookies=force) + flags, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    result = attempt(False)
    if (result is not None and result.returncode and browser and browser != "none"
            and core["looks_like_bot_check"](result.stderr)):
        result = attempt(True)
    if result is None or result.returncode:
        return None
    try:
        info = from_ytdlp(target, json.loads(result.stdout))
    except ValueError:
        return None
    if info:
        info["source_url"] = url
    return info


# ---------------------------------------------------------------- 选择 → 任务

def parse_selection(spec, entries):
    """'all' 或 '1,3,5-7' → 序号列表；用清单里的序号，超出范围直接报错。"""
    known = [e["index"] for e in entries]
    if spec == "all":
        return known
    wanted = set()
    for part in str(spec).split(","):
        m = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*", part)
        if not m:
            raise ValueError(f"看不懂的序号：{part!r}（例：all 或 1,3,5-7）")
        low, high = int(m.group(1)), int(m.group(2) or m.group(1))
        wanted.update(range(low, high + 1))
    outside = sorted(wanted - set(known))
    if outside:
        raise ValueError(f"列表里没有这些序号：{outside}")
    return [i for i in known if i in wanted]


def work_dir(lib, info, safe):
    parts = [info["platform"]]
    if info.get("uploader"):
        parts.append(safe(info["uploader"]))
    parts.append(safe(info["id"], 60))
    return Path(lib).expanduser() / LIBRARY_DIR / "_".join(parts)


def write_job(info, selected, lib, safe):
    if not selected:
        raise ValueError("没有选中任何条目")
    work = work_dir(lib, info, safe)
    work.mkdir(parents=True, exist_ok=True)
    path = work / "job.json"
    job = dict(info, selected=list(selected))
    path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def describe(info):
    lines = [f"{info['title']}（{info.get('uploader') or '作者未知'}）共 {info['count']} 条"
             + ("，只取了前面这些" if info.get("truncated") else "")]
    for e in info["entries"]:
        mark = "▶" if e["index"] == info.get("current_index") else " "
        lines.append(f"{mark}{e['index']:>4}  {e['title']}" + ("（不可用）" if e.get("unavailable") else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- 断点与总表

def read_archive(path):
    try:
        return {line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return set()


def read_index(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            return {int(row["index"]): row for row in csv.DictReader(f)}
    except (OSError, KeyError, ValueError):
        return {}


def write_index(path, entries, rows):
    """每条结束都整表重写一次：中途被取消或断电，总表也能反映真实进度。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for e in entries:
            row = dict(rows.get(e["index"]) or {})
            row.update(index=e["index"], video_id=e["id"], title=e["title"], duration_sec=e["duration"], url=e["url"])
            row.setdefault("status", "pending")
            writer.writerow(row)
    os.replace(tmp, path)


def name_prefix(index, total):
    return f"{index:0{max(2, len(str(total)))}d}_"


def run_job(job, args, process, find_media, log, sleep=time.sleep):
    """按序下载选中的条目。单条失败、抛异常都只记录，不影响后面的条目。"""
    work = Path(job["_work"])
    work.mkdir(parents=True, exist_ok=True)
    archive_path, index_path = work / "archive.txt", work / "index.csv"
    entries = job["entries"]
    selected = [e for e in entries if e["index"] in set(job["selected"])]
    archive = read_archive(archive_path)
    rows = read_index(index_path)
    batch = len(selected) >= BATCH_THRESHOLD
    gap = max(args.sleep, BATCH_MIN_SLEEP) if batch else args.sleep
    log(f"{'批量档' if batch else '列表'}：{job['title']}，选中 {len(selected)}/{len(entries)} 条")
    log(f"总表 {index_path}")
    write_index(index_path, entries, rows)
    ignore_archive = args.force or getattr(args, "redownload", False)
    results, networked = [], False
    for n, entry in enumerate(selected, 1):
        key = f"{job['platform']} {entry['id']}"
        row = rows.setdefault(entry["index"], {})
        print(f"\n━━ 列表 {n}/{len(selected)} · 序号 {entry['index']} ━━", flush=True)
        # 只有“仅下载”能凭 archive 跳过；要转写时还得进主流程，它自己按 .done 判断。
        if key in archive and not ignore_archive and getattr(args, "download_only", False):
            log(f"已下载过，跳过：{entry['title']}", "↷")
            row["status"] = "skipped"
            results.append({"url": entry["url"], "result": "skipped"})
            write_index(index_path, entries, rows)
            continue
        if networked and gap:
            sleep(gap)
        networked = True
        item = {"id": job["id"], "title": job["title"], "url": job["source_url"], "index": entry["index"],
                "total": len(entries), "prefix": name_prefix(entry["index"], len(entries))}
        args.playlist_item = item
        try:
            result = process(entry["url"], args)
        except Exception as e:
            log(f"未预期的错误：{type(e).__name__}: {e}", "✗")
            result = "failed"
        finally:
            args.playlist_item = None
        outdir = item.get("outdir")
        if outdir:
            row["slug"] = Path(outdir).name
            media = find_media(Path(outdir))
            row["media"] = media.name if media else ""
        row["status"] = result
        if result in DONE_STATUSES or result == "dry":
            if result != "dry" and key not in archive:
                with open(archive_path, "a", encoding="utf-8") as f:
                    f.write(key + "\n")
                archive.add(key)
        else:
            log(f"序号 {entry['index']} 未完成（{result}），继续下一条；重跑同一链接会只补这些", "!")
        write_index(index_path, entries, rows)
        results.append({"url": entry["url"], "result": result})
    return results
