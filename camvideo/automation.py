"""Minute navigation and per-device recording deadlines."""
import concurrent.futures
import math
import re
import subprocess
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET

MAX_SECONDS = 29 * 60 + 59


def normalize(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                            if not unicodedata.combining(c)).split())


def recording_duration(seconds):
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds < 61.5:
        raise ValueError('O vídeo precisa ter pelo menos 61,5 segundos para salvar no Minute.')
    return min(seconds, MAX_SECONDS)


def stop_deadline(play_started, record_triggered, duration):
    # Includes countdown/setup in the recording cap; reserve time for the ADB tap.
    return min(play_started + duration, record_triggered + MAX_SECONDS - 1)


class Automation:
    def __init__(self, engine, update):
        self.e, self.update = engine, update
        self.lock = threading.Lock()
        self.rows = {}

    def snapshot(self):
        with self.lock:
            return {s: dict(row) for s, row in self.rows.items()}

    def mark(self, serial, **data):
        with self.lock:
            self.rows.setdefault(serial, {}).update(data)

    def check_cancel(self):
        if self.e.cancelar_sync.is_set():
            raise InterruptedError('Automação interrompida')

    def xml(self, serial):
        path = '/data/local/tmp/minute-automation.xml'
        self.e._adb(serial, 'shell', 'rm', '-f', path, timeout=5, check=True)
        self.e._adb(serial, 'shell', 'uiautomator', 'dump', '--compressed', path, timeout=12, check=True)
        raw = self.e._adb(serial, 'shell', 'cat', path, timeout=5, check=True).stdout
        return ET.fromstring(raw)

    def tap(self, serial, node):
        bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
        if not bounds:
            raise RuntimeError('Botão sem posição válida')
        x1, y1, x2, y2 = map(int, bounds.groups())
        if x2 <= x1 or y2 <= y1 or node.get('enabled') == 'false':
            raise RuntimeError('Botão fora da tela ou desabilitado')
        self.e._adb(serial, 'shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2), timeout=5, check=True)

    def rotate_left(self, serial):
        for attempt in range(4):
            self.check_cancel()
            raw = self.e._adb(serial, 'emu', 'sensor', 'get', 'acceleration', timeout=5, check=True).stdout
            match = re.search(r'acceleration\s*=\s*([-\d.e+]+):([-\d.e+]+):', raw)
            if not match:
                raise RuntimeError('Não foi possível confirmar a orientação do emulador')
            x, y = map(float, match.groups())
            if x > 7 and abs(y) < 3:
                return
            # Console rotates the window and sensors, just like its toolbar button.
            if attempt == 3:
                break
            self.e._adb(serial, 'emu', 'rotate', timeout=5, check=True)
            time.sleep(.25)
        raise RuntimeError('Não foi possível girar para a esquerda')

    def navigate(self, serial, task):
        # Return to the task list even when an old preview was left open.
        for _ in range(12):
            self.check_cancel()
            if self.e._camera_pronta(serial) is not None:
                self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=5, check=True)
            root = self.xml(serial)
            nodes = list(root.iter('node'))
            nav = next((n for n in nodes if n.get('resource-id') == 'nav-index'), None)
            if nav is not None:
                self.tap(serial, nav)
                break
            close = next((n for n in nodes if n.get('resource-id') in {'record-close', 'record-new-task'}), None)
            if close is not None:
                self.tap(serial, close)
            time.sleep(.5)
        else:
            raise RuntimeError('Abra o Minute com login ativo na lista de tarefas')
        cleared = False
        searched = False
        words = re.findall(r'[A-Za-z]{3,}', task)
        query = max(words, key=len) if words else ''
        for _ in range(35):
            self.check_cancel()
            root = self.xml(serial)
            nodes = list(root.iter('node'))
            clear = next((n for n in nodes if n.get('resource-id') == 'home-search-clear'), None)
            if clear is not None and not cleared:
                self.tap(serial, clear)
                cleared = True
                continue
            search = next((n for n in nodes if n.get('resource-id') == 'home-search-input'), None)
            if query and search is not None and not searched:
                self.tap(serial, search)
                self.e._adb(serial, 'shell', 'input', 'text', query, timeout=20, check=True)
                self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=5, check=True)
                searched = True
                cleared = True
                time.sleep(.5)
                continue
            cards = [n for n in nodes if n.get('resource-id', '').startswith(('task-card-', 'featured-card-'))
                     and normalize(n.get('content-desc', '').split(',')[0]) == normalize(task)]
            valid = []
            for node in cards:
                bound = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
                if bound:
                    x1, y1, x2, y2 = map(int, bound.groups())
                    if x2>x1 and y2>y1: valid.append(node)
            if valid:
                self.tap(serial, valid[0])
                break
            size = self.e._adb(serial, 'shell', 'wm', 'size', timeout=5, check=True).stdout
            w, h = map(int, re.findall(r'(\d+)x(\d+)', size)[-1])
            self.e._adb(serial, 'shell', 'input', 'swipe', str(w//2), str(int(h*.78)), str(w//2), str(int(h*.40)), '350', timeout=5, check=True)
        else:
            raise RuntimeError('Tarefa não encontrada: '+task+'. Use o nome completo exibido no Minute.')
        for _ in range(8):
            self.check_cancel()
            if self.e._camera_pronta(serial) is not None:
                return
            root = self.xml(serial)
            # Only known task workflow buttons, never arbitrary dialogs.
            button = next((n for n in root.iter('node') if n.get('resource-id') in
                           {'record-start-task', 'recording-tips-got-it'}), None)
            if button is None:
                raise RuntimeError('O Minute está pedindo uma ação não reconhecida; confira este celular')
            self.tap(serial, button)
            time.sleep(.4)
        raise RuntimeError('A câmera da tarefa não abriu')

    def run(self, targets, prepare, installed, task='', auto=True):
        self.e.cancelar_sync.clear()
        with self.lock:
            self.rows = {s: {'name': n, 'stage': 'Aguardando', 'elapsed': 0, 'total': 0, 'percent': 0}
                         for n, (s, _) in targets.items()}
        if not targets:
            raise ValueError('Nenhum celular selecionado')
        records = [installed.get(s, {}) for s, _ in targets.values()]
        if any(not r.get('confirmed') or not r.get('assetId') for r in records):
            raise ValueError('Instale e confirme o vídeo na aba Vídeos em todos os celulares participantes.')
        if len({r['assetId'] for r in records}) != 1:
            raise ValueError('Os celulares têm vídeos diferentes. Use “Usar em todos” na aba Vídeos.')
        if auto and not task.strip():
            raise ValueError('Informe o nome completo da tarefa para a busca automática.')
        self.update(task=task, elapsed=0, total=0, progress=0, message='Preparando os celulares...')
        durations = {}
        def ready(item):
            name, (s, port) = item
            try:
                self.check_cancel()
                self.mark(s, stage='Ligando e girando à esquerda', video=installed[s].get('name', ''))
                prepare(name, s, port)
                self.rotate_left(s)
                if auto:
                    self.mark(s, stage='Procurando a tarefa')
                    self.navigate(s, task)
                self.check_cancel()
                value = self.e._camera_pronta(s)
                if value is None:
                    raise RuntimeError('A câmera da tarefa não está pronta')
                durations[s] = recording_duration(value)
                if auto and self.e._uso_tarefa(name, task)+durations[s] > 7200:
                    raise RuntimeError('Limite diário de 2 horas insuficiente para esta gravação')
                self.mark(s, stage='Pronto', total=durations[s])
            except Exception as exc:
                self.mark(s, stage='Erro na preparação', error=str(exc))
                raise
        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
            for future in [pool.submit(ready, item) for item in targets.items()]:
                try:
                    future.result()
                except Exception as exc:
                    errors.append(str(exc))
        if errors:
            raise RuntimeError('Gravação não iniciada: '+'; '.join(errors))
        self.check_cancel()
        barrier = threading.Barrier(len(targets))
        task_ids = {}
        def record(name, s):
            triggered = False
            started = None
            try:
                generation = self.e._ler_geracao(s)+1
                self.e._escrever_controle(s, 'pause', generation)
                before = self.e._pastas_gravacao(s)
                barrier.wait(timeout=45)
                self.check_cancel()
                self.mark(s, stage='Contagem do Minute')
                trigger_time = time.monotonic()
                triggered = True
                self.e._tocar_botao_gravacao(s)
                session = self.e._esperar_gravacao(s, before, time.monotonic()+18)
                task_id, actual = self.e._detectar_tarefa_sessao(s, session)
                task_ids[s] = task_id
                if auto and normalize(actual) != normalize(task):
                    raise RuntimeError('Tarefa aberta diferente da escolhida: '+actual)
                if self.e._uso_tarefa(name, actual)+durations[s] > 7200:
                    raise RuntimeError('Limite diário insuficiente')
                self.mark(s, task=actual, stage='Sincronizando o início')
                barrier.wait(timeout=45)
                if len(set(task_ids.values())) != 1:
                    raise RuntimeError('Os celulares estão em tarefas diferentes')
                self.check_cancel()
                self.update(task=actual)
                self.e._escrever_controle(s, 'play', generation)
                started = time.monotonic()
                remaining_daily = 7200-self.e._uso_tarefa(name, actual)
                deadline = min(stop_deadline(started, trigger_time, durations[s]), trigger_time+remaining_daily-1)
                target = deadline-started
                if target < 60:
                    raise RuntimeError('Preparação demorou demais para gravar com segurança')
                while True:
                    elapsed = min(time.monotonic()-started, target)
                    self.mark(s, stage='Gravando', elapsed=elapsed, total=target, percent=min(99, int(elapsed/target*100)))
                    if self.e.cancelar_sync.wait(min(.1, max(0, deadline-time.monotonic()))) or time.monotonic() >= deadline:
                        break
                elapsed = min(time.monotonic()-started, target)
                self.mark(s, stage='Encerrando', elapsed=elapsed)
                self.e._tocar_botao_gravacao(s)
                triggered = False
                recorded_seconds = min(MAX_SECONDS, time.monotonic()-trigger_time)
                # Once stopped, save even if the user requested early stop.
                self.mark(s, stage='Salvando')
                if elapsed < 60:
                    self.mark(s, stage='Interrompido: gravação curta; confira o Minute')
                    return
                self.save(s)
                self.e._somar_uso_tarefa(name, actual, recorded_seconds)
                self.mark(s, stage='Salvo', percent=100, elapsed=elapsed)
            except Exception as exc:
                barrier.abort()
                if triggered:
                    try:
                        self.e._tocar_botao_gravacao(s)
                    except Exception as stop_error:
                        exc = RuntimeError(str(exc)+'; falha ao parar: '+str(stop_error))
                self.mark(s, stage='Erro — confira o celular', error=str(exc))
            finally:
                try:
                    self.e._escrever_controle(s, 'pause', generation)
                except Exception:
                    pass
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = [pool.submit(record, n, s) for n, (s, _) in targets.items()]
            while any(not f.done() for f in futures):
                rows = list(self.snapshot().values())
                self.update(elapsed=min(r['elapsed'] for r in rows), total=max(r['total'] for r in rows),
                            progress=int(sum(r['percent'] for r in rows)/len(rows)), message='Automação em andamento; acompanhe cada celular abaixo.')
                time.sleep(.2)
            for future in futures:
                future.result()
        rows = list(self.snapshot().values())
        saved = sum(r['stage'] == 'Salvo' for r in rows)
        self.update(busy=False, progress=100 if saved == len(rows) else 0,
                    level='ok' if saved == len(rows) else 'warn',
                    message=f'{saved} de {len(rows)} celulares salvos. '+('Concluído.' if saved == len(rows) else 'Confira os resultados por celular.'))

    def save(self, serial, pause_preview=True):
        # Independent of the stop event: stopping must not skip the Save button.
        if pause_preview:
            # Minute autoplays the just-recorded preview. Its moving seek bar
            # prevents UIAutomator reaching idle; pause via the preview surface.
            end_transition = time.monotonic()+10
            while time.monotonic()<end_transition:
                if self.e._camera_pronta(serial) is None:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError('A tela de gravação não encerrou; confira o celular imediatamente')
            time.sleep(.5)
            size = self.e._adb(serial, 'shell', 'wm', 'size', timeout=5, check=True).stdout
            w, h = map(int, re.findall(r'(\d+)x(\d+)', size)[-1])
            self.e._adb(serial, 'shell', 'input', 'tap', str(w//2), str(round(h*.52)), timeout=5, check=True)
        end = time.monotonic()+45
        clicked = False
        while time.monotonic() < end:
            try:
                root = self.xml(serial)
            except (subprocess.TimeoutExpired, RuntimeError, ET.ParseError):
                time.sleep(.5)
                continue
            nodes = list(root.iter('node'))
            if any(n.get('text') == 'Minute salvo.' for n in nodes):
                return
            confirm = any(n.get('text') == 'Salvar este Minute?' for n in nodes)
            if confirm:
                accept = next((n for n in nodes if n.get('clickable') == 'true' and
                               (n.get('content-desc') == 'Salvar' or n.get('text') == 'Salvar')), None)
                if accept is not None:
                    self.tap(serial, accept)
                    clicked = True
                    time.sleep(.5)
                    continue
            button = next((n for n in nodes if n.get('resource-id') in {'minute-save', 'record-accept'}), None)
            if button is not None and not clicked:
                self.tap(serial, button)
                clicked = True
            elif clicked and any(n.get('resource-id') in {'nav-index', 'nav-minutes'} for n in nodes):
                return
            time.sleep(.5)
        raise RuntimeError('O Minute não confirmou o retorno após salvar; confira o celular')
