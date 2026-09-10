#!/usr/bin/env python3
"""Interface HTML local para o motor do emulador."""
import concurrent.futures, ctypes, datetime, hashlib, json, mimetypes, os, re, shutil, socket, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from mirror import TouchMirror
from camera_transfer import Transfers
from automation import Automation
from automation_queue import run_queue
from shared_camera import SharedCamera
from storage import clone_offline, finish_resize, DEFAULT_STORAGE_GIB
from voice_manager import VoiceManager
from product_writer import ProductWriter
from live_voice import LiveVoice
from tiktok_live import TikTokLive
from panel_runtime import runtime_identity, find_running_backend

HERE=os.path.dirname(os.path.abspath(__file__))
FROZEN=bool(getattr(sys,"frozen",False)); RES=getattr(sys,"_MEIPASS",HERE)
APP=os.path.dirname(sys.executable) if FROZEN else HERE
RUNTIME_ID=runtime_identity(RES,APP,sys.executable if FROZEN else None)
PORT=int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else 8768
WEB=os.path.join(RES,"web"); VIDEOS=os.path.join(APP,"videos")
AREA=os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam"); ATUAL=os.path.join(AREA,"atual.mp4")
SELECTED=os.path.join(AREA,"video-selecionado.json"); THUMBS=os.path.join(AREA,"previews"); RAW_READY=os.path.join(AREA,"emu_camera_video.i420")
LIBRARY_CONFIG=os.path.join(AREA,"video-library.json")
try:
    with open(LIBRARY_CONFIG,encoding="utf-8") as f:library_path=json.load(f)["path"]
    if os.path.isdir(library_path):VIDEOS=os.path.abspath(library_path)
except (OSError,ValueError,KeyError,TypeError):pass
os.makedirs(AREA,exist_ok=True)
with open(LIBRARY_CONFIG,"w",encoding="utf-8") as f:json.dump({"path":VIDEOS},f)
P=SourceFileLoader("engine",os.path.join(RES,"painel.pyw")).load_module()
E=object.__new__(P.Painel); E.cancelar_sync=threading.Event(); E.lock_historico=threading.Lock()
LOCK=threading.Lock(); S={"busy":False,"message":"Sistema pronto.","level":"ok","progress":0,"elapsed":0,"total":0,"task":""}
META_CACHE={}; PROXY_JOBS=set(); PROXY_LOCK=threading.Lock()
PHONE_NAMES=os.path.join(AREA,"phone-names.json")
PHONE_NAMES_LOCK=threading.Lock()

def phone_names():
    try:
        with open(PHONE_NAMES,encoding="utf-8") as f:return json.load(f)
    except (OSError,ValueError):return {}

def rename_phone(serial,name,label):
    if serial not in {v[0] for v in devices().values()}:raise ValueError("Celular desconhecido")
    name=str(name).strip();label=str(label).strip()
    if not name or len(name)>60 or len(label)>60:raise ValueError("Informe um nome de 1 a 60 caracteres; identificacao de ate 60 caracteres")
    if any(ord(c)<32 for c in name+label):raise ValueError("Nome invalido")
    with PHONE_NAMES_LOCK:
        data=phone_names();data[serial]={"name":name,"label":label}
        os.makedirs(AREA,exist_ok=True)
        with open(PHONE_NAMES+".tmp","w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False)
        os.replace(PHONE_NAMES+".tmp",PHONE_NAMES)

def hidden(): return P.sem_console()
MIRROR=TouchMirror(P.ADB,hidden)
TRANSFERS=Transfers(P.ADB,AREA,hidden)
SHARED=SharedCamera(AREA,os.path.dirname(os.path.dirname(P.ADB)),P.AVD_HOME,TRANSFERS,RES)
def update(**kw):
    with LOCK:S.update(kw)
def snap():
    with LOCK:return dict(S,backendPid=os.getpid(),backendVersion=5)
AUTOMATION=Automation(E,update)

def devices(): return P.descobrir_celulares() or {"MinutePlay":("emulator-5554","5554")}
VOICE=VoiceManager(AREA,RES,hidden)
WRITER=ProductWriter(AREA)
LIVE_VOICE=LiveVoice(VOICE,WRITER)
TIKTOK=TikTokLive(E._adb,devices)

def status(serial):
    try:
        r=E._adb(serial,"get-state",timeout=3)
        if r.returncode:return "off"
        b=E._adb(serial,"shell","getprop","sys.boot_completed",timeout=3)
        return "online" if b.stdout.strip()=="1" else "booting"
    except Exception:return "off"
def analytics(phone_names):
    with E.lock_historico:data=E._ler_historico()
    days=data.get("dias",{}) if isinstance(data,dict) else {}
    today=time.strftime("%Y-%m-%d"); by_task={}; by_phone={}; total_all=0.0
    for day,phones in days.items():
        if not isinstance(phones,dict):continue
        for phone,tasks in phones.items():
            if not isinstance(tasks,dict):continue
            for entry in tasks.values():
                if not isinstance(entry,dict):continue
                seconds=max(0.0,float(entry.get("segundos",0) or 0));total_all+=seconds
                if day==today:
                    name=str(entry.get("nome") or "Tarefa sem nome")
                    by_task[name]=by_task.get(name,0)+seconds;by_phone[phone]=by_phone.get(phone,0)+seconds
    recent=[]
    for offset in range(6,-1,-1):
        day=(datetime.date.today()-datetime.timedelta(days=offset)).isoformat();value=0.0
        for tasks in days.get(day,{}).values():
            if isinstance(tasks,dict):
                value+=sum(max(0.0,float(e.get("segundos",0) or 0)) for e in tasks.values() if isinstance(e,dict))
        recent.append({"date":day,"seconds":value})
    phone_rows=[{"name":name,"seconds":by_phone.get(name,0)} for name in phone_names]
    task_rows=[{"name":name,"seconds":seconds,"limit":P.LIMITE_TAREFA_SEGUNDOS*max(1,len(phone_names))} for name,seconds in sorted(by_task.items(),key=lambda x:x[1],reverse=True)]
    return {"todaySeconds":sum(by_task.values()),"totalSeconds":total_all,"activeTasks":len(by_task),"limitSeconds":P.LIMITE_TAREFA_SEGUNDOS,"byTask":task_rows,"byPhone":phone_rows,"last7Days":recent}
def video_meta(path):
    st=os.stat(path);key=(path,st.st_mtime_ns,st.st_size)
    if key in META_CACHE:return META_CACHE[key]
    result={"duration":0,"width":0,"height":0,"codec":""};probe=P.achar("ffprobe")
    if probe:
        try:
            p=subprocess.run([probe,"-v","error","-select_streams","v:0","-show_entries","stream=width,height,codec_name:format=duration","-of","json",path],capture_output=True,text=True,timeout=20,**hidden())
            raw=json.loads(p.stdout or "{}");stream=(raw.get("streams") or [{}])[0];fmt=raw.get("format") or {}
            result={"duration":float(fmt.get("duration") or 0),"width":int(stream.get("width") or 0),"height":int(stream.get("height") or 0),"codec":str(stream.get("codec_name") or "")}
        except Exception:pass
    for old in list(META_CACHE):
        if old[0]==path and old!=key:META_CACHE.pop(old,None)
    META_CACHE[key]=result;return result
def preview_source(path,meta):
    if meta.get("codec") in {"h264","vp8","vp9","av1"}:return {"playback":"/media?name="+urllib.parse.quote(os.path.basename(path)),"previewReady":True}
    os.makedirs(THUMBS,exist_ok=True);st=os.stat(path);ident=hashlib.sha1((path+str(st.st_mtime_ns)).encode()).hexdigest();out=os.path.join(THUMBS,ident+".mp4")
    if os.path.isfile(out):return {"playback":"/preview?id="+ident,"previewReady":True}
    def convert():
        tmp=os.path.join(THUMBS,ident+".building.mp4")
        try:
            ff=P.achar("ffmpeg")
            if ff:
                r=subprocess.run([ff,"-y","-i",path,"-map","0:v:0","-vf","scale='min(1280,iw)':-2","-c:v","libx264","-preset","veryfast","-crf","27","-pix_fmt","yuv420p","-movflags","+faststart","-an",tmp],capture_output=True,timeout=3600,**hidden())
                if r.returncode==0 and os.path.isfile(tmp):os.replace(tmp,out)
        finally:
            try:
                if os.path.isfile(tmp):os.remove(tmp)
            except OSError:pass
            with PROXY_LOCK:PROXY_JOBS.discard(ident)
    with PROXY_LOCK:
        if ident not in PROXY_JOBS:PROXY_JOBS.add(ident);threading.Thread(target=convert,daemon=True).start()
    return {"playback":"","previewReady":False}
def selected_name():
    try:return json.load(open(SELECTED,"r",encoding="utf-8")).get("name","")
    except Exception:return ""
STATUS_CACHE={};STATUS_AT=0;STATUS_LOCK=threading.Lock()
def panel_statuses():
    global STATUS_CACHE,STATUS_AT
    if time.monotonic()-STATUS_AT<5 or not STATUS_LOCK.acquire(blocking=False):return dict(STATUS_CACHE)
    try:
        r=subprocess.run([P.ADB,"devices"],capture_output=True,text=True,timeout=5,**hidden())
        if r.returncode==0:
            STATUS_CACHE={parts[0]:("online" if parts[1]=="device" else "booting") for line in r.stdout.splitlines()[1:] if len(parts:=line.split())==2}
        STATUS_AT=time.monotonic()
    except (OSError,subprocess.TimeoutExpired):STATUS_AT=time.monotonic()
    finally:STATUS_LOCK.release()
    return dict(STATUS_CACHE)

def payload():
    found=devices();states=panel_statuses();ps=[{"name":n,"serial":s,"port":p,"status":states.get(s,"off")} for n,(s,p) in found.items()]
    aliases=phone_names()
    for phone in ps:
        alias=aliases.get(phone["serial"],{})
        phone["avd"]=phone["name"]
        phone["name"]=alias.get("name") or phone["name"]
        phone["label"]=alias.get("label") or phone["serial"]
    os.makedirs(VIDEOS,exist_ok=True); vs=[]
    for n in sorted(os.listdir(VIDEOS),key=str.casefold):
        q=os.path.join(VIDEOS,n)
        if os.path.isfile(q) and n.lower().endswith(P.EXTS) and not os.path.splitext(n)[0].endswith((".pronto",".montado")):
            meta=video_meta(q);vs.append({"name":n,"size":os.path.getsize(q),**meta,"media":"/media?name="+urllib.parse.quote(n),"thumb":"/api/thumb?name="+urllib.parse.quote(n),**preview_source(q,meta)})
    transfer_state=TRANSFERS.snapshot()
    installed=transfer_state["installedVideos"]
    for phone in ps:
        phone["installedVideo"]=installed.get(phone["serial"])
        try:
            cfg=open(os.path.join(P.AVD_HOME,phone["avd"]+".avd","config.ini"),encoding="utf-8-sig").read()
            phone["storage"]=re.search(r"(?m)^disk.dataPartition.size\s*=\s*(.*)",cfg).group(1).strip()
        except (OSError,AttributeError):phone["storage"]="Desconhecido"
    known=[(installed[p["serial"]].get("name"),installed[p["serial"]].get("assetId")) if installed.get(p["serial"],{}).get("confirmed") else None for p in ps]
    common=known[0][0] if known and all(n and n==known[0] for n in known) else ""
    x=snap(); x.update(phones=ps,videos=vs,current=0,currentName=common,allVideoName=common,analytics=analytics(list(found)),mirror=MIRROR.state(),defaultStorageGiB=DEFAULT_STORAGE_GIB,apiVersion=4,sharedCameraVersion=1,automationVersion=5,queueVersion=1,automation=AUTOMATION.snapshot(),**transfer_state); return x

def start_phone(n,s,p):
    if status(s)!="off":return
    class MemoryStatus(ctypes.Structure):
        _fields_=[("length",ctypes.c_ulong),("load",ctypes.c_ulong)]+[(k,ctypes.c_ulonglong) for k in ("total","available","pageTotal","pageAvailable","virtualTotal","virtualAvailable","extended")]
    memory=MemoryStatus();memory.length=ctypes.sizeof(memory)
    if os.name=="nt" and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)) and memory.available<2300*1024**2:
        raise RuntimeError(f"RAM insuficiente para ligar {n}: {memory.available/1024**3:.1f} GiB livres. Feche outro celular ou aplicativo antes de continuar.")
    exe=os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe")
    if not os.path.isfile(exe):
        raise RuntimeError(f"Executável do emulador não encontrado: {exe}")
    args=[exe,"-avd",n,"-port",str(p),"-memory","2048","-no-snapshot","-timezone","America/Sao_Paulo","-camera-back","emulated","-camera-front","emulated","-gpu","auto"]+SHARED.arguments(n)
    log_path=os.path.join(AREA,n+"-startup.log")
    try:
        with open(log_path,"ab") as log:
            subprocess.Popen(args,cwd=os.path.dirname(exe),stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden())
    except OSError as exc:
        raise RuntimeError(f"Não foi possível iniciar {n} com {exe}: {exc}. Log: {log_path}") from exc
def open_minute(s):
    r=E._adb(s,"shell","monkey","-p","com.bakerdata.minute","-c","android.intent.category.LAUNCHER","1",timeout=15)
    if r.returncode:raise RuntimeError("Minute nao abriu")
def wait_open(s,end):
    while time.monotonic()<end:
        if status(s)=="online":open_minute(s);return True
        time.sleep(2)
    return False
def open_all():
    ds=list(devices().items());update(message="Ligando celulares...",progress=5)
    for n,(s,p) in ds:start_phone(n,s,p)
    end=time.monotonic()+420
    ok=E._paralelo([v[0] for _,v in ds],lambda s:wait_open(s,end))
    if not all(ok.values()):raise RuntimeError("algum celular nao concluiu o boot")
    update(busy=False,message="Tudo aberto: administrador e Minute.",level="ok",progress=100)
def video_control(s,a):
    subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",os.path.join(RES,"controlar-videocam.ps1"),"-Acao",a,"-Serial",s],check=True,**hidden())
def prepare_video(name,fill):
    src=os.path.join(VIDEOS,os.path.basename(name))
    if not os.path.isfile(src):raise RuntimeError("video nao encontrado")
    if prepared_cache(src,fill):
        update(stage="Quadros prontos",progress=100,message="Reutilizando os quadros ja preparados")
        return os.path.basename(name)
    os.makedirs(AREA,exist_ok=True);update(message="Preparando quadros sem compressao a partir do original...",progress=1)
    duration=video_meta(src).get("duration",0)
    if duration<=0:raise RuntimeError("Nao foi possivel ler a duracao do video")
    required=int(duration*640*360*1.5*30)+512*1024*1024
    if shutil.disk_usage(AREA).free<required:raise RuntimeError(f"O PC precisa de {required/1024**3:.1f} GiB livres para preparar este video")
    ff=P.achar("ffmpeg")
    if not ff:raise RuntimeError("ffmpeg nao encontrado")
    filt="scale=640:360:force_original_aspect_ratio=increase,crop=640:360,setsar=1" if fill else "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    cache_dir=os.path.join(AREA,"frame-cache");os.makedirs(cache_dir,exist_ok=True)
    raw_path=os.path.join(cache_dir,str(time.time_ns())+".i420")
    pending=raw_path+".partial"
    with open(os.path.join(AREA,"camera-conversion.log"),"w",encoding="utf-8") as log:
        p=subprocess.Popen([ff,"-y","-v","error","-progress","pipe:1","-nostats","-i",src,"-map","0:v:0","-vf",filt,"-r","30","-an","-pix_fmt","yuv420p","-f","rawvideo",pending],stdout=subprocess.PIPE,stderr=log,text=True,**hidden())
        for line in p.stdout:
            if line.startswith("out_time_us="):
                try:
                    percent=min(99,int(float(line.split("=",1)[1])/1e6/duration*100))
                    update(stage="Preparando quadros",progress=percent,message=f"Preparando quadros da camera: {percent}%")
                except ValueError:pass
        if p.wait():raise RuntimeError("Falha na preparacao; veja camera-conversion.log")
    os.replace(pending,raw_path)
    update(stage="Identificando vídeo",progress=0,message="Identificando o original para reutilizar os quadros...")
    copied=0;total=os.path.getsize(src);digest=hashlib.sha256()
    with open(src,"rb") as inp:
        while chunk:=inp.read(8*1024**2):
            digest.update(chunk);copied+=len(chunk);update(progress=int(copied*100/total))
    data={"name":os.path.basename(name),"sha256":digest.hexdigest(),"fill":bool(fill),"sourceSize":os.path.getsize(src),"sourceMtime":os.stat(src).st_mtime_ns,"rawSize":os.path.getsize(raw_path),"rawPath":raw_path}
    with open(cache_metadata_path(src,fill),"w",encoding="utf-8") as meta:json.dump(data,meta)
    with open(os.path.join(AREA,"prepared-video.json"),"w",encoding="utf-8") as meta:json.dump(data,meta)
    return os.path.basename(name)

def cache_metadata_path(src,fill):
    signature=f"{os.path.abspath(src)}:{os.stat(src).st_mtime_ns}:{os.path.getsize(src)}:{bool(fill)}"
    directory=os.path.join(AREA,"frame-cache");os.makedirs(directory,exist_ok=True)
    return os.path.join(directory,hashlib.sha256(signature.encode()).hexdigest()+".json")

def prepared_cache(src,fill):
    try:
        for metadata in [cache_metadata_path(src,fill),os.path.join(AREA,"prepared-video.json")]:
            try:
                with open(metadata,encoding="utf-8") as f:meta=json.load(f)
                meta.setdefault("rawPath",RAW_READY)
                if (meta["name"]==os.path.basename(src) and meta["fill"]==bool(fill) and
                    meta["sourceSize"]==os.path.getsize(src) and meta["sourceMtime"]==os.stat(src).st_mtime_ns and
                    meta["rawSize"]==os.path.getsize(meta["rawPath"])):
                    if metadata!=cache_metadata_path(src,fill):
                        with open(cache_metadata_path(src,fill),"w",encoding="utf-8") as f:json.dump(meta,f)
                    return meta
            except (OSError,ValueError,KeyError):pass
    except OSError:pass
    return None

def check_camera_space(serial,name):
    src=os.path.join(VIDEOS,os.path.basename(name))
    duration=video_meta(src).get("duration",0)
    if duration<=0:raise RuntimeError("Nao foi possivel ler o video")
    required=int(duration*640*360*1.5*30)+256*1024*1024
    result=E._adb(serial,"shell","df","-k","/data",timeout=15)
    rows=result.stdout.strip().splitlines()
    try:free=int(rows[-1].split()[3])*1024
    except (IndexError,ValueError):raise RuntimeError("Nao foi possivel conferir o espaco do celular")
    if free<required:raise RuntimeError(f"{serial}: video completo precisa de {required/1024**3:.1f} GiB livres; disponivel {free/1024**3:.1f} GiB. Aumente o armazenamento do emulador antes de enviar.")
def remember_video(name):
    with open(SELECTED,"w",encoding="utf-8") as f:json.dump({"name":os.path.basename(name)},f,ensure_ascii=False)

def install_video(s,name,fill):
    targets=[(n,s) for n,(serial,_) in devices().items() if serial==s]
    if not targets:raise RuntimeError("Selecione um celular valido")
    install_targets(targets,name,fill)

def install_video_all(name,fill):
    targets=[(n,s) for n,(s,_) in devices().items()]
    if not targets:raise RuntimeError("nenhum celular configurado")
    install_targets(targets,name,fill)

def install_targets(targets,name,fill):
    name=os.path.basename(name)
    aliases=phone_names()
    TRANSFERS.reset([(aliases.get(s,{}).get("name") or n,s) for n,s in targets],name)
    cache=prepared_cache(os.path.join(VIDEOS,name),fill)
    existing=TRANSFERS.snapshot()["installedVideos"]
    cache_id=(cache["sha256"]+":"+str(bool(fill))) if cache else None
    pending_targets=[(n,s) for n,s in targets if not(cache_id and existing.get(s,{}).get("confirmed") and existing[s].get("assetId")==cache_id and existing[s].get("mode")=="shared")]
    if not pending_targets:
        for n,s in targets:TRANSFERS.mark(s,stage="Concluido",bytes=cache["rawSize"],total=cache["rawSize"],percent=100)
        update(busy=False,stage="Concluido",progress=100,message="Este video ja esta confirmado em todos os destinos",level="ok")
        return
    for n,s in targets:TRANSFERS.mark(s,stage="Aguardando preparação",mode="shared")
    name=prepare_video(name,fill)
    cache=prepared_cache(os.path.join(VIDEOS,name),fill)
    if not cache:raise RuntimeError("Os quadros preparados não foram confirmados")
    asset_id=cache["sha256"]+":"+str(bool(fill));raw_path=cache["rawPath"]
    update(stage="Ativando câmeras",progress=0,message=f"Ativando vídeo compartilhado em {len(targets)} celulares...")
    failures=[]
    def send(target):
        n,s=target
        was_off=status(s)=="off"
        try:
            installed=TRANSFERS.snapshot()["installedVideos"].get(s,{})
            if installed.get("confirmed") and installed.get("assetId")==asset_id and installed.get("mode")=="shared":
                TRANSFERS.mark(s,stage="Concluido",bytes=os.path.getsize(raw_path),total=os.path.getsize(raw_path),percent=100)
                return n,None
            SHARED.install(n,s,dict(devices())[n][1],raw_path,name,os.path.getsize(os.path.join(VIDEOS,name)),asset_id,
                           start_phone,lambda serial:status(serial)=="online")
            return n,None
        except Exception as exc:
            TRANSFERS.mark(s,stage="Falhou",error=str(exc));return n,str(exc)
        finally:
            if was_off and len(targets)>1:
                E._adb(s,"shell","sync",timeout=90,check=True)
                E._adb(s,"emu","kill",timeout=15)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(2,len(targets))) as pool:
        futures=[pool.submit(send,target) for target in targets]
        while not all(f.done() for f in futures):
            rows=TRANSFERS.snapshot()["transfers"].values()
            percent=int(sum(r.get("percent",0) for r in rows)/len(targets))
            update(progress=percent,stage="Ativando câmeras",message=f"Ativando {name}: {percent}% • um único arquivo no PC, sem copiar os quadros para cada celular")
            time.sleep(1)
        for future in futures:
            n,error=future.result()
            if error:failures.append(n+": "+error)
    remember_video(name)
    if failures:raise RuntimeError(f"instalado em {len(targets)-len(failures)} de {len(targets)}; falhou: "+", ".join(failures))
    update(busy=False,stage="Concluido",progress=100,message=f"{name} instalado e confirmado nos {len(targets)} celulares.",level="ok")

def add_phone():
    ds=devices(); idx=max([P.indice_minuteplay(os.path.splitext(n)[0]) or 0 for n in os.listdir(P.AVD_HOME)]+[0])+1;n="MinutePlay"+str(idx);port=str(5554+(idx-1)*2);s="emulator-"+port
    dst=os.path.join(P.AVD_HOME,n+".avd")
    if not os.path.isdir(P.TEMPLATE_AVD):raise RuntimeError("modelo-base nao encontrado")
    clone_offline(P.TEMPLATE_AVD,dst,lambda done,total:update(progress=min(88,int(done/max(1,total)*88)),message="Criando "+n+" com 128 GiB..."))
    with open(os.path.join(P.AVD_HOME,n+".ini"),"w",encoding="utf8") as f:f.write("avd.ini.encoding=UTF-8\npath="+dst+"\npath.rel=avd\\"+n+".avd\ntarget=android-33\n")
    start_phone(n,s,port)
    if not wait_open(s,time.monotonic()+360):raise RuntimeError("boot demorou mais de 6 minutos")
    finish_resize(s,lambda message:update(message=message))
    E._adb(s,"shell","pm","clear","com.bakerdata.minute",timeout=30);open_minute(s)
    update(busy=False,progress=100,message=n+" criado sem login no Minute.",level="ok")
def sync(options=None):
    options=options or {}
    targets=devices()
    if options.get("scope")=="online":
        targets={n:(s,p) for n,(s,p) in targets.items() if status(s)=="online"}
    def prepare(n,s,p):
        if status(s)!="online":
            start_phone(n,s,p)
            if not wait_open(s,time.monotonic()+360):raise RuntimeError(n+": não iniciou em 6 minutos")
        if options.get("autoNavigate",True):
            open_minute(s)
            AUTOMATION.mark(s,stage="Aguardando o Minute abrir")
            AUTOMATION.wait_minute_ready(s)
    if options.get('manageRam', options.get('scope') != 'online') and options.get('autoNavigate',True):
        def boot(n,s,p):
            start_phone(n,s,p)
            deadline=time.monotonic()+360
            while time.monotonic()<deadline:
                AUTOMATION.check_cancel()
                if status(s)=='online' and E._adb(s,'shell','getprop','sys.boot_completed',timeout=8).stdout.strip()=='1':
                    time.sleep(4)
                    return
                time.sleep(2)
            raise RuntimeError(n+': Android não terminou de iniciar em 6 minutos')
        def shutdown(s):
            E._adb(s,'shell','sync',timeout=90,check=True)
            E._adb(s,'emu','kill',timeout=8,check=True)
            deadline=time.monotonic()+30
            while status(s)!='off' and time.monotonic()<deadline:time.sleep(1)
            if status(s)!='off':raise RuntimeError('Celular salvo não desligou: '+s)
            time.sleep(2)
        return run_queue(AUTOMATION,targets,prepare,TRANSFERS.snapshot()['installedVideos'],
                         str(options.get('taskName','')),True,bool(options.get('repeat',False)),
                         lambda s:status(s)=='online',boot,shutdown)
    update(queueActive=False,queueBatch=0,queueSaved=[],queuePending=[])
    AUTOMATION.run(targets,prepare,TRANSFERS.snapshot()["installedVideos"],
                   str(options.get("taskName", "")),bool(options.get("autoNavigate",True)),
                   repeat=bool(options.get("repeat",False)))


def job(kind,fn):
    with LOCK:
        if S["busy"]:raise RuntimeError("ja existe uma operacao em andamento")
        S.update(busy=True,level="info",progress=0,stage="Iniciando",operation=kind)
    def work():
        try:fn()
        except InterruptedError:update(busy=False,level="warn",message="Automação interrompida; confira os resultados por celular.")
        except Exception as x:update(busy=False,level="error",message=str(x))
    threading.Thread(target=work,daemon=True).start()

def action(d):
    a=d.get("action");s=d.get("serial","");by={v[0]:(n,v[1]) for n,v in devices().items()}
    if a=="mirror_stop":MIRROR.stop()
    elif a=="mirror_start":
        if snap()["busy"]:raise ValueError("Aguarde a operacao atual terminar")
        if s not in by or status(s)!="online":raise ValueError("Selecione um celular ligado")
        MIRROR.start(s,[serial for serial in by if serial!=s and status(serial)=="online"])
    elif a=="rename":rename_phone(s,d.get("name",""),d.get("label",""))
    elif a=="all_start":job(a,open_all)
    elif a=="start":n,p=by[s];start_phone(n,s,p)
    elif a=="stop":
        E._adb(s,"shell","sync",timeout=90,check=True)
        E._adb(s,"emu","kill",timeout=8)
    elif a=="minute":open_minute(s)
    elif a=="control":video_control(s,d["control"])
    elif a=="install":job(a,lambda:install_video(s,d["video"],d.get("fill",False)))
    elif a=="install_all":job(a,lambda:install_video_all(d["video"],d.get("fill",False)))
    elif a=="add":job(a,add_phone)
    elif a=="sync":
        if MIRROR.state()["active"]:raise ValueError("Pare o espelhamento antes da gravacao automatica")
        job(a,lambda:sync(d))
    elif a=="cancel":E.cancelar_sync.set()
    elif a=="loop_stop_after_round":AUTOMATION.request_stop_after_round()
    elif a=="adjust":
        if not snap()["task"]:raise RuntimeError("nenhuma tarefa detectada")
        E._definir_uso_tarefa(by[s][0],snap()["task"],int(d["minutes"])*60)
    else:raise RuntimeError("acao invalida")

class H(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def sendj(self,x,c=200):
        b=json.dumps(x,ensure_ascii=False).encode();self.send_response(c);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def video_path(self):
        name=os.path.basename(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("name",[""])[0]);path=os.path.abspath(os.path.join(VIDEOS,name))
        return path if path.startswith(os.path.abspath(VIDEOS)+os.sep) and os.path.isfile(path) else None
    def send_media(self,path):
        size=os.path.getsize(path);start,end=0,size-1;partial=False
        match=re.match(r"bytes=(\d*)-(\d*)",self.headers.get("Range", ""))
        if match:
            partial=True
            if match.group(1):start=int(match.group(1))
            if match.group(2):end=min(end,int(match.group(2)))
            elif start==0:end=min(end,4*1024*1024-1)
        if start<0 or start>end or start>=size:return self.send_error(416)
        length=end-start+1;self.send_response(206 if partial else 200)
        self.send_header("Content-Type",mimetypes.guess_type(path)[0] or "video/mp4");self.send_header("Accept-Ranges","bytes");self.send_header("Content-Length",str(length))
        if partial:self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path,"rb") as f:
            f.seek(start);left=length
            while left:
                chunk=f.read(min(left,1024*1024))
                if not chunk:break
                try:self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):break
                left-=len(chunk)
    def send_thumb(self,path):
        os.makedirs(THUMBS,exist_ok=True);st=os.stat(path);name=hashlib.sha1((path+str(st.st_mtime_ns)).encode()).hexdigest()+".jpg";out=os.path.join(THUMBS,name)
        if not os.path.isfile(out):
            ff=P.achar("ffmpeg")
            if ff:subprocess.run([ff,"-y","-ss","1","-i",path,"-frames:v","1","-vf","scale=640:-2","-q:v","3",out],capture_output=True,timeout=45,**hidden())
        if not os.path.isfile(out):return self.send_error(404)
        b=open(out,"rb").read();self.send_response(200);self.send_header("Content-Type","image/jpeg");self.send_header("Cache-Control","public, max-age=86400");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=urllib.parse.urlparse(self.path).path
        if path=="/api/version":return self.sendj(RUNTIME_ID)
        if path=="/api/state":return self.sendj(payload())
        if path=="/api/voice/state":return self.sendj(dict(VOICE.snapshot(),live=LIVE_VOICE.snapshot()))
        if path=="/api/voice/audio":
            ident=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id",[""])[0]
            try:q=VOICE.clip_path(ident)
            except ValueError:return self.send_error(404)
            return self.send_media(q) if q.is_file() and q.with_suffix('.json').is_file() else self.send_error(404)
        if path=="/media":
            q=self.video_path();return self.send_media(q) if q else self.send_error(404)
        if path=="/preview":
            ident=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id",[""])[0]
            q=os.path.join(THUMBS,ident+".mp4") if re.fullmatch(r"[0-9a-f]{40}",ident) else ""
            return self.send_media(q) if q and os.path.isfile(q) else self.send_error(404)
        if path=="/api/thumb":
            q=self.video_path();return self.send_thumb(q) if q else self.send_error(404)
        if path=="/":path="/index.html"
        q=os.path.abspath(os.path.join(WEB,path.lstrip("/")))
        if not q.startswith(os.path.abspath(WEB)) or not os.path.isfile(q):return self.send_error(404)
        b=open(q,"rb").read();mime={".html":"text/html",".css":"text/css",".js":"application/javascript"}.get(os.path.splitext(q)[1],"application/octet-stream")
        self.send_response(200);self.send_header("Content-Type",mime+"; charset=utf-8");self.send_header("Cache-Control","no-cache");self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        if self.path=="/api/voice/action":
            origin=self.headers.get("Origin")
            if origin and origin != "http://"+self.headers.get("Host", ""):
                return self.sendj({"error":"Origem não autorizada"},403)
            try:
                size=int(self.headers.get("Content-Length", "0"))
                if not 0<size<=16384:return self.sendj({"error":"Requisição inválida"},400)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError("Requisição inválida")
                command=data.get("action")
                result={"ok":True}
                if LIVE_VOICE.snapshot()['active'] and command in {'generate','play','unload'}:
                    raise ValueError('Pare a sessão contínua antes de usar este controle.')
                if command=="save_openai_key":WRITER.save_key(data.get('key'))
                elif command=="save_product":WRITER.save_product(data.get('product'))
                elif command in {'live_prepare','live_start'}:
                    LIVE_VOICE.start(data.get('product'),data.get('output',''),data.get('volume',.8),
                        data.get('minutes',60),data.get('steps',32),continuous=command=='live_start')
                elif command=="live_stop":LIVE_VOICE.stop()
                elif command=="unload":VOICE.unload()
                elif command=="generate":result["id"]=VOICE.generate(data.get("text"),data.get("style","natural"),data.get('steps',32))
                elif command=="play":VOICE.play(data.get("id"),data.get("output"),data.get("volume",0.8))
                elif command=="stop":VOICE.stop("playback")
                elif command=="cancel_generation":VOICE.stop("generation")
                elif command=="outputs":VOICE.refresh_outputs()
                elif command in {"tiktok_check","tiktok_open","tiktok_store","microphone_on","microphone_off"}:
                    if snap()["busy"]:raise ValueError("Aguarde a operação atual do painel terminar.")
                    serial=data.get("serial", "")
                    if command=="tiktok_check":result.update(TIKTOK.inspect(serial))
                    elif command=="tiktok_open":result.update(TIKTOK.open(serial))
                    elif command=="tiktok_store":result.update(TIKTOK.store(serial))
                    else:result.update(TIKTOK.microphone(serial,command=="microphone_on"))
                else:raise ValueError("Ação de voz inválida")
                return self.sendj(result)
            except (ValueError,TypeError,KeyError) as error:return self.sendj({"error":str(error)},400)
            except Exception as error:return self.sendj({"error":str(error)},500)
        if self.path=="/api/upload":
            n=os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename","video.mp4")));z=int(self.headers.get("Content-Length","0"));os.makedirs(VIDEOS,exist_ok=True)
            if not n.lower().endswith(P.EXTS):return self.sendj({"error":"formato de video invalido"},400)
            if not n or z<=0:return self.sendj({"error":"Arquivo vazio"},400)
            with LOCK:
                if S["busy"]:return self.sendj({"error":"Aguarde a operacao atual"},409)
                S.update(busy=True,stage="Importando",progress=0,level="info",message="Importando "+n)
            stem,extension=os.path.splitext(n);suffix=2
            while os.path.exists(os.path.join(VIDEOS,n)):
                n=f"{stem} ({suffix}){extension}";suffix+=1
            total=z;pending=os.path.join(VIDEOS,n)+".uploading"
            try:
                if shutil.disk_usage(VIDEOS).free<z+256*1024**2:raise RuntimeError("Espaco insuficiente no PC")
                with open(pending,"wb") as f:
                    while z:
                        q=self.rfile.read(min(z,8*1024*1024))
                        if not q:raise RuntimeError("Upload interrompido")
                        f.write(q);z-=len(q)
                        update(progress=int((total-z)*100/total),message="Importando "+n)
                os.replace(pending,os.path.join(VIDEOS,n))
                update(busy=False,progress=100,message=n+" importado",stage="Concluido",level="ok")
                return self.sendj({"ok":True,"name":n})
            except Exception as exc:
                if os.path.isfile(pending):os.remove(pending)
                update(busy=False,level="error",message=str(exc))
                return self.sendj({"error":str(exc)},400)
        try:d=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}");action(d);self.sendj({"ok":True},202)
        except Exception as x:self.sendj({"error":str(x)},400)
def open_ui():
    url=f"http://127.0.0.1:{PORT}/";edge=next((x for x in [os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")] if os.path.isfile(x)),None)
    subprocess.Popen([edge,"--app="+url,"--start-maximized"],**hidden()) if edge else webbrowser.open(url)
class PanelServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR allows multiple processes to steal the same listener.
    allow_reuse_address=False

    def server_bind(self):
        if os.name=="nt":
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


def main():
    global PORT
    if FROZEN and len(sys.argv)>1 and sys.argv[1]=="--montar":import montar;montar.main(sys.argv[2:]);return
    # Closing the Edge window does not stop the backend. Reuse only an exact
    # compatible version, otherwise bind a free local port and leave it intact.
    first_port=PORT
    existing=find_running_backend(first_port,RUNTIME_ID)
    if existing is not None:
        PORT=existing
        publish_runtime()
        if "--no-open" not in sys.argv:open_ui()
        return
    server=None
    for candidate in range(first_port,first_port+8):
        try:server=PanelServer(("127.0.0.1",candidate),H)
        except OSError:continue
        PORT=candidate
        break
    if server is None:raise RuntimeError("Não há uma porta local disponível para abrir o painel atualizado.")
    publish_runtime()
    if "--no-open" not in sys.argv:threading.Timer(.5,open_ui).start()
    if "--abrir-tudo" in sys.argv:threading.Timer(1,lambda:job("all",open_all)).start()
    server.serve_forever()
def publish_runtime():
    target=os.path.join(WEB,'current-runtime.json')
    temporary=target+'.tmp'
    with open(temporary,'w',encoding='utf-8') as out:
        json.dump(dict(RUNTIME_ID,url=f'http://127.0.0.1:{PORT}/'),out)
    os.replace(temporary,target)

if __name__=="__main__":main()
