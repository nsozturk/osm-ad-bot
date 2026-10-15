#!/usr/bin/env python3
"""
OSM Auto Free Reward Bot
========================
Claims free rewards from OSM Shop -> Featured section (Product 653 / WebShopFree).

Can run as:
  1. Standalone CLI:
       python3 auto_free_reward.py [--dump PATH] [--mode {api,browser}] [--headed] [--loop]
  2. Imported module in osm_ad_bot_conductor:
       from auto_free_reward import FreeRewardManager
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import glob
import json
import os
import re
import signal
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

from storage_loader import StorageLoader

OSM_ORIGIN = "https://en.onlinesoccermanager.com"
OSM_API_ORIGIN = "https://web-api.onlinesoccermanager.com"
OSM_CLIENT_ID = "jPs3vVbg4uYnxGoyunSiNf1nIqUJmSFnpqJSVgWrJleu6Ak7Ga"
CLIENT_SECRET_CACHE = (
    Path(__file__).resolve().parent / "transfer-advisor" / "data" / ".client_secret"
)

KNOWN_FREE_ACTIONS = [
    "Webshop Free Reward 1",
]

def _clean_error_message(resp: Any, default: str = "") -> str:
    if not isinstance(resp, dict):
        return default
    model_state = resp.get("modelState")
    if isinstance(model_state, dict):
        parts = []
        for k, v in model_state.items():
            if isinstance(v, list) and v:
                parts.append(f"{k}: {v[0]}")
            else:
                parts.append(f"{k}: {v}")
        if parts:
            return "; ".join(parts)
    if resp.get("message"):
        return str(resp.get("message"))
    if resp.get("error"):
        return str(resp.get("error"))
    return default

ApiRequest = Callable[
    [str, str, Optional[dict[str, Any]]],
    Awaitable[tuple[int, Any]],
]


def _jwt_expiry(token: str) -> int:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return int(claims.get("exp", 0))
    except Exception:
        return 0


def _token_expiring(token: str, skew_seconds: int = 60) -> bool:
    expiry = _jwt_expiry(token)
    return bool(expiry and expiry <= int(time.time()) + max(0, skew_seconds))


def find_default_storage_dump() -> Optional[Path]:
    """Auto-detect the most appropriate StorageDump file or folder."""
    # 1. Check runtime copy if conductor is active
    runtime_dump = Path(__file__).resolve().parent / "tmp" / "osm-runtime" / "launchd-storage-dump.zip"
    if runtime_dump.is_file():
        return runtime_dump

    # 2. Check Downloads folder for latest OSM dump
    downloads = Path.home() / "Downloads"
    if downloads.is_dir():
        dumps = sorted(
            downloads.glob("storagedump_en.onlinesoccermanager.com_*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if dumps:
            return dumps[0]
        dump_dirs = sorted(
            [d for d in downloads.glob("storagedump_en.onlinesoccermanager.com_*") if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if dump_dirs:
            return dump_dirs[0]

    # 3. Check workspace directory
    local_dumps = sorted(
        Path(".").glob("storagedump_en.onlinesoccermanager.com_*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if local_dumps:
        return local_dumps[0]

    return None


@dataclass
class ClaimResult:
    product_id: int
    product_payment_method_id: int
    title: str
    action_id: str
    bag_id: str = ""
    bag_name: str = ""
    rewards: list[dict[str, Any]] = field(default_factory=list)
    coins_gained: int = 0
    energy_gained: int = 0
    success: bool = False
    message: str = ""


class FreeRewardManager:
    """Manages querying and claiming free rewards from OSM store via API."""

    def __init__(
        self,
        api_request: ApiRequest,
        log: Callable[[str], None] = lambda m: print(m, flush=True),
        poll_interval: int = 3600,
        should_stop: Optional[Callable[[], bool]] = None,
        claim_daily_bonus: bool = True,
    ):
        self.api_request = api_request
        self.log = log
        self.poll_interval = poll_interval
        self.should_stop = should_stop or (lambda: False)
        self.claim_daily_bonus = claim_daily_bonus
        self._lock = asyncio.Lock()
        self._stats_lock = asyncio.Lock()
        self.stats = {
            "claims_count": 0,
            "coins_gained": 0,
            "bags_opened": 0,
            "energy_gained": 0,
            "attempts": 0,
            "errors": 0,
            "last_error": "",
        }

    async def get_products(self) -> list[dict[str, Any]]:
        status, data = await self.api_request("GET", "/api/v1.1/products/web/")
        if status != 200 or not isinstance(data, list):
            self.log(f"[FREE-REWARD] Failed to fetch products (HTTP {status})")
            return []
        return data

    def filter_free_products(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Identify available free products in store (price 0, enabled)."""
        free_items = []
        for p in products:
            if not isinstance(p, dict):
                continue
            price = p.get("price")
            enabled = p.get("enabled", False)
            ppm_id = p.get("productPaymentMethodId")
            cat_id = p.get("productCategoryId")
            action_id = p.get("actionId", "")

            # Product 653 or category 14 (WebShopFree) or price == 0 with valid payment method
            if price == 0 and enabled and ppm_id:
                free_items.append(p)
            elif cat_id == 14 and enabled and ppm_id:
                free_items.append(p)
            elif "free" in action_id.lower() and price == 0 and enabled and ppm_id:
                free_items.append(p)

        # Sort with category 14 (WebShopFree) / actionId "Webshop Free Reward 1" first
        def priority_key(item: dict[str, Any]) -> int:
            if item.get("productCategoryId") == 14:
                return 0
            if "webshop free reward" in item.get("actionId", "").lower():
                return 1
            return 2

        free_items.sort(key=priority_key)
        return free_items

    async def _unpack_and_consume(self, items: list[dict[str, Any]], result: ClaimResult) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            reward_meta = item.get("reward") or {}
            reward_type = reward_meta.get("type")
            bag_name = reward_meta.get("name") or "Reward Bag"
            result.bag_id = str(item_id or "")
            result.bag_name = bag_name

            # If it's a random reward consumable (type 13), claim the bag
            if reward_type == 13 or item.get("action", {}).get("type") == 15:
                claim_status, claim_resp = await self.api_request(
                    "PUT",
                    f"/api/v1/user/randomrewards/{item_id}/claim",
                )
                if claim_status == 200 and isinstance(claim_resp, list):
                    async with self._stats_lock:
                        self.stats["bags_opened"] += 1
                    flattened = []
                    for sub in claim_resp:
                        if isinstance(sub, list):
                            flattened.extend(sub)
                        elif isinstance(sub, dict):
                            flattened.append(sub)

                    for granted in flattened:
                        if not isinstance(granted, dict):
                            continue
                        r_id = granted.get("id")
                        r_meta = granted.get("reward") or {}
                        r_type = r_meta.get("type")
                        r_val = int(r_meta.get("value", 0))
                        r_act = granted.get("action", {}).get("id", "")

                        result.rewards.append({
                            "reward_id": r_id,
                            "type": r_type,
                            "value": r_val,
                            "action": r_act,
                        })

                        # Boss Coins reward (type 1) -> consume into wallet
                        if r_type == 1 and r_id:
                            consume_status, _ = await self.api_request(
                                "POST",
                                "/api/v1/user/bosscoinwallet/consumereward",
                                payload={"rewardId": r_id},
                            )
                            if consume_status == 200:
                                result.coins_gained += r_val
                                async with self._stats_lock:
                                    self.stats["coins_gained"] += r_val
                        # Energy reward (type 5) -> consume into wallet
                        elif r_type == 5 and r_id:
                            consume_status, _ = await self.api_request(
                                "POST",
                                "/api/v1/user/wallets/energy/consumereward",
                                payload={"rewardId": r_id},
                            )
                            if consume_status == 200:
                                result.energy_gained += r_val
                                async with self._stats_lock:
                                    self.stats["energy_gained"] += r_val

            # Direct boss coin reward in purchase response
            elif reward_type == 1 and item_id:
                consume_status, _ = await self.api_request(
                    "POST",
                    "/api/v1/user/bosscoinwallet/consumereward",
                    payload={"rewardId": item_id},
                )
                if consume_status == 200:
                    val = int(reward_meta.get("value", 0))
                    result.coins_gained += val
                    async with self._stats_lock:
                        self.stats["coins_gained"] += val

    async def claim_free_product(self, product: dict[str, Any]) -> ClaimResult:
        prod_id = int(product.get("id", 0))
        ppm_id = int(product.get("productPaymentMethodId", 0))
        action_id = str(product.get("actionId", ""))
        title = str(product.get("title", "") or action_id or f"Product {prod_id}")

        result = ClaimResult(
            product_id=prod_id,
            product_payment_method_id=ppm_id,
            title=title,
            action_id=action_id,
        )

        # Step 1: Process store purchase
        status, purchase_resp = await self.api_request(
            "POST",
            "/api/v1/bosscoinstorepurchase/process",
            payload={"productPaymentMethodId": ppm_id},
        )
        if status != 200 or not isinstance(purchase_resp, list) or not purchase_resp:
            err_msg = _clean_error_message(purchase_resp)
            result.message = f"Purchase rejected (HTTP {status}) {err_msg}".strip()
            return result

        result.success = True
        async with self._stats_lock:
            self.stats["claims_count"] += 1

        # Step 2: Unpack purchase response
        await self._unpack_and_consume(purchase_resp, result)
        return result

    async def claim_action_reward(self, action_id: str) -> ClaimResult:
        """Attempt direct action claim via /api/v1/user/actions/{actionId}."""
        enc_action = urllib.parse.quote(action_id)
        endpoint = f"/api/v1/user/actions/{enc_action}"
        status, resp = await self.api_request("POST", endpoint)
        result = ClaimResult(
            product_id=0,
            product_payment_method_id=0,
            title=f"Action: {action_id}",
            action_id=action_id,
        )
        if status != 200 or not resp:
            err_msg = _clean_error_message(resp)
            result.message = f"Action rejected (HTTP {status}) {err_msg}".strip()
            return result

        result.success = True
        async with self._stats_lock:
            self.stats["claims_count"] += 1

        raw_items = resp if isinstance(resp, list) else [resp]
        await self._unpack_and_consume(raw_items, result)
        return result

    async def claim_daily_login_bonus(self) -> int:
        """Check wallet for unclaimed daily bonus coins and claim them."""
        status, wallet = await self.api_request("GET", "/api/v1/user/bosscoinwallet")
        if status != 200 or not isinstance(wallet, dict):
            return 0
        unclaimed = int(wallet.get("unclaimedCoins", 0))
        if unclaimed > 0:
            claim_status, _ = await self.api_request("PUT", "/api/v1/user/bosscoinwallet/claim")
            if claim_status == 200:
                self.log(f"[FREE-REWARD] Claimed daily login bonus: +{unclaimed} Boss Coins")
                async with self._stats_lock:
                    self.stats["coins_gained"] += unclaimed
                return unclaimed
        return 0

    async def reconcile(self, max_attempts: int = 20, check_actions: bool = True) -> list[ClaimResult]:
        """Perform a full check and claim pass for all available free store rewards."""
        async with self._lock:
            claimed_results: list[ClaimResult] = []

            # 1. Claim daily wallet bonus if available
            if self.claim_daily_bonus:
                try:
                    await self.claim_daily_login_bonus()
                except Exception as exc:
                    self.log(f"[FREE-REWARD] Daily bonus check error: {exc}")

            # 2. Check store products
            products = await self.get_products()
            free_products = self.filter_free_products(products)

            if not free_products:
                self.log("[FREE-REWARD] No free products available in store right now.")
            else:
                self.log(f"[FREE-REWARD] Found {len(free_products)} free product(s) in store.")

                # Claim each free product.
                attempt = 0
                while max_attempts <= 0 or attempt < max_attempts:
                    attempt += 1
                    if attempt > 1:
                        # Re-fetch products to see if still enabled
                        products = await self.get_products()
                        free_products = self.filter_free_products(products)
                        if not free_products:
                            break

                    p = free_products[0]
                    ppm_id = p.get("productPaymentMethodId")
                    self.log(
                        f"[FREE-REWARD] Claiming {p.get('actionId') or p.get('title') or 'Free Reward'} "
                        f"(ppmId={ppm_id}, attempt {attempt})..."
                    )

                    res = await self.claim_free_product(p)
                    if res.success:
                        reward_desc = []
                        if res.coins_gained:
                            reward_desc.append(f"+{res.coins_gained} Boss Coins")
                        if res.energy_gained:
                            reward_desc.append(f"+{res.energy_gained} Energy")
                        if not reward_desc and res.bag_name:
                            reward_desc.append(res.bag_name)

                        summary = ", ".join(reward_desc) if reward_desc else "Reward claimed"
                        self.log(
                            f"[FREE-REWARD] Successfully claimed! [{res.bag_name}]: {summary}"
                        )
                        claimed_results.append(res)
                        await asyncio.sleep(0.5)
                    else:
                        self.log(f"[FREE-REWARD] Claim attempt stopped: {res.message}")
                        break

            # 3. Direct action fallback
            if check_actions:
                for act in KNOWN_FREE_ACTIONS:
                    res = await self.claim_action_reward(act)
                    if res.success:
                        reward_desc = []
                        if res.coins_gained:
                            reward_desc.append(f"+{res.coins_gained} Boss Coins")
                        summary = ", ".join(reward_desc) if reward_desc else "Claimed"
                        self.log(f"[FREE-REWARD] Successfully claimed via Action [{act}]: {summary}")
                        claimed_results.append(res)

            return claimed_results

    async def run_parallel(
        self,
        workers: int = 3,
        delay: float = 0.5,
        max_claims: int = 0,
        check_actions: bool = True,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        """Aggressive concurrent worker pool running without pause until stopped."""
        if stop_event is None:
            stop_event = asyncio.Event()

        self.log(
            f"🚀 [FREE-REWARD-PARALLEL] Starting {workers} concurrent workers "
            f"(failure delay: {delay}s, max_claims: {max_claims or 'unlimited'}, action_fallback: {check_actions})"
        )

        if self.claim_daily_bonus:
            try:
                await self.claim_daily_login_bonus()
            except Exception:
                pass

        shared_cache: dict[str, Any] = {
            "products": [],
            "last_fetch": 0.0,
        }
        cache_lock = asyncio.Lock()

        async def get_cached_free_products() -> list[dict[str, Any]]:
            now = time.time()
            async with cache_lock:
                if now - shared_cache["last_fetch"] > 10.0 or not shared_cache["products"]:
                    prods = await self.get_products()
                    shared_cache["products"] = self.filter_free_products(prods)
                    shared_cache["last_fetch"] = now
                return shared_cache["products"]

        async def worker_loop(wid: int):
            while not stop_event.is_set() and not self.should_stop():
                try:
                    if max_claims > 0 and self.stats["claims_count"] >= max_claims:
                        stop_event.set()
                        break

                    free_prods = await get_cached_free_products()
                    claimed = False

                    # 1. Try store purchase on free products
                    for p in free_prods:
                        res = await self.claim_free_product(p)
                        if res.success:
                            claimed = True
                            coins = res.coins_gained
                            total_c = self.stats["coins_gained"]
                            self.log(
                                f"🔥 [WORKER-{wid}] SUCCESS! [{res.bag_name or 'Reward'}]: "
                                f"+{coins} BC (Total: +{total_c} BC)"
                            )
                            # Continuous: immediately loop for next without pause!
                            break
                        else:
                            async with self._stats_lock:
                                self.stats["attempts"] += 1
                                self.stats["last_error"] = res.message

                    # 2. Try direct actions if store didn't claim
                    if not claimed and check_actions:
                        for act in KNOWN_FREE_ACTIONS:
                            res = await self.claim_action_reward(act)
                            if res.success:
                                claimed = True
                                coins = res.coins_gained
                                total_c = self.stats["coins_gained"]
                                self.log(
                                    f"🔥 [WORKER-{wid}] ACTION SUCCESS [{act}]: "
                                    f"+{coins} BC (Total: +{total_c} BC)"
                                )
                                break
                            else:
                                async with self._stats_lock:
                                    self.stats["attempts"] += 1
                                    self.stats["last_error"] = res.message

                    if not claimed:
                        if "429" in res.message or "rate" in res.message.lower():
                            self.log(f"⚠️ [WORKER-{wid}] Rate limit encountered, backing off 3s...")
                            await asyncio.sleep(3.0)
                        elif delay > 0:
                            await asyncio.sleep(delay)
                        else:
                            await asyncio.sleep(0.05)
                    else:
                        await asyncio.sleep(0.01)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    async with self._stats_lock:
                        self.stats["errors"] += 1
                        self.stats["last_error"] = str(exc)
                    await asyncio.sleep(max(1.0, delay))

        async def reporter_loop():
            await asyncio.sleep(1.5)
            last_attempts = 0
            while not stop_event.is_set() and not self.should_stop():
                async with self._stats_lock:
                    attempts = self.stats["attempts"]
                    claims = self.stats["claims_count"]
                    coins = self.stats["coins_gained"]
                    last_err = self.stats.get("last_error", "")
                delta = attempts - last_attempts
                last_attempts = attempts
                rate = delta / 5.0
                clean_err = (last_err[:75] + "...") if len(last_err) > 75 else last_err
                self.log(
                    f"⚡ [PARALLEL STATUS] Workers: {workers} | Rate: {rate:.1f} req/s | "
                    f"Total Attempts: {attempts} | Total Claims: {claims} | Coins: +{coins} BC | Status: {clean_err}"
                )
                await asyncio.sleep(5.0)

        tasks = [asyncio.create_task(worker_loop(i + 1)) for i in range(workers)]
        reporter_task = asyncio.create_task(reporter_loop())

        try:
            await stop_event.wait()
        finally:
            reporter_task.cancel()
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, reporter_task, return_exceptions=True)
            self.log(
                f"\n🏁 [FREE-REWARD-PARALLEL] Finished! "
                f"Total Claims: {self.stats['claims_count']}, Total Coins Gained: +{self.stats['coins_gained']} BC, "
                f"Total Attempts: {self.stats['attempts']}"
            )

    async def run(self) -> None:
        """Periodic background worker for the conductor."""
        self.log(f"[FREE-REWARD] Background worker started (poll every {self.poll_interval}s)")
        while not self.should_stop():
            try:
                await self.reconcile()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                async with self._stats_lock:
                    self.stats["errors"] += 1
                self.log(f"[FREE-REWARD] Check error: {exc}")

            # Sleep poll interval in small chunks to stay responsive
            elapsed = 0
            while elapsed < self.poll_interval and not self.should_stop():
                await asyncio.sleep(min(5, self.poll_interval - elapsed))
                elapsed += 5


class StandaloneApiClient:
    """Provides an authenticated api_request callback without running a full browser."""

    def __init__(self, dump_path: Path):
        self.dump_path = dump_path
        self.loader = StorageLoader(str(dump_path))
        self.cookies = {c["name"]: c["value"] for c in self.loader.cookies}
        self.access_token = self.cookies.get("access_token", "")
        self.refresh_token = self.cookies.get("refresh_token", "")
        self.client_id = os.environ.get("OSM_CLIENT_ID", "").strip() or OSM_CLIENT_ID
        self.client_secret = self._read_client_secret()
        self._refresh_lock = asyncio.Lock()
        self._client: Optional[httpx.AsyncClient] = None

    async def get_http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=15.0,
                limits=httpx.Limits(max_keepalive_connections=30, max_connections=60),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _read_client_secret(self) -> str:
        sec = os.environ.get("OSM_CLIENT_SECRET", "").strip()
        if sec:
            return sec
        try:
            return CLIENT_SECRET_CACHE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    async def refresh_token_if_needed(self, force: bool = False) -> Optional[str]:
        if not force and self.access_token and not _token_expiring(self.access_token):
            return self.access_token

        async with self._refresh_lock:
            if not force and self.access_token and not _token_expiring(self.access_token):
                return self.access_token

            if not self.refresh_token or not self.client_secret:
                return self.access_token or None

            try:
                client = await self.get_http_client()
                resp = await client.post(
                    f"{OSM_API_ORIGIN}/api/tokenRefresh",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                    },
                    headers={
                        "Accept": "application/json; charset=utf-8",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "AppVersion": "3.256.2",
                        "PlatformId": "14",
                        "Origin": OSM_ORIGIN,
                        "Referer": f"{OSM_ORIGIN}/",
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    new_acc = data.get("access_token")
                    new_ref = data.get("refresh_token")
                    if new_acc:
                        self.access_token = new_acc
                    if new_ref:
                        self.refresh_token = new_ref
                    return self.access_token
            except Exception:
                pass
            return self.access_token or None

    async def api_request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> tuple[int, Any]:
        token = await self.refresh_token_if_needed()
        if not token:
            return 0, {"error": "No valid access token"}

        url = f"{OSM_API_ORIGIN}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json; charset=utf-8",
            "AppVersion": "3.256.2",
            "PlatformId": "14",
            "Origin": OSM_ORIGIN,
            "Referer": f"{OSM_ORIGIN}/",
        }

        # Form-urlencoded vs JSON
        form_endpoints = (
            "/trainingsessions",
            "/bosscoinstorepurchase/process",
            "/consumereward",
        )
        if payload is None:
            req_body: dict[str, Any] = {}
        elif any(endpoint.rstrip("/").endswith(suffix) for suffix in form_endpoints):
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            req_body = {"data": payload}
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
            req_body = {"json": payload}

        try:
            client = await self.get_http_client()
            resp = await client.request(
                method.upper(), url, headers=headers, timeout=15, **req_body
            )
            if resp.status_code in (401, 403):
                token = await self.refresh_token_if_needed(force=True)
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = await client.request(
                        method.upper(), url, headers=headers, timeout=15, **req_body
                    )

            if not resp.content:
                return resp.status_code, {}
            try:
                return resp.status_code, resp.json()
            except Exception:
                return resp.status_code, {"raw": resp.text}
        except Exception as exc:
            return 0, {"error": str(exc)}


async def run_browser_flow(dump_path: Path, headed: bool = False) -> None:
    """Run interactive Playwright flow clicking Shop -> Featured -> Free Reward."""
    from playwright.async_api import async_playwright

    loader = StorageLoader(str(dump_path))
    print(f"[BROWSER] Launching Playwright (headed={headed})...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        )

        # Inject cookies
        if loader.cookies:
            await context.add_cookies(loader.cookies)

        page = await context.new_page()

        # Inject local and session storage
        origin = OSM_ORIGIN
        await page.goto(f"{origin}/Inventory", wait_until="commit", timeout=30000)

        if loader.local_storage or loader.session_storage:
            await page.evaluate(
                """([local, session]) => {
                    for (const item of local) {
                        try { localStorage.setItem(item.key, item.value); } catch(e){}
                    }
                    for (const item of session) {
                        try { sessionStorage.setItem(item.key, item.value); } catch(e){}
                    }
                }""",
                [loader.local_storage, loader.session_storage],
            )
            await page.reload(wait_until="domcontentloaded", timeout=30000)

        print("[BROWSER] Page loaded. Opening Shop...")
        await page.wait_for_timeout(3000)

        # Click Shop button
        shop_selectors = [
            ".menu-icon.icon-shop",
            ".menu-title:has-text('Shop')",
            "a[data-bind*='Shop']",
            ".wallet-container.bosscoin-wallet",
            ".event-timer[data-bind*='goToEvent']",
        ]
        opened_shop = False
        for sel in shop_selectors:
            try:
                el = page.locator(sel).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    opened_shop = True
                    print(f"[BROWSER] Clicked shop trigger: {sel}")
                    break
            except Exception:
                continue

        if not opened_shop:
            print("[BROWSER] Could not find shop button in UI. Trying direct call...")
            await page.evaluate("() => { if (window.appViewModel?.bossCoinWalletPartial()?.openBosscoinShopModal) appViewModel.bossCoinWalletPartial().openBosscoinShopModal('ShopMenuButton'); }")

        # Wait for Store Modal
        try:
            await page.wait_for_selector("#modal-dialog-store, .modal-dialog-dynamic-height", timeout=10000)
            print("[BROWSER] Shop modal opened.")
        except Exception:
            print("[BROWSER] Failed to open shop modal.")
            await browser.close()
            return

        # Look for free product in Featured / WebShopFree section
        max_claims = 5
        claimed_any = False

        for cycle in range(max_claims):
            await page.wait_for_timeout(2000)

            # Look for free reward tile
            free_selectors = [
                "#product-category-webshopfree .product",
                ".products-section:has-text('Featured') .product",
                ".product:has(.consumable-image[style*='Product_653'])",
                ".product:has-text('Free Reward')",
                ".product:has(.payment-option-price:has-text('Free'))",
            ]

            found_product = None
            for sel in free_selectors:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1500):
                    found_product = loc
                    print(f"[BROWSER] Located free reward tile: {sel}")
                    break

            if not found_product:
                if cycle == 0:
                    print("[BROWSER] No free reward tile found in Shop.")
                else:
                    print(f"[BROWSER] Finished claiming ({cycle} claimed).")
                break

            # Click product tile
            await found_product.click()
            print("[BROWSER] Clicked Free Reward product.")

            # Check if confirmation popup appears
            try:
                confirm_btn = page.locator("#modal-dialog-confirmpayment .btn-success, [data-bind*='okAction']").first
                if await confirm_btn.is_visible(timeout=2000):
                    await confirm_btn.click()
                    print("[BROWSER] Confirmed purchase popup.")
            except Exception:
                pass

            # Wait for reward claim / bag reveal modal
            try:
                await page.wait_for_selector("#modal-dialog-claimfreereward, .modal-claim-free-reward", timeout=8000)
                print("[BROWSER] Free reward bag revealed modal opened.")

                # Click bag to reveal
                bag_loc = page.locator(".free-reward-animation, .free-reward-open-label, #modal-dialog-claimfreereward canvas").first
                if await bag_loc.is_visible(timeout=3000):
                    await bag_loc.click()
                    print("[BROWSER] Clicked 'Tap to reveal'.")

                # Wait for continue button
                await page.wait_for_timeout(2000)
                continue_btn = page.locator(".claim-reward button, .btn-primary:has-text('Continue'), #modal-dialog-claimfreereward button.btn-primary").first
                await continue_btn.wait_for(state="visible", timeout=6000)
                await continue_btn.click()
                print("[BROWSER] Clicked 'Continue'. Reward secured!")
                claimed_any = True
            except Exception as exc:
                print(f"[BROWSER] Reward claim modal interaction: {exc}")
                break

        # Close shop modal if open
        try:
            close_btn = page.locator("#modal-dialog-store .close, #modal-dialog-store [data-dismiss='modal']").first
            if await close_btn.is_visible(timeout=2000):
                await close_btn.click()
        except Exception:
            pass

        print(f"[BROWSER] Completed browser flow. Claimed: {claimed_any}")
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="OSM Free Reward Bot (Shop -> Featured -> Free Reward)")
    parser.add_argument(
        "--dump",
        help="Path to StorageDump directory or ZIP archive (auto-detected if omitted)",
    )
    parser.add_argument(
        "--mode",
        choices=["api", "browser"],
        default="api",
        help="Execution mode: 'api' (fast direct HTTP) or 'browser' (Playwright UI automation)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in visible mode (only for --mode browser)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect available store products without purchasing",
    )
    parser.add_argument(
        "--continuous",
        "-c",
        action="store_true",
        help="Run continuously without waiting (aggressive parallel hammering loop)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=3,
        help="Number of concurrent workers for parallel claiming (default 3)",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=0.5,
        help="Delay in seconds between retries when claim is rejected / waiting (default 0.5)",
    )
    parser.add_argument(
        "--max-claims",
        type=int,
        default=0,
        help="Maximum successful claims before stopping (0 = unlimited)",
    )
    parser.add_argument(
        "--no-actions",
        action="store_false",
        dest="check_actions",
        default=True,
        help="Disable trying known direct action IDs",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run periodic checks in background (legacy mode)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Minutes between checks when running with --loop (default 60)",
    )
    args = parser.parse_args()

    # Find storage dump
    dump_path = Path(args.dump) if args.dump else find_default_storage_dump()
    if not dump_path or not dump_path.exists():
        print("ERROR: StorageDump not found. Please specify --dump <path-to-storagedump.zip>")
        sys.exit(1)

    print(f"Using StorageDump: {dump_path}")

    if args.mode == "browser":
        asyncio.run(run_browser_flow(dump_path, headed=args.headed))
        return

    # API Mode
    client = StandaloneApiClient(dump_path)

    async def run_api():
        if args.dry_run:
            print("[DRY-RUN] Fetching store products...")
            status, prods = await client.api_request("GET", "/api/v1.1/products/web/")
            if status != 200 or not isinstance(prods, list):
                print(f"[DRY-RUN] Failed to fetch products (HTTP {status})")
                return
            manager = FreeRewardManager(api_request=client.api_request)
            free = manager.filter_free_products(prods)
            print(f"[DRY-RUN] Total products: {len(prods)}, Free products found: {len(free)}")
            for p in free:
                print(
                    f"  - ID: {p.get('id')} | Title: {p.get('actionId') or p.get('title')} | "
                    f"PPM_ID: {p.get('productPaymentMethodId')} | Cat: {p.get('productCategoryId')}"
                )
            return

        manager = FreeRewardManager(
            api_request=client.api_request,
            poll_interval=args.interval * 60,
        )

        stop_event = asyncio.Event()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: stop_event.set())
            except (NotImplementedError, RuntimeError):
                pass

        try:
            if args.continuous or args.workers > 1:
                await manager.run_parallel(
                    workers=max(1, args.workers),
                    delay=max(0.0, args.delay),
                    max_claims=args.max_claims,
                    check_actions=args.check_actions,
                    stop_event=stop_event,
                )
            elif args.loop:
                await manager.run()
            else:
                results = await manager.reconcile(check_actions=args.check_actions)
                print(f"\nFinished: {len(results)} free reward(s) processed. Total coins gained: {manager.stats['coins_gained']}")
        finally:
            await client.close()

    asyncio.run(run_api())


if __name__ == "__main__":
    main()
