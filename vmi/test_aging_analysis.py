import unittest

from aging_test_simple import AgingTestConfig, AgingTestRunner


class AgingAnalysisTest(unittest.TestCase):
    def test_equal_success_rate_and_entity_count_are_stable(self):
        runner = AgingTestRunner(AgingTestConfig())
        runner.metrics_history = [
            {
                "timestamp": "2026-04-06T14:51:21",
                "elapsed_minutes": 5,
                "metrics": {
                    "total_operations": 100,
                    "successful_operations": 100,
                    "failed_operations": 0,
                    "success_rate": 100.0,
                    "avg_duration": 3.2,
                    "total_entities": 0,
                },
            },
            {
                "timestamp": "2026-04-06T15:16:24",
                "elapsed_minutes": 30,
                "metrics": {
                    "total_operations": 200,
                    "successful_operations": 200,
                    "failed_operations": 0,
                    "success_rate": 100.0,
                    "avg_duration": 3.6,
                    "total_entities": 0,
                },
            },
        ]

        analysis = runner._analyze_metrics()
        trend = analysis["trend_analysis"]

        self.assertEqual("stable", trend["success_rate_trend"])
        self.assertEqual("worsening", trend["duration_trend"])
        self.assertEqual("stable", trend["entity_growth_trend"])


if __name__ == "__main__":
    unittest.main()
