"""Read task usage consistently for limits and queue ordering."""
import math
from automation import task_key


def task_usage(history, phone, task, day=None):
    total = 0.0
    for date, phones in history.get('dias', {}).items():
        if day is not None and date != day:
            continue
        for key, entry in phones.get(phone, {}).items():
            if task_key(entry.get('nome') or key) != task_key(task):
                continue
            value = float(entry.get('segundos', 0) or 0)
            if math.isfinite(value):
                total += max(0, value)
    return total


def priority(targets, usage, lifetime):
    ordered = sorted(targets, key=lambda n: (usage(n), lifetime(n), n))
    skipped = [n for n in ordered if 7200 - usage(n) < 90]
    return {n: targets[n] for n in ordered if n not in skipped}, skipped
