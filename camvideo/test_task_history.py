import unittest
from task_history import task_usage, priority


class UsageTests(unittest.TestCase):
    def test_day_rollover_retains_total_and_aliases(self):
        history = {'dias': {
            '2026-09-09': {'phone': {'old': {'nome': 'Lavar Louça na Pia', 'segundos': 3600}}},
            '2026-09-10': {'phone': {'new': {'nome': 'Lavar Louças na Pia', 'segundos': 1800}}}}}
        self.assertEqual(task_usage(history, 'phone', 'lavar louca na pia'), 5400)
        self.assertEqual(task_usage(history, 'phone', 'lavar louca na pia', '2026-09-10'), 1800)
        self.assertEqual(task_usage(history, 'phone', 'lavar louca no tanque'), 0)

    def test_less_today_then_lifetime_and_skip_limit(self):
        targets = dict.fromkeys(['full', 'more', 'zeroOld', 'zeroNew', 'tooShort'])
        today = dict(full=7200, more=1800, zeroOld=0, zeroNew=0, tooShort=7150)
        total = dict(full=7200, more=1800, zeroOld=5000, zeroNew=0, tooShort=7150)
        ordered, skipped = priority(targets, today.get, total.get)
        self.assertEqual(list(ordered), ['zeroNew', 'zeroOld', 'more'])
        self.assertEqual(set(skipped), {'full', 'tooShort'})


if __name__ == '__main__': unittest.main()
