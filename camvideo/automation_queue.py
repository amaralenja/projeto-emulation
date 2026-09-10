"""Run Minute recordings in memory-bounded batches, never advancing after failure."""
import ctypes
from task_history import priority

GIB = 1024 ** 3
RESERVE = int(2.5 * GIB)
PHONE_BUDGET = 3 * GIB  # 2 GiB guest plus rendering/host overhead.


def memory_available():
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ('total', 'available', 'pageTotal', 'pageAvailable', 'virtualTotal', 'virtualAvailable', 'extended')]
    value = Status()
    value.length = ctypes.sizeof(value)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
        raise RuntimeError('Não foi possível medir a RAM disponível.')
    return value.available


def additional_capacity(available):
    return max(0, int((available - RESERVE) // PHONE_BUDGET))


def run_queue(automation, targets, prepare, installed, task, auto, repeat,
              online, boot, shutdown, available=memory_available, usage=lambda n: 0, lifetime=lambda n: 0):
    if not targets:
        raise ValueError('Nenhum celular participante.')
    if auto and not task.strip():
        raise ValueError('Informe o nome completo da tarefa no Minute.')
    if not auto:
        raise ValueError('As rodadas por RAM precisam da busca automática da tarefa.')
    eligible, _ = priority(targets, usage, lifetime)
    records = [installed.get(s, {}) for s, _ in eligible.values()]
    if any(not r.get('confirmed') or not r.get('assetId') for r in records):
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
            saved = []
            update(loopCycle=cycle, queueSaved=saved, queuePending=list(pending), queueSkipped=skipped)
            if not pending:
                update(message='Todos os participantes atingiram o limite diário disponível nesta tarefa.')
                break
            while pending:
                automation.check_cancel()
                if automation.stop_after_round.is_set():
                    return
                pending, newly_skipped = priority(pending, usage, lifetime)
                skipped = list(dict.fromkeys(skipped + newly_skipped))
                update(queuePending=list(pending), queueSkipped=skipped)
                if not pending:
                    break
                live = {n for n, pair in targets.items() if online(pair[0])}
                slots = max(1, len(live) + additional_capacity(available()))
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
