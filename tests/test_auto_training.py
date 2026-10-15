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
    rank_candidates,
    resolve_target_cap,
    session_finished,
    session_occupies_slot,
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

    def test_candidate_pool_excludes_injured_listed_and_occupied(self):
        players = [
            {"id": 1, "name": "Best", "position": 1, "age": 21, "statAtt": 95, "injuryId": 0},
            {"id": 2, "name": "Edge", "position": 1, "age": 20, "statAtt": 90, "injuryId": 0},
            {"id": 3, "name": "Low", "position": 1, "age": 19, "statAtt": 80, "injuryId": 0},
            {"id": 4, "name": "Injured", "position": 1, "age": 18, "statAtt": 98, "injuryId": 2},
            {"id": 5, "name": "Listed", "position": 1, "age": 18, "statAtt": 97, "injuryId": 0},
            {"id": 6, "name": "Occupied", "position": 1, "age": 18, "statAtt": 96, "injuryId": 0},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70},
            {"playerId": 2, "forecast": 75},
            {"playerId": 3, "forecast": 80},
            {"playerId": 4, "forecast": 100},
            {"playerId": 5, "forecast": 100},
            {"playerId": 6, "forecast": 100},
        ]
        pool = build_candidate_pool(players, forecasts, 1, {6}, {5})
        self.assertEqual([item.player["id"] for item in pool], [1, 2, 3])

    def test_all_positive_stats_are_eligible_when_floor_is_zero(self):
        players = [
            {"id": 1, "position": 1, "age": 16, "statAtt": 55},
            {"id": 2, "position": 1, "age": 40, "statAtt": 85},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 90},
            {"playerId": 2, "forecast": 70},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())

        # Player 2 (85) is closest to 120 and deficit is 30 (> 7), so Player 2 stays #1
        self.assertEqual([item.player["id"] for item in pool], [2, 1])

    def test_goalkeeper_selection_with_zero_floor(self):
        players = [
            {"id": 1, "position": 4, "age": 18, "statDef": 50},
            {"id": 2, "position": 4, "age": 34, "statDef": 83},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 93},
            {"playerId": 2, "forecast": 60},
        ]

        pool = build_candidate_pool(players, forecasts, 4, set(), set())
        chosen = choose_candidate(pool)

        # Player 2 (83) is closest to 120 (deficit 33 > 7), so Player 2 is chosen
        self.assertEqual([item.player["id"] for item in pool], [2, 1])
        self.assertEqual(chosen.player["id"], 2)

    def test_closest_to_130_wins_regardless_of_forecast_or_age(self):
        players = [
            {"id": 1, "position": 3, "age": 16, "statDef": 99},
            {"id": 2, "position": 3, "age": 39, "statDef": 90},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 60},
            {"playerId": 2, "forecast": 81},
        ]

        pool = build_candidate_pool(players, forecasts, 3, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [1, 2])
        self.assertEqual(choose_candidate(pool).player["id"], 1)

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

    def test_equal_main_stat_prefers_higher_forecast(self):
        players = [
            {"id": 1, "position": 2, "age": 21, "statOvr": 95},
            {"id": 2, "position": 2, "age": 33, "statOvr": 95},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70},
            {"playerId": 2, "forecast": 85},
        ]

        pool = build_candidate_pool(players, forecasts, 2, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [2, 1])

    def test_main_stat_120_and_above_is_excluded_from_candidate_pool(self):
        players = [
            {"id": 1, "position": 1, "age": 25, "statAtt": 120},
            {"id": 2, "position": 1, "age": 26, "statAtt": 121},
            {"id": 3, "position": 1, "age": 22, "statAtt": 119},
            {"id": 4, "position": 1, "age": 20, "statAtt": 110},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 50},
            {"playerId": 2, "forecast": 50},
            {"playerId": 3, "forecast": 60},
            {"playerId": 4, "forecast": 70},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())

        self.assertEqual([item.player["id"] for item in pool], [3, 4])
        self.assertEqual(choose_candidate(pool).player["id"], 3)

    def test_resolve_target_cap_ladder(self):
        self.assertEqual(resolve_target_cap([]), 120)
        self.assertEqual(resolve_target_cap([95, 119]), 120)
        self.assertEqual(resolve_target_cap([120, 125]), 130)
        self.assertEqual(resolve_target_cap([130, 135]), 140)
        self.assertEqual(resolve_target_cap([135, 139]), 140)
        self.assertEqual(resolve_target_cap([140, 140]), 150)
        self.assertEqual(resolve_target_cap([190, 195]), 200)
        self.assertEqual(resolve_target_cap([200, 205]), 200)

    def test_advances_to_140_when_all_position_players_reach_130(self):
        players = [
            {"id": 1, "position": 4, "age": 24, "statDef": 133},
            {"id": 2, "position": 4, "age": 27, "statDef": 130},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70},
            {"playerId": 2, "forecast": 75},
        ]

        pool = build_candidate_pool(players, forecasts, 4, set(), set())

        # Target advances to 140. Player 1 (133) is closest to 140.
        self.assertEqual([item.player["id"] for item in pool], [1, 2])
        self.assertEqual(choose_candidate(pool).player["id"], 1)

    def test_stops_at_140_until_all_players_in_position_reach_140(self):
        players = [
            {"id": 1, "position": 4, "age": 24, "statDef": 140},
            {"id": 2, "position": 4, "age": 27, "statDef": 130},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70},
            {"playerId": 2, "forecast": 75},
        ]

        pool = build_candidate_pool(players, forecasts, 4, set(), set())

        # Target remains 140 because Player 2 < 140. Player 1 (140) is excluded.
        self.assertEqual([item.player["id"] for item in pool], [2])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

    def test_advances_to_150_when_all_players_in_position_reach_140(self):
        players = [
            {"id": 1, "position": 4, "age": 24, "statDef": 142},
            {"id": 2, "position": 4, "age": 27, "statDef": 140},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 65},
            {"playerId": 2, "forecast": 75},
        ]

        pool = build_candidate_pool(players, forecasts, 4, set(), set())

        # All >= 140, target advances to 150. Player 1 (142) chosen first.
        self.assertEqual([item.player["id"] for item in pool], [1, 2])
        self.assertEqual(choose_candidate(pool).player["id"], 1)

    def test_universal_trainer_keeps_lowest_squad_tier(self):
        players = [
            {"id": 1, "position": 4, "age": 24, "statDef": 133},
            {"id": 2, "position": 2, "age": 21, "statOvr": 128},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 70, "forecastUniversal": 70},
            {"playerId": 2, "forecast": 60, "forecastUniversal": 60},
        ]

        # Universal trainer (5) sees squad minimum tier is 130 because of player 2.
        # Player 1 (133) is excluded; Player 2 (128) is chosen.
        pool = build_candidate_pool(players, forecasts, 5, set(), set())
        self.assertEqual([item.player["id"] for item in pool], [2])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

    def test_tier_efficiency_override_selects_lower_rated_player_with_high_gain(self):
        # User scenario: Player 1 at 129 with 10% forecast vs Player 2 at 127 with 100% forecast.
        # Deficit is 2 (<= 5) and gain is 90 (>= 35), so Player 2 should be chosen first.
        players = [
            {"id": 1, "position": 1, "age": 25, "statAtt": 129},
            {"id": 2, "position": 1, "age": 20, "statAtt": 127},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 10},
            {"playerId": 2, "forecast": 100},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())
        self.assertEqual([item.player["id"] for item in pool], [2, 1])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

    def test_tier_efficiency_override_rejects_deficit_greater_than_7(self):
        # Player 1 at 119 with 10% vs Player 2 at 111 with 100%.
        # Deficit is 8 (> 7), so Player 2 cannot challenge; Player 1 stays first.
        players = [
            {"id": 1, "position": 1, "age": 25, "statAtt": 119},
            {"id": 2, "position": 1, "age": 20, "statAtt": 111},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 10},
            {"playerId": 2, "forecast": 100},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())
        self.assertEqual([item.player["id"] for item in pool], [1, 2])
        self.assertEqual(choose_candidate(pool).player["id"], 1)

    def test_tier_efficiency_override_rejects_gain_less_than_25(self):
        # Player 1 at 119 with 60% vs Player 2 at 115 with 84% (gain 24 < 25).
        # Player 1 stays first.
        players = [
            {"id": 1, "position": 1, "age": 25, "statAtt": 119},
            {"id": 2, "position": 1, "age": 20, "statAtt": 115},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 60},
            {"playerId": 2, "forecast": 84},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())
        self.assertEqual([item.player["id"] for item in pool], [1, 2])
        self.assertEqual(choose_candidate(pool).player["id"], 1)

        # When Player 2 has 85% (gain 25 >= 25), Player 2 takes priority.
        forecasts[1]["forecast"] = 85
        pool = build_candidate_pool(players, forecasts, 1, set(), set())
        self.assertEqual([item.player["id"] for item in pool], [2, 1])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

    def test_tier_efficiency_override_multi_challenger_ranking(self):
        # Player 1: 119 @ 10%
        # Player 2: 118 @ 80% (beats Player 1: deficit 1, gain 70 >= 25)
        # Player 3: 117 @ 100% (gain over Player 2 is only 20 < 25, so Player 2 stays #1)
        players = [
            {"id": 1, "position": 1, "age": 25, "statAtt": 119},
            {"id": 2, "position": 1, "age": 22, "statAtt": 118},
            {"id": 3, "position": 1, "age": 20, "statAtt": 117},
        ]
        forecasts = [
            {"playerId": 1, "forecast": 10},
            {"playerId": 2, "forecast": 80},
            {"playerId": 3, "forecast": 100},
        ]

        pool = build_candidate_pool(players, forecasts, 1, set(), set())
        # Winner is Player 2. In second round between 3 (117 @ 100) and 1 (119 @ 10),
        # Player 3 beats Player 1 (deficit 2, gain 90 >= 25).
        self.assertEqual([item.player["id"] for item in pool], [2, 3, 1])
        self.assertEqual(choose_candidate(pool).player["id"], 2)

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
        below = {"id": 2, "position": 1, "age": 18, "statAtt": -1}

        no_forecast = build_candidate_pool_result([player], [], 1, set(), set())
        below_floor = build_candidate_pool_result(
            [below], [{"playerId": 2, "forecast": 100}], 1, set(), set()
        )
        unavailable = build_candidate_pool_result(
            [player], [{"playerId": 1, "forecast": 100}], 1, {1}, set()
        )

        self.assertEqual(
            no_forecast.empty_reason,
            "no positive forecast candidate at or above main stat 0",
        )
        self.assertEqual(
            below_floor.empty_reason,
            "all available candidates are below main stat 0",
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
        self.assertEqual(choices, [7] * 20)

    def test_finished_session_uses_server_timestamp(self):
        session = {
            "countdownTimer": {
                "currentTimestamp": 200,
                "finishedTimestamp": 199,
                "isClaimed": False,
            }
        }
        self.assertTrue(session_finished(session, now=100))

    def test_claimed_session_does_not_occupy_a_slot(self):
        session = {
            "trainer": 1,
            "playerId": 101,
            "countdownTimer": {
                "currentTimestamp": 200,
                "finishedTimestamp": 300,
                "isClaimed": True,
            },
        }

        self.assertFalse(session_occupies_slot(session, now=200))

    def test_finished_session_does_not_occupy_a_slot(self):
        session = {
            "trainer": 1,
            "playerId": 101,
            "countdownTimer": {
                "currentTimestamp": 200,
                "finishedTimestamp": 199,
                "isClaimed": False,
            },
        }

        self.assertFalse(session_occupies_slot(session, now=100))

    def test_future_session_occupies_a_slot(self):
        session = {
            "trainer": 1,
            "playerId": 101,
            "countdownTimer": {
                "currentTimestamp": 200,
                "finishedTimestamp": 300,
                "isClaimed": False,
            },
        }

        self.assertTrue(session_occupies_slot(session, now=100))

    def test_session_without_finished_timestamp_is_conservatively_active(self):
        session = {
            "trainer": 1,
            "playerId": 101,
            "countdownTimer": {"isClaimed": False},
        }

        self.assertTrue(session_occupies_slot(session, now=100))

    def test_session_without_valid_identifiers_cannot_occupy_a_slot(self):
        session = {
            "trainer": 1,
            "countdownTimer": {
                "finishedTimestamp": 300,
                "isClaimed": False,
            },
        }

        self.assertFalse(session_occupies_slot(session, now=100))


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


class StickyClaimTrainingApi(FakeTrainingApi):
    async def __call__(self, method, endpoint, payload=None):
        if endpoint.endswith("/claim"):
            self.requests.append((method, endpoint, payload))
            session_id = int(endpoint.split("/")[-2])
            for session in self.sessions:
                if session["id"] == session_id:
                    session["countdownTimer"]["isClaimed"] = True
            return 200, {"progressImprovement": 10}
        return await super().__call__(method, endpoint, payload)


class AlreadyResolvedTrainingApi(FakeTrainingApi):
    async def __call__(self, method, endpoint, payload=None):
        if endpoint.endswith("/claim"):
            self.requests.append((method, endpoint, payload))
            return 409, {}
        return await super().__call__(method, endpoint, payload)


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

    async def test_claimed_session_retained_by_api_does_not_block_refill(self):
        api = StickyClaimTrainingApi()
        logs = []
        manager = AutoTrainingManager(api, "123", "4", logs.append, poll_interval=15)

        await manager.reconcile()

        trainer_one_sessions = [
            session for session in api.sessions if session["trainer"] == 1
        ]
        self.assertEqual(manager.stats["claimed"], 1)
        self.assertEqual(len(trainer_one_sessions), 2)
        self.assertTrue(trainer_one_sessions[0]["countdownTimer"]["isClaimed"])
        self.assertFalse(trainer_one_sessions[1]["countdownTimer"]["isClaimed"])
        self.assertTrue(any("trainer 1 started" in line for line in logs))

    async def test_finished_session_retained_after_409_does_not_block_refill(self):
        api = AlreadyResolvedTrainingApi()
        logs = []
        manager = AutoTrainingManager(api, "123", "4", logs.append, poll_interval=15)

        await manager.reconcile()

        trainer_one_sessions = [
            session for session in api.sessions if session["trainer"] == 1
        ]
        self.assertEqual(manager.stats["claimed"], 0)
        self.assertEqual(len(trainer_one_sessions), 2)
        self.assertTrue(any("already resolved" in line for line in logs))
        self.assertTrue(any("trainer 1 started" in line for line in logs))

    async def test_normal_coach_occupancy_log_is_not_repeated_without_change(self):
        api = FakeTrainingApi()
        logs = []
        manager = AutoTrainingManager(api, "123", "4", logs.append, poll_interval=15)

        await manager.reconcile()
        await manager.reconcile()

        occupancy_logs = [
            line for line in logs if "normal coaches active=" in line
        ]
        self.assertEqual(len(occupancy_logs), 1)
        self.assertIn("active=1,2,3,4", occupancy_logs[0])
        self.assertIn("empty=none", occupancy_logs[0])

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
