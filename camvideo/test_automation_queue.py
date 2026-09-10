import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from automation_queue import run_queue, additional_capacity, GIB


class QueueTests(unittest.TestCase):
    def setup_queue(self, failure=False):
        targets = {f'p{i}': (f's{i}', i) for i in range(5)}
        installed = {s: dict(confirmed=True, assetId='same') for s, _ in targets.values()}
        active, calls, rows = set(), [], {}
        a = SimpleNamespace(e=SimpleNamespace(cancelar_sync=threading.Event()),
                            stop_after_round=threading.Event(), update=Mock())
        def check():
            if a.e.cancelar_sync.is_set(): raise InterruptedError()
        a.check_cancel = check
        def cycle(batch, *args, **kwargs):
            calls.append(list(batch))
            rows.clear()
            rows.update({s: {'stage': 'Error' if failure else 'Salvo'} for s, _ in batch.values()})
        a._run_cycle = cycle
        a.snapshot = lambda: rows
        def boot(n, s, p): active.add(s)
        shutdown = Mock(side_effect=lambda s: active.remove(s))
        memory = lambda: (9 - len(active)*3)*GIB
        return a, targets, installed, active, calls, boot, shutdown, memory

    def execute(self, data):
        a, targets, installed, active, calls, boot, shutdown, memory = data
        run_queue(a, targets, Mock(), installed, 'Lavar Louça na Pia', True, False,
                  lambda s: s in active, boot, shutdown, memory)

    def test_capacity_scales_with_available_memory(self):
        self.assertEqual(additional_capacity(2*GIB), 0)
        self.assertEqual(additional_capacity(9*GIB), 2)
        self.assertEqual(additional_capacity(27*GIB), 8)

    def test_all_devices_once_and_saved_batches_close(self):
        data = self.setup_queue()
        self.execute(data)
        self.assertEqual(data[4], [['p0', 'p1'], ['p2', 'p3'], ['p4']])
        self.assertEqual(data[6].call_count, 4)
        self.assertEqual(data[3], {'s4'})

    def test_failure_does_not_shutdown_or_advance(self):
        data = self.setup_queue(True)
        with self.assertRaises(RuntimeError): self.execute(data)
        self.assertEqual(len(data[4]), 1)
        data[6].assert_not_called()

    def test_wrong_video_rejected_before_boot(self):
        data = self.setup_queue()
        data[2]['s4']['assetId'] = 'different'
        with self.assertRaises(ValueError): self.execute(data)
        self.assertFalse(data[3])

    def test_cancel_after_save_does_not_start_next_batch(self):
        data = self.setup_queue()
        original = data[0]._run_cycle
        def cancelled(*args, **kwargs):
            original(*args, **kwargs)
            data[0].e.cancelar_sync.set()
        data[0]._run_cycle = cancelled
        with self.assertRaises(InterruptedError): self.execute(data)
        self.assertEqual(len(data[4]), 1)
        data[6].assert_not_called()

    def test_no_memory_does_not_boot(self):
        data = list(self.setup_queue())
        data[-1] = lambda: GIB
        with self.assertRaises(RuntimeError): self.execute(data)
        self.assertFalse(data[3])


if __name__ == '__main__': unittest.main()
