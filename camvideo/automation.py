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
        self.stop_after_round = threading.Event()

    def request_stop_after_round(self):
        self.stop_after_round.set()
        self.update(loopStopping=True, message='O loop vai parar depois de salvar esta rodada.')

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
        path = f'/data/local/tmp/minute-automation-{threading.get_ident()}.xml'
        for attempt in range(2):
            try:
                self.e._adb(serial, 'shell', 'rm', '-f', path, timeout=5, check=True)
                self.e._adb(serial, 'shell', 'uiautomator', 'dump', '--compressed', path, timeout=20, check=True)
                raw = self.e._adb(serial, 'shell', 'cat', path, timeout=5, check=True).stdout
                root = ET.fromstring(raw)
                if any(n.get('resource-id') == 'com.android.systemui:id/notification_panel' for n in root.iter('node')):
                    self.e._adb(serial, 'shell', 'cmd', 'statusbar', 'collapse', timeout=8, check=True)
                    if not attempt:
                        time.sleep(.5)
                        continue
                    raise RuntimeError('A cortina de notificações está cobrindo o Minute')
                return root
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                if attempt:
                    raise
                time.sleep(.5)

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

    def hide_keyboard(self, serial):
        state = self.e._adb(serial, 'shell', 'dumpsys', 'input_method', timeout=8, check=True).stdout
        if re.search(r'(?:mInputShown|isInputViewShown)=true', state):
            # Submit the search; BACK can exit the app when IME state is stale.
            self.e._adb(serial, 'shell', 'input', 'keyevent', '66', timeout=8, check=True)

    def minute_foreground(self, serial):
        raw = self.e._adb(serial, 'shell', 'dumpsys', 'activity', 'activities', timeout=8, check=True).stdout
        return any('com.bakerdata.minute' in line for line in raw.splitlines()
                   if 'mResumedActivity' in line or 'topResumedActivity' in line)

    @staticmethod
    def visible(node):
        bound = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
        return bool(bound and int(bound[3]) > int(bound[1]) and int(bound[4]) > int(bound[2]))

    def scroll_tasks(self, serial, down=True):
        nodes = list(self.xml(serial).iter('node'))
        container = next((n for n in nodes if n.get('resource-id') == 'home-tasks' and self.visible(n)), None)
        if container is None:
            raise RuntimeError('A lista do Minute não está visível; rolagem interrompida')
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', container.get('bounds')))
        start, end = (.70, .30) if down else (.30, .70)
        self.e._adb(serial, 'shell', 'input', 'swipe', str((x1+x2)//2), str(int(y1+(y2-y1)*start)),
                    str((x1+x2)//2), str(int(y1+(y2-y1)*end)), '300', timeout=8, check=True)

    def task_list(self, serial):
        left_camera = False
        reopened = False
        for _ in range(10):
            self.check_cancel()
            if not self.minute_foreground(serial):
                if reopened:
                    raise RuntimeError('O Minute não ficou em primeiro plano; confira login ou permissões')
                self.mark(serial, stage='Reabrindo o Minute')
                self.e._adb(serial, 'shell', 'monkey', '-p', 'com.bakerdata.minute',
                            '-c', 'android.intent.category.LAUNCHER', '1', timeout=20, check=True)
                reopened = True
                time.sleep(1)
                continue
            # Native capture sometimes has no accessibility tree. Leave it once,
            # only after confirming both the foreground app and native camera.
            try:
                nodes = list(self.xml(serial).iter('node'))
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                if not left_camera and self.minute_foreground(serial) and self.e._camera_pronta(serial) is not None:
                    self.e._adb(serial, 'shell', 'input', 'keyevent', '4', timeout=8, check=True)
                    left_camera = True
                    time.sleep(1)
                    continue
                raise RuntimeError('Não consegui reconhecer a tela do Minute; navegação interrompida')
            if any(n.get('resource-id') in {'record-accept', 'minute-save'} for n in nodes):
                raise RuntimeError('Há uma gravação na tela de revisão; salve ou descarte antes de iniciar outra')
            nav = next((n for n in nodes if n.get('resource-id') == 'nav-index' and self.visible(n)), None)
            if nav is not None:
                self.tap(serial, nav)
                self.hide_keyboard(serial)
                return
            close = next((n for n in nodes if n.get('resource-id') in {'record-close', 'record-new-task'} and self.visible(n)), None)
            if close is not None:
                self.tap(serial, close)
            else:
                time.sleep(.5)
        raise RuntimeError('Não consegui abrir a lista de tarefas; confira a tela do Minute')

    def wait_minute_ready(self, serial, timeout=90):
        """ADB online does not mean the cold-started React Native screen is ready."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check_cancel()
            try:
                if self.minute_foreground(serial):
                    if self.e._camera_pronta(serial) is not None:
                        return
                    nodes = list(self.xml(serial).iter('node'))
                    if any(n.get('package') == 'com.bakerdata.minute' and
                           (n.get('resource-id') in {'nav-index', 'home-search-input', 'record-close',
                                                    'record-new-task', 'record-accept', 'minute-save'} or
                            len(n.get('text', '').strip()) > 3) for n in nodes):
                        return
            except (RuntimeError, subprocess.TimeoutExpired, ET.ParseError):
                pass
            if self.e.cancelar_sync.wait(1):
                self.check_cancel()
        raise RuntimeError('O Minute não terminou de abrir em 90 segundos; confira o celular')

    def search_field(self, serial):
        for _ in range(10):
            self.check_cancel()
            nodes = list(self.xml(serial).iter('node'))
            field = next((n for n in nodes if n.get('resource-id') == 'home-search-input' and self.visible(n)), None)
            if field is not None:
                return field
            self.scroll_tasks(serial, down=False)
        raise RuntimeError('Campo de busca não encontrado na lista de tarefas')

    def set_query(self, serial, query):
        for _ in range(3):
            field = self.search_field(serial)
            self.tap(serial, field)
            text = field.get('text', '')
            if text:
                self.e._adb(serial, 'shell', 'input', 'keyevent', '123',
                            *(['67'] * min(len(text), 512)), timeout=25, check=True)
            if query:
                self.e._adb(serial, 'shell', 'input', 'text', query, timeout=25, check=True)
            self.hide_keyboard(serial)
            time.sleep(.8)
            nodes = list(self.xml(serial).iter('node'))
            actual = next((n for n in nodes if n.get('resource-id') == 'home-search-input'), None)
            if actual is not None and normalize(actual.get('text', '')) == normalize(query):
                return
        raise RuntimeError('O campo de busca não confirmou o texto digitado; nenhuma tarefa foi iniciada')

    def navigate(self, serial, task):
        self.task_list(serial)
        # Try alternative meaningful words, but only accept the complete title.
        words = re.findall(r'[a-z0-9]{3,}', normalize(task))
        words = [w for w in words if w not in {'para', 'com', 'uma', 'dos', 'das'}]
        queries = list(dict.fromkeys(sorted(words, key=len, reverse=True)))[:3] + ['']
        deadline = time.monotonic() + 240
        for query in queries:
            self.check_cancel()
            if time.monotonic() >= deadline:
                break
            self.mark(serial, stage='Buscando: '+(query or 'lista completa'))
            self.set_query(serial, query)
            previous = None
            unchanged = 0
            for _ in range(18):
                self.check_cancel()
                if time.monotonic() >= deadline:
                    break
                nodes = list(self.xml(serial).iter('node'))
                cards = [n for n in nodes if n.get('resource-id', '').startswith(('task-card-', 'featured-card-')) and self.visible(n)]
                matches = [n for n in cards if normalize(n.get('content-desc', '').split(',')[0]) == normalize(task)]
                if matches:
                    card = matches[0]
                    x1,y1,x2,y2 = map(int,re.findall(r'\d+',card.get('bounds')))
                    footers = [int(re.findall(r'\d+',n.get('bounds'))[1]) for n in nodes
                               if n.get('resource-id') in {'nav-index','nav-minutes','nav-settings'} and self.visible(n)]
                    if footers: y2=min(y2,min(footers)-8)
                    if y2-y1 >= 40:
                        card.set('bounds',f'[{x1},{y1}][{x2},{y2}]')
                        self.mark(serial, stage='Tarefa encontrada: '+task)
                        self.tap(serial, card)
                        self.finish_camera(serial)
                        return
                signature = tuple((n.get('resource-id'), n.get('bounds')) for n in cards)
                unchanged = unchanged+1 if signature == previous else 0
                previous = signature
                if unchanged >= 2:
                    break
                self.scroll_tasks(serial)
        raise RuntimeError('Tarefa não encontrada: '+task+'. Confira o nome completo e se ela está disponível nesta conta.')

    def finish_camera(self, serial):
        for _ in range(8):
            self.check_cancel()
            try:
                root = self.xml(serial)
            except (subprocess.TimeoutExpired, RuntimeError, ET.ParseError):
                # Native camera preview may not expose an idle accessibility tree.
                if self.e._camera_pronta(serial) is not None:
                    return
                continue
            # Only known task workflow buttons, never arbitrary dialogs.
            button = next((n for n in root.iter('node') if n.get('resource-id') in
                           {'record-start-task', 'recording-tips-got-it'}), None)
            if button is None:
                if self.e._camera_pronta(serial) is not None:
                    return
                # A task tap can return an accessibility snapshot of the old
                # list while the detail screen is still mounting.
                time.sleep(.5)
                continue
            self.tap(serial, button)
            if button.get('resource-id') == 'recording-tips-got-it':
                for _ in range(10):
                    self.check_cancel()
                    time.sleep(.5)
                    if self.e._camera_pronta(serial) is not None:
                        return
            time.sleep(.4)
        raise RuntimeError('A câmera da tarefa não abriu')

    def wait_recording(self, serial, before, triggered_at):
        # A session directory can exist before the ten-second countdown finishes.
        if self.e.cancelar_sync.wait(max(0, triggered_at + 10 - time.monotonic())):
            self.check_cancel()
        end = time.monotonic() + 60
        session = self.e._esperar_gravacao(serial, before, end)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', session):
            raise RuntimeError('Identificador de gravação inválido')
        previous = None
        path = '/data/user/0/com.bakerdata.minute/files/recordings/' + session + '/video.mp4'
        while time.monotonic() < end:
            self.check_cancel()
            raw = self.e._shell_root(serial, 'if [ -f ' + path + ' ]; then stat -c %s ' + path + '; else echo 0; fi', timeout=12, check=True).stdout.strip()
            size = int(raw)
            if previous is not None and size > previous and previous > 0:
                return session
            previous = size
            if self.e.cancelar_sync.wait(1):
                self.check_cancel()
        raise RuntimeError('A contagem terminou, mas o arquivo de vídeo não está crescendo; confira o celular')

    def run(self, targets, prepare, installed, task='', auto=True, repeat=False):
        self.e.cancelar_sync.clear()
        self.stop_after_round.clear()
        if repeat and (not auto or not task.strip()):
            raise ValueError('Para repetir, use a busca automática e informe o nome completo da tarefa.')
        cycle = 0
        completed = 0
        self.update(loopActive=repeat, loopStopping=False, loopCycle=0, loopCompleted=0)
        try:
            while True:
                self.check_cancel()
                if cycle and self.stop_after_round.is_set():
                    break
                cycle += 1
                self.update(loopCycle=cycle, message=f'Preparando rodada {cycle}...')
                self._run_cycle(targets, prepare, installed, task, auto, keep_busy=repeat)
                saved = all(r.get('stage') == 'Salvo' for r in self.snapshot().values())
                saved = saved and len(self.snapshot()) == len(targets) and bool(targets)
                if saved:
                    completed += 1
                self.update(loopCompleted=completed)
                if not repeat or not saved or self.e.cancelar_sync.is_set() or self.stop_after_round.is_set():
                    break
                self.update(message=f'Rodada {cycle} salva. Reiniciando o vídeo e a tarefa...')
            if repeat and saved:
                self.update(message=f'Loop encerrado. {completed} rodada(s) salva(s).')
        finally:
            self.update(busy=False, loopActive=False, loopStopping=False)

    def _run_cycle(self, targets, prepare, installed, task='', auto=True, keep_busy=False):
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
                self.e._escrever_controle(s, 'pause', self.e._ler_geracao(s)+1)
                self.rotate_left(s)
                if auto:
                    self.mark(s, stage='Procurando a tarefa')
                    self.navigate(s, task)
                else:
                    self.finish_camera(s)
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(2, len(targets))) as pool:
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
            capture_confirmed = False
            started = None
            generation = None
            try:
                generation = self.e._ler_geracao(s)+1
                self.e._escrever_controle(s, 'pause', generation)
                before = self.e._pastas_gravacao(s)
                barrier.wait(timeout=90)
                self.check_cancel()
                self.mark(s, stage='Contagem do Minute')
                trigger_time = time.monotonic()
                triggered = True
                self.e._tocar_botao_gravacao(s)
                session = self.wait_recording(s, before, trigger_time)
                capture_confirmed = True
                task_id, actual = self.e._detectar_tarefa_sessao(s, session)
                task_ids[s] = task_id
                if auto and normalize(actual) != normalize(task):
                    raise RuntimeError('Tarefa aberta diferente da escolhida: '+actual)
                if self.e._uso_tarefa(name, actual)+durations[s] > 7200:
                    raise RuntimeError('Limite diário insuficiente')
                self.mark(s, task=actual, stage='Sincronizando o início')
                barrier.wait(timeout=90)
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
                if isinstance(exc, threading.BrokenBarrierError):
                    exc = RuntimeError('Outro celular falhou ou demorou para confirmar a gravação; início em grupo cancelado')
                if triggered:
                    try:
                        # Back cancels countdown or leaves capture; a second record
                        # tap could START capture after an unconfirmed first tap.
                        if capture_confirmed:
                            self.e._tocar_botao_gravacao(s)
                        elif self.minute_foreground(s) and self.e._camera_pronta(s) is not None:
                            self.e._adb(s, 'shell', 'input', 'keyevent', '4', timeout=12, check=True)
                    except Exception as stop_error:
                        exc = RuntimeError(str(exc)+'; falha ao parar: '+str(stop_error))
                self.mark(s, stage='Erro — confira o celular', error=str(exc))
            finally:
                try:
                    if generation is not None:
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
        self.update(busy=keep_busy, progress=100 if saved == len(rows) else 0,
                    level='ok' if saved == len(rows) else 'warn',
                    message=f'{saved} de {len(rows)} celulares salvos. '+('Concluído.' if saved == len(rows) else 'Confira os resultados por celular.'))

    def save(self, serial, pause_preview=True):
        # Independent of the stop event: stopping must not skip the Save button.
        if pause_preview:
            # Minute autoplays the just-recorded preview. Its moving seek bar
            # prevents UIAutomator reaching idle; pause via the preview surface.
            end_transition = time.monotonic()+90
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
