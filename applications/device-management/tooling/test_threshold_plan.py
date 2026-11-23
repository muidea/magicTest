import unittest
from threshold_plan import build
from simulator.common import Failure


class ThresholdPlanTests(unittest.TestCase):
    def test_only_submits_measurements_and_preserves_expected_events(self):
        plan = build('a' * 32, 'AABBCCDDEEFF', '2026-10-25T08:00:00Z')
        self.assertEqual(len(plan['bootstrap']), 5)
        self.assertEqual(len(plan['telemetry']), 10)
        self.assertEqual(sum(len(x['candidates']) for x in plan['expectedEffects']), 9)
        self.assertEqual({x['entity'] for x in plan['telemetry']}, {'telemetry'})
        self.assertFalse(any(x['entity'] in ('alarm', 'maintenance') for x in plan['bootstrap'] + plan['telemetry']))
        self.assertEqual(plan['telemetry'][-1]['fields']['sampledAt'], '2026-10-25T08:00:00.000Z')
        self.assertIsNone(plan['telemetry'][-1]['fields']['temperature'])
        self.assertEqual(plan['telemetry'][-1]['fields']['loadPercent'], 0)
        self.assertEqual(plan, build('a' * 32, 'AABBCCDDEEFF', '2026-10-25T08:00:00Z'))
        self.assertNotEqual(plan['digest'], build('b' * 32, 'AABBCCDDEEFF', plan['anchor'])['digest'])

    def test_requires_exact_installation_and_fresh_run_identity(self):
        for deployment, run in (('', 'AABBCCDDEEFF'), ('A' * 32, 'AABBCCDDEEFF'), ('a' * 32, 'old')):
            with self.assertRaises(Failure): build(deployment, run, '2026-10-25T08:00:00Z')


if __name__ == '__main__': unittest.main()
