import unittest
from unittest.mock import Mock
from interleaved_plan import validate_plan, run_interleaved_plan


class InterleavedTests(unittest.TestCase):
    def test_alternates_saved_pairs_with_correct_video_and_daily_limits(self):
        rows=[dict(task=t,video=t+'.mov') for t in ('Louça','Ervas','Jardim')]
        targets={str(i):(str(i),i) for i in range(3)}
        totals={}; events=[]
        def record(pair,task):
            events.append(('save',task,list(pair)))
            for n in pair: totals[n,task]=totals.get((n,task),0)+1800
        run_interleaved_plan(rows,targets,lambda n,t:totals.get((n,t),0),Mock(),
            lambda pair,v:events.append(('video',v,list(pair))),record,Mock(),lambda:False,Mock(),shuffle=lambda rows:None)
        self.assertEqual(len(totals),9)
        self.assertTrue(all(v==7200 for v in totals.values()))
        saved=[e for e in events if e[0]=='save']
        self.assertEqual([e[1] for e in saved[:6]],['Louça','Ervas','Jardim']*2)
        for i in range(0,len(events),2):
            self.assertEqual(events[i][1],events[i+1][1]+'.mov')
            self.assertEqual(events[i][2],events[i+1][2])
            self.assertLessEqual(len(events[i][2]),2)

    def test_missing_task_skips_only_failed_pair_without_credit(self):
        totals={}; seen=[]
        def record(pair,task):
            seen.append((tuple(pair),task))
            if task=='A' and 'p1' in pair:return False
            for n in pair:totals[n,task]=7200
        update=Mock()
        run_interleaved_plan([dict(task='A',video='a.mov'),dict(task='B',video='b.mov')],
            {n:(n,1) for n in ['p1','p2','p3']},lambda n,t:totals.get((n,t),0),Mock(),Mock(),record,
            Mock(),lambda:False,update,shuffle=lambda rows:None)
        self.assertNotIn(('p1','A'),totals)
        self.assertNotIn(('p2','A'),totals)
        self.assertEqual(totals['p3','A'],7200)
        self.assertEqual(sum(totals.get((n,'B'),0) for n in ['p1','p2','p3']),21600)
        self.assertEqual(seen.count((('p1','p2'),'A')),1)

    def test_no_source_switch_after_save_failure(self):
        activate=Mock()
        with self.assertRaises(RuntimeError):
            run_interleaved_plan([dict(task='A',video='a.mov'),dict(task='B',video='b.mov')],
                {'p':('s',1)},lambda n,t:0,Mock(),activate,Mock(side_effect=RuntimeError('save failed')),
                Mock(),lambda:False,Mock())
        activate.assert_called_once()

    def test_validates_duplicates_and_paths_before_start(self):
        for rows in ([],[dict(task='A',video='../a.mov')],
                     [dict(task='A',video='a.mov'),dict(task='a',video='b.mov')]):
            with self.assertRaises(ValueError): validate_plan(rows)

    def test_stop_after_save_prevents_switch(self):
        stopped=[False]; activate=Mock()
        run_interleaved_plan([dict(task='A',video='a.mov'),dict(task='B',video='b.mov')],
            {'p':('s',1)},lambda n,t:0,Mock(),activate,lambda *args:stopped.__setitem__(0,True),
            Mock(),lambda:stopped[0],Mock())
        activate.assert_called_once()

    def test_missing_video_aborts_before_activation(self):
        activate=Mock()
        with self.assertRaises(ValueError):
            run_interleaved_plan([dict(task='A',video='a.mov')],{'p':('s',1)},lambda n,t:0,
                Mock(side_effect=ValueError('missing')),activate,Mock(),Mock(),lambda:False,Mock())
        activate.assert_not_called()
