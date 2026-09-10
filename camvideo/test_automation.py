import itertools
import threading
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch
from automation import Automation, recording_duration, stop_deadline, normalize


class AutomationTests(unittest.TestCase):
    def test_wait_for_cold_start_ignores_empty_screen(self):
        a = Automation(self.engine(), Mock())
        a.minute_foreground = Mock(return_value=True)
        a.e._camera_pronta.return_value = None
        a.xml = Mock(side_effect=[ET.fromstring('<hierarchy/>'), ET.fromstring(
            '<hierarchy><node package="com.bakerdata.minute" resource-id="nav-index"/></hierarchy>')])
        a.e.cancelar_sync.wait = Mock(return_value=False)
        a.wait_minute_ready('s')
        self.assertEqual(a.xml.call_count, 2)

    def test_cold_start_timeout_does_not_tap(self):
        a = Automation(self.engine(), Mock())
        with self.assertRaises(RuntimeError): a.wait_minute_ready('s', timeout=0)
        a.e._tocar_botao_gravacao.assert_not_called()

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
        a.wait_recording = Mock(return_value='session_0')
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
        self.assertEqual(e._escrever_controle.call_args_list[2].args, ('s', 'play', 5))
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

    def test_tips_are_handled_before_native_camera_readiness(self):
        a = Automation(self.engine(), Mock())
        a.xml = Mock(side_effect=[
            ET.fromstring('<hierarchy><node resource-id="record-start-task"/></hierarchy>'),
            ET.fromstring('<hierarchy><node resource-id="recording-tips-got-it"/></hierarchy>'),
            ET.fromstring('<hierarchy/>')])
        a.tap = Mock()
        with patch('automation.time.sleep'):
            a.finish_camera('s')
        self.assertEqual(a.tap.call_count, 2)

    def test_countdown_and_growing_video_required_before_play(self):
        e = self.engine()
        e.cancelar_sync = Mock()
        e.cancelar_sync.wait.return_value = False
        e.cancelar_sync.is_set.return_value = False
        e._esperar_gravacao.return_value = 'session_0'
        e._shell_root.side_effect = [Mock(stdout=str(n)) for n in (0, 32, 32, 4096)]
        a = Automation(e, Mock())
        with patch('automation.time.monotonic', return_value=0):
            self.assertEqual(a.wait_recording('s', set(), 0), 'session_0')
        self.assertEqual(e.cancelar_sync.wait.call_args_list[0].args, (10,))
        self.assertEqual(e._shell_root.call_count, 4)
        e._escrever_controle.assert_not_called()

    def test_failed_start_does_not_tap_record_a_second_time(self):
        e = self.engine()
        e._adb.return_value.stdout = 'mResumedActivity: launcher'
        a = Automation(e, Mock())
        a.rotate_left = Mock()
        a.navigate = Mock()
        a.wait_recording = Mock(side_effect=RuntimeError('countdown failed'))
        a.run({'one': ('s', '1')}, Mock(), {'s': {'confirmed': True, 'assetId': '1'}}, 'task')
        self.assertEqual(e._tocar_botao_gravacao.call_count, 1)
        self.assertFalse(any(c.args[1] == 'play' for c in e._escrever_controle.call_args_list))
        self.assertIn('countdown failed', a.snapshot()['s']['error'])
        self.assertFalse(any(c.args[-2:] == ('keyevent', '4') for c in e._adb.call_args_list))

    def test_keyboard_back_only_when_keyboard_is_visible(self):
        e = self.engine()
        a = Automation(e, Mock())
        e._adb.return_value.stdout = 'mInputShown=false'
        a.hide_keyboard('s')
        self.assertEqual(e._adb.call_count, 1)
        e._adb.return_value.stdout = 'mInputShown=true'
        a.hide_keyboard('s')
        self.assertEqual(e._adb.call_args.args[-1], '66')

    def test_native_camera_is_left_only_once(self):
        e = self.engine()
        e._adb.return_value.stdout = 'mResumedActivity: com.bakerdata.minute/.MainActivity'
        a = Automation(e, Mock())
        a.xml = Mock(side_effect=RuntimeError('native camera inaccessible'))
        with patch('automation.time.sleep'), self.assertRaises(RuntimeError):
            a.task_list('s')
        backs = [c for c in e._adb.call_args_list if c.args[-2:] == ('keyevent', '4')]
        self.assertEqual(len(backs), 1)

    def test_reopens_minute_from_home_without_back(self):
        e = self.engine()
        e._camera_pronta.return_value = None
        e._adb.side_effect = [Mock(stdout='mResumedActivity: launcher'), Mock(stdout='ok'),
                             Mock(stdout='mResumedActivity: com.bakerdata.minute/.MainActivity')]
        a = Automation(e, Mock())
        a.xml = Mock(return_value=ET.fromstring('<hierarchy><node resource-id="nav-index" bounds="[1,1][100,100]"/></hierarchy>'))
        a.tap = Mock(); a.hide_keyboard = Mock()
        with patch('automation.time.sleep'): a.task_list('s')
        self.assertTrue(any('monkey' in c.args for c in e._adb.call_args_list))
        self.assertFalse(any('keyevent' in c.args for c in e._adb.call_args_list))

    def test_visible_task_list_wins_over_stale_native_camera_flag(self):
        e = self.engine()
        e._adb.return_value.stdout = 'mResumedActivity: com.bakerdata.minute/.MainActivity'
        a = Automation(e, Mock())
        a.xml = Mock(return_value=ET.fromstring('<hierarchy><node resource-id="nav-index" bounds="[1,1][100,100]"/></hierarchy>'))
        a.tap = Mock(); a.hide_keyboard = Mock()
        a.task_list('s')
        e._camera_pronta.assert_not_called()
        self.assertFalse(any('keyevent' in c.args for c in e._adb.call_args_list))

    def test_scroll_refuses_unknown_screen(self):
        a = Automation(self.engine(), Mock())
        a.xml = Mock(return_value=ET.fromstring('<hierarchy/>'))
        with self.assertRaises(RuntimeError): a.scroll_tasks('s')
        a.e._adb.assert_not_called()

    def test_search_tries_alternative_word_and_rejects_similar_title(self):
        a = Automation(self.engine(), Mock())
        a.task_list = Mock(); a.set_query = Mock(); a.scroll_tasks = Mock(); a.finish_camera = Mock(); a.tap = Mock()
        wrong = ET.fromstring('<hierarchy><node resource-id="task-card-1" content-desc="Lavar Louça no Tanque, descrição" bounds="[1,1][100,100]"/></hierarchy>')
        right = ET.fromstring('<hierarchy><node resource-id="task-card-2" content-desc="LAVAR LOUÇA NA PIA, descrição" bounds="[1,1][100,100]"/></hierarchy>')
        a.xml = Mock(side_effect=[wrong,wrong,wrong,right])
        a.navigate('s','Lavar Louça na Pia')
        self.assertEqual(a.set_query.call_count,2)
        self.assertEqual(a.tap.call_args.args[1].get('resource-id'),'task-card-2')

    def test_search_replaces_old_text_and_verifies_new_text(self):
        a = Automation(self.engine(), Mock())
        a.search_field = Mock(return_value=ET.fromstring('<node text="LavarLavar"/>'))
        a.tap = Mock(); a.hide_keyboard = Mock()
        a.xml = Mock(return_value=ET.fromstring('<hierarchy><node resource-id="home-search-input" text="lavar"/></hierarchy>'))
        with patch('automation.time.sleep'): a.set_query('s','lavar')
        self.assertEqual(a.e._adb.call_args_list[0].args.count('67'),10)

    def test_loop_runs_again_only_after_all_saved_and_keeps_busy(self):
        e = self.engine(); updates = Mock(); a = Automation(e, updates)
        calls = []
        def cycle(*args, **kwargs):
            calls.append(kwargs)
            a.rows = {'s': {'stage': 'Salvo'}, 't': {'stage': 'Salvo'}}
            if len(calls) == 2: a.request_stop_after_round()
        a._run_cycle = Mock(side_effect=cycle)
        a.run({'one': ('s','1'), 'two': ('t','2')}, Mock(), {}, 'task', repeat=True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c['keep_busy'] for c in calls))
        self.assertEqual(updates.call_args.kwargs, {'busy': False, 'loopActive': False, 'loopStopping': False})
        self.assertTrue(any(c.kwargs.get('loopCompleted') == 2 for c in updates.call_args_list))

    def test_loop_stops_when_any_device_has_not_saved(self):
        a = Automation(self.engine(), Mock())
        def cycle(*args, **kwargs): a.rows = {'s': {'stage': 'Salvo'}, 't': {'stage': 'Erro'}}
        a._run_cycle = Mock(side_effect=cycle)
        a.run({'one': ('s','1'), 'two': ('t','2')}, Mock(), {}, 'task', repeat=True)
        a._run_cycle.assert_called_once()

    def test_stop_now_is_not_cleared_between_rounds(self):
        e = self.engine(); a = Automation(e, Mock())
        def cycle(*args, **kwargs):
            a.rows = {'s': {'stage': 'Salvo'}}
            e.cancelar_sync.set()
        a._run_cycle = Mock(side_effect=cycle)
        a.run({'one': ('s','1')}, Mock(), {}, 'task', repeat=True)
        a._run_cycle.assert_called_once()
        self.assertTrue(e.cancelar_sync.is_set())

    def test_loop_does_not_retry_daily_limit_error(self):
        a = Automation(self.engine(), Mock())
        def cycle(*args, **kwargs):
            if a.rows: raise RuntimeError('Limite diário insuficiente')
            a.rows = {'s': {'stage': 'Salvo'}}
        a._run_cycle = Mock(side_effect=cycle)
        with self.assertRaisesRegex(RuntimeError,'Limite diário'):
            a.run({'one': ('s','1')}, Mock(), {}, 'task', repeat=True)
        self.assertEqual(a._run_cycle.call_count, 2)

    def test_loop_requires_task_search(self):
        a = Automation(self.engine(), Mock())
        with self.assertRaises(ValueError): a.run({}, Mock(), {}, 'task', auto=False, repeat=True)


if __name__ == '__main__': unittest.main()
