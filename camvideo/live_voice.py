"""Bounded audio prefetch queue: OpenAI writes, local OmniVoice synthesizes."""
from collections import deque
import threading
import time
from voice_manager import read_json


class LiveVoice:
    def __init__(self, voice, writer):
        self.voice, self.writer = voice, writer
        self.lock = threading.RLock()
        self.cancel = threading.Event()
        self.thread = None
        self.state = dict(active=False, message='Informe o produto e prepare uma amostra.',
                          queued=0, generated=0, played=0, requests=0, tokens=0)

    def snapshot(self):
        with self.lock:
            return dict(self.state, apiKeyConfigured=self.writer.configured(), product=self.writer.product())

    def start(self, product, output='', volume=.8, minutes=60, steps=32, continuous=True):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Aguarde a sessão anterior parar.')
            if any(self.voice.jobs.values()):
                raise ValueError('Aguarde ou pare a fala atual primeiro.')
            if not self.voice.installed():
                raise ValueError('Instale o OmniVoice primeiro.')
            if not self.writer.configured():
                raise ValueError('Salve sua chave da OpenAI primeiro.')
            if steps not in (16, 32) or minutes not in (0, 15, 30, 60, 120):
                raise ValueError('Configuração da sessão inválida.')
            if not isinstance(volume, (float, int)) or not 0 <= volume <= 1:
                raise ValueError('Volume inválido.')
            if continuous and not any(row['key'] == output for row in self.voice.output_devices):
                raise ValueError('Selecione a saída de áudio da live.')
            product = self.writer.save_product(product)
            self.cancel = threading.Event()
            self.state = dict(active=True, message='Preparando roteiro com a OpenAI...', queued=0,
                              generated=0, played=0, requests=0, tokens=0, script='', error=False,
                              continuous=continuous, minutes=minutes, started=time.time())
            self.thread = threading.Thread(target=self._run,
                args=(product, output, volume, minutes, steps, continuous), daemon=True)
            self.thread.start()

    def stop(self):
        with self.lock:
            self.cancel.set()
            if self.state['active']:
                self.voice.stop('generation')
                self.voice.stop('playback')
                self.state['message'] = 'Parando. Uma solicitação à OpenAI já enviada pode terminar.'

    def update(self, **values):
        with self.lock:
            self.state.update(values)

    def _run(self, product, output, volume, minutes, steps, continuous):
        queue, history = deque(), []
        pending = None
        playback = None
        started_playing = False
        deadline = time.monotonic() + minutes * 60 if minutes else float('inf')
        try:
            while not self.cancel.is_set() and time.monotonic() < deadline:
                with self.voice.lock:
                    generating = self.voice.jobs['generation'] is not None
                    playing = self.voice.jobs['playback'] is not None
                    generation_state = dict(self.voice.states['generation'])
                    playback_state = dict(self.voice.states['playback'])
                if pending and not generating:
                    clip = read_json(self.voice.clip_path(pending).with_suffix('.json'), {})
                    if not clip:
                        raise ValueError(generation_state.get('message', 'A voz não foi gerada.'))
                    queue.append(pending)
                    pending = None
                    self.update(generated=self.state['generated'] + 1, queued=len(queue))
                    if not continuous:
                        self.update(message='Amostra pronta na biblioteca. Ouça antes de iniciar.', lastClip=queue[0])
                        return
                if playback and not playing:
                    if playback_state.get('error'):
                        raise ValueError(playback_state['message'])
                    self.update(played=self.state['played'] + 1)
                    playback = None
                # Start with two complete files, then synthesize ahead of playback.
                if not playing and queue and (started_playing or len(queue) >= 2):
                    playback = queue.popleft()
                    self.voice.play(playback, output, volume)
                    started_playing = True
                    self.update(queued=len(queue), message='Falando sobre o produto e preparando as próximas falas.')
                if not pending and len(queue) < 2:
                    self.update(message='Criando a próxima fala com a OpenAI...', requests=self.state['requests'] + 1)
                    text, usage = self.writer.write(product, history)
                    if self.cancel.is_set() or time.monotonic() >= deadline:
                        break
                    history.append(text)
                    history = history[-3:]
                    self.update(script=text, tokens=self.state['tokens'] + usage.get('total_tokens', 0))
                    pending = self.voice.generate(text, steps=steps, target_duration=60,
                        seed=42 + self.state['generated'])
                    self.update(message='Gerando áudio local; a primeira preparação precisa de duas falas.')
                self.cancel.wait(.1)
        except Exception as error:
            self.update(error=True, message=str(error))
        finally:
            if continuous or self.cancel.is_set() or self.state.get('error'):
                self.voice.stop('generation')
                self.voice.stop('playback')
            with self.lock:
                self.state['active'] = False
                if not self.state.get('error') and (continuous or self.cancel.is_set()):
                    self.state['message'] = 'Sessão encerrada. As falas geradas ficaram salvas.'
