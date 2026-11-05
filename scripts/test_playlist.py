"""播放列表：链接判定、清单解析、序号选择、断点续跑、单条失败不中断。不联网。"""
import importlib.util, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))
import vx_link, vx_playlist as p

PL = "PLvwIpSsrHtucawr7BSbwB55gDwUk13JWq"
WATCH = f"https://www.youtube.com/watch?v=Pbwkq5X0nTU&list={PL}&index=10"

# ── 判定：列表要查，普通单条绝不多发请求 ──
for url, want in [
    (WATCH, "explicit"), (f"https://www.youtube.com/playlist?list={PL}", "explicit"),
    (f"https://youtu.be/Pbwkq5X0nTU?list={PL}", "explicit"),
    ("https://www.youtube.com/@somebody/videos", "explicit"),
    ("https://www.youtube.com/watch?v=Pbwkq5X0nTU", None), ("https://youtu.be/Pbwkq5X0nTU", None),
    ("https://www.youtube.com/shorts/abc", None),
    ("https://www.bilibili.com/video/BV15PtJ6JEBh?p=2", "explicit"),
    ("https://www.bilibili.com/video/BV15PtJ6JEBh", "implicit"), ("https://b23.tv/AbCd", "implicit"),
    ("https://space.bilibili.com/1/lists/2?type=season", "explicit"),
    ("https://www.douyin.com/video/7681863407733165321", None),
    ("https://www.kuaishou.com/short-video/3xm4y3b94veigzi", None),
    ("https://weixin.qq.com/sph/abc", None), ("https://mp.weixin.qq.com/s/abc", None),
    ("https://www.instagram.com/reel/abc/", None), ("https://www.instagram.com/p/abc/", "implicit"),
    ("https://vimeo.com/showcase/123", "implicit"), ("https://example.com/a.mp4", None),
    ("/Users/me/a.mp4", None),
]:
    assert p.hint(url) == want, (url, p.hint(url))
assert vx_link.classify(WATCH).playlist_id == PL
assert vx_link.classify(WATCH).video_id == "Pbwkq5X0nTU"
assert vx_link.classify("https://www.douyin.com/video/7?list=x").playlist_id is None
many = [f"https://www.bilibili.com/video/BV{i}" for i in range(4)] + [WATCH]
assert p.to_probe(many) == [WATCH], "一次贴很多条时只查明确的列表"
assert p.to_probe(["https://www.bilibili.com/video/BV1"]) == ["https://www.bilibili.com/video/BV1"]

# ── 清单解析 ──
raw = {"_type": "playlist", "id": PL, "title": "教程", "uploader": "Colin Chang", "entries": [
    {"id": "aaa", "title": "一", "duration": 60}, {"id": "Pbwkq5X0nTU", "title": "二", "duration": 61},
    {"id": "ccc", "title": "[Private video]"}, None]}
info = p.from_ytdlp(WATCH, raw)
assert info["count"] == 3 and info["current_index"] == 2
assert info["current_url"] == "https://www.youtube.com/watch?v=Pbwkq5X0nTU", "选当前一条时不能再带 list="
assert info["entries"][2]["unavailable"] and not info["entries"][0]["unavailable"]
assert p.from_ytdlp(f"https://www.youtube.com/playlist?list={PL}", raw)["current_url"] is None
assert p.from_ytdlp(WATCH, {"_type": "playlist", "entries": [{"id": "a", "title": "x"}]}) is None, "只有一条不算列表"
assert p.from_ytdlp(WATCH, {"id": "a", "title": "普通视频"}) is None
assert p.from_ytdlp(WATCH, dict(raw, id="RDabc"))["generated_mix"] is True

# ── B 站分P 与合集 ──
view = {"bvid": "BV1111111111", "title": "总标题", "owner": {"name": "UP"},
        "pages": [{"page": 1, "part": "上", "duration": 10}, {"page": 2, "part": "下", "duration": 20}]}
parts = p.from_bilibili_view("https://www.bilibili.com/video/BV1111111111?p=2", view)
assert parts["count"] == 2 and parts["current_index"] == 2 and parts["entries"][1]["url"].endswith("BV1111111111?p=2")
season = {"bvid": "BV2222222222", "owner": {"name": "UP"}, "pages": [{"page": 1}], "ugc_season": {"id": 9, "title": "合集", "sections": [
    {"episodes": [{"bvid": "BV1111111111", "title": "a", "arc": {"duration": 5}}, {"bvid": "BV2222222222", "title": "b", "arc": {"duration": 6}}]}]}}
col = p.from_bilibili_view("https://www.bilibili.com/video/BV2222222222", season)
assert col["id"] == "season9" and col["current_index"] == 2 and col["title"] == "合集"
assert p.from_bilibili_view("https://www.bilibili.com/video/BV3333333333", {"bvid": "BV3333333333", "pages": [{"page": 1}]}) is None

# ── 序号选择 ──
entries = [{"index": i} for i in range(1, 11)]
assert p.parse_selection("all", entries) == list(range(1, 11))
assert p.parse_selection("1, 3,5-7", entries) == [1, 3, 5, 6, 7]
for bad in ("99", "abc", "3-"):
    try:
        p.parse_selection(bad, entries); raise SystemExit(f"应报错：{bad}")
    except ValueError:
        pass
assert p.name_prefix(3, 10) == "03_" and p.name_prefix(3, 1000) == "0003_"

# ── 查不出来就回到单条流程，机器人校验时才带 cookie ──
calls = []
def fake_run(cmd, timeout=None):
    calls.append(cmd)
    if len(calls) == 1:
        return SimpleNamespace(returncode=1, stdout="", stderr="Sign in to confirm")
    return SimpleNamespace(returncode=0, stdout=json.dumps(raw), stderr="")
core = {"throttle": lambda u: None, "run": fake_run, "looks_like_bot_check": lambda m: "Sign in" in m,
        "ytdlp_base": lambda u, b, force_cookies=False: ["yt-dlp"] + (["--cookies-from-browser", b] if force_cookies else [])}
assert p.probe(WATCH, core, "chrome")["source_url"] == WATCH
assert "--cookies-from-browser" not in calls[0] and "--cookies-from-browser" in calls[1]
assert "--no-playlist" not in calls[1] and "--flat-playlist" in calls[1]
core["run"] = lambda cmd, timeout=None: SimpleNamespace(returncode=1, stdout="", stderr="boom")
assert p.probe(WATCH, core, "none") is None

# ── 批量：序号、断点续跑、单条失败不中断、总表反映真实状态 ──
with tempfile.TemporaryDirectory() as td:
    lib = Path(td)
    es = [p._entry(i, f"v{i}", f"第{i}条", 60, f"https://www.youtube.com/watch?v=v{i}") for i in range(1, 7)]
    job = {"platform": "youtube", "id": "L1", "title": "列表", "source_url": "https://y/L1", "uploader": "作者",
           "entries": es, "selected": [1, 2, 3, 4, 5]}
    path = p.write_job(job, job["selected"], lib, lambda s, n=40: str(s).replace(" ", "_"))
    assert path.parent == lib / "_playlists" / "youtube_作者_L1"
    job = json.loads(path.read_text(encoding="utf-8")); job["_work"] = str(path.parent)
    seen, fail, sleeps = [], {"v2", "v3"}, []
    def process(url, args):
        vid = url.rsplit("=", 1)[1]
        seen.append(vid)
        item = args.playlist_item
        assert item["total"] == 6 and item["id"] == "L1"
        out = lib / f"youtube_作者_2026_{vid}"; (out / "media").mkdir(parents=True, exist_ok=True)
        item["outdir"] = str(out)
        if vid in fail:
            if vid == "v3":
                raise RuntimeError("意外")
            return "failed"
        (out / "media" / f"{item['prefix']}{vid}.mp4").write_bytes(b"x")
        return "ok"
    def find(out):
        return next((out / "media").glob("*.mp4"), None)
    args = SimpleNamespace(lib=str(lib), sleep=0, force=False, redownload=False, download_only=True)
    log = lambda *a: None
    res = p.run_job(job, args, process, find, log, sleep=sleeps.append)
    assert [r["result"] for r in res] == ["ok", "failed", "failed", "ok", "ok"], res
    assert seen == ["v1", "v2", "v3", "v4", "v5"], "失败和异常都不能中断后面的条目"
    assert sleeps and set(sleeps) == {p.BATCH_MIN_SLEEP}, "≥5 条走批量档，至少留出间隔"
    rows = p.read_index(path.parent / "index.csv")
    assert list(rows) == [1, 2, 3, 4, 5, 6]
    assert rows[1]["status"] == "ok" and rows[1]["media"] == "01_v1.mp4" and rows[1]["slug"].endswith("v1")
    assert rows[2]["status"] == "failed" and rows[6]["status"] == "pending"
    assert p.read_archive(path.parent / "archive.txt") == {"youtube v1", "youtube v4", "youtube v5"}
    # 续跑：只补失败的，成功的不再联网，已有记录不丢
    fail.clear(); seen.clear()
    res = p.run_job(job, args, process, find, log, sleep=sleeps.append)
    assert seen == ["v2", "v3"] and all(r["result"] in ("ok", "skipped") for r in res)
    rows = p.read_index(path.parent / "index.csv")
    assert rows[1]["status"] == "skipped" and rows[1]["media"] == "01_v1.mp4" and rows[2]["status"] == "ok"
    # 少于 5 条：沿用用户设定的间隔
    sleeps.clear(); job2 = dict(job, selected=[1, 2]); args.force = True
    p.run_job(job2, args, process, find, log, sleep=sleeps.append)
    assert sleeps == [] or set(sleeps) == {0}
    # 要转写时不能凭 archive 跳过，要进主流程
    seen.clear(); args.force = False; args.download_only = False
    p.run_job(dict(job, selected=[1]), args, process, find, log)
    assert seen == ["v1"]

# ── 内核：序号进文件名、meta 和总表；单条路径不变；exit 3 ──
s = importlib.util.spec_from_file_location("vx", SRC / "vx.py"); v = importlib.util.module_from_spec(s); s.loader.exec_module(v)
from unittest.mock import patch
with tempfile.TemporaryDirectory() as td:
    cmds = []
    def fake_sub(cmd, **kw):
        cmds.append(cmd); return SimpleNamespace(returncode=0)
    with patch.object(v, "throttle"), patch.object(v.subprocess, "run", fake_sub):
        assert v.download("https://youtu.be/a", Path(td), "none", want_subs=False, name_prefix="03_")
        assert v.download("https://youtu.be/a", Path(td), "none", want_subs=False)
    tpl = [c[c.index("-o") + 1] for c in cmds]
    assert tpl[0].endswith("media/03_%(id)s.%(ext)s") and tpl[1].endswith("media/%(id)s.%(ext)s")
    assert all("--no-playlist" in c for c in cmds), "单条下载仍然不能展开列表"
    meta = {"platform": "youtube", "video_id": "a", "title": "t", "author": {"name": "x"}, "published_at": "2026",
            "duration_sec": 1, "stats": {}, "text": {}, "capture": {}, "url": "u", "playlist": {"id": "L", "index": 3}}
    v.append_index(Path(td), meta, Path(td) / "slug")
    import csv
    row = list(csv.DictReader(open(Path(td) / "index.csv", encoding="utf-8-sig")))[0]
    assert row["playlist_id"] == "L" and row["playlist_index"] == "3"
    meta.pop("playlist"); v.append_index(Path(td), meta, Path(td) / "slug2")
    rows = list(csv.DictReader(open(Path(td) / "index.csv", encoding="utf-8-sig")))
    assert len(rows) == 2 and rows[1]["playlist_id"] == "" and rows[0]["playlist_id"] == "L"
print("PASS playlist: hint, parsing, bilibili parts/seasons, selection, resume, failure isolation, index, numbering")
