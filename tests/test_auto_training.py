import asyncio
import json
import random
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from auto_training import (
    AutoTrainingManager,
    build_candidate_pool,
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

    def test_candidate_pool_excludes_low_yield_injured_listed_and_occupied(self):
        players = [
            {"id": 1, "name": "Best", "position": 1, "age": 21, "statAtt": 70, "injuryId": 0},
            {"id": 2, "name": "Edge", "position": 1, "age": 20, "statAtt": 60, "injuryId": 0},
            {"id": 3, "name": "Below", "position": 1, "age": 19, "statAtt": 60, "injuryId": 0},
            {"id": 4, "name": "Injured", "position": 1, "age": 18, "statAtt": 60, "injuryId": 2},
            {"id": 5, "name": "Listed", "position": 1, "age": 18, "statAtt": 60, "injuryId": 0},
            {"id": 6, "name": "Occupied", "position": 1, "age": 18, "statAtt": 60, "injuryId": 0},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 100},
            {"playerId": 2, "forecast": 85},
            {"playerId": 3, "forecast": 84},
            {"playerId": 4, "forecast": 100},
            {"playerId": 5, "forecast": 100},
            {"playerId": 6, "forecast": 100},
        ]
        pool = build_candidate_pool(players, forecasts, 1, {6}, {5})
        self.assertEqual([item.player["id"] for item in pool], [1, 2])

    def test_weighted_choice_stays_inside_top_band(self):
        players = [
            {"id": i, "position": 2, "age": 20 + i, "statOvr": 50}
            for i in range(1, 8)
        ]
        forecasts = [
            {"playerId": i, "forecast": 100 - i}
            for i in range(1, 8)
        ]
        pool = build_candidate_pool(players, forecasts, 2, set(), set())
        self.assertLessEqual(len(pool), 5)
        chosen = choose_candidate(pool, random.Random(7))
        self.assertIn(chosen, pool)

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
            {"id": 101, "name": "A1", "position": 1, "age": 21, "statAtt": 60, "injuryId": 0},
            {"id": 102, "name": "M1", "position": 2, "age": 22, "statOvr": 60, "injuryId": 0},
            {"id": 103, "name": "D1", "position": 3, "age": 23, "statDef": 60, "injuryId": 0},
            {"id": 104, "name": "G1", "position": 4, "age": 24, "statDef": 60, "injuryId": 0},
            {"id": 105, "name": "A2", "position": 1, "age": 19, "statAtt": 55, "injuryId": 0},
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
            api, "123", "4", logs.append, poll_interval=15, rng=random.Random(1)
        )

        await manager.reconcile()

        self.assertEqual(manager.stats["claimed"], 1)
        self.assertEqual(manager.stats["started"], 4)
        trainers = [session["trainer"] for session in api.sessions]
        self.assertEqual(sorted(trainers), [1, 2, 3, 4, 5])
        player_ids = [session["playerId"] for session in api.sessions]
        self.assertEqual(len(player_ids), len(set(player_ids)))
        self.assertTrue(any("claimed completed session" in line for line in logs))
        self.assertFalse(any("universaltrainer/buy" in endpoint for _, endpoint, _ in api.requests))

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


if __name__ == "__main__":
    unittest.main()
