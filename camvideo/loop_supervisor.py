"""Durable run intent and capture journal; recovery never discards a video."""
import json
import math
import os
import re
import threading
import time
from automation import task_key, confirmed_recording_seconds, recording_abandoned
from log_events import log as log_event


def recent_folders(shell_root, serial, minutes=720):
    """Recording folders touched in the last 'minutes': only those can be a
    capture in flight. Old leftovers the Minute app already discarded must
    neither be adopted nor block a reorganisation. The wide 720-minute default
    keeps any still-registered pending capture recoverable for the whole night;
    adoption of brand-new orphans uses the narrower 60-minute window."""
    r = shell_root(
        serial,
        f'find /data/user/0/com.bakerdata.minute/files/recordings '
        f'-mindepth 1 -maxdepth 1 -type d -mmin -{minutes} 2>/dev/null',
        timeout=8)
    return {
        line.strip().rstrip('/').rsplit('/', 1)[-1]
        for line in r.stdout.splitlines() if line.strip()
    }


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
        self.area=area
        self.e,self.a,self.update=engine,automation,update
        self.lock=threading.RLock()
        self.ensure_online=lambda serial:None
        self.device_serials=lambda:()

    def state(self):return read_json(self.path,{'enabled':False,'pending':{}})

    def change(self, **fields):
        with self.lock:
            state=self.state();state.update(fields);write_json(self.path,state)
        if 'lastError' in fields:
            log_event(self.area, 'supervisor_erro', error=fields['lastError'])
        for key in ('enabled','stage','ownerPid','restarts'):
            if key in fields:
                log_event(self.area, 'supervisor_estado', **{key: fields[key]})

    def begin(self, options, url):
        self.change(enabled=True,options=options,url=url,ownerPid=os.getpid(),lastError='',restarts=0)

    def stop(self):self.change(enabled=False)

    def checkpoint(self, serial, **fields):
        with self.lock:
            state=self.state();entry=state.setdefault('pending',{}).setdefault(serial,{})
            entry.update(fields);entry['serial']=serial
            write_json(self.path,state)
        if fields:
            log_event(self.area, 'captura_pendente', serial=serial, **fields)

    def clear(self,serial):
        with self.lock:
            state=self.state();state.setdefault('pending',{}).pop(serial,None);write_json(self.path,state)
        log_event(self.area, 'captura_limpa', serial=serial)

    def credit(self,serial,seconds):
        entry=self.state()['pending'][serial]
        with self.e.lock_historico:
            history=self.e._ler_historico()
            if credit_history(history,entry,seconds):write_json(self.history_path,history)
        self.clear(serial)
        log_event(self.area, 'captura_creditada', serial=serial,
                  task=entry.get('task'), seconds=seconds, session=entry.get('session'))

    def resgatar(self, serial, session):
        """Copy an abandoned capture to the host before dropping its pending
        entry, so nothing the app still owns on the phone is ever lost."""
        origem = '/data/user/0/com.bakerdata.minute/files/recordings/' + session
        destino = os.path.join(self.area, 'resgates', time.strftime('%Y-%m-%d'),
                               serial + '-' + session)
        os.makedirs(destino, exist_ok=True)
        temp = '/data/local/tmp/camresgate-' + session
        self.e._shell_root(serial,
            f'rm -rf {temp}; mkdir -p {temp}; '
            f'cp {origem}/video.mp4 {origem}/imu.csv {temp}/ 2>/dev/null; '
            f'chmod 644 {temp}/* 2>/dev/null; ls {temp}', timeout=20)
        salvos = []
        for nome in ('video.mp4', 'imu.csv'):
            r = self.e._adb(serial, 'pull', f'{temp}/{nome}',
                            os.path.join(destino, nome), timeout=30)
            if r.returncode == 0:
                salvos.append(nome)
        self.e._shell_root(serial, f'rm -rf {temp}; rm -rf {origem}', timeout=15)
        return destino, salvos

    def recover(self):
        # Adopt orphan captures: a phone left with the camera open and a
        # recording folder, but no pending entry, must be recovered instead of
        # blocking every plan reorganisation at shutdown(). Only phones already
        # reachable are scanned; reconnecting offline ones is the operation's job.
        # Only folders touched very recently can be a capture in flight; old
        # leftovers the Minute app already discarded are to be let go.
        for serial in self.device_serials():
            if serial in self.state().get('pending', {}):
                continue
            self.a.check_cancel()
            try:
                if self.e._camera_pronta(serial) is None:
                    continue
                if not recent_folders(self.e._shell_root, serial, 60):
                    continue
                self.ensure_online(serial)
                if (self.e._camera_pronta(serial) is not None
                        and recent_folders(self.e._shell_root, serial, 60)):
                    self.checkpoint(serial, task='')
                    log_event(self.area, 'captura_orfa_adotada', serial=serial)
            except Exception:
                # Offline or unreachable phones are handled by the retry loop.
                continue
        for serial,entry in self.state().get('pending',{}).items():
            self.a.check_cancel()
            self.ensure_online(serial)
            connection=self.e._adb(serial,'get-state',timeout=8,check=True)
            if connection.stdout.strip()!='device':raise RuntimeError('Celular pendente desconectado: '+serial)
            session=entry.get('session')
            if not session:
                new=recent_folders(self.e._shell_root, serial)-set(entry.get('before',[]))
                if not new:
                    self.clear(serial);continue
                if len(new)!=1:raise RuntimeError('Mais de uma captura pendente em '+serial+'; vídeos preservados.')
                session=next(iter(new));self.checkpoint(serial,session=session)
            if not re.fullmatch(r'[\w-]+',session):raise RuntimeError('Identificador de captura inválido')
            if session not in recent_folders(self.e._shell_root, serial):
                # The Minute app no longer owns this folder (capture already
                # discarded); keeping it pending would block every retry.
                self.clear(serial)
                log_event(self.area, 'captura_expirou', serial=serial, session=session)
                continue
            self.update(supervisorStage='Recuperando gravação',message='Conferindo gravação pendente em '+serial)
            raw=self.e._shell_root_bytes(serial,'cat /data/user/0/com.bakerdata.minute/files/mmkv/recording-store',timeout=15)
            seconds=confirmed_recording_seconds(raw,session)
            if seconds is None:
                if (recording_abandoned(raw, session)
                        and self.e._camera_pronta(serial) is None):
                    # The app ended the capture without accepting it and no
                    # longer offers the save screen. Save the video to the host
                    # and let the plan move on instead of retrying forever.
                    destino, salvos = self.resgatar(serial, session)
                    self.clear(serial)
                    log_event(self.area, 'captura_abandonada', serial=serial,
                              session=session, destino=destino, salvos=salvos)
                    self.update(supervisorStage='Recuperando',
                                message='Captura abandonada pelo Minute em '+serial
                                        +'; vídeo resgatado para o computador')
                    continue
                # Stop only a known journaled capture whose file is still growing.
                pasta='/data/user/0/com.bakerdata.minute/files/recordings/'+session
                path=pasta+'/video.mp4'
                if self.e._shell_root(serial,'ls -d '+pasta,timeout=12).returncode!=0:
                    # The whole capture dir is gone and the store never confirmed it:
                    # the app discarded the capture, there is no video to preserve.
                    self.clear(serial)
                    self.update(supervisorStage='Recuperando',
                                message='Captura descartada em '+serial+'; entrada removida')
                    log_event(self.area, 'captura_descartada', serial=serial, session=session)
                    continue
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
            if entry.get('task') and task_key(actual)!=task_key(entry['task']):
                raise RuntimeError('A tarefa da gravação pendente precisa ser conferida.')
            if not entry.get('task'):
                self.checkpoint(serial,session=session,task=actual)
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
                log_event(self.area, 'supervisor_tentativa', attempt=failures+1)
                operation()
                log_event(self.area, 'supervisor_sucesso', attempt=failures+1)
                self.stop();return
            except InterruptedError:
                self.stop();raise
            except Exception as exc:
                failures+=1
                if self.e.cancelar_sync.is_set() or self.a.stop_after_round.is_set():self.stop();return
                delay=min(120,30*failures)
                self.change(lastError=str(exc))
                log_event(self.area, 'supervisor_falha', attempt=failures, error=str(exc), delay=delay)
                self.update(busy=True,planActive=True,supervisorStage='Recuperando',supervisorAttempts=failures,
                            level='warn',message=f'Supervisor: {exc}. Nova tentativa em {delay}s; vídeos pendentes preservados.')
                # Only reset idle apps when no capture needs saving.
                if not self.state().get('pending'):
                    try:reset_idle()
                    except Exception:pass
                for _ in range(delay):
                    if not self.state().get('enabled') or self.a.stop_after_round.is_set():self.stop();return
                    if self.e.cancelar_sync.wait(1):self.stop();return
