"""One saved pair per task turn; shuffle fair rounds of eligible tasks."""
import random
from automation import task_key


def validate_plan(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Adicione pelo menos uma tarefa e seu vídeo.')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict): raise ValueError('Tarefa inválida.')
        task, video = str(row.get('task', '')).strip(), str(row.get('video', '')).strip()
        if not task or len(task) > 160: raise ValueError('Informe o nome completo de cada tarefa, até 160 caracteres.')
        if not video or '/' in video or '\\' in video or video in {'.', '..'}:
            raise ValueError('Selecione um vídeo da biblioteca para cada tarefa.')
        key = task_key(task)
        if key in seen: raise ValueError('Não repita a mesma tarefa na lista: '+task)
        seen.add(key); result.append(dict(task=task, video=video))
    return result


def run_interleaved_plan(rows, targets, usage, preflight, activate, record_pair,
                         check_cancel, stopped, update, shuffle=random.shuffle):
    rows = validate_plan(rows)
    for video in dict.fromkeys(row['video'] for row in rows): preflight(video)
    unavailable = set()
    previous = None
    turn = 0
    while True:
        check_cancel()
        if stopped(): return
        choices = [row for row in rows if any((n,row['task']) not in unavailable and 7200-usage(n,row['task']) >= 90 for n in targets)]
        if not choices:
            update(planCompleted=True, message='Sem combinações disponíveis neste ciclo: limites concluídos ou tarefas não encontradas.')
            return
        shuffle(choices)
        if len(choices)>1 and choices[0]['task']==previous:
            choices[0], choices[1] = choices[1], choices[0]
        for row in choices:
            check_cancel()
            if stopped(): return
            task = row['task']
            eligible = [n for n in targets if (n,task) not in unavailable and 7200-usage(n,task) >= 90]
            eligible.sort(key=lambda n: (usage(n,task), n))
            pair = {n:targets[n] for n in eligible[:2]}
            if not pair: continue
            turn += 1
            update(planMode='interleaved', planStep=turn, planTask=task, planVideo=row['video'],
                   message=f'Plano intercalado • rodada {turn}: {task}')
            activate(pair,row['video'])
            check_cancel()
            if stopped(): return
            # This call must finish and confirm saving before changing the source.
            if record_pair(pair,task) is False:
                unavailable.update((n,task) for n in pair)
                update(planSkipped=[{'phone':n,'task':t} for n,t in sorted(unavailable)],
                       message='Tarefa não encontrada neste par; seguindo o plano sem contar horas: '+task)
                continue
            previous = task
