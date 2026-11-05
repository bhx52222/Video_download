"""App bridge: JSON on stdin, readable progress on stdout; never invokes a shell."""
import json, os, re, signal, subprocess, sys, threading, runpy, time
from pathlib import Path
import downie_bridge
BACKEND = Path(__file__).resolve().parent / 'backend'
# 链接解析只留 vx_link 一份。这里原来有一份自己的正则和标点表，
# 和 vx_link.py、LinkTools.swift 三份互相不一致：抖音「精选」页不规范化、
# 尾部的 ？】》… 会被吃进 URL，结果是 CLI 能下、App 下不了。
sys.path.insert(0, str(BACKEND))
import vx_link
import vx_playlist
from vx_process import spawn
from vx_runtime import configure
configure(Path(__file__).resolve().parent)
CORE = BACKEND / 'vx.py'
child = None
cancelled = False

def stop(signum, frame):
    global cancelled
    cancelled = True
    if child and child.poll() is None:
        if os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True)
            return
        pgid=child.pid
        try: os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError: return
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired: pass
        try: os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError: pass

def targets(text):
    """输入区文本 → 待处理队列。本地文件按原路径入队，其余交给 vx_link 解析。

    vx_link 负责剥中文标点、还原 HTML 转义、规范化平台链接
    （如抖音 /jingxuan?modal_id=<id> → /video/<id>，否则 yt-dlp 报 Unsupported URL）。
    认不出平台不算失败，原样入队交给内核通用兜底。"""
    found=[]
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        p=Path(line.strip('"')).expanduser()
        try: local=p.is_file()
        except OSError: local=False
        if local:
            item=vx_link.read_file_link(p)
            if item:found.append(vx_link.classify(item).url)
            elif p.suffix.lower() not in ('.webloc','.url'):found.append(str(p))
            continue
        found.extend(link.url for link in vx_link.parse_text(line))
    return list(dict.fromkeys(found))

def probe_action(config):
    """只回答“输入里哪些是列表”，不下载。查不出来按单条走，所以这里永远不算失败。"""
    # 查询是只读的：取消时直接退出，不必等 yt-dlp 跑完。
    signal.signal(signal.SIGTERM,lambda *_:os._exit(130));signal.signal(signal.SIGINT,lambda *_:os._exit(130))
    urls=vx_playlist.to_probe(targets(config.get('text','')))
    found=[]
    if urls:
        core=runpy.run_path(str(CORE))
        core['run'].__globals__['YOUTUBE_COOKIES']=bool(config.get('youtube_cookies'))
        browser=core['browser_list'](config.get('cookies','none'))[0]
        for url in urls:
            print('正在读取列表清单：'+url,flush=True)
            try:info=vx_playlist.probe(url,core,browser)
            except Exception as e:
                print(f'读取清单失败，按单条处理：{type(e).__name__}: {e}',flush=True);continue
            if info:found.append(info)
    print(vx_playlist.MARKER+json.dumps(found,ensure_ascii=False),flush=True)
    return 0

def resolve_selection(url,selections):
    """返回 (实际要跑的单条链接, 列表信息)，两者只有一个有值；都没有表示跳过。"""
    chosen=selections.get(url)
    if not chosen:return url,None
    if chosen.get('choice')=='single':return chosen.get('current_url'),None
    return None,chosen

def command(url, config, job=None):
    target=['--playlist-job',str(job)] if job else [url]
    cmd=[sys.executable, '-X', 'utf8', '-B', '-u', str(CORE), *target, '--lib', str(Path(config['folder']).expanduser()),
         '--cookies', config.get('cookies','edge,chrome'), '--tiktok-backend',config.get('tiktok','direct')]
    max_res=int(config.get('max_res',1080))
    if max_res not in (720,1080,2160):raise ValueError('无效画质选项')
    cmd+=['--max-res',str(max_res)]
    if config.get('youtube_cookies'):cmd+=['--youtube-cookies']
    mode=config.get('mode',0)
    if mode==0:cmd+=['--download-only']
    elif mode==2:cmd+=['--dual']
    lang=config.get('language','auto')
    if lang in ('zh','en'):cmd+=['--lang',lang]
    if config.get('force'):cmd+=['--force']
    if config.get('redownload'):cmd+=['--redownload']
    return cmd

def main():
    global child
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    config=json.load(sys.stdin)
    if config.get('action')=='probe':return probe_action(config)
    if config.get('youtube_backend','core') not in ('core','auto','downie','idm'):raise ValueError('无效 YouTube 下载方式')
    if config.get('tiktok','direct') not in ('direct','auto','tikwm'):raise ValueError('无效 TikTok 模式')
    if config.get('cookies','edge,chrome') not in ('edge,chrome','chrome,edge','edge','chrome','none'):raise ValueError('无效浏览器选项')
    queue=targets(config.get('text',''))
    selections={item['source_url']:item for item in config.get('playlists',[])}
    if not queue:print('没有找到有效链接或本地文件。',flush=True);return 2
    folder=Path(config['folder']).expanduser();folder.mkdir(parents=True,exist_ok=True)
    if not CORE.exists():print('App 内核文件缺失。',flush=True);return 2
    # App 子进程不能共享内核内存；在父进程按同一套平台规则补足间隔。
    policy=runpy.run_path(str(Path(__file__).resolve().parent/'backend/vx.py'))
    previous={}
    ok=0;failed=0
    def execute(cmd):
        global child
        mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT}) if os.name != 'nt' else None
        try:
            child=spawn(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',errors='replace',start_new_session=os.name != 'nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,bufsize=1)
        finally:
            if mask is not None:signal.pthread_sigmask(signal.SIG_SETMASK,mask)
        for line in child.stdout:
            clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',line)
            print(clean.rstrip(),flush=True)
        code=child.wait();child=None
        return code

    for index,source in enumerate(queue,1):
        if cancelled:break
        url,playlist=resolve_selection(source,selections)
        if not url and not playlist:
            print(f'跳过：{source}（列表里没有当前视频）',flush=True);failed+=1;continue
        url=url or source
        platform=policy.get('platform_of',lambda u:'unknown')(url)
        gap=policy.get('PLATFORM_MIN_GAP',{}).get(platform,policy.get('DEFAULT_MIN_GAP',1.5))
        deadline=previous.get(platform,0)+gap
        if time.monotonic()<deadline:print(f'同平台间隔等待 {deadline-time.monotonic():.1f} 秒…',flush=True)
        while not cancelled and time.monotonic()<deadline:time.sleep(max(0,min(.1,deadline-time.monotonic())))
        if cancelled:break
        print(f'\n━━ 任务 {index}/{len(queue)} ━━\n{url}',flush=True)
        if playlist:
            # 列表走内核：序号、断点和总表都在内核里，外部下载器接不上这一套。
            job=vx_playlist.write_job(playlist,playlist['selected'],folder,policy['safe'])
            code=execute(command(url,config,job))
            previous[platform]=time.monotonic()
            if cancelled:break
            # 小结按视频计数，不把整个列表算成一条。
            rows=vx_playlist.read_index(job.parent/'index.csv')
            chosen=playlist['selected']
            done=sum(rows.get(i,{}).get('status') in vx_playlist.DONE_STATUSES for i in chosen) if rows else (len(chosen) if code==0 else 0)
            ok+=done;failed+=len(chosen)-done
            continue
        backend=config.get('youtube_backend','core') if downie_bridge.youtube_url(url) else 'core'
        code=1 if backend in ('downie','idm') else execute(command(url,config))
        if code==3:
            # 这是列表而不是下载失败，转给 Downie/IDM 只会白等 10 分钟。
            print('这个链接是列表或合集，没有转交外部下载器。',flush=True)
            backend='core'
        if os.name == 'nt' and code and backend in ('auto','idm') and not cancelled:
            import idm_bridge
            try:
                media, metadata=idm_bridge.download(url,config,policy,lambda:cancelled,lambda m:print(m,flush=True))
                if media and not cancelled:
                    cmd=command(str(media),config)+['--as','youtube','--source-url',url,'--title',metadata.get('title') or media.stem,'--channel','IDM 备用下载','--tool','IDM']
                    code=execute(cmd)
                    (media.parent/'source.json').write_text(json.dumps({'url':url,'status':'imported' if code==0 else 'import_failed'}),encoding='utf-8')
            except Exception as e:print('IDM 未完成：'+str(e),flush=True)
        if os.name != 'nt' and code and backend in ('auto','downie') and not cancelled:
            token=config.get('handoff_token')
            if not token:
                print('Downie 备用需要由 App 启动，未发送下载任务。',flush=True)
            else:
                job=downie_bridge.make_job(url,folder,token)
                print('@@VX_DOWNIE@@'+json.dumps(job,ensure_ascii=False),flush=True)
                media=downie_bridge.wait_media(job,lambda:cancelled,lambda msg:print(msg,flush=True))
                if media and not cancelled:
                    print('Downie 已返回可读视频，继续校验并归档。',flush=True)
                    follow=dict(config);follow['youtube_backend']='core'
                    cmd=command(str(media),follow)+['--as','youtube','--source-url',url,'--title',media.stem,
                        '--channel','Downie 备用下载','--tool','Downie 4','--note','媒体由 Downie 获取；画质遵循 Downie 的选择，非拾影画质上限。']
                    code=execute(cmd)
                    (Path(job['destination'])/'source.json').write_text(json.dumps({'url':url,'status':'imported' if code==0 else 'import_failed'},ensure_ascii=False))
                elif not cancelled:
                    print('Downie 未在等待期限内返回有效媒体；未标记成功。可稍后通过添加本地视频继续导入。',flush=True)
        previous[platform]=time.monotonic()
        if cancelled:break
        if code==0:ok+=1
        else:failed+=1
    if cancelled:
        print(f'\n已取消。完成 {ok} 条，失败 {failed} 条；已下载的文件保留。',flush=True);return 130
    print(f'\n全部处理结束：完成或已存在 {ok} 条，失败 {failed} 条。\n结果目录：{folder}',flush=True)
    return 1 if failed else 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc: print(f'无法继续：{type(exc).__name__}: {exc}',flush=True);sys.exit(2)
