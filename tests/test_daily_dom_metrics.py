import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from osm_ad_bot_conductor import DailyDomMetrics, OSMConductorBot, ScoutOutcome


class DailyDomMetricsTests(unittest.TestCase):
    def test_metrics_survive_a_new_instance_and_are_grouped_by_day(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "daily-dom-metrics.json"
            metrics = DailyDomMetrics(path)

            self.assertEqual(
                metrics.increment("dom_reward_detected", now=datetime(2026, 8, 29, 12, 0)),
                1,
            )
            self.assertEqual(
                metrics.increment("dom_reward_detected", now=datetime(2026, 8, 29, 12, 1)),
                2,
            )
            self.assertEqual(
                metrics.increment("scout_navigation_error", now=datetime(2026, 8, 30, 0, 1)),
                1,
            )

            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["2026-08-29"]["dom_reward_detected"], 2)
            self.assertEqual(persisted["2026-08-30"]["scout_navigation_error"], 1)

            reloaded = DailyDomMetrics(path)
            self.assertEqual(
                reloaded.increment("dom_reward_detected", now=datetime(2026, 8, 29, 12, 2)),
                3,
            )


class ScoutOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_ad_retries_without_claiming_a_rate_limit(self):
        bot = object.__new__(OSMConductorBot)
        bot._shutdown = False
        bot.stats = {"dom_rewards_detected": 0, "errors": 0, "cycles": 0}
        bot.watcher_tabs = 4
        bot.poll_interval = 15
        bot.ad_duration = 120
        logs = []
        bot._log = logs.append

        async def scout_check():
            return ScoutOutcome.AD_UNAVAILABLE

        async def wait_for_retry(outcome):
            self.assertIs(outcome, ScoutOutcome.AD_UNAVAILABLE)
            bot._shutdown = True

        bot._scout_check = scout_check
        bot._wait_for_scout_retry = wait_for_retry

        await bot._conductor_loop()

        self.assertFalse(any("Rate-limit cooldown handled" in line for line in logs))

    async def test_consecutive_navigation_errors_raise_runtime_error(self):
        bot = object.__new__(OSMConductorBot)
        bot._shutdown = False
        bot.stats = {"dom_rewards_detected": 0, "errors": 0, "cycles": 0}
        bot.watcher_tabs = 4
        bot.poll_interval = 15
        bot.ad_duration = 120
        logs = []
        bot._log = logs.append

        async def scout_check():
            return ScoutOutcome.NAVIGATION_ERROR

        async def wait_for_retry(outcome):
            pass

        bot._scout_check = scout_check
        bot._wait_for_scout_retry = wait_for_retry

        with self.assertRaises(RuntimeError) as ctx:
            await bot._conductor_loop()

        self.assertIn("consecutive scout navigation errors", str(ctx.exception))
        self.assertTrue(any("Exceeded 5 consecutive scout navigation errors" in line for line in logs))
