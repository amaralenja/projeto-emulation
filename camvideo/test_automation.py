import itertools
import threading
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
from automation import Automation, recording_duration, stop_deadline, normalize


class AutomationTests(unittest.TestCase):
    def engine(self):
        e = Mock()
        e.cancelar_sync = threading.Event()
        e._camera_pronta.return_value = 900
        e._uso_tarefa.return_value = 0
        e._ler_geracao.return_value = 4
        e._detectar_tarefa_sessao.return_value = ('task-id', 'Lavar Louça na Pia')
        return e

    def test_video_duration_and_cap(self):
        self.assertEqual(recording_duration(900), 900)
        self.assertEqual(recording_duration(1799), 1799)
        self.assertEqual(recording_duration(1860), 1799)
        for bad in [0, 60, float('nan'), float('inf')]:
            with self.assertRaises(ValueError): recording_duration(bad)

    def test_recording_overhead_counts_towards_cap(self):
        self.assertEqual(stop_deadline(20, 0, 900), 920)
        self.assertLessEqual(stop_deadline(20, 0, 1799), 1799)

    def test_accent_case_normalization(self):
        self.assertEqual(normalize(' LAVAR  LOUÇA na Pia '), normalize('Lavar louca na pia'))

    def test_rotation_is_idempotent(self):
        e = self.engine()
        e._adb.return_value.stdout = 'acceleration = 9.81:-0.0001:0\nOK'
        Automation(e, Mock()).rotate_left('s')
        self.assertEqual(e._adb.call_count, 1)

    def test_unknown_or_different_video_prevents_recording(self):
        e = self.engine()
        a = Automation(e, Mock())
        targets = {'one': ('s', '1'), 'two': ('t', '2')}
        for installed in [{}, {'s': {'confirmed': True, 'assetId': '1'}, 't': {'confirmed': True, 'assetId': '2'}}]:
            with self.assertRaises(ValueError): a.run(targets, Mock(), installed, 'task')
        e._tocar_botao_gravacao.assert_not_called()

    def test_preparation_failure_starts_none(self):
        e = self.engine()
        a = Automation(e, Mock())
        a.rotate_left = Mock(side_effect=RuntimeError('orientation'))
        with self.assertRaises(RuntimeError):
            a.run({'one': ('s', '1')}, Mock(), {'s': {'confirmed': True, 'assetId': '1'}}, 'task')
        e._tocar_botao_gravacao.assert_not_called()
        self.assertIn('orientation', a.snapshot()['s']['error'])

    def run_record(self, save_error=False):
        e = self.engine()
        a = Automation(e, Mock())
        a.rotate_left = Mock()
        a.navigate = Mock()
        a.save = Mock(side_effect=RuntimeError('save failed') if save_error else None)
        with patch('automation.time.monotonic', side_effect=itertools.count(0, 61)), \
             patch('automation.stop_deadline', side_effect=lambda play, trigger, duration: play+61):
            a.run({'one': ('s', '1')}, Mock(), {'s': {'confirmed': True, 'assetId': '1'}}, 'Lavar Louça na Pia')
        return a, e

    def test_resets_video_then_stops_and_confirms_save(self):
        a, e = self.run_record()
        self.assertEqual(e._tocar_botao_gravacao.call_count, 2)
        self.assertEqual(a.snapshot()['s']['stage'], 'Salvo')
        self.assertEqual(e._escrever_controle.call_args_list[0].args, ('s', 'pause', 5))
        self.assertEqual(e._escrever_controle.call_args_list[1].args, ('s', 'play', 5))
        e._somar_uso_tarefa.assert_called_once()

    def test_failed_save_is_not_counted_or_reported_as_saved(self):
        a, e = self.run_record(True)
        self.assertNotEqual(a.snapshot()['s']['stage'], 'Salvo')
        e._somar_uso_tarefa.assert_not_called()

    def test_save_accepts_preview_confirms_dialog_and_checks_success(self):
        a = Automation(self.engine(), Mock())
        a.xml = Mock(side_effect=[
            ET.fromstring('<hierarchy><node resource-id="record-accept" /></hierarchy>'),
            ET.fromstring('<hierarchy><node text="Salvar este Minute?"/><node content-desc="Salvar" clickable="true"/></hierarchy>'),
            ET.fromstring('<hierarchy><node text="Minute salvo."/></hierarchy>')])
        a.tap = Mock()
        a.save('s', pause_preview=False)
        self.assertEqual(a.tap.call_count, 2)


if __name__ == '__main__': unittest.main()
