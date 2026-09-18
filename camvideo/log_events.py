"""Apend-only elapsed log of supervisor and server events, one file per day."""
import datetime
import json
import os


def _pattern(area):
    logs = os.path.join(area, 'logs')
    os.makedirs(logs, exist_ok=True)
    return os.path.join(logs, datetime.date.today().isoformat() + '.log')


def log(area, event, **fields):
    line = {'when': datetime.datetime.now().isoformat(timespec='seconds'), 'event': event}
    line.update(fields)
    try:
        with open(_pattern(area), 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(line, ensure_ascii=False) + '\n')
    except OSError:
        pass