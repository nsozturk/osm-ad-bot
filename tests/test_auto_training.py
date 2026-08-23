import asyncio
import json
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from auto_training import (
    AutoTrainingManager,
    build_candidate_pool,
    build_candidate_pool_result,
    choose_candidate,
    load_training_profile,
    session_finished,
)


class AutoTrainingSelectionTests(unittest.TestCase):
    def test_profile_parser_reads_timer_ids_and_context_without_credentials(self):
        root = Path("tmp")
        root.mkdir(exist_ok=True)
        path = root / "test-training-profile.har"
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://web-api.onlinesoccermanager.com/api/v1/leagues/123/teams/4/trainingsessions",
                            "headers": [{"name": "Authorization", "value": "Bearer must-not-be-read"}],
                            "postData": {"params": [
                                {"name": "playerId", "value": "10"},
                                {"name": "trainer", "value": "1"},
                                {"name": "timerGameSettingId", "value": "700"},
                            ]},
                        },
                        "response": {"status": 200, "content": {"text": "{}"}},
                    },
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://web-api.onlinesoccermanager.com/api/v1/leagues/123/teams/4/trainingsessions",
                            "postData": {"params": [
                                {"name": "playerId", "value": "11"},
                                {"name": "trainer", "value": "5"},
                                {"name": "timerGameSettingId", "value": "900"},
                            ]},
                        },
                        "response": {"status": 200, "content": {"text": "{}"}},
                    },
                ]
            }
        }
        try:
            path.write_text(json.dumps(har), encoding="utf-8")
            profile = load_training_profile(str(path))
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual(profile.normal_timer_id, 700)
        self.assertEqual(profile.universal_timer_id, 900)
        self.assertEqual((profile.league_id, profile.team_id), ("123", "4"))
        self.assertFalse(hasattr(profile, "token"))

    def test_candidate_pool_excludes_below_90_injured_listed_and_occupied(self):
        players = [
            {"id": 1, "name": "Best", "position": 1, "age": 21, "statAtt": 95, "injuryId": 0},
            {"id": 2, "name": "Edge", "position": 1, "age": 20, "statAtt": 90, "injuryId": 0},
            {"id": 3, "name": "Below", "position": 1, "age": 19, "statAtt": 89, "injuryId": 0},
            {"id": 4, "name": "Injured", "position": 1, "age": 18, "statAtt": 98, "injuryId": 2},
            {"id": 5, "name": "Listed", "position": 1, "age": 18, "statAtt": 97, "injuryId": 0},
            {"id": 6, "name": "Occupied", "position": 1, "age": 18, "statAtt": 96, "injuryId": 0},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70},
            {"playerId": 2, "forecast": 92},
            {"playerId": 3, "forecast": 100},
            {"playerId": 4, "forecast": 100},
            {"playerId": 5, "forecast": 100},
            {"playerId": 6, "forecast": 100},
        ]
        pool = build_candidate_pool(players, forecasts, 1, {6}, {5})
        self.assertEqual([item.player["id"] for item in pool], [2, 1])

    def test_main_stat_90_is_included_and_89_is_rejected(self):
        players = [
            {"id": 1, "position": 1, "age": 16, "statAtt": 89},
            {"id": 2, "position": 1, "age": 40, "statAtt": 90},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 100},
            {"playerId": 2, "forecast": 60},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [2])

    def test_goalkeeper_uses_the_same_inclusive_90_threshold(self):
        players = [
            {"id": 1, "position": 4, "age": 18, "statDef": 89},
            {"id": 2, "position": 4, "age": 34, "statDef": 90},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 100},
            {"playerId": 2, "forecast": 60},
        ]

        pool = build_candidate_pool(players, forecasts, 4, set(), set())
        chosen = choose_candidate(pool)

        self.assertEqual([item.player["id"] for item in pool], [2])
        self.assertEqual(chosen.player["id"], 2)

    def test_highest_forecast_wins_regardless_of_age(self):
        players = [
            {"id": 1, "position": 3, "age": 16, "statDef": 99},
            {"id": 2, "position": 3, "age": 39, "statDef": 90},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 60},
            {"playerId": 2, "forecast": 81},
        ]

        pool = build_candidate_pool(players, forecasts, 3, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [2, 1])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

    def test_equal_forecast_prefers_higher_main_stat(self):
        players = [
            {"id": 1, "position": 2, "age": 21, "statOvr": 90},
            {"id": 2, "position": 2, "age": 33, "statOvr": 97},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 80},
            {"playerId": 2, "forecast": 80},
        ]

        pool = build_candidate_pool(players, forecasts, 2, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [2, 1])

    def test_equal_forecast_and_main_stat_prefers_lower_player_id(self):
        players = [
            {"id": 20, "position": 1, "age": 18, "statAtt": 95},
            {"id": 10, "position": 1, "age": 40, "statAtt": 95},
        ]
        forecasts = [
            {"playerId": 20, "forecast": 75},
            {"playerId": 10, "forecast": 75},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [10, 20])

    def test_universal_coach_uses_forecast_universal(self):
        players = [
            {"id": 1, "position": 1, "age": 21, "statAtt": 95},
            {"id": 2, "position": 2, "age": 22, "statOvr": 95},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 99, "forecastUniversal": 40},
            {"playerId": 2, "forecast": 50, "forecastUniversal": 80},
        ]

        normal_pool = build_candidate_pool(players, forecasts, 1, set(), set())
        universal_pool = build_candidate_pool(players, forecasts, 5, set(), set())

        self.assertEqual(choose_candidate(normal_pool).player["id"], 1)
        self.assertEqual(choose_candidate(universal_pool).player["id"], 2)

    def test_empty_pool_reasons_distinguish_forecast_and_unavailable_players(self):
        player = {"id": 1, "position": 1, "age": 21, "statAtt": 90}
        below = {"id": 2, "position": 1, "age": 18, "statAtt": 89}

        no_forecast = build_candidate_pool_result([player], [], 1, set(), set())
        below_floor = build_candidate_pool_result(
            [below], [{"playerId": 2, "forecast": 100}], 1, set(), set()
        )
        unavailable = build_candidate_pool_result(
            [player], [{"playerId": 1, "forecast": 100}], 1, {1}, set()
        )

        self.assertEqual(
            no_forecast.empty_reason,
            "no positive forecast candidate at or above main stat 90",
        )
        self.assertEqual(
            below_floor.empty_reason,
            "all available candidates are below main stat 90",
        )
        self.assertEqual(
            unavailable.empty_reason,
            "all position candidates are occupied, injured, listed, or maxed",
        )

    def test_choice_is_repeatable_and_never_random(self):
        players = [
            {"id": i, "position": 2, "age": 20 + i, "statOvr": 90 + i}
            for i in range(1, 8)
        ]
        forecasts = [
            {"playerId": i, "forecast": 100 - i}
            for i in range(1, 8)
        ]
        pool = build_candidate_pool(players, forecasts, 2, set(), set())
        choices = [choose_candidate(pool).player["id"] for _ in range(20)]

        self.assertEqual(len(pool), 7)
        self.assertEqual(choices, [1] * 20)

    def test_finished_session_uses_server_timestamp(self):
        session = {
            "countdownTimer": {
                "currentTimestamp": 200,
                "finishedTimestamp": 199,
                "isClaimed": False,
            }
        }
        self.assertTrue(session_finished(session, now=100))


class FakeTrainingApi:
    def __init__(self):
        now = int(time.time())
        self.sessions = [
            {
                "id": 50,
                "trainer": 1,
                "playerId": 101,
                "countdownTimer": {
                    "currentTimestamp": now,
                    "finishedTimestamp": now - 1,
                    "isClaimed": False,
                },
            },
            {
                "id": 51,
                "trainer": 2,
                "playerId": 102,
                "countdownTimer": {
                    "currentTimestamp": now,
                    "finishedTimestamp": now + 999,
                    "isClaimed": False,
                },
            },
        ]
        self.players = [
            {"id": 101, "name": "A1", "position": 1, "age": 21, "statAtt": 95, "injuryId": 0},
            {"id": 102, "name": "M1", "position": 2, "age": 22, "statOvr": 96, "injuryId": 0},
            {"id": 103, "name": "D1", "position": 3, "age": 23, "statDef": 97, "injuryId": 0},
            {"id": 104, "name": "G1", "position": 4, "age": 24, "statDef": 98, "injuryId": 0},
            {"id": 105, "name": "A2", "position": 1, "age": 19, "statAtt": 94, "injuryId": 0},
        ]
        self.forecasts = [
            {"playerId": player["id"], "forecast": 70, "forecastUniversal": 80}
            for player in self.players
        ]
        self.requests = []

    async def __call__(self, method, endpoint, payload=None):
        self.requests.append((method, endpoint, payload))
        if endpoint.endswith("/trainingsessions/ongoing"):
            return (200, list(self.sessions)) if self.sessions else (404, {})
        if endpoint.endswith("/claim"):
            session_id = int(endpoint.split("/")[-2])
            self.sessions = [item for item in self.sessions if item["id"] != session_id]
            return 200, {"progressImprovement": 10}
        if method == "POST" and endpoint.endswith("/trainingsessions"):
            now = int(time.time())
            self.sessions.append({
                "id": 1000 + len(self.sessions),
                "trainer": payload["trainer"],
                "playerId": payload["playerId"],
                "countdownTimer": {
                    "currentTimestamp": now,
                    "finishedTimestamp": now + 999,
                    "isClaimed": False,
                },
            })
            return 200, {"id": self.sessions[-1]["id"]}
        if endpoint.endswith("/players"):
            return 200, self.players
        if endpoint.endswith("/trainingforecasts"):
            return 200, self.forecasts
        if endpoint.endswith("/transferplayers/0"):
            return 200, []
        if endpoint.endswith("/finances/balanceandsavings"):
            return 200, {"balance": 1_000_000}
        if endpoint.endswith("/timers"):
            now = int(time.time())
            return 200, [{
                "id": -2,
                "type": 16,
                "currentTimestamp": now,
                "finishedTimestamp": now + 999,
                "isClaimed": False,
            }]
        return 500, {}


class AutoTrainingManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconcile_claims_finished_and_fills_each_free_slot_once(self):
        api = FakeTrainingApi()
        logs = []
        manager = AutoTrainingManager(
            api, "123", "4", logs.append, poll_interval=15
        )

        await manager.reconcile()

        self.assertEqual(manager.stats["claimed"], 1)
        self.assertEqual(manager.stats["started"], 4)
        trainers = [session["trainer"] for session in api.sessions]
        self.assertEqual(sorted(trainers), [1, 2, 3, 4, 5])
        player_ids = [session["playerId"] for session in api.sessions]
        self.assertEqual(len(player_ids), len(set(player_ids)))
        self.assertTrue(any("claimed completed session" in line for line in logs))
        self.assertTrue(any(
            "stat " in line and "forecast " in line and "selection deterministic-max" in line
            for line in logs
        ))
        self.assertFalse(any("priority " in line for line in logs))
        self.assertFalse(any("universaltrainer/buy" in endpoint for _, endpoint, _ in api.requests))

    async def test_candidate_ranking_failure_skips_only_affected_trainer(self):
        api = FakeTrainingApi()
        logs = []
        manager = AutoTrainingManager(
            api, "123", "4", logs.append, poll_interval=15
        )
        original = build_candidate_pool_result

        def fail_attacker_only(players, forecasts, trainer, occupied, listed):
            if trainer == 1:
                raise ValueError("bad player state")
            return original(players, forecasts, trainer, occupied, listed)

        with patch("auto_training.build_candidate_pool_result", side_effect=fail_attacker_only):
            await manager.reconcile()

        trainers = sorted(session["trainer"] for session in api.sessions)
        self.assertEqual(trainers, [2, 3, 4, 5])
        self.assertEqual(manager.stats["errors"], 1)
        self.assertTrue(any("trainer 1 candidate ranking failed" in line for line in logs))

    async def test_empty_ongoing_404_is_normalized_to_empty_list(self):
        async def api(method, endpoint, payload=None):
            return 404, {}

        manager = AutoTrainingManager(api, "123", "4", lambda _: None)
        self.assertEqual(
            await manager._get("/trainingsessions/ongoing", empty_404=True),
            [],
        )

    async def test_run_contains_reconcile_failure_and_retries(self):
        stop = {"value": False}
        manager = AutoTrainingManager(
            AsyncMock(), "123", "4", lambda _: None,
            poll_interval=15, should_stop=lambda: stop["value"],
        )
        manager.reconcile = AsyncMock(side_effect=RuntimeError("boom"))

        async def stop_after_sleep(_):
            stop["value"] = True

        with patch("auto_training.asyncio.sleep", side_effect=stop_after_sleep):
            await manager.run()

        self.assertEqual(manager.stats["errors"], 1)
        manager.reconcile.assert_awaited_once()

    async def test_run_logs_first_successful_reconciliation(self):
        stop = {"value": False}
        logs = []
        manager = AutoTrainingManager(
            AsyncMock(), "123", "4", logs.append,
            poll_interval=15, should_stop=lambda: stop["value"],
        )
        manager.reconcile = AsyncMock()

        async def stop_after_sleep(_):
            stop["value"] = True

        with patch("auto_training.asyncio.sleep", side_effect=stop_after_sleep):
            await manager.run()

        manager.reconcile.assert_awaited_once()
        self.assertIn("[TRAINING] reconciliation healthy", logs)


if __name__ == "__main__":
    unittest.main()
