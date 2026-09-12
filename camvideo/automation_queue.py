"""Run Minute recordings in memory-bounded batches, never advancing after failure."""
import ctypes
import random
import time
from task_history import priority

GIB = 1024 ** 3
RESERVE = int(2.5 * GIB)
PHONE_BUDGET = 3 * GIB  # 2 GiB guest plus rendering/host overhead.


def wait_for_shutdown(serial, adb, update, timeout=300):
    """Wait for removal from ADB, without querying a shutting-down Android shell."""
    started = time.monotonic()
    absent = 0
    while time.monotonic() - started < timeout:
        try:
            result = adb(serial, 'devices', timeout=8)
            valid = result.returncode == 0 and 'List of devices attached' in result.stdout
            present = any(line.split() and line.split()[0] == serial for line in result.stdout.splitlines())
            absent = absent + 1 if valid and not present else 0
        except Exception:
            absent = 0
        if absent >= 3:
            return
        update(message=f'Aguardando {serial} desligar após salvar ({int(time.monotonic()-started)}s; até {timeout}s)...')
        time.sleep(2)
    raise RuntimeError('Celular salvo não confirmou desligamento em '+str(timeout)+' segundos: '+serial)


def memory_info():
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ('total', 'available', 'pageTotal', 'pageAvailable', 'virtualTotal', 'virtualAvailable', 'extended')]
    value = Status()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise RuntimeError('Não foi possível medir a RAM disponível.')
    return {'freeBytes': value.available, 'totalBytes': value.total}


def memory_available():
    return memory_info()['freeBytes']


def capacity_snapshot(registered, online):
    try:
        info = memory_info()
        additional = min(max(0, registered-online), additional_capacity(info['freeBytes']))
        return dict(info, additional=additional, estimatedTotal=min(registered, online+additional),
                    online=online, reserveBytes=RESERVE, phoneBudgetBytes=PHONE_BUDGET,
                    lowMemory=info['freeBytes'] < GIB)
    except (OSError, RuntimeError, AttributeError):
        return {'error': 'Não foi possível medir a RAM disponível agora.'}


def additional_capacity(available):
    return max(0, int((available - RESERVE) // PHONE_BUDGET))


def run_queue(automation, targets, prepare, installed, task, auto, repeat,
              online, boot, shutdown, available=memory_available, usage=lambda n: 0, lifetime=lambda n: 0,
              randomize=False, resume_phones=()):
    if not targets:
        raise ValueError('Nenhum celular participante.')
    if auto and not task.strip():
        raise ValueError('Informe o nome completo da tarefa no Minute.')
    if not auto:
        raise ValueError('As rodadas por RAM precisam da busca automática da tarefa.')
    eligible, _ = priority(targets, usage, lifetime)
    records = [installed.get(s, {}) for s, _ in eligible.values()]
    if any(not (r.get('confirmed') or (r.get('staged') and r.get('mode') == 'shared')) or not r.get('assetId') for r in records):
        raise ValueError('Use o mesmo vídeo em todos os participantes na aba Vídeos antes de iniciar.')
    if records and len({r['assetId'] for r in records}) != 1:
        raise ValueError('Os participantes têm vídeos diferentes. Use “Usar em todos”.')
    automation.e.cancelar_sync.clear()
    automation.stop_after_round.clear()
    update = automation.update
    update(queueActive=True, queueSaved=[], queuePending=list(targets), loopActive=repeat,
           loopStopping=False, loopCompleted=0, loopCycle=0, queueBatch=0)
    cycle = batch_number = 0
    try:
        while True:
            cycle += 1
            pending, skipped = priority(targets, usage, lifetime)
            if randomize:
                order = list(pending)
                random.shuffle(order)
                pending = {name: pending[name] for name in order}
            if cycle == 1 and resume_phones:
                order = [name for name in resume_phones if name in pending]
                order += [name for name in pending if name not in order]
                pending = {name: pending[name] for name in order}
            saved = []
            update(loopCycle=cycle, queueSaved=saved, queuePending=list(pending), queueSkipped=skipped)
            if not pending:
                update(message='Todos os participantes atingiram o limite diário disponível nesta tarefa.')
                break
            while pending:
                automation.check_cancel()
                if automation.stop_after_round.is_set():
                    return
                eligible_now, newly_skipped = priority(pending, usage, lifetime)
                pending = ({name: pair for name, pair in pending.items() if name in eligible_now}
                           if randomize else eligible_now)
                skipped = list(dict.fromkeys(skipped + newly_skipped))
                update(queuePending=list(pending), queueSkipped=skipped)
                if not pending:
                    break
                live = {n for n, pair in targets.items() if online(pair[0])}
                slots = min(3, max(1, len(live) + additional_capacity(available())))
                chosen = dict(list(pending.items())[:slots])
                # Higher-usage phones must not occupy the slots of lower-usage ones.
                # The backend refuses shutdown if a camera or review is open.
                for name in live - chosen.keys():
                    shutdown(targets[name][0])
                batch = {n: pair for n, pair in chosen.items() if online(pair[0])}
                # Boot one at a time; remeasure only after Android is ready.
                # A fixed allowance also bounds growth before guest pages are touched.
                allowance = additional_capacity(available())
                for name, (serial, port) in chosen.items():
                    if name in batch:
                        continue
                    if allowance <= 0 or additional_capacity(available()) <= 0:
                        break
                    automation.check_cancel()
                    update(message='Ligando '+name+'; conferindo RAM...', queueFreeGiB=available()/GIB)
                    boot(name, serial, port)
                    batch[name] = (serial, port)
                    allowance -= 1
                if not batch:
                    raise RuntimeError('RAM insuficiente para a próxima rodada. Feche aplicativos e tente novamente; os resultados salvos permanecem no histórico.')
                if available() < GIB:
                    raise RuntimeError('Menos de 1 GiB de RAM livre após iniciar. Feche aplicativos antes de gravar.')
                batch_number += 1
                update(queueBatch=batch_number, queueCurrent=list(batch), queueFreeGiB=available()/GIB,
                       queuePending=[n for n in pending if n not in batch])
                automation._run_cycle(batch, prepare, installed, task, auto, keep_busy=True)
                rows = automation.snapshot()
                if not all(rows.get(s, {}).get('stage') == 'Salvo' for s, _ in batch.values()):
                    raise RuntimeError('A rodada não foi totalmente salva. A fila foi interrompida; confira os celulares.')
                for name in batch:
                    pending.pop(name)
                    saved.append(name)
                update(queueSaved=list(saved), queuePending=list(pending))
                automation.check_cancel()
                if automation.stop_after_round.is_set():
                    return
                if pending:
                    for serial, _ in batch.values():
                        shutdown(serial)
            update(loopCompleted=cycle, message=f'{len(saved)} celulares salvos. Concluído.')
            if not repeat:
                break
    finally:
        update(busy=False, queueActive=False, loopActive=False, loopStopping=False)
