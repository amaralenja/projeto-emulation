"""Durable run intent and capture journal; recovery never discards a video."""
import json
import math
import os
import re
import threading
import time
from automation import task_key, confirmed_recording_seconds


def read_json(path, fallback):
    try:
        with open(path,encoding='utf-8') as stream: return json.load(stream)
    except (OSError,ValueError): return fallback


def write_json(path, value):
    with open(path+'.tmp','w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False)
        stream.flush();os.fsync(stream.fileno())
    os.replace(path+'.tmp',path)


def credit_history(history, entry, seconds):
    """Credit + session marker are committed in the same history document."""
    seconds=float(seconds)
    if not math.isfinite(seconds) or not 0<seconds<=1799: raise ValueError('Duração inválida')
    session=entry['session']
    ledger=history.setdefault('supervisorSessions',{})
    if session in ledger:return False
    task=entry['task'];key=' '.join(task_key(task))
    tasks=history.setdefault('dias',{}).setdefault(entry['day'],{}).setdefault(entry['phone'],{})
    keys=[k for k,v in tasks.items() if task_key(v.get('nome') or k)==task_key(task)]
    total=sum(float(tasks[k].get('segundos',0)) for k in keys)
    for old in keys:del tasks[old]
    tasks[key]={'nome':task,'segundos':min(7200,total+seconds)}
    ledger[session]={'day':entry['day'],'phone':entry['phone'],'seconds':seconds}
    return True


class LoopSupervisor:
    def __init__(self, area, history_path, engine, automation, update):
        self.path=os.path.join(area,'loop-supervisor.json')
        self.history_path=history_path
        self.e,self.a,self.update=engine,automation,update
        self.lock=threading.RLock()
        self.ensure_online=lambda serial:None

    def state(self):return read_json(self.path,{'enabled':False,'pending':{}})

    def change(self, **fields):
        with self.lock:
            state=self.state();state.update(fields);write_json(self.path,state)

    def begin(self, options, url):
        self.change(enabled=True,options=options,url=url,ownerPid=os.getpid(),lastError='',restarts=0)

    def stop(self):self.change(enabled=False)

    def checkpoint(self, serial, **fields):
        with self.lock:
            state=self.state();entry=state.setdefault('pending',{}).setdefault(serial,{})
            entry.update(fields);entry['serial']=serial
            write_json(self.path,state)

    def clear(self,serial):
        with self.lock:
            state=self.state();state.setdefault('pending',{}).pop(serial,None);write_json(self.path,state)

    def credit(self,serial,seconds):
        entry=self.state()['pending'][serial]
        with self.e.lock_historico:
            history=self.e._ler_historico()
            if credit_history(history,entry,seconds):write_json(self.history_path,history)
        self.clear(serial)

    def recover(self):
        for serial,entry in self.state().get('pending',{}).items():
            self.a.check_cancel()
            self.ensure_online(serial)
            connection=self.e._adb(serial,'get-state',timeout=8,check=True)
            if connection.stdout.strip()!='device':raise RuntimeError('Celular pendente desconectado: '+serial)
            session=entry.get('session')
            if not session:
                new=self.e._pastas_gravacao(serial)-set(entry.get('before',[]))
                if not new:
                    self.clear(serial);continue
                if len(new)!=1:raise RuntimeError('Mais de uma captura pendente em '+serial+'; vídeos preservados.')
                session=next(iter(new));self.checkpoint(serial,session=session)
            if not re.fullmatch(r'[\w-]+',session):raise RuntimeError('Identificador de captura inválido')
            self.update(supervisorStage='Recuperando gravação',message='Conferindo gravação pendente em '+serial)
            raw=self.e._shell_root_bytes(serial,'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store',timeout=15)
            seconds=confirmed_recording_seconds(raw,session)
            if seconds is None:
                # Stop only a known journaled capture whose file is still growing.
                path='/data/user/0/com.bakerdata.minute/files/recordings/'+session+'/video.mp4'
                def size():return int(self.e._shell_root(serial,'stat -c %s '+path,timeout=12,check=True).stdout.strip())
                first=size()
                if self.e.cancelar_sync.wait(2):self.a.check_cancel()
                if size()>first and self.a.minute_foreground(serial) and self.e._camera_pronta(serial) is not None:
                    self.e._tocar_botao_gravacao(serial)
                self.a.launch_minute(serial)
                self.a.save(serial)
                raw=self.e._shell_root_bytes(serial,'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store',timeout=15)
                seconds=confirmed_recording_seconds(raw,session)
            if seconds is None:raise RuntimeError('Vídeo preservado; aguardando confirmação do salvamento/envio em '+serial)
            _,actual=self.e._detectar_tarefa_sessao(serial,session)
            if task_key(actual)!=task_key(entry['task']):raise RuntimeError('A tarefa da gravação pendente precisa ser conferida.')
            self.credit(serial,seconds)
            self.a.mark(serial,stage='Salvo',percent=100,error='')

    def run(self, operation, reset_idle):
        failures=0
        while self.state().get('enabled'):
            self.a.check_cancel()
            if self.a.stop_after_round.is_set():self.stop();return
            try:
                self.recover()
                self.update(supervisorStage='Acompanhando',supervisorAttempts=failures)
                operation()
                self.stop();return
            except InterruptedError:
                self.stop();raise
            except Exception as exc:
                failures+=1
                if self.e.cancelar_sync.is_set() or self.a.stop_after_round.is_set():self.stop();return
                delay=min(120,30*failures)
                self.change(lastError=str(exc))
                self.update(busy=True,planActive=True,supervisorStage='Recuperando',supervisorAttempts=failures,
                            level='warn',message=f'Supervisor: {exc}. Nova tentativa em {delay}s; vídeos pendentes preservados.')
                # Only reset idle apps when no capture needs saving.
                if not self.state().get('pending'):
                    try:reset_idle()
                    except Exception:pass
                for _ in range(delay):
                    if not self.state().get('enabled') or self.a.stop_after_round.is_set():self.stop();return
                    if self.e.cancelar_sync.wait(1):self.stop();return
