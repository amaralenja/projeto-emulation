#!/usr/bin/env python3
"""Interface HTML local para o motor do emulador."""
import concurrent.futures, datetime, hashlib, json, mimetypes, os, re, shutil, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader

HERE=os.path.dirname(os.path.abspath(__file__))
FROZEN=bool(getattr(sys,"frozen",False)); RES=getattr(sys,"_MEIPASS",HERE)
APP=os.path.dirname(sys.executable) if FROZEN else HERE
WEB=os.path.join(RES,"web"); VIDEOS=os.path.join(APP,"videos")
AREA=os.path.expandvars(r"%LOCALAPPDATA%\emulation-cam"); ATUAL=os.path.join(AREA,"atual.mp4")
SELECTED=os.path.join(AREA,"video-selecionado.json"); THUMBS=os.path.join(AREA,"previews"); RAW_READY=os.path.join(AREA,"emu_camera_video.i420")
P=SourceFileLoader("engine",os.path.join(RES,"painel.pyw")).load_module()
E=object.__new__(P.Painel); E.cancelar_sync=threading.Event(); E.lock_historico=threading.Lock()
LOCK=threading.Lock(); S={"busy":False,"message":"Sistema pronto.","level":"ok","progress":0,"elapsed":0,"total":0,"task":""}
META_CACHE={}; PROXY_JOBS=set(); PROXY_LOCK=threading.Lock()

def hidden(): return P.sem_console()
def update(**kw):
    with LOCK:S.update(kw)
def snap():
    with LOCK:return dict(S)
def devices(): return P.descobrir_celulares() or {"MinutePlay":("emulator-5554","5554")}
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
def payload():
    found=devices();ps=[{"name":n,"serial":s,"port":p,"status":status(s)} for n,(s,p) in found.items()]
    os.makedirs(VIDEOS,exist_ok=True); vs=[]
    for n in sorted(os.listdir(VIDEOS),key=str.casefold):
        q=os.path.join(VIDEOS,n)
        if os.path.isfile(q) and n.lower().endswith(P.EXTS) and not os.path.splitext(n)[0].endswith((".pronto",".montado")):
            meta=video_meta(q);vs.append({"name":n,"size":os.path.getsize(q),**meta,"media":"/media?name="+urllib.parse.quote(n),"thumb":"/api/thumb?name="+urllib.parse.quote(n),**preview_source(q,meta)})
    x=snap(); x.update(phones=ps,videos=vs,current=os.path.getsize(ATUAL) if os.path.isfile(ATUAL) else 0,currentName=selected_name(),analytics=analytics(list(found))); return x
def start_phone(n,s,p):
    if status(s)!="off":return
    exe=os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe")
    subprocess.Popen([exe,"-avd",n,"-port",p,"-no-snapshot","-timezone","America/Sao_Paulo","-camera-back","emulated","-camera-front","emulated","-gpu","auto"],**hidden())
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
    os.makedirs(AREA,exist_ok=True);update(message="Convertendo video...",progress=1)
    cmd=([sys.executable,"--montar"] if FROZEN else [sys.executable,os.path.join(RES,"montar.py")])+["--fundo",src,"--ajuste","cheio" if fill else "caber","--instalar","--progresso","-o",os.path.join(AREA,"trabalho.mp4")]
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,**hidden())
    for line in p.stdout:
        if line.startswith("PROGRESSO:"):
            try:update(progress=min(78,int(int(line.split(":")[1])*.78)),message=line.strip().replace("PROGRESSO:","Preparando video: ")+"%")
            except:pass
    if p.wait():raise RuntimeError("falha ao converter video")
    update(progress=79,message="Gerando formato da camera uma unica vez...")
    ff=P.achar("ffmpeg")
    if not ff:raise RuntimeError("ffmpeg nao encontrado")
    r=subprocess.run([ff,"-y","-i",ATUAL,"-vf","scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1","-r","30","-an","-pix_fmt","yuv420p","-f","rawvideo",RAW_READY],capture_output=True,timeout=7200,**hidden())
    if r.returncode or not os.path.isfile(RAW_READY):raise RuntimeError("falha ao gerar o video da camera")
    return os.path.basename(name)
def push_ready(s):
    subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",os.path.join(RES,"instalar-videocam.ps1"),"-Video",RAW_READY,"-Serial",s,"-I420Pronto"],check=True,**hidden())
def remember_video(name):
    with open(SELECTED,"w",encoding="utf-8") as f:json.dump({"name":os.path.basename(name)},f,ensure_ascii=False)
def install_video(s,name,fill):
    name=prepare_video(name,fill);update(progress=82,message="Enviando para a camera...");push_ready(s);remember_video(name)
    update(busy=False,progress=100,message="Video instalado; Android reiniciando.",level="ok")
def install_video_all(name,fill):
    targets=[(n,s) for n,(s,_) in devices().items() if status(s)=="online"]
    if not targets:raise RuntimeError("nenhum celular online")
    name=prepare_video(name,fill);done=0;failures=[];update(progress=82,message=f"Enviando para {len(targets)} celulares...")
    def send(target):
        n,s=target
        try:push_ready(s);return n,None
        except Exception as exc:return n,str(exc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(6,len(targets))) as pool:
        futures=[pool.submit(send,target) for target in targets]
        for future in concurrent.futures.as_completed(futures):
            n,error=future.result();done+=1
            if error:failures.append(n)
            update(progress=82+int(done/len(targets)*18),message=f"Instalando: {done} de {len(targets)} celulares...")
    remember_video(name)
    if failures:raise RuntimeError(f"instalado em {len(targets)-len(failures)} de {len(targets)}; falhou: "+", ".join(failures))
    update(busy=False,progress=100,message=f"Video instalado nos {len(targets)} celulares; reiniciando Android.",level="ok")
def add_phone():
    ds=devices(); idx=max(P.indice_minuteplay(n) for n in ds)+1;n="MinutePlay"+str(idx);port=str(5554+(idx-1)*2);s="emulator-"+port
    dst=os.path.join(P.AVD_HOME,n+".avd")
    if not os.path.isdir(P.TEMPLATE_AVD):raise RuntimeError("modelo-base nao encontrado")
    files=[];total=0
    for root,dirs,names in os.walk(P.TEMPLATE_AVD):
        dirs[:]=[d for d in dirs if not d.endswith(".lock") and d!="tmpAdbCmds"]
        for f in names:
            if f.endswith(".lock") or f in {"hardware-qemu.ini","emu-launch-params.txt","multiinstance.lock"}:continue
            a=os.path.join(root,f);b=os.path.join(dst,os.path.relpath(a,P.TEMPLATE_AVD));z=os.path.getsize(a);files.append((a,b,z));total+=z
    done=0
    for a,b,z in files:
        os.makedirs(os.path.dirname(b),exist_ok=True)
        with open(a,"rb") as i,open(b,"wb") as o:
            while q:=i.read(8*1024*1024):o.write(q);done+=len(q);update(progress=min(88,int(done/max(1,total)*88)),message="Criando "+n+"...")
        shutil.copystat(a,b)
    with open(os.path.join(P.AVD_HOME,n+".ini"),"w",encoding="utf8") as f:f.write("avd.ini.encoding=UTF-8\npath="+dst+"\npath.rel=avd\\"+n+".avd\ntarget=android-33\n")
    start_phone(n,s,port)
    if not wait_open(s,time.monotonic()+360):raise RuntimeError("boot demorou mais de 6 minutos")
    E._adb(s,"shell","pm","clear","com.bakerdata.minute",timeout=30);open_minute(s)
    update(busy=False,progress=100,message=n+" criado sem login no Minute.",level="ok")
def sync():
    E.cancelar_sync.clear();parts=[];names={};durs={};trigger=False
    update(message="Procurando cameras prontas...",progress=1,task="",elapsed=0,total=0)
    for n,(s,_) in devices().items():
        d=E._camera_pronta(s)
        if d is not None:parts.append(s);names[s]=n;durs[s]=d
    if not parts:raise RuntimeError("abra a camera da tarefa em cada Minute")
    if max(durs.values())-min(durs.values())>.15:raise RuntimeError("videos diferentes nos celulares")
    total=min(durs.values());duration=total-1
    if total<61.5:raise RuntimeError("o Minute exige pelo menos 1 minuto")
    try:
        gens=E._paralelo(parts,E._ler_geracao);gens={s:g+1 for s,g in gens.items()}
        E._paralelo(parts,lambda s:E._escrever_controle(s,"pause",gens[s]))
        before=E._paralelo(parts,E._pastas_gravacao);E._paralelo(parts,E._tocar_botao_gravacao);trigger=True
        end=time.monotonic()+18;sessions=E._paralelo(parts,lambda s:E._esperar_gravacao(s,before[s],end))
        tasks=E._paralelo(parts,lambda s:E._detectar_tarefa_sessao(s,sessions[s]))
        if len({x[0] for x in tasks.values()})!=1:
            E._paralelo(parts,E._tocar_botao_gravacao);E._paralelo(parts,E._confirmar_descarte_curto);trigger=False;raise RuntimeError("celulares em tarefas diferentes")
        task=next(iter(tasks.values()))[1];update(task=task,message="Tarefa detectada: "+task)
        blocked=[]
        for s in parts:
            used=E._uso_tarefa(names[s],tasks[s][1])
            if used+duration>P.LIMITE_TAREFA_SEGUNDOS+.01:blocked.append(names[s]+": "+E._horas_minutos(max(0,P.LIMITE_TAREFA_SEGUNDOS-used))+" restantes")
        if blocked:
            E._paralelo(parts,E._tocar_botao_gravacao);E._paralelo(parts,E._confirmar_descarte_curto);trigger=False;raise RuntimeError("limite de 2h para "+task+". "+"; ".join(blocked))
        E._paralelo(parts,lambda s:E._escrever_controle(s,"play",gens[s]));t=time.monotonic()
        while not E.cancelar_sync.is_set():
            e=time.monotonic()-t;update(elapsed=min(e,total),total=total,progress=min(99,int(e/duration*100)),message="Gravando "+task+"...")
            if e>=duration:break
            time.sleep(.1)
        if E.cancelar_sync.is_set():raise InterruptedError()
        E._paralelo(parts,E._tocar_botao_gravacao);trigger=False;update(message="Salvando em todos...",progress=99)
        saved=E._paralelo(parts,lambda s:E._salvar_minute(s))
        for s in parts:
            if saved[s]:E._somar_uso_tarefa(names[s],tasks[s][1],duration)
        update(busy=False,progress=100,message=task+": salvo em todos.",level="ok")
    except:
        if trigger:
            try:E._paralelo(parts,E._tocar_botao_gravacao)
            except:pass
        raise
def job(kind,fn):
    if snap()["busy"]:raise RuntimeError("ja existe uma operacao em andamento")
    def work():
        try:update(busy=True,level="info",progress=0);fn()
        except InterruptedError:update(busy=False,level="warn",message="Cancelado sem salvar.")
        except Exception as x:update(busy=False,level="error",message=str(x),progress=0)
    threading.Thread(target=work,daemon=True).start()
def action(d):
    a=d.get("action");s=d.get("serial","");by={v[0]:(n,v[1]) for n,v in devices().items()}
    if a=="all_start":job(a,open_all)
    elif a=="start":n,p=by[s];start_phone(n,s,p)
    elif a=="stop":E._adb(s,"emu","kill",timeout=8)
    elif a=="minute":open_minute(s)
    elif a=="control":video_control(s,d["control"])
    elif a=="install":job(a,lambda:install_video(s,d["video"],d.get("fill",False)))
    elif a=="install_all":job(a,lambda:install_video_all(d["video"],d.get("fill",False)))
    elif a=="add":job(a,add_phone)
    elif a=="sync":job(a,sync)
    elif a=="cancel":E.cancelar_sync.set()
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
        if path=="/api/state":return self.sendj(payload())
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
        if self.path=="/api/upload":
            n=os.path.basename(urllib.parse.unquote(self.headers.get("X-Filename","video.mp4")));z=int(self.headers.get("Content-Length","0"));os.makedirs(VIDEOS,exist_ok=True)
            if not n.lower().endswith(P.EXTS):return self.sendj({"error":"formato de video invalido"},400)
            with open(os.path.join(VIDEOS,n),"wb") as f:
                while z:q=self.rfile.read(min(z,8*1024*1024));f.write(q);z-=len(q)
            return self.sendj({"ok":True,"name":n})
        try:d=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}");action(d);self.sendj({"ok":True},202)
        except Exception as x:self.sendj({"error":str(x)},400)
def open_ui():
    url="http://127.0.0.1:8765/";edge=next((x for x in [os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")] if os.path.isfile(x)),None)
    subprocess.Popen([edge,"--app="+url,"--start-maximized"],**hidden()) if edge else webbrowser.open(url)
def main():
    if FROZEN and len(sys.argv)>1 and sys.argv[1]=="--montar":import montar;montar.main(sys.argv[2:]);return
    try:server=ThreadingHTTPServer(("127.0.0.1",8765),H)
    except OSError:open_ui();return
    if "--no-open" not in sys.argv:threading.Timer(.5,open_ui).start()
    if "--abrir-tudo" in sys.argv:threading.Timer(1,lambda:job("all",open_all)).start()
    server.serve_forever()
if __name__=="__main__":main()
