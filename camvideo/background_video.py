"""Sequential cache-only preparation, independent of the active camera source."""
import threading

class BackgroundVideo:
    def __init__(self, prepare):
        self.prepare = prepare
        self.lock = threading.Lock()
        self.queue = []
        self.results = []
        self.active = None
        self.state = dict(busy=False, progress=0, stage='Aguardando', name='')

    def snapshot(self):
        with self.lock:
            return dict(self.state, queued=[name for name, fill in self.queue], results=list(self.results))

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, name, fill=False):
        return self.enqueue(name, fill)

    def enqueue(self, name, fill=False):
        item = (name, bool(fill))
        with self.lock:
            if item == self.active or item in self.queue:
                return
            self.queue.append(item)
            if self.state['busy']:
                return
            self.state.update(busy=True, stage='Aguardando preparação')
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.active = None
                    self.state['busy'] = False
                    return
                name, fill = self.active = self.queue.pop(0)
                self.state.update(name=name, fill=fill, progress=0,
                                  stage='Aguardando preparação', error='')
            error = ''
            try:
                self.prepare(name, fill, notify=self.update, background=True)
                self.update(progress=100, stage='Pronto para usar')
            except Exception as exc:
                error = str(exc)
                self.update(stage='Falha na preparação', error=error)
            with self.lock:
                self.results.append(dict(name=name, fill=fill, error=error,
                                         stage='Falha' if error else 'Pronto para todos os celulares'))
                self.results = self.results[-100:]
