"""Forecast-aware automatic training for the OSM conductor.

This module deliberately knows nothing about browser cookies or credentials.
The conductor supplies a small authenticated API callback; logs produced here
contain only game identifiers and action outcomes.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import parse_qs


NORMAL_TRAINING_TIMER_ID = 746
UNIVERSAL_TRAINING_TIMER_ID = 982
MAX_PLAYER_MAIN_STAT = 200
UNIVERSAL_ENTITLEMENT_TIMER_TYPE = 16

TRAINERS = {
    1: ("attacker", 1, "forecast"),
    2: ("midfielder", 2, "forecast"),
    3: ("defender", 3, "forecast"),
    4: ("goalkeeper", 4, "forecast"),
    5: ("universal", None, "forecastUniversal"),
}


@dataclass(frozen=True)
class TrainingProfile:
    normal_timer_id: int = NORMAL_TRAINING_TIMER_ID
    universal_timer_id: int = UNIVERSAL_TRAINING_TIMER_ID
    league_id: str = ""
    team_id: str = ""


@dataclass(frozen=True)
class Candidate:
    player: dict[str, Any]
    forecast: int


class TrainingApiError(RuntimeError):
    def __init__(self, action: str, status: int):
        super().__init__(f"{action} failed (HTTP {status or 'network'})")
        self.action = action
        self.status = status


ApiRequest = Callable[
    [str, str, Optional[dict[str, Any]]],
    Awaitable[tuple[int, Any]],
]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _har_post_fields(request: dict[str, Any]) -> dict[str, Any]:
    post = request.get("postData") or {}
    params = post.get("params") or []
    if params:
        return {
            str(item.get("name")): item.get("value")
            for item in params
            if item.get("name")
        }
    text = post.get("text") or ""
    if not text:
        return {}
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        parsed = parse_qs(text, keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items() if values}


def load_training_profile(path: Optional[str]) -> TrainingProfile:
    """Read only non-secret training settings and context from a HAR."""
    if not path:
        return TrainingProfile()
    har_path = Path(path)
    if not har_path.is_file():
        raise ValueError(f"training HAR profile not found: {har_path}")
    if har_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("training HAR profile is unexpectedly large")
    try:
        har = json.loads(har_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("training HAR profile is not valid JSON") from exc

    normal_ids: list[int] = []
    universal_ids: list[int] = []
    contexts: set[tuple[str, str]] = set()
    path_re = re.compile(r"/leagues/(\d+)/teams/(\d+)/")
    for entry in har.get("log", {}).get("entries", []):
        request = entry.get("request", {}) or {}
        url = request.get("url", "")
        context_match = path_re.search(url)
        if context_match:
            contexts.add(context_match.groups())
        if request.get("method") != "POST" or not url.rstrip("/").endswith("/trainingsessions"):
            continue
        if _safe_int(entry.get("response", {}).get("status")) not in range(200, 300):
            continue
        fields = _har_post_fields(request)
        trainer = _safe_int(fields.get("trainer"))
        timer_id = _safe_int(fields.get("timerGameSettingId"))
        if trainer in (1, 2, 3, 4) and timer_id > 0:
            normal_ids.append(timer_id)
        elif trainer == 5 and timer_id > 0:
            universal_ids.append(timer_id)

    def most_common(values: list[int], fallback: int) -> int:
        if not values:
            return fallback
        return max(set(values), key=lambda item: (values.count(item), item))

    league_id = team_id = ""
    if len(contexts) == 1:
        league_id, team_id = contexts.pop()
    return TrainingProfile(
        normal_timer_id=most_common(normal_ids, NORMAL_TRAINING_TIMER_ID),
        universal_timer_id=most_common(universal_ids, UNIVERSAL_TRAINING_TIMER_ID),
        league_id=league_id,
        team_id=team_id,
    )


def extract_team_context(storage: Any, profile: TrainingProfile) -> tuple[str, str]:
    """Derive league/team from injected storage, with HAR context as fallback."""
    candidates: set[tuple[str, str]] = set()
    key_re = re.compile(r"(?:TeamTactic|TeamTrainings)_(\d+)_(\d+)(?:_\d+)?$")
    for item in getattr(storage, "local_storage", []):
        match = key_re.fullmatch(str(item.get("key", "")))
        if match:
            candidates.add(match.groups())
    if len(candidates) == 1:
        return candidates.pop()

    for cookie in getattr(storage, "cookies", []):
        if cookie.get("name") != "access_token":
            continue
        try:
            token = str(cookie.get("value", ""))
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            value = claims.get("team")
            match = re.fullmatch(r"(\d+)\D+(\d+)", value or "")
            if match:
                return match.groups()
        except (IndexError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return profile.league_id, profile.team_id


def player_main_stat(player: dict[str, Any]) -> int:
    position = _safe_int(player.get("position"))
    if position == 1:
        return _safe_int(player.get("statAtt"))
    if position == 2:
        return _safe_int(player.get("statOvr"))
    return _safe_int(player.get("statDef"))


def listed_player_ids(transfers: list[dict[str, Any]], squad_ids: set[int]) -> set[int]:
    result: set[int] = set()
    for entry in transfers:
        player = entry.get("player") or {}
        player_id = _safe_int(player.get("id"))
        if player_id in squad_ids:
            result.add(player_id)
    return result


def build_candidate_pool(
    players: list[dict[str, Any]],
    forecasts: list[dict[str, Any]],
    trainer: int,
    occupied_player_ids: set[int],
    transfer_listed_ids: set[int],
) -> list[Candidate]:
    role = TRAINERS.get(trainer)
    if not role:
        return []
    _, required_position, forecast_field = role
    forecast_by_id = {
        _safe_int(item.get("playerId")): _safe_int(item.get(forecast_field))
        for item in forecasts
    }
    candidates: list[Candidate] = []
    for player in players:
        player_id = _safe_int(player.get("id"))
        if not player_id or player_id in occupied_player_ids or player_id in transfer_listed_ids:
            continue
        if required_position is not None and _safe_int(player.get("position")) != required_position:
            continue
        if _safe_int(player.get("injuryId")) > 0:
            continue
        if player_main_stat(player) >= MAX_PLAYER_MAIN_STAT:
            continue
        forecast = forecast_by_id.get(player_id, 0)
        if forecast <= 0:
            continue
        candidates.append(Candidate(player=player, forecast=forecast))

    candidates.sort(
        key=lambda item: (
            -item.forecast,
            _safe_int(item.player.get("age"), 99),
            -int(_safe_int(item.player.get("lineup")) > 0),
            -player_main_stat(item.player),
            _safe_int(item.player.get("id")),
        )
    )
    if not candidates:
        return []
    best = candidates[0].forecast
    return [item for item in candidates if item.forecast >= best * 0.85][:5]


def choose_candidate(pool: list[Candidate], rng: Optional[random.Random] = None) -> Optional[Candidate]:
    if not pool:
        return None
    rng = rng or random.SystemRandom()
    weights = [item.forecast ** 2 for item in pool]
    cursor = rng.random() * sum(weights)
    for item, weight in zip(pool, weights):
        cursor -= weight
        if cursor <= 0:
            return item
    return pool[-1]


def session_finished(session: dict[str, Any], now: Optional[int] = None) -> bool:
    timer = session.get("countdownTimer") or {}
    if timer.get("isClaimed"):
        return False
    finished = _safe_int(timer.get("finishedTimestamp"))
    server_now = _safe_int(timer.get("currentTimestamp"))
    compare = max(_safe_int(now, int(time.time())), server_now)
    return bool(finished and finished <= compare)


def has_universal_entitlement(timers: list[dict[str, Any]], now: Optional[int] = None) -> bool:
    current = _safe_int(now, int(time.time()))
    return any(
        _safe_int(timer.get("type")) == UNIVERSAL_ENTITLEMENT_TIMER_TYPE
        and not timer.get("isClaimed")
        and _safe_int(timer.get("finishedTimestamp")) > max(current, _safe_int(timer.get("currentTimestamp")))
        for timer in timers
    )


class AutoTrainingManager:
    """Claim completed sessions and fill empty trainers without purchases."""

    def __init__(
        self,
        api_request: ApiRequest,
        league_id: str,
        team_id: str,
        log: Callable[[str], None],
        normal_timer_id: int = NORMAL_TRAINING_TIMER_ID,
        universal_timer_id: int = UNIVERSAL_TRAINING_TIMER_ID,
        poll_interval: int = 60,
        should_stop: Callable[[], bool] = lambda: False,
        rng: Optional[random.Random] = None,
    ):
        self.api_request = api_request
        self.league_id = str(league_id)
        self.team_id = str(team_id)
        self.log = log
        self.normal_timer_id = int(normal_timer_id)
        self.universal_timer_id = int(universal_timer_id)
        self.poll_interval = max(15, int(poll_interval))
        self.should_stop = should_stop
        self.rng = rng
        self.stats = {"claimed": 0, "started": 0, "errors": 0}
        self._lock = asyncio.Lock()
        self._universal_probe_failed = False
        self._universal_timer_signature: tuple[Any, ...] = ()

    @property
    def base(self) -> str:
        return f"/api/v1/leagues/{self.league_id}/teams/{self.team_id}"

    async def _get(self, suffix: str, empty_404: bool = False) -> Any:
        status, data = await self.api_request("GET", self.base + suffix, None)
        if empty_404 and status == 404:
            return []
        if not 200 <= status < 300:
            raise TrainingApiError("GET " + suffix, status)
        return data

    async def _claim(self, session_id: int) -> bool:
        endpoint = (
            f"/api/v1.1/leagues/{self.league_id}/teams/{self.team_id}"
            f"/trainingsessions/{session_id}/claim"
        )
        status, _ = await self.api_request("PUT", endpoint, None)
        if 200 <= status < 300:
            self.stats["claimed"] += 1
            self.log(f"[TRAINING] claimed completed session {session_id}")
            return True
        if status in (404, 409):
            self.log(f"[TRAINING] session {session_id} was already resolved; refreshing")
            return True
        raise TrainingApiError("claim training", status)

    async def _start(self, trainer: int, candidate: Candidate) -> tuple[bool, int]:
        timer_id = self.universal_timer_id if trainer == 5 else self.normal_timer_id
        payload = {
            "playerId": _safe_int(candidate.player.get("id")),
            "trainer": trainer,
            "timerGameSettingId": timer_id,
        }
        status, _ = await self.api_request("POST", self.base + "/trainingsessions", payload)
        name = candidate.player.get("name") or candidate.player.get("fullName") or payload["playerId"]
        if 200 <= status < 300:
            self.stats["started"] += 1
            self.log(
                f"[TRAINING] trainer {trainer} started {name} "
                f"(player {payload['playerId']}, forecast {candidate.forecast})"
            )
            return True, status
        self.log(
            f"[TRAINING] trainer {trainer} skipped {name}: "
            f"start rejected (HTTP {status or 'network'})"
        )
        return False, status

    @staticmethod
    def _timer_signature(timers: list[dict[str, Any]]) -> tuple[Any, ...]:
        return tuple(sorted(
            (
                _safe_int(timer.get("id")),
                _safe_int(timer.get("type")),
                _safe_int(timer.get("finishedTimestamp")),
                bool(timer.get("isClaimed")),
            )
            for timer in timers
        ))

    async def reconcile(self) -> None:
        async with self._lock:
            sessions = await self._get("/trainingsessions/ongoing", empty_404=True)
            if not isinstance(sessions, list):
                raise TrainingApiError("decode ongoing trainings", 0)

            claimed_any = False
            for session in sessions:
                if session_finished(session):
                    session_id = _safe_int(session.get("id"))
                    if session_id:
                        claimed_any = await self._claim(session_id) or claimed_any
            if claimed_any:
                sessions = await self._get("/trainingsessions/ongoing", empty_404=True)

            players = await self._get("/players")
            forecasts = await self._get("/trainingforecasts")
            transfers = await self._get("/transferplayers/0")
            await self._get("/finances/balanceandsavings")
            timers = await self._get("/timers")
            if not all(isinstance(value, list) for value in (players, forecasts, transfers, timers)):
                raise TrainingApiError("decode training state", 0)

            occupied_trainers = {_safe_int(item.get("trainer")) for item in sessions}
            occupied_players = {_safe_int(item.get("playerId")) for item in sessions}
            squad_ids = {_safe_int(player.get("id")) for player in players}
            listed_ids = listed_player_ids(transfers, squad_ids)

            for trainer in (1, 2, 3, 4):
                if trainer in occupied_trainers:
                    continue
                pool = build_candidate_pool(players, forecasts, trainer, occupied_players, listed_ids)
                candidate = choose_candidate(pool, self.rng)
                if not candidate:
                    self.log(f"[TRAINING] trainer {trainer} empty: no eligible forecast candidate")
                    continue
                started, _ = await self._start(trainer, candidate)
                if started:
                    occupied_trainers.add(trainer)
                    occupied_players.add(_safe_int(candidate.player.get("id")))
                    sessions = await self._get("/trainingsessions/ongoing", empty_404=True)

            signature = self._timer_signature(timers)
            if signature != self._universal_timer_signature:
                self._universal_timer_signature = signature
                self._universal_probe_failed = False
            if 5 not in occupied_trainers and (
                has_universal_entitlement(timers) or not self._universal_probe_failed
            ):
                pool = build_candidate_pool(players, forecasts, 5, occupied_players, listed_ids)
                candidate = choose_candidate(pool, self.rng)
                if candidate:
                    started, status = await self._start(5, candidate)
                    if not started and status in (400, 402, 403, 404, 409, 422):
                        self._universal_probe_failed = True

    async def run(self) -> None:
        failures = 0
        self.log(
            f"[TRAINING] manager enabled for league {self.league_id}, team {self.team_id}; "
            f"poll every {self.poll_interval}s"
        )
        while not self.should_stop():
            try:
                await self.reconcile()
                failures = 0
                delay = self.poll_interval
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.stats["errors"] += 1
                failures += 1
                delay = min(300, self.poll_interval * (2 ** min(failures - 1, 4)))
                status = getattr(exc, "status", 0)
                self.log(
                    f"[TRAINING] reconciliation failed "
                    f"(HTTP {status or 'network'}); retry in {delay}s"
                )
            if self.should_stop():
                break
            await asyncio.sleep(delay)
        self.log("[TRAINING] manager stopped")
