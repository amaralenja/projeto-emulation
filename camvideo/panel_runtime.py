"""Find a running copy of this backend without reusing an outdated server."""
import hashlib
import http.client
import json
import os
from pathlib import Path

APP_VERSION = '2.3.2'

BACKEND_FILES = ('modern_server.pyw', 'painel.pyw', 'automation.py', 'automation_queue.py', 'task_history.py', 'unicode_search.py', 'camera_transfer.py',
                 'shared_camera.py', 'mirror.py', 'storage.py', 'voice_manager.py',
                 'voice_worker.py', 'tiktok_live.py', 'panel_runtime.py', 'product_writer.py', 'live_voice.py')


def runtime_identity(resources, owner, executable=None):
    digest = hashlib.sha256()
    for name in BACKEND_FILES:
        path = Path(resources) / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    if executable:
        stat = Path(executable).stat()
        digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
    return {'app': 'EmulationControl', 'revision': digest.hexdigest(),
            'root': os.path.normcase(os.path.realpath(owner)), 'voiceApi': 1, 'appVersion': APP_VERSION}


def find_running_backend(first_port, expected, count=8):
    for port in range(first_port, first_port + count):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=.75)
        try:
            connection.request('GET', '/api/version')
            response = connection.getresponse()
            if response.status == 200:
                body = response.read(8193)
                if len(body) <= 8192 and json.loads(body) == expected:
                    return port
        except (OSError, ValueError, http.client.HTTPException):
            pass
        finally:
            connection.close()
    return None
