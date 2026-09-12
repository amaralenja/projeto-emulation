"""A single cache-only preparation job, independent of camera automation."""
import threading


class BackgroundVideo:
    def __init__(self, prepare):
        self.prepare = prepare
        self.lock = threading.Lock()
        self.state = {'busy': False, 'progress': 0, 'stage': 'Aguardando', 'name': ''}

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def start(self, name, fill=False):
        with self.lock:
            if self.state['busy']:
                raise ValueError('Já existe um vídeo sendo preparado em segundo plano')
            self.state = dict(busy=True, name=name, fill=bool(fill), progress=0,
                              stage='Aguardando preparação', error='')

        def work():
            try:
                self.prepare(name, fill, notify=self.update, background=True)
                self.update(busy=False, progress=100, stage='Pronto para usar')
            except Exception as exc:
                self.update(busy=False, stage='Falha na preparação', error=str(exc))

        threading.Thread(target=work, daemon=True).start()
