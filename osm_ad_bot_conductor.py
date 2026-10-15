#!/usr/bin/env python3
"""
OSM Ad Watcher Bot — Conductor / Orchestrator Edition
========================================================
1 conductor tab stays open forever, polling the server.
When rate-limit is detected (API or DOM toast), ALL watcher tabs are closed.
Conductor sleeps for the exact cooldown duration (parsed from server or DOM).
When cooldown expires, conductor re-opens watcher tabs and they start watching.
All tabs are muted. Loop repeats forever.
"""
import argparse
import asyncio
import base64
import json
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import async_playwright, BrowserContext, Page

from auto_training import (
    AutoTrainingManager,
    extract_team_context,
    load_training_profile,
)
from auto_free_reward import FreeRewardManager
from storage_loader import StorageLoader

OSM_ORIGIN = "https://en.onlinesoccermanager.com"
OSM_TRAINING = f"{OSM_ORIGIN}/Training"
OSM_API_ORIGIN = "https://web-api.onlinesoccermanager.com"
# Public web client identifier used by the OSM frontend's tokenRefresh flow.
# It is not an account credential; the refresh token remains in the dump.
OSM_CLIENT_ID = "jPs3vVbg4uYnxGoyunSiNf1nIqUJmSFnpqJSVgWrJleu6Ak7Ga"
CLIENT_SECRET_CACHE = (
    Path(__file__).resolve().parent / "transfer-advisor" / "data" / ".client_secret"
)

SELECTORS = {
    "wallet_container": ".wallet-container.bosscoin-wallet",
    "watch_ad_btn": ".product-free",
}

# Regex to parse DOM toast: "You have reached... Come back in 13 minutes..."
DOM_COOLDOWN_RE = re.compile(
    r"Come\s+back\s+in\s+(\d+)\s+minute",
    re.IGNORECASE,
)
SCOUT_RETRY_DELAY_SECONDS = 60
CONDUCTOR_STARTUP_ATTEMPTS = 2
CONDUCTOR_STARTUP_RETRY_DELAY_SECONDS = 10
BROWSER_LAUNCH_TIMEOUT_SECONDS = 45


def _jwt_expiry(token: str) -> int:
    """Read a JWT ``exp`` claim locally without logging or validating secrets."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return int(claims.get("exp", 0))
    except (IndexError, TypeError, ValueError, json.JSONDecodeError):
        return 0


def _token_expiring(token: str, skew_seconds: int = 60) -> bool:
    """Return true when a token is expired or close enough to expiry to race."""
    expiry = _jwt_expiry(token)
    return bool(expiry and expiry <= int(time.time()) + max(0, skew_seconds))


@dataclass
class RateLimitInfo:
    is_limited: bool
    cooldown_seconds: int
    source: str  # 'api' or 'dom'

    def __str__(self) -> str:
        m, s = divmod(self.cooldown_seconds, 60)
        return f"RATE-LIMIT ({self.source}) — next ad in {m}m {s}s"


class ScoutOutcome(str, Enum):
    READY = "ready"
    RATE_LIMITED = "rate_limited"
    AD_UNAVAILABLE = "ad_unavailable"
    NAVIGATION_ERROR = "navigation_error"


class DailyDomMetrics:
    """Persist local DOM observations; never present them as ad-network receipts."""

    def __init__(self, path: Path):
        self.path = path
        self.data = self._read()

    def _read(self) -> dict[str, dict[str, Any]]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {
            str(day): entry
            for day, entry in value.items()
            if isinstance(entry, dict)
        }

    def increment(self, event: str, *, now: Optional[datetime] = None) -> int:
        timestamp = now or datetime.now()
        day = timestamp.date().isoformat()
        entry = self.data.setdefault(day, {})
        current = int(entry.get(event, 0)) + 1
        entry[event] = current
        entry["updated_at"] = timestamp.isoformat(timespec="seconds")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".new")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
        return current


class OSMConductorBot:
    def __init__(self, dump_dir: str, headless: bool = False,
                 watcher_tabs: int = 1, poll_interval: int = 30,
                 ad_duration: int = 30, log_file: Optional[str] = None,
                 auto_training: bool = False,
                 training_poll_interval: int = 60,
                 training_har_profile: Optional[str] = None,
                 normal_training_timer_id: Optional[int] = None,
                 universal_training_timer_id: Optional[int] = None,
                 auto_free_reward: bool = True,
                 free_reward_poll_interval: int = 1800):
        self.dump_dir = dump_dir
        self.headless = headless
        self.watcher_tabs = min(watcher_tabs, 9)
        self.poll_interval = poll_interval
        # Minimum 2 min ad wait regardless of flag
        self.ad_duration = max(ad_duration, 120)
        self.log_file = log_file

        self.storage = StorageLoader(dump_dir)
        self.auto_training = auto_training
        self.training_poll_interval = max(15, training_poll_interval)
        self.training_profile = load_training_profile(training_har_profile)
        self.normal_training_timer_id = (
            normal_training_timer_id or self.training_profile.normal_timer_id
        )
        self.universal_training_timer_id = (
            universal_training_timer_id or self.training_profile.universal_timer_id
        )
        self.training_league_id, self.training_team_id = extract_team_context(
            self.storage, self.training_profile
        )
        self.training_manager: Optional[AutoTrainingManager] = None
        self._training_task: Optional[asyncio.Task] = None
        self.auto_free_reward = auto_free_reward
        self.free_reward_poll_interval = max(60, free_reward_poll_interval)
        self.free_reward_manager: Optional[FreeRewardManager] = None
        self._free_reward_task: Optional[asyncio.Task] = None
        # Training and rate-limit checks can hit the API at the same time.
        # Serialize refresh-token rotation so only one request consumes the
        # current refresh token and updates the browser cookies.
        self._token_refresh_lock: Optional[asyncio.Lock] = None
        self._token_refresh_warning_active = False
        # Account id derived from the loaded dump's token — never hardcoded.
        self.user_id = self._extract_user_id()
        self.stats = {"dom_rewards_detected": 0, "errors": 0, "cycles": 0}
        self.daily_metrics = (
            DailyDomMetrics(Path(log_file).resolve().parent / "daily-dom-metrics.json")
            if log_file
            else None
        )
        self._shutdown = False

        self.context: Optional[BrowserContext] = None
        self.conductor_page: Optional[Page] = None
        self.watcher_pages: list[Page] = []
        self._watcher_tasks: list[asyncio.Task] = []

        if log_file:
            self._log_fp = open(log_file, "a", buffering=1)
            sys.stdout = self._log_fp
            sys.stderr = self._log_fp

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        # stdout is already redirected to the log file in __init__ when --log is
        # set, so a single print() writes there; writing again would duplicate
        # every line (the "double log" you saw).
        print(f"[{ts}] {msg}", flush=True)

    def _should_stop(self) -> bool:
        return self._shutdown

    def _record_daily_metric(self, event: str) -> None:
        metrics = getattr(self, "daily_metrics", None)
        if not metrics:
            return
        try:
            metrics.increment(event)
        except OSError as exc:
            if not getattr(self, "_daily_metrics_warning_active", False):
                self._log(f"[METRICS] unable to persist local metrics: {exc}")
                self._daily_metrics_warning_active = True

    def _record_dom_reward_detected(self, prefix: str, source: str) -> None:
        self.stats["dom_rewards_detected"] += 1
        self._record_daily_metric("dom_reward_detected")
        self._log(
            f"{prefix} ✅ DOM REWARD DETECTED ({source}; local count: "
            f"{self.stats['dom_rewards_detected']}, not an ad-network receipt)"
        )

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------
    async def _create_context(self, playwright):
        self._log("Launching browser...")
        try:
            browser = await asyncio.wait_for(
                playwright.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--mute-audio",
                        "--no-sandbox",
                        # Kill the software-WebGL (swiftshader) GPU process that was
                        # burning ~4 cores: with no real GPU in headless, OSM's
                        # WebGL/canvas was being rasterised on CPU. We fake ad
                        # completion, so we don't need any of it rendered.
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-gpu-compositing",
                        "--disable-accelerated-2d-canvas",
                        "--disable-dev-shm-usage",
                        "--disable-webgl",
                        "--disable-webgl2",
                        "--disable-3d-apis",
                    ],
                ),
                timeout=BROWSER_LAUNCH_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            self._record_daily_metric("browser_launch_timeout")
            raise RuntimeError(
                "Playwright browser launch exceeded "
                f"{BROWSER_LAUNCH_TIMEOUT_SECONDS}s; letting launchd restart cleanly"
            ) from exc
        self._log(f"Browser launched (headless={self.headless}, watchers={self.watcher_tabs})")
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            locale="en-GB",
        )
        # Monkey-patch StoreModal to prevent null.hasOwnProperty crash on setUpClaimDailyReward
        # when no daily reward timer is active in appViewModel.bossCoinWalletPartial().
        await ctx.add_init_script(
            script="""
            (() => {
                let _StoreModal = window.StoreModal;
                const patch = (SM) => {
                    if (SM && SM.prototype && !SM.prototype._patchedSetUpClaimDailyReward) {
                        SM.prototype._patchedSetUpClaimDailyReward = true;
                        SM.prototype.setUpClaimDailyReward = function() {
                            try {
                                const e = (window.appViewModel && window.appViewModel.bossCoinWalletPartial)
                                    ? window.appViewModel.bossCoinWalletPartial()
                                    : null;
                                if (e && e.countdownTimer) {
                                    try { this.dailyRewardClaimTimer(new CountdownTimerPartial(e.countdownTimer)); } catch (_) {}
                                }
                                if (e && e.unclaimedCoins) {
                                    try { this.dailyRewardCounter(new Counter(e.unclaimedCoins)); } catch (_) {}
                                }
                            } catch (err) {
                                console.warn('[Patch] setUpClaimDailyReward suppressed error:', err);
                            }
                        };
                    }
                };
                Object.defineProperty(window, 'StoreModal', {
                    configurable: true,
                    enumerable: true,
                    get: () => _StoreModal,
                    set: (val) => {
                        _StoreModal = val;
                        patch(val);
                    }
                });
                const interval = setInterval(() => {
                    if (window.StoreModal) {
                        patch(window.StoreModal);
                    }
                }, 100);
                setTimeout(() => clearInterval(interval), 60000);
            })();
            """
        )
        # NOTE: do NOT block media/image/font here. The rewarded ad runs in a
        # googlesyndication safeframe whose resources must load for the reward
        # to fire — blocking them breaks the reward entirely. Idle CPU is kept
        # low by --disable-gpu (no swiftshader) + parking the conductor; and
        # since the reward lands in a few seconds, watcher tabs close quickly.
        return ctx

    async def _inject_storage(self):
        self._log("Injecting cookies & storage...")
        token = self._get_access_token()
        if not token or _token_expiring(token):
            refreshed = await self._refresh_access_token(force=True)
            if refreshed:
                self._log("Pre-emptively refreshed expired access token before storage injection")
        await self.storage.inject(self.context)
        self._log("Storage injected")

    async def _open_conductor(self):
        """Open the Training page, retrying one transient readiness failure.

        The OSM SPA can return its shell before ``#page-content`` becomes
        visible.  A single bounded retry avoids handing this short startup
        race to launchd as a full-process crash.  A login redirect remains a
        terminal session error and is never retried.
        """
        for attempt in range(1, CONDUCTOR_STARTUP_ATTEMPTS + 1):
            self.conductor_page = await self.context.new_page()
            try:
                await self.conductor_page.goto(
                    OSM_TRAINING, wait_until="domcontentloaded", timeout=60000
                )
                await self.conductor_page.wait_for_selector("#page-content", timeout=30000)
                await asyncio.sleep(3)
                # Accept the consent dialog once — cookies are domain-wide so later tabs stay clean
                await self._dismiss_consent(self.conductor_page, "[CONDUCTOR]")
                self._log("Conductor tab ready")
                return
            except Exception as exc:
                page_url = self.conductor_page.url
                if "login" in page_url.lower():
                    raise RuntimeError(
                        "StorageDump session is no longer valid after logout/login; "
                        "export a fresh post-login StorageDump and run again"
                    ) from exc

                if attempt == CONDUCTOR_STARTUP_ATTEMPTS:
                    self._record_daily_metric("conductor_startup_failure")
                    raise RuntimeError(
                        "Training page did not become ready after "
                        f"{CONDUCTOR_STARTUP_ATTEMPTS} attempts "
                        f"(last URL: {page_url}; {type(exc).__name__})"
                    ) from exc

                self._record_daily_metric("conductor_startup_retry")
                self._log(
                    "[CONDUCTOR] Training page was not ready "
                    f"(attempt {attempt}/{CONDUCTOR_STARTUP_ATTEMPTS}; "
                    f"URL: {page_url}; {type(exc).__name__}); retrying once in "
                    f"{CONDUCTOR_STARTUP_RETRY_DELAY_SECONDS}s"
                )
                await self._close_page_bounded(
                    self.conductor_page, "startup retry page"
                )
                self.conductor_page = None
                await asyncio.sleep(CONDUCTOR_STARTUP_RETRY_DELAY_SECONDS)

    async def _park_conductor(self):
        """During long idle waits, navigate the conductor to about:blank so the
        OSM SPA stops running its render loop / ad refreshes / timers. Drops the
        single idle tab from steady CPU to ~0 while we just sleep.
        """
        try:
            page = self.conductor_page
            if page and not page.is_closed() and page.url != "about:blank":
                await page.goto("about:blank")
                self._log("[CONDUCTOR] parked (about:blank) — idle, no CPU")
        except Exception as e:
            self._log(f"[CONDUCTOR] park error: {e}")

    async def _ensure_conductor_awake(self):
        """Bring the conductor back onto OSM before a watch phase so the DOM
        toast observer works and the frontend keeps the access_token fresh."""
        try:
            if not self.conductor_page or self.conductor_page.is_closed():
                self.conductor_page = await self.context.new_page()
            if not self.conductor_page.url.startswith(OSM_ORIGIN):
                await self.conductor_page.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
                await self.conductor_page.wait_for_selector("#page-content", timeout=30000)
                await asyncio.sleep(2)
                await self._dismiss_consent(self.conductor_page, "[CONDUCTOR]")
                await self._start_mutation_observer()
                self._log("[CONDUCTOR] awake on OSM")
        except Exception as e:
            self._log(f"[CONDUCTOR] wake error: {e}")

    async def _start_mutation_observer(self, timeout: float = 5):
        """Install a JS mutation observer that watches for toast/alert nodes
        containing the rate-limit text and pushes cooldown minutes to a
        window.__osm_toast_queue array so we can read it from Python."""
        page = self.conductor_page
        if not page or page.is_closed():
            return False
        try:
            installed = await asyncio.wait_for(page.evaluate("""
            () => {
                if (!document.body) return false;
                const existing = window.__osm_toast_observer;
                if (existing && typeof existing.disconnect === 'function') {
                    existing.disconnect();
                }
                if (!Array.isArray(window.__osm_toast_queue)) {
                    window.__osm_toast_queue = [];
                }
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        mutation.addedNodes.forEach((node) => {
                            if (node.nodeType === 1) { // Element
                                const text = node.innerText || node.textContent || '';
                                const match = text.match(/Come\\s+back\\s+in\\s+(\\d+)\\s+minute/i);
                                if (match) {
                                    window.__osm_toast_queue.push(parseInt(match[1], 10));
                                }
                            }
                        });
                    });
                });
                window.__osm_toast_observer = observer;
                window.__osm_toast_observer_body = document.body;
                observer.observe(document.body, { childList: true, subtree: true });
                return true;
            }
            """), timeout=timeout)
        except Exception as exc:
            if not getattr(self, "_dom_observer_warning_active", False):
                self._log(f"  [CHECK] DOM toast observer unavailable: {exc}")
                self._dom_observer_warning_active = True
            return False
        if installed:
            self._dom_observer_warning_active = False
            self._log("DOM toast observer installed")
        return bool(installed)

    async def _read_dom_cooldown(self, timeout: float = 5) -> Optional[int]:
        """Read newly-seen cooldown minutes; self-heal after page reloads.

        The toast queue and observer are page-scoped JavaScript globals. OSM can
        replace the document while refreshing its session, so a missing queue is
        an expected transient state and must never terminate the conductor.
        """
        page = self.conductor_page
        if not page or page.is_closed():
            await self._ensure_conductor_awake()
            page = self.conductor_page
            if not page or page.is_closed():
                return None

        try:
            result = await asyncio.wait_for(page.evaluate("""
                () => {
                    const q = window.__osm_toast_queue;
                    const observer = window.__osm_toast_observer;
                    const observerBody = window.__osm_toast_observer_body;
                    if (!Array.isArray(q) || !observer ||
                            typeof observer.disconnect !== 'function' ||
                            observerBody !== document.body) {
                        return { ready: false, value: null };
                    }
                    if (q.length === 0) {
                        return { ready: true, value: null };
                    }
                    const values = q.map(Number).filter(Number.isFinite);
                    q.length = 0;
                    return {
                        ready: true,
                        value: values.length ? Math.max(...values) : null,
                    };
                }
            """), timeout=timeout)
        except asyncio.TimeoutError:
            if not getattr(self, "_dom_check_warning_active", False):
                self._log(
                    f"  [CHECK] DOM cooldown check timed out after {timeout:g}s; "
                    "continuing with API detection"
                )
                self._dom_check_warning_active = True
            return None
        except Exception as exc:
            if not getattr(self, "_dom_check_warning_active", False):
                self._log(f"  [CHECK] DOM cooldown check interrupted — self-healing: {exc}")
                self._dom_check_warning_active = True
            try:
                await self._ensure_conductor_awake()
                await self._start_mutation_observer()
            except Exception:
                pass
            return None

        if not isinstance(result, dict) or not result.get("ready"):
            if await self._start_mutation_observer():
                self._log("  [CHECK] DOM toast observer restored after page reload")
            return None

        self._dom_check_warning_active = False
        value = result.get("value")
        return value if isinstance(value, int) and value > 0 else None

    # ------------------------------------------------------------------
    # Auth / API helpers
    # ------------------------------------------------------------------
    def _extract_user_id(self) -> str:
        """Derive the logged-in account id from the dump's token (JWT `sub`),
        so no account id is ever hardcoded. The id is stable even when the
        token itself is expired."""
        def claim(token: str, *keys) -> str:
            try:
                payload = token.split(".")[1]
                payload += "=" * (-len(payload) % 4)
                data = json.loads(base64.urlsafe_b64decode(payload))
                for k in keys:
                    if data.get(k):
                        return str(data[k])
            except Exception:
                pass
            return ""
        sources = (
            ("access_token", ("sub",
                "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier")),
            ("forum_token", ("id",)),
        )
        for name, keys in sources:
            for c in self.storage.cookies:
                if c["name"] == name:
                    uid = claim(c["value"], *keys)
                    if uid:
                        return uid
        return ""

    def _get_access_token(self) -> Optional[str]:
        for c in self.storage.cookies:
            if c["name"] == "access_token":
                return c["value"]
        return None

    def _get_refresh_token(self) -> Optional[str]:
        for c in self.storage.cookies:
            if c["name"] == "refresh_token":
                return c["value"]
        return None

    async def _get_live_refresh_token(self) -> Optional[str]:
        if self.context:
            try:
                for c in await self.context.cookies(OSM_ORIGIN):
                    if c["name"] == "refresh_token" and c.get("value"):
                        return c["value"]
            except Exception:
                pass
        return self._get_refresh_token()

    async def _replace_runtime_cookie(self, name: str, value: str) -> None:
        found = False
        for cookie in self.storage.cookies:
            if cookie["name"] == name:
                cookie["value"] = value
                found = True
                break
        if not found:
            self.storage.cookies.append({
                "name": name, "value": value,
                "domain": "en.onlinesoccermanager.com", "path": "/",
                "httpOnly": False, "secure": True, "sameSite": "None",
            })
        if self.context:
            await self.context.add_cookies([{
                "name": name, "value": value,
                "domain": "en.onlinesoccermanager.com", "path": "/",
                "httpOnly": False, "secure": True, "sameSite": "None",
            }])

    async def _get_live_access_token(self) -> Optional[str]:
        """Read the access_token cookie the OSM frontend keeps auto-refreshed
        in the live browser context. Lets API checks work WITHOUT
        OSM_CLIENT_ID / OSM_CLIENT_SECRET (the page handles the refresh)."""
        if not self.context:
            return None
        try:
            for c in await self.context.cookies(OSM_ORIGIN):
                if c["name"] == "access_token" and c.get("value"):
                    return c["value"]
        except Exception:
            pass
        return None

    @staticmethod
    def _cached_client_secret() -> str:
        """Read the existing ignored refresh secret without ever logging it."""
        value = os.environ.get("OSM_CLIENT_SECRET", "").strip()
        if value:
            return value
        try:
            return CLIENT_SECRET_CACHE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    async def _refresh_access_token(self, force: bool = False) -> Optional[str]:
        import httpx

        observed_access = await self._get_live_access_token()
        refresh = await self._get_live_refresh_token()
        if not refresh:
            return None
        client_id = os.environ.get("OSM_CLIENT_ID", "").strip() or OSM_CLIENT_ID
        client_secret = self._cached_client_secret()
        if not client_id or not client_secret:
            if not self._token_refresh_warning_active:
                self._log("! OSM_CLIENT_ID / OSM_CLIENT_SECRET not set — API rate-limit "
                          "check disabled, falling back to DOM detection (this is fine)")
                self._token_refresh_warning_active = True
            return None

        if self._token_refresh_lock is None:
            self._token_refresh_lock = asyncio.Lock()
        async with self._token_refresh_lock:
            # Another concurrent API call may already have rotated the token
            # while this call was waiting for the lock.
            current = await self._get_live_access_token()
            if current and not _token_expiring(current) and (
                not force or current != observed_access
            ):
                return current
            refresh = await self._get_live_refresh_token()
            if not refresh:
                return None
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{OSM_API_ORIGIN}/api/tokenRefresh",
                        data={
                            "grant_type": "refresh_token",
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "refresh_token": refresh,
                        },
                        headers={
                            "Accept": "application/json; charset=utf-8",
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "AppVersion": "3.251.0",
                            "PlatformId": "13",
                            "Origin": OSM_ORIGIN,
                            "Referer": f"{OSM_ORIGIN}/",
                        },
                        timeout=10,
                    )
                    data = resp.json()
                    new_token = data.get("access_token")
                    if new_token:
                        await self._replace_runtime_cookie("access_token", new_token)
                        rotated_refresh = data.get("refresh_token")
                        if rotated_refresh:
                            await self._replace_runtime_cookie("refresh_token", rotated_refresh)
                        self._token_refresh_warning_active = False
                        return new_token
                    self._log(f"Token refresh failed (HTTP {resp.status_code})")
                    return None
            except Exception as e:
                self._log(f"Token refresh error: {e}")
                return None

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> tuple[int, Any]:
        import httpx
        # Prefer the live browser cookie, but do not send an expired short-lived
        # token. The refresh token is rotated in the browser context and kept
        # only in memory.
        token = await self._get_live_access_token()
        if token and _token_expiring(token):
            token = await self._refresh_access_token() or token
        if not token:
            for c in self.storage.cookies:
                if c["name"] == "access_token":
                    token = c["value"]
                    break
        if token and _token_expiring(token):
            token = await self._refresh_access_token() or token
        if not token:
            token = await self._refresh_access_token(force=True)
        if not token:
            return 0, {"error": "No token"}
        url = f"{OSM_API_ORIGIN}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json; charset=utf-8",
            "Content-Type": "application/json; charset=utf-8",
            "AppVersion": "3.251.0", "PlatformId": "13",
            "Origin": OSM_ORIGIN,
            "Referer": f"{OSM_ORIGIN}/",
        }
        try:
            async with httpx.AsyncClient() as client:
                if payload is None:
                    request_body = {}
                elif endpoint.rstrip("/").endswith(
                    ("/trainingsessions", "/bosscoinstorepurchase/process", "/consumereward")
                ):
                    request_body = {"data": payload}
                    headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
                else:
                    request_body = {"json": payload}
                resp = await client.request(
                    method.upper(), url, headers=headers, timeout=15, **request_body
                )
                if resp.status_code in (401, 403):
                    # The frontend may have rotated the cookie since the first
                    # read. If it did not, try the existing explicit refresh
                    # fallback. Neither path logs or persists token values.
                    live_token = await self._get_live_access_token()
                    if not live_token or live_token == token or _token_expiring(live_token):
                        live_token = await self._refresh_access_token(force=True)
                    if not live_token and self.context:
                        await self._ensure_conductor_awake()
                        live_token = await self._get_live_access_token()
                    if live_token:
                        headers["Authorization"] = f"Bearer {live_token}"
                        resp = await client.request(
                            method.upper(), url, headers=headers, timeout=15, **request_body
                        )
                if not resp.content:
                    data: Any = {}
                else:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"error": "Invalid JSON"}
                return resp.status_code, data
        except httpx.HTTPError:
            return 0, {"error": "Network request failed"}

    async def _api_get(self, endpoint: str) -> dict:
        status, data = await self._api_request("GET", endpoint)
        if 200 <= status < 300 and isinstance(data, dict):
            return data
        if isinstance(data, dict) and data.get("error"):
            return {"error": data["error"], "status": status}
        return {"error": "API request failed", "status": status}

    # ------------------------------------------------------------------
    # Rate-limit detection (dual source)
    # ------------------------------------------------------------------
    async def _check_api_rate_limit(self) -> Optional[RateLimitInfo]:
        body = await self._api_get("/api/v1/user/caps/actions/Shop/0")
        if "error" in body:
            # API check unavailable (no creds / no live token). Say it once —
            # DOM toast detection still catches rate-limits every cycle.
            if not getattr(self, "_warned_api_skip", False):
                self._log("  [CHECK] API rate-limit check unavailable — relying on DOM detection")
                self._warned_api_skip = True
            return None
        is_limited = body.get("isCapReached", False) and not body.get("isClaimable", False)
        ts = body.get("timestampUntilUnreached")
        current = body.get("currentCount", 0)
        threshold = body.get("threshold", 10)
        if is_limited and ts:
            secs = max(0, ts - int(time.time()))
            self._log(f"  [CHECK] ⛔ RATE-LIMITED ({current}/{threshold}) — next ad in {self._fmt_cooldown(secs)}")
            return RateLimitInfo(True, secs, "api")
        self._log(f"  [CHECK] ✅ OK ({current}/{threshold}) — no limit")
        return None

    async def _check_dom_rate_limit(self) -> Optional[RateLimitInfo]:
        minutes = await self._read_dom_cooldown()
        if minutes is not None:
            self._log(f"  [CHECK] ⛔ DOM toast: next ad in {minutes}m")
            return RateLimitInfo(True, minutes * 60, "dom")
        return None

    def _fmt_cooldown(self, seconds: int) -> str:
        m, s = divmod(seconds, 60)
        if m >= 60:
            h, m = divmod(m, 60)
            return f"{h}h {m}m"
        return f"{m}m {s}s"

    async def _wait_rate_limit(self, info: RateLimitInfo):
        self._record_daily_metric("rate_limit_cooldown")
        self._log(f"⛔ RATE-LIMIT ({info.source}): Waiting {self._fmt_cooldown(info.cooldown_seconds)}")
        # Close all watcher tabs immediately
        await self._close_all_watchers()
        # Park the conductor too — nothing to watch during cooldown, so idle at ~0 CPU
        await self._park_conductor()
        # Sleep in chunks, log progress every minute or when < 2 min
        remaining = info.cooldown_seconds
        last_log = remaining
        while remaining > 0 and not self._should_stop():
            chunk = min(10, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk
            # Log every 60 seconds or final 2 minutes
            if remaining <= 120 or (last_log - remaining) >= 60:
                self._log(f"  ... ⏳ {self._fmt_cooldown(remaining)} remaining")
                last_log = remaining
        if not self._should_stop():
            self._log("✅ Rate-limit cooldown expired!")
            # After rate-limit expires, wait additional 5 minutes before retrying
            self._log("[CYCLE] Waiting extra 5 min before next scout check...")
            extra_wait = 300
            while extra_wait > 0 and not self._should_stop():
                chunk = min(30, extra_wait)
                await asyncio.sleep(chunk)
                extra_wait -= chunk
                if extra_wait > 0 and extra_wait % 60 == 0:
                    m = extra_wait // 60
                    self._log(f"  ... {m} min until next check")
            if not self._should_stop():
                self._log("✅ Extra 5 min wait done. Ready for next cycle!")

    # ------------------------------------------------------------------
    # Watcher tab lifecycle
    # ------------------------------------------------------------------
    async def _close_page_bounded(
        self, page: Optional[Page], label: str, timeout: float = 5.0
    ) -> bool:
        """Close a page without allowing an unresponsive renderer to stall.

        ``asyncio.wait_for(page.close())`` cancels the underlying close when
        the timeout expires. Playwright can then retain the half-closed page
        in the shared context, which eventually starves later navigations.
        Shield the close task instead: callers stay bounded while the browser
        is allowed to finish cleaning up in the background.
        """
        if not page or page.is_closed():
            return True
        close_task = asyncio.create_task(page.close())
        pending_closes = getattr(self, "_pending_page_close_tasks", None)
        if pending_closes is None:
            pending_closes = set()
            self._pending_page_close_tasks = pending_closes
        pending_closes.add(close_task)

        def _discard_finished_close(task: asyncio.Task) -> None:
            pending_closes.discard(task)
            if task.cancelled():
                return
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                return
            if exc:
                self._log(f"[WATCHERS]   {label} background close error: {exc}")

        close_task.add_done_callback(_discard_finished_close)
        try:
            await asyncio.wait_for(asyncio.shield(close_task), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            self._log(
                f"[WATCHERS]   {label} close timeout after {timeout:g}s; "
                "cleanup continues in background"
            )
        except Exception as exc:
            self._log(f"[WATCHERS]   {label} close error: {exc}")
        return False

    async def _open_watchers(self, page_create_timeout: float = 15.0):
        self._log("[WATCHERS] Opening {} watcher tabs...".format(self.watcher_tabs))
        prepared: list[tuple[int, Page]] = []
        opened = 0
        for i in range(self.watcher_tabs):
            page = None
            try:
                page = await asyncio.wait_for(
                    self.context.new_page(), timeout=page_create_timeout
                )
                await page.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector("#page-content", timeout=30000)
                await asyncio.sleep(2)
                self.watcher_pages.append(page)
                prepared.append((i, page))
                self._log("[WATCHERS]   Tab {} prepared".format(i))
            except Exception as e:
                self._record_daily_metric("watcher_setup_failure")
                self._log("[WATCHERS]   Tab {} failed: {}".format(i, e))
                if page in self.watcher_pages:
                    self.watcher_pages.remove(page)
                if await self._close_page_bounded(page, f"Tab {i} failed page"):
                    self._log("[WATCHERS]   Tab {} failed page closed".format(i))

        for i, page in prepared:
            try:
                task = asyncio.create_task(self._watcher_loop(page, i))
                self._watcher_tasks.append(task)
                opened += 1
                self._log("[WATCHERS]   Tab {} started".format(i))
            except Exception as exc:
                self._log("[WATCHERS]   Tab {} task failed: {}".format(i, exc))
                if page in self.watcher_pages:
                    self.watcher_pages.remove(page)
                await self._close_page_bounded(page, f"Tab {i} task failure")
        self._log("[WATCHERS] {}/{} tabs ready".format(opened, self.watcher_tabs))

    async def _close_all_watchers(self):
        self._log("[WATCHERS] Closing all watcher tabs...")
        pages_before = len(self.context.pages) if self.context else 0
        # Cancel background loops
        tasks = list(self._watcher_tasks)
        cancelled = 0
        for t in tasks:
            if not t.done():
                t.cancel()
                cancelled += 1
        self._log("[WATCHERS]   {} loop(s) cancelled".format(cancelled))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._watcher_tasks.clear()

        closed = 0
        for page in list(self.watcher_pages):
            if not page.is_closed() and await self._close_page_bounded(
                page, "tracked watcher"
            ):
                closed += 1
        self.watcher_pages.clear()

        # Defensive ownership sweep: failed watcher setup paths are not allowed
        # to leave untracked pages in the shared browser context.
        stray_closed = 0
        if self.context:
            for page in list(self.context.pages):
                if page is self.conductor_page:
                    continue
                if not page.is_closed() and await self._close_page_bounded(
                    page, "stray page"
                ):
                    stray_closed += 1

        pages_after = len(self.context.pages) if self.context else 0
        self._log(
            "[WATCHERS]   page cleanup: pages before={}, tracked_closed={}, "
            "stray_closed={}, after={}".format(
                pages_before, closed, stray_closed, pages_after
            )
        )
        expected_after = (
            1
            if self.conductor_page
            and not self.conductor_page.is_closed()
            else 0
        )
        if pages_after > expected_after:
            self._log(
                "[WATCHERS]   ! page cleanup incomplete: expected at most {}, got {}".format(
                    expected_after, pages_after
                )
            )
        self._log("[WATCHERS] All watchers confirmed closed")

    # ------------------------------------------------------------------
    # Consent dialog (Funding Choices / GDPR)
    # ------------------------------------------------------------------
    async def _dismiss_consent(self, page: Page, prefix: str = "") -> bool:
        """The Funding Choices CMP renders a `.fc-consent-root` whose
        `.fc-dialog-overlay` intercepts ALL pointer events, so every click
        times out. Accept it via the 'Consent' CTA; if that fails, rip the
        overlay/root out of the DOM so clicks go through. Returns True if a
        dialog was found."""
        try:
            root = await page.query_selector(".fc-consent-root")
            if not root:
                return False
            self._log(f"{prefix}   [CONSENT] dialog detected, dismissing...")
            for sel in (".fc-cta-consent", "button.fc-cta-consent",
                        ".fc-confirm-choices", "[aria-label='Consent']"):
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click(timeout=5000)
                        await page.wait_for_selector(
                            ".fc-consent-root", state="detached", timeout=8000)
                        self._log(f"{prefix}   [CONSENT] accepted via {sel}")
                        return True
                except Exception:
                    continue
            # Fallback: forcibly remove overlay + root so clicks aren't blocked
            await page.evaluate("""
                () => {
                    document.querySelectorAll('.fc-consent-root, .fc-dialog-overlay')
                        .forEach(el => el.remove());
                }
            """)
            self._log(f"{prefix}   [CONSENT] force-removed overlay from DOM")
            return True
        except Exception as e:
            msg = str(e)
            # Benign: page was navigating/closing while we probed — not an error.
            if ("Execution context was destroyed" in msg
                    or "navigation" in msg.lower() or "closed" in msg.lower()):
                return False
            self._log(f"{prefix}   [CONSENT] dismiss error: {e}")
            return False

    async def _clear_overlays(self, page: Page, prefix: str = "") -> bool:
        """Remove the click-blocking overlay LAYERS (consent root + any
        `.modal-backdrop`, e.g. from a generic OSM popup stacked on the shop)
        by stripping just those divs from the DOM. We never click a modal's
        buttons — those can trigger navigation — so a real (trusted) click can
        then land on the target. Modal dialogs themselves are left intact."""
        try:
            removed = await page.evaluate("""
                () => {
                    let n = 0;
                    document.querySelectorAll('.fc-consent-root, .fc-dialog-overlay, .modal-backdrop')
                        .forEach(el => { try { el.remove(); n++; } catch(e){} });
                    return n;
                }
            """)
            if removed:
                self._log(f"{prefix}   [OVERLAY] cleared {removed} blocking layer(s)")
            return removed > 0
        except Exception:
            return False

    async def _robust_click(self, page: Page, selector: str,
                            prefix: str = "", label: str = "element",
                            timeout: int = 8000) -> bool:
        """Click an element even when a modal backdrop / consent overlay sits on
        top. Tries a real click; on failure clears overlays + generic modals and
        retries; last resort dispatches the DOM click directly (ignores pointer
        interception). Re-queries each attempt so a stale handle can't break it."""
        async def fresh():
            # wait_for_selector (not bare query) so a briefly detached / late
            # re-rendering element isn't seen as missing.
            try:
                return await page.wait_for_selector(selector, timeout=6000, state="attached")
            except Exception:
                return None
        # 1) real click
        el = await fresh()
        if el:
            try:
                await el.click(timeout=timeout)
                return True
            except Exception:
                pass
        # 2) strip blocking overlays/backdrops (no button clicks → no navigation)
        #    then retry a REAL, trusted click — important for rewarded video,
        #    which needs a genuine user gesture to start.
        await self._clear_overlays(page, prefix)
        el = await fresh()
        if el:
            try:
                await el.click(timeout=timeout)
                return True
            except Exception:
                pass
        # 3) last resort: dispatch the DOM click directly. Fine for non-gesture
        #    actions (e.g. opening the shop); may not start a gated video, but
        #    better than giving up.
        el = await fresh()
        if el:
            try:
                await el.evaluate("e => e.click()")
                self._log(f"{prefix}   [{label}] clicked via JS dispatch")
                return True
            except Exception as e:
                self._log(f"{prefix}   ! {label} click failed: {e}")
        return False

    # ------------------------------------------------------------------
    # Single ad watch (same as before but isolated per tab)
    # ------------------------------------------------------------------
    async def _watcher_loop(self, page: Page, tab_id: int):
        prefix = f"[W{tab_id}]"
        self._log(f"{prefix} ▶ Watcher thread started")
        while not self._should_stop():
            try:
                if page.is_closed():
                    self._log(f"{prefix} ▶ Tab already closed, exiting")
                    return
                ok = await self._watch_single_ad_bounded(page, tab_id)
                # Single-ad policy: close tab after every attempt
                self._log(f"{prefix} ▶ Closing tab...")
                if await self._close_page_bounded(page, f"{prefix} tab"):
                    self._log(f"{prefix} ▶ Tab closed")
                # Remove from tracking list
                try:
                    if page in self.watcher_pages:
                        self.watcher_pages.remove(page)
                        self._log(f"{prefix} ▶ Removed from active list. Remaining: {len(self.watcher_pages)}")
                except ValueError:
                    pass
                if not ok:
                    self._log(f"{prefix} ▶ No reward, pausing 5s before retry...")
                    await asyncio.sleep(5)
                else:
                    self._log(f"{prefix} ▶ Success, pausing 3s...")
                    await asyncio.sleep(3)
            except asyncio.CancelledError:
                self._log(f"{prefix} ▶ Cancelled by conductor, exiting")
                return
            except Exception as e:
                if "closed" in str(e).lower():
                    self._log(f"{prefix} ▶ Browser/connection closed, exiting")
                    return
                self._log(f"{prefix} ! Error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(10)

    async def _watch_single_ad_bounded(
        self, page: Page, tab_id: int, timeout: Optional[float] = None
    ) -> bool:
        limit = timeout if timeout is not None else max(180, self.ad_duration + 90)
        try:
            return await asyncio.wait_for(
                self._watch_single_ad(page, tab_id), timeout=limit
            )
        except asyncio.TimeoutError:
            self._record_daily_metric("ad_attempt_timeout")
            self._log(
                f"[W{tab_id}] ! ad attempt timeout after {limit:g}s; closing page"
            )
            return False

    async def _watch_single_ad(self, page: Page, tab_id: int) -> bool:
        prefix = f"[W{tab_id}]"
        self._log(f"{prefix} ▶ Starting ad watch...")
        try:
            # Clear any GDPR/consent overlay that would intercept clicks
            await self._dismiss_consent(page, prefix)

            # Open shop
            self._log(f"{prefix}   Opening shop...")
            body = await page.query_selector("body.modal-open")
            shop_open = False
            if body:
                shop_open = bool(await page.query_selector(".modal-dialog .products-container, #modal-container .products-container"))
            if not shop_open:
                # Give the wallet up to 10s to render (slower under load / GPU-off)
                # instead of failing on an immediate miss.
                try:
                    await page.wait_for_selector(SELECTORS["wallet_container"], timeout=10000)
                except Exception:
                    pass
                wallet = await page.query_selector(SELECTORS["wallet_container"])
                if wallet:
                    if not await self._robust_click(page, SELECTORS["wallet_container"],
                                                    prefix, "wallet"):
                        self._log(f"{prefix}   ! Could not click wallet")
                        return False
                    try:
                        await page.wait_for_selector("body.modal-open", timeout=15000)
                        self._log(f"{prefix}   Shop opened")
                    except Exception:
                        self._log(f"{prefix}   Shop open timeout (continuing)")
                        pass
                    await asyncio.sleep(2)
                else:
                    self._log(f"{prefix}   ! Wallet not found")
                    return False

            # Find button
            self._log(f"{prefix}   Looking for 'Watch ad' button...")
            try:
                await page.wait_for_selector(SELECTORS["watch_ad_btn"], timeout=5000)
            except Exception:
                pass
            buttons = await page.query_selector_all(SELECTORS["watch_ad_btn"])
            if not buttons:
                # When the shop can't load the ad slot, OSM pops a generic
                # "Oops, something went wrong" modal — report that distinctly so
                # it's not confused with a missing button.
                err = await page.evaluate("""() => {
                    const c = document.querySelector('#genericModalContainer');
                    const t = c ? (c.innerText || '') : '';
                    return /something went wrong|oops/i.test(t)
                        ? t.replace(/\\s+/g,' ').trim().slice(0,80) : '';
                }""")
                if err:
                    self._log(f"{prefix}   ! OSM error modal (\"{err}\") — ad slot not served, retry")
                else:
                    self._log(f"{prefix}   ! No 'Watch ad' button found")
                return False
            self._log(f"{prefix}   Found {len(buttons)} button(s)")

            self._log(f"{prefix}   Clicking 'Watch ad'...")
            if not await self._robust_click(page, SELECTORS["watch_ad_btn"],
                                            prefix, "watch-ad"):
                self._log(f"{prefix}   ! Could not click 'Watch ad'")
                return False
            await asyncio.sleep(2)
            self._log(f"{prefix}   Ad started")

            # Fake completion attempt
            self._log(f"{prefix}   Trying fake completion...")
            await page.evaluate("""
                (uid) => {
                    if (window.invokeApplixirVideoUnit) {
                        try { window.invokeApplixirVideoUnit({zoneId:1989,devId:2999,gameId:4074,
                            userId:uid,status:'ad-watched',reward:true}); } catch(e){}
                    }
                    if (window.adinplay && window.adinplay.rewardedVideo) {
                        try { window.adinplay.rewardedVideo.onAdRewarded(); } catch(e){}
                    }
                    ['applixirAdCompleted','adCompleted','rewardedAdCompleted','videoFinished']
                        .forEach(n => { try { document.dispatchEvent(new Event(n, {bubbles:true})); } catch(e){} });
                }
            """, self.user_id)
            await asyncio.sleep(3)
            self._log(f"{prefix}   Fake callbacks dispatched")

            # Check reward (10s window)
            self._log(f"{prefix}   Checking reward (10s)...")
            start = time.time()
            rewarded = False
            while time.time() - start < 10:
                try:
                    reward = await page.query_selector(".modal-dialog .reward-container, .consumable-image-tile")
                    if reward:
                        rewarded = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            if rewarded:
                self._record_dom_reward_detected(prefix, "initial DOM probe")
                return True

            # No reward yet — wait real ad duration
            self._log(f"{prefix}   No reward yet. Waiting {self.ad_duration}s for real ad...")
            await asyncio.sleep(self.ad_duration)
            self._log(f"{prefix}   Ad wait complete")

            # Try fake again
            self._log(f"{prefix}   Retrying fake completion...")
            await page.evaluate("""
                (uid) => {
                    if (window.invokeApplixirVideoUnit) {
                        try { window.invokeApplixirVideoUnit({zoneId:1989,devId:2999,gameId:4074,
                            userId:uid,status:'ad-watched',reward:true}); } catch(e){}
                    }
                }
            """, self.user_id)
            await asyncio.sleep(3)

            # Final check
            self._log(f"{prefix}   Final reward check...")
            try:
                reward = await page.query_selector(".modal-dialog .reward-container, .consumable-image-tile")
                if reward:
                    self._record_dom_reward_detected(prefix, "post-wait DOM probe")
                    return True
            except Exception:
                pass

            self._log(f"{prefix} ❌ No reward confirmed")

            # Close modal if stuck
            try:
                for btn in await page.query_selector_all(".modal-dialog .close, .modal-header .close"):
                    await btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            self.stats["errors"] += 1
            return False
        except Exception as e:
            self._log(f"{prefix} ! Error: {e}")
            return False

    # ------------------------------------------------------------------
    # Main conductor loop
    # ------------------------------------------------------------------
    async def _scout_check(self) -> ScoutOutcome:
        """Open 1 scout tab, try to watch an ad, then check if rate-limit appeared.
        Distinguishes a real cooldown from unavailable ad/UI and navigation errors."""
        self._log("[SCOUT] Step 1/3: Opening scout tab...")
        scout = await self.context.new_page()
        try:
            await scout.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
            await scout.wait_for_selector("#page-content", timeout=30000)
            await asyncio.sleep(2)
            
            self._log("[SCOUT] Step 2/3: Watching 1 ad to test rate-limit...")
            ok = await self._watch_single_ad_bounded(scout, tab_id=99)  # 99 = scout
            
            self._log("[SCOUT] Step 3/3: Checking rate-limit AFTER ad...")
            if not scout.is_closed():
                await self._close_page_bounded(scout, "scout")
            
            # CRITICAL: Check rate-limit AFTER watching the ad
            api_limit = await self._check_api_rate_limit()
            if api_limit:
                self._log("[SCOUT] ⛔ Rate-limit ACTIVE after ad (cooldown: {}).".format(
                    self._fmt_cooldown(api_limit.cooldown_seconds)))
                await self._wait_rate_limit(api_limit)
                return ScoutOutcome.RATE_LIMITED
            
            if ok:
                self._log("[SCOUT] ✅ Local DOM reward + no rate-limit. Safe to open watchers.")
                return ScoutOutcome.READY
            else:
                self._log("[SCOUT] ⚠️ Ad/UI unavailable but no rate-limit.")
                return ScoutOutcome.AD_UNAVAILABLE
                
        except Exception as e:
            url_info = ""
            try:
                url_info = f" (url={scout.url})"
            except Exception:
                pass
            self._log(f"[SCOUT] ! Error{url_info}: {e}")
            await self._close_page_bounded(scout, "scout failure")
            return ScoutOutcome.NAVIGATION_ERROR

    async def _wait_for_scout_retry(self, outcome: ScoutOutcome) -> None:
        event = (
            "scout_ad_unavailable"
            if outcome is ScoutOutcome.AD_UNAVAILABLE
            else "scout_navigation_error"
        )
        self._record_daily_metric(event)
        self._log(
            f"[SCOUT] {outcome.value}; waiting {SCOUT_RETRY_DELAY_SECONDS}s before retry "
            "(not a rate-limit cooldown)."
        )
        await self._park_conductor()
        await asyncio.sleep(SCOUT_RETRY_DELAY_SECONDS)

    async def _conductor_loop(self):
        """Forever loop:
        1. Open scout tab → test if rate-limit active
        2. If rate-limited: close scout, wait cooldown, go to step 1
        3. If OK: close scout, open all watcher tabs (8), let them watch
        4. When watchers done: wait 5 min, go to step 1 (scout again)
        """
        self._log("═══════════════════════════════════════════")
        self._log("  CONDUCTOR STARTED")
        self._log("  Mode: 1 conductor + {} watcher tabs".format(self.watcher_tabs))
        self._log("  Polling every: {}s".format(self.poll_interval))
        self._log("  Min ad duration: {}s (2 min)".format(self.ad_duration))
        self._log("═══════════════════════════════════════════")
        
        consecutive_nav_errors = 0
        while not self._should_stop():
            self.stats["cycles"] += 1
            self._log("")
            self._log("═══════════════════════════════════════════")
            self._log("  CYCLE #{}".format(self.stats['cycles']))
            self._log(
                "  DOM rewards detected so far: {} | Errors: {}".format(
                    self.stats["dom_rewards_detected"], self.stats["errors"]
                )
            )
            self._log("═══════════════════════════════════════════")

            # STEP 1: Scout check — 1 tab ile rate-limit test et
            scout_outcome = await self._scout_check()
            
            if scout_outcome is not ScoutOutcome.READY:
                if scout_outcome is ScoutOutcome.RATE_LIMITED:
                    consecutive_nav_errors = 0
                    self._log("[CYCLE] Rate-limit cooldown handled. Looping back to scout check...")
                elif scout_outcome is ScoutOutcome.NAVIGATION_ERROR:
                    consecutive_nav_errors += 1
                    if consecutive_nav_errors >= 5:
                        self._log(
                            f"[CYCLE] ⛔ Exceeded {consecutive_nav_errors} consecutive scout navigation errors; "
                            "exiting to let launchd cleanly restart with a fresh browser"
                        )
                        raise RuntimeError(
                            f"Exceeded {consecutive_nav_errors} consecutive scout navigation errors"
                        )
                    await self._wait_for_scout_retry(scout_outcome)
                else:
                    consecutive_nav_errors = 0
                    await self._wait_for_scout_retry(scout_outcome)
                continue
            
            consecutive_nav_errors = 0
            
            # STEP 2: Rate-limit YOK — tüm watcher tablarını aç
            # Wake the conductor back onto OSM (it may have been parked during the
            # last wait) so the DOM toast observer + token refresh are live.
            await self._ensure_conductor_awake()
            self._log("[CYCLE] Scout OK! Opening all {} watcher tabs...".format(self.watcher_tabs))
            await self._open_watchers()
            
            # STEP 3: Bekle — watcher'ların bitirmesini bekle (polling ile)
            poll_count = 0
            while not self._should_stop() and self.watcher_pages:
                poll_count += 1
                self._log("[POLL #{}] {} watcher(s) active. Sleeping {}s...".format(
                    poll_count, len(self.watcher_pages), self.poll_interval))
                await asyncio.sleep(self.poll_interval)
                
                if self._should_stop():
                    break
                
                # Check if rate-limit appeared during watching
                api_limit = await self._check_api_rate_limit()
                if api_limit:
                    self._log("[POLL #{}] ⛔ Rate-limit appeared! Closing watchers...".format(poll_count))
                    await self._close_all_watchers()
                    await self._wait_rate_limit(api_limit)
                    break
                
                # Check DOM
                dom_limit = await self._check_dom_rate_limit()
                if dom_limit:
                    self._log("[POLL #{}] ⛔ DOM rate-limit! Closing watchers...".format(poll_count))
                    await self._close_all_watchers()
                    await self._wait_rate_limit(dom_limit)
                    break
                
                self._log("[POLL #{}] ✅ {} watcher(s) still running. DOM rewards: {}".format(
                    poll_count, len(self.watcher_pages), self.stats['dom_rewards_detected']))
            
            # STEP 4: Watcher'lar kapandı veya rate-limit geldi
            # STEP 4b: Tüm watcher tabların kapandığından emin ol
            self._log("[CYCLE] Closing any remaining watchers...")
            await self._close_all_watchers()
            
            # Double-check: wait up to 10s for all watcher tabs to actually close
            confirm_wait = 0
            while (self.watcher_pages or self._watcher_tasks) and confirm_wait < 10 and not self._should_stop():
                self._log("[CYCLE]   ... waiting for tabs to close ({}/{})".format(
                    len(self.watcher_pages), len(self._watcher_tasks)))
                await asyncio.sleep(1)
                confirm_wait += 1
                # Try close again if anything still open
                if self.watcher_pages:
                    for p in list(self.watcher_pages):
                        await self._close_page_bounded(p, "confirmation watcher")
                    self.watcher_pages.clear()
            
            self._log("[CYCLE] ✅ All watchers confirmed closed. {} local DOM rewards detected this run.".format(
                self.stats['dom_rewards_detected']))
            
            # STEP 5: 5 dk bekle, sonra tekrar scout check
            # Park the conductor for the idle gap so it draws ~0 CPU while waiting.
            await self._park_conductor()
            self._log("[CYCLE] Waiting 5 min before next scout check...")
            wait_5min = 300
            while wait_5min > 0 and not self._should_stop():
                chunk = min(30, wait_5min)
                await asyncio.sleep(chunk)
                wait_5min -= chunk
                if wait_5min > 0 and wait_5min % 60 == 0:
                    m = wait_5min // 60
                    self._log("  ... {} min until next check".format(m))
            
            if not self._should_stop():
                self._log("[CYCLE] 5 min wait done. Ready for next cycle!")

        self._log("═══════════════════════════════════════════")
        self._log("  CONDUCTOR STOPPED")
        self._log("═══════════════════════════════════════════")

    async def run(self):
        async with async_playwright() as p:
            self.context = await self._create_context(p)
            await self._inject_storage()
            await self._open_conductor()
            await self._start_mutation_observer()
            if self.auto_training:
                if self.training_league_id and self.training_team_id:
                    self.training_manager = AutoTrainingManager(
                        api_request=self._api_request,
                        league_id=self.training_league_id,
                        team_id=self.training_team_id,
                        log=self._log,
                        normal_timer_id=self.normal_training_timer_id,
                        universal_timer_id=self.universal_training_timer_id,
                        poll_interval=self.training_poll_interval,
                        should_stop=self._should_stop,
                    )
                    self._training_task = asyncio.create_task(
                        self.training_manager.run(), name="osm-auto-training"
                    )
                else:
                    self._log(
                        "[TRAINING] disabled: league/team context was not found in "
                        "the StorageDump or HAR profile"
                    )
            if self.auto_free_reward:
                self.free_reward_manager = FreeRewardManager(
                    api_request=self._api_request,
                    log=self._log,
                    poll_interval=self.free_reward_poll_interval,
                    should_stop=self._should_stop,
                    claim_daily_bonus=True,
                )
                self._free_reward_task = asyncio.create_task(
                    self.free_reward_manager.run(), name="osm-auto-free-reward"
                )
            try:
                await self._conductor_loop()
            finally:
                tasks_to_cancel = [
                    t for t in (self._training_task, self._free_reward_task)
                    if t and not t.done()
                ]
                if tasks_to_cancel:
                    for t in tasks_to_cancel:
                        t.cancel()
                    await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

    def print_summary(self):
        self._log("")
        self._log("═══════════════════════════════════════════")
        self._log("           FINAL SUMMARY")
        self._log("═══════════════════════════════════════════")
        self._log("  Total Cycles      : {}".format(self.stats['cycles']))
        self._log("  DOM Rewards Detected : {}".format(self.stats['dom_rewards_detected']))
        self._log("  Errors            : {}".format(self.stats['errors']))
        self._log("  BossCoins Earned  : not verified locally")
        if self.training_manager:
            self._log("  Trainings Claimed : {}".format(
                self.training_manager.stats["claimed"]
            ))
            self._log("  Trainings Started : {}".format(
                self.training_manager.stats["started"]
            ))
        if self.free_reward_manager:
            self._log("  Free Rewards Claimed: {}".format(
                self.free_reward_manager.stats["claims_count"]
            ))
            self._log("  Free Coins Gained   : {}".format(
                self.free_reward_manager.stats["coins_gained"]
            ))
            self._log("  Training Errors   : {}".format(
                self.training_manager.stats["errors"]
            ))
        self._log("  End Time          : {}".format(datetime.now().isoformat()))
        self._log("═══════════════════════════════════════════")

    def shutdown(self, signum, frame):
        self._log("Shutdown signal received")
        self._shutdown = True


def main():
    parser = argparse.ArgumentParser(description="OSM Ad Watcher — Conductor Edition")
    parser.add_argument("--dump", required=True, help="Path to StorageDump directory or ZIP")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--watcher-tabs", type=int, default=1,
                        help="Number of watcher tabs to open after cooldown (max 9)")
    parser.add_argument("--poll-interval", type=int, default=30,
                        help="Seconds between conductor polls (default 30)")
    parser.add_argument("--ad-duration", type=int, default=30,
                        help="Seconds to wait for real ad to finish")
    parser.add_argument("--auto-training", action="store_true",
                        help="Claim completed trainings and fill empty trainer slots")
    parser.add_argument("--training-poll-interval", type=int, default=60,
                        help="Seconds between automatic training checks (default 60)")
    parser.add_argument("--training-har-profile",
                        help="HAR used only for timer IDs/context; never for credentials")
    parser.add_argument("--normal-training-timer-id", type=int,
                        help="Override normal trainer timer setting ID")
    parser.add_argument("--universal-training-timer-id", type=int,
                        help="Override universal trainer timer setting ID")
    parser.add_argument("--auto-free-reward", action="store_true", default=True,
                        help="Automatically claim free store rewards and daily bonus (default True)")
    parser.add_argument("--no-auto-free-reward", dest="auto_free_reward", action="store_false",
                        help="Disable automatic free store reward claims")
    parser.add_argument("--free-reward-poll-interval", type=int, default=1800,
                        help="Seconds between automatic free reward checks (default 1800)")
    parser.add_argument("--log", help="Log file path")
    args = parser.parse_args()

    bot = OSMConductorBot(
        dump_dir=args.dump,
        headless=args.headless,
        watcher_tabs=args.watcher_tabs,
        poll_interval=args.poll_interval,
        ad_duration=args.ad_duration,
        log_file=args.log,
        auto_training=args.auto_training,
        training_poll_interval=args.training_poll_interval,
        training_har_profile=args.training_har_profile,
        normal_training_timer_id=args.normal_training_timer_id,
        universal_training_timer_id=args.universal_training_timer_id,
        auto_free_reward=args.auto_free_reward,
        free_reward_poll_interval=args.free_reward_poll_interval,
    )

    signal.signal(signal.SIGINT, bot.shutdown)
    signal.signal(signal.SIGTERM, bot.shutdown)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Surface startup/runtime crashes IN THE LOG FILE (stderr tracebacks
        # otherwise vanish when stdout is redirected to the log). Common cause:
        # missing Playwright browser binary → run `python3 -m playwright install chromium`.
        import traceback
        bot._log("")
        bot._log("!!! FATAL: {}: {}".format(type(e).__name__, e))
        for line in traceback.format_exc().splitlines():
            bot._log("    " + line)
        if "Executable doesn't exist" in str(e):
            bot._log("    → FIX: python3 -m playwright install chromium")
    finally:
        bot.print_summary()
        if bot.log_file and hasattr(bot, '_log_fp'):
            bot._log_fp.close()


if __name__ == "__main__":
    main()
