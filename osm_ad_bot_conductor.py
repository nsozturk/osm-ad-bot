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
import json
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

from storage_loader import StorageLoader

OSM_ORIGIN = "https://en.onlinesoccermanager.com"
OSM_TRAINING = f"{OSM_ORIGIN}/Training"

SELECTORS = {
    "wallet_container": ".wallet-container.bosscoin-wallet",
    "watch_ad_btn": ".product-free",
}

# Regex to parse DOM toast: "You have reached... Come back in 13 minutes..."
DOM_COOLDOWN_RE = re.compile(
    r"Come\s+back\s+in\s+(\d+)\s+minute",
    re.IGNORECASE,
)


@dataclass
class RateLimitInfo:
    is_limited: bool
    cooldown_seconds: int
    source: str  # 'api' or 'dom'

    def __str__(self) -> str:
        m, s = divmod(self.cooldown_seconds, 60)
        return f"RATE-LIMIT ({self.source}) — next ad in {m}m {s}s"


class OSMConductorBot:
    def __init__(self, dump_dir: str, headless: bool = False,
                 watcher_tabs: int = 1, poll_interval: int = 30,
                 ad_duration: int = 30, log_file: Optional[str] = None):
        self.dump_dir = dump_dir
        self.headless = headless
        self.watcher_tabs = min(watcher_tabs, 9)
        self.poll_interval = poll_interval
        # Minimum 2 min ad wait regardless of flag
        self.ad_duration = max(ad_duration, 120)
        self.log_file = log_file

        self.storage = StorageLoader(dump_dir)
        self.stats = {"watched": 0, "errors": 0, "cycles": 0}
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
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        # Also write to log file immediately if configured
        if self.log_file and hasattr(self, '_log_fp'):
            self._log_fp.write(line + "\n")
            self._log_fp.flush()

    def _should_stop(self) -> bool:
        return self._shutdown

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------
    async def _create_context(self, playwright):
        self._log("Launching browser...")
        browser = await playwright.chromium.launch(
            headless=self.headless,
            args=["--mute-audio", "--no-sandbox"]
        )
        self._log(f"Browser launched (headless={self.headless}, watchers={self.watcher_tabs})")
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            locale="en-GB",
        )
        return ctx

    async def _inject_storage(self):
        self._log("Injecting cookies & storage...")
        await self.storage.inject(self.context)
        self._log("Storage injected")

    async def _open_conductor(self):
        self.conductor_page = await self.context.new_page()
        await self.conductor_page.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
        await self.conductor_page.wait_for_selector("#page-content", timeout=30000)
        await asyncio.sleep(3)
        self._log("Conductor tab ready")

    async def _start_mutation_observer(self):
        """Install a JS mutation observer that watches for toast/alert nodes
        containing the rate-limit text and pushes cooldown minutes to a
        window.__osm_toast_queue array so we can read it from Python."""
        await self.conductor_page.evaluate("""
            () => {
                window.__osm_toast_queue = [];
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
                observer.observe(document.body, { childList: true, subtree: true });
            }
        """)
        self._log("DOM toast observer installed")

    async def _read_dom_cooldown(self) -> Optional[int]:
        """Read any newly-seen toast cooldown minutes and clear the queue."""
        result = await self.conductor_page.evaluate("""
            () => {
                const q = window.__osm_toast_queue;
                if (q.length === 0) return null;
                const maxVal = Math.max(...q);
                window.__osm_toast_queue = [];
                return maxVal;
            }
        """)
        return result

    # ------------------------------------------------------------------
    # Auth / API helpers
    # ------------------------------------------------------------------
    def _get_refresh_token(self) -> Optional[str]:
        for c in self.storage.cookies:
            if c["name"] == "refresh_token":
                return c["value"]
        return None

    async def _refresh_access_token(self) -> Optional[str]:
        import httpx
        import os
        refresh = self._get_refresh_token()
        if not refresh:
            return None
        client_id = os.environ.get("OSM_CLIENT_ID", "")
        client_secret = os.environ.get("OSM_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            self._log("! OSM_CLIENT_ID / OSM_CLIENT_SECRET env vars not set")
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://web-api.onlinesoccermanager.com/api/tokenRefresh",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh,
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "AppVersion": "3.248.3",
                        "PlatformId": "13",
                        "Origin": "https://en.onlinesoccermanager.com",
                        "Referer": "https://en.onlinesoccermanager.com/",
                    },
                    timeout=10,
                )
                data = resp.json()
                new_token = data.get("access_token")
                if new_token:
                    # Update internal cookies
                    found = False
                    for c in self.storage.cookies:
                        if c["name"] == "access_token":
                            c["value"] = new_token
                            found = True
                            break
                    if not found:
                        self.storage.cookies.append({
                            "name": "access_token", "value": new_token,
                            "domain": "en.onlinesoccermanager.com", "path": "/",
                            "httpOnly": False, "secure": True, "sameSite": "None",
                        })
                    # Update browser cookies on conductor
                    await self.context.add_cookies([{
                        "name": "access_token", "value": new_token,
                        "domain": "en.onlinesoccermanager.com", "path": "/",
                        "httpOnly": False, "secure": True, "sameSite": "None",
                    }])
                    return new_token
                else:
                    self._log(f"Token refresh failed: {data}")
                    return None
        except Exception as e:
            self._log(f"Token refresh error: {e}")
            return None

    async def _api_get(self, endpoint: str) -> dict:
        import httpx
        token = None
        for c in self.storage.cookies:
            if c["name"] == "access_token":
                token = c["value"]
                break
        if not token:
            token = await self._refresh_access_token()
        if not token:
            return {"error": "No token"}
        url = f"https://web-api.onlinesoccermanager.com{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "AppVersion": "3.248.3", "PlatformId": "13",
            "Origin": "https://en.onlinesoccermanager.com",
            "Referer": "https://en.onlinesoccermanager.com/",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code in (401, 403):
                token = await self._refresh_access_token()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                    resp = await client.get(url, headers=headers, timeout=10)
            try:
                return resp.json()
            except Exception:
                return {"error": "Invalid JSON", "status": resp.status_code, "text": resp.text[:200]}

    # ------------------------------------------------------------------
    # Rate-limit detection (dual source)
    # ------------------------------------------------------------------
    async def _check_api_rate_limit(self) -> Optional[RateLimitInfo]:
        self._log("  [CHECK] API rate limit check...")
        body = await self._api_get("/api/v1/user/caps/actions/Shop/0")
        if "error" in body:
            self._log("  [CHECK] API error, skipping")
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
        self._log(f"⛔ RATE-LIMIT ({info.source}): Waiting {self._fmt_cooldown(info.cooldown_seconds)}")
        # Close all watcher tabs immediately
        await self._close_all_watchers()
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
    async def _open_watchers(self):
        self._log("[WATCHERS] Opening {} watcher tabs...".format(self.watcher_tabs))
        opened = 0
        for i in range(self.watcher_tabs):
            try:
                page = await self.context.new_page()
                await page.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_selector("#page-content", timeout=30000)
                await asyncio.sleep(2)
                self.watcher_pages.append(page)
                t = asyncio.create_task(self._watcher_loop(page, i))
                self._watcher_tasks.append(t)
                opened += 1
                self._log("[WATCHERS]   Tab {} opened and started".format(i))
            except Exception as e:
                self._log("[WATCHERS]   Tab {} failed: {}".format(i, e))
        self._log("[WATCHERS] {}/{} tabs ready".format(opened, self.watcher_tabs))

    async def _close_all_watchers(self):
        self._log("[WATCHERS] Closing all watcher tabs...")
        # Cancel background loops
        cancelled = 0
        for t in list(self._watcher_tasks):
            if not t.done():
                t.cancel()
                cancelled += 1
        self._watcher_tasks.clear()
        self._log("[WATCHERS]   {} loop(s) cancelled".format(cancelled))
        # Wait for cancel to propagate
        await asyncio.sleep(1)
        closed = 0
        for page in list(self.watcher_pages):
            try:
                if not page.is_closed():
                    await page.close()
                    closed += 1
            except Exception:
                pass
        self.watcher_pages.clear()
        self._log("[WATCHERS]   {}/{} tab(s) closed".format(closed, cancelled))
        # Double-check no stray pages
        all_pages = self.context.pages if self.context else []
        if len(all_pages) > 1:  # conductor + 0 watchters expected
            self._log("[WATCHERS]   {} total page(s) in context (conductor + watchers)".format(len(all_pages)))
        self._log("[WATCHERS] All watchers confirmed closed")

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
                ok = await self._watch_single_ad(page, tab_id)
                # Single-ad policy: close tab after every attempt
                self._log(f"{prefix} ▶ Closing tab...")
                try:
                    if not page.is_closed():
                        await page.close()
                        self._log(f"{prefix} ▶ Tab closed")
                except Exception as e:
                    self._log(f"{prefix} ! Close error: {e}")
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

    async def _watch_single_ad(self, page: Page, tab_id: int) -> bool:
        prefix = f"[W{tab_id}]"
        self._log(f"{prefix} ▶ Starting ad watch...")
        try:
            # Open shop
            self._log(f"{prefix}   Opening shop...")
            body = await page.query_selector("body.modal-open")
            if not body:
                wallet = await page.query_selector(SELECTORS["wallet_container"])
                if wallet:
                    await wallet.click()
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
            buttons = await page.query_selector_all(SELECTORS["watch_ad_btn"])
            if not buttons:
                self._log(f"{prefix}   ! No 'Watch ad' button found")
                return False
            self._log(f"{prefix}   Found {len(buttons)} button(s)")

            self._log(f"{prefix}   Clicking 'Watch ad'...")
            await buttons[0].click()
            await asyncio.sleep(2)
            self._log(f"{prefix}   Ad started")

            # Fake completion attempt
            self._log(f"{prefix}   Trying fake completion...")
            await page.evaluate("""
                () => {
                    if (window.invokeApplixirVideoUnit) {
                        try { window.invokeApplixirVideoUnit({zoneId:1989,devId:2999,gameId:4074,
                            userId:'965391039',status:'ad-watched',reward:true}); } catch(e){}
                    }
                    if (window.adinplay && window.adinplay.rewardedVideo) {
                        try { window.adinplay.rewardedVideo.onAdRewarded(); } catch(e){}
                    }
                    ['applixirAdCompleted','adCompleted','rewardedAdCompleted','videoFinished']
                        .forEach(n => { try { document.dispatchEvent(new Event(n, {bubbles:true})); } catch(e){} });
                }
            """)
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
                self.stats["watched"] += 1
                self._log(f"{prefix} ✅ REWARD CONFIRMED (total watched: {self.stats['watched']})")
                return True

            # No reward yet — wait real ad duration
            self._log(f"{prefix}   No reward yet. Waiting {self.ad_duration}s for real ad...")
            await asyncio.sleep(self.ad_duration)
            self._log(f"{prefix}   Ad wait complete")

            # Try fake again
            self._log(f"{prefix}   Retrying fake completion...")
            await page.evaluate("""
                () => {
                    if (window.invokeApplixirVideoUnit) {
                        try { window.invokeApplixirVideoUnit({zoneId:1989,devId:2999,gameId:4074,
                            userId:'965391039',status:'ad-watched',reward:true}); } catch(e){}
                    }
                }
            """)
            await asyncio.sleep(3)

            # Final check
            self._log(f"{prefix}   Final reward check...")
            try:
                reward = await page.query_selector(".modal-dialog .reward-container, .consumable-image-tile")
                if reward:
                    self.stats["watched"] += 1
                    self._log(f"{prefix} ✅ REWARD AFTER WAIT (total watched: {self.stats['watched']})")
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
    async def _scout_check(self) -> bool:
        """Open 1 scout tab, try to watch an ad, then check if rate-limit appeared.
        Returns True if ad was watched AND no rate-limit after watching.
        Returns False if rate-limited (will wait cooldown)."""
        self._log("[SCOUT] Step 1/3: Opening scout tab...")
        scout = await self.context.new_page()
        try:
            await scout.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
            await scout.wait_for_selector("#page-content", timeout=30000)
            await asyncio.sleep(2)
            
            self._log("[SCOUT] Step 2/3: Watching 1 ad to test rate-limit...")
            ok = await self._watch_single_ad(scout, tab_id=99)  # 99 = scout
            
            self._log("[SCOUT] Step 3/3: Checking rate-limit AFTER ad...")
            if not scout.is_closed():
                await scout.close()
            
            # CRITICAL: Check rate-limit AFTER watching the ad
            api_limit = await self._check_api_rate_limit()
            if api_limit:
                self._log("[SCOUT] ⛔ Rate-limit ACTIVE after ad (cooldown: {}).".format(
                    self._fmt_cooldown(api_limit.cooldown_seconds)))
                await self._wait_rate_limit(api_limit)
                return False
            
            if ok:
                self._log("[SCOUT] ✅ Ad watched + NO rate-limit after. Safe to open watchers.")
                return True
            else:
                self._log("[SCOUT] ⚠️ Ad failed but no rate-limit. Will retry scout.")
                return False
                
        except Exception as e:
            self._log("[SCOUT] ! Error: {}".format(e))
            try:
                if not scout.is_closed():
                    await scout.close()
            except Exception:
                pass
            return False

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
        
        while not self._should_stop():
            self.stats["cycles"] += 1
            self._log("")
            self._log("═══════════════════════════════════════════")
            self._log("  CYCLE #{}".format(self.stats['cycles']))
            self._log("  Watched so far: {} | Errors: {}".format(self.stats['watched'], self.stats['errors']))
            self._log("═══════════════════════════════════════════")

            # STEP 1: Scout check — 1 tab ile rate-limit test et
            scout_ok = await self._scout_check()
            
            if not scout_ok:
                # Rate-limit active, already waited in _scout_check
                self._log("[CYCLE] Scout reported rate-limit. Looping back to scout check...")
                continue
            
            # STEP 2: Rate-limit YOK — tüm watcher tablarını aç
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
                
                self._log("[POLL #{}] ✅ {} watcher(s) still running. Watched: {}".format(
                    poll_count, len(self.watcher_pages), self.stats['watched']))
            
            # STEP 4: Watcher'lar kapandı veya rate-limit geldi
            # STEP 4b: Tüm watcher tabların kapandığından emin ol
            if self.watcher_pages or self._watcher_tasks:
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
                        try:
                            if not p.is_closed():
                                await p.close()
                        except Exception:
                            pass
                    self.watcher_pages.clear()
            
            self._log("[CYCLE] ✅ All watchers confirmed closed. {} ads watched this cycle.".format(
                self.stats['watched']))
            
            # STEP 5: 5 dk bekle, sonra tekrar scout check
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
            await self._conductor_loop()

    def print_summary(self):
        self._log("")
        self._log("═══════════════════════════════════════════")
        self._log("           FINAL SUMMARY")
        self._log("═══════════════════════════════════════════")
        self._log("  Total Cycles      : {}".format(self.stats['cycles']))
        self._log("  Ads Watched       : {}".format(self.stats['watched']))
        self._log("  Errors            : {}".format(self.stats['errors']))
        self._log("  BossCoins Earned  : ~{}".format(self.stats['watched']))
        self._log("  End Time          : {}".format(datetime.now().isoformat()))
        self._log("═══════════════════════════════════════════")

    def shutdown(self, signum, frame):
        self._log("Shutdown signal received")
        self._shutdown = True


def main():
    parser = argparse.ArgumentParser(description="OSM Ad Watcher — Conductor Edition")
    parser.add_argument("--dump", required=True, help="Path to StorageDump directory")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--watcher-tabs", type=int, default=1,
                        help="Number of watcher tabs to open after cooldown (max 9)")
    parser.add_argument("--poll-interval", type=int, default=30,
                        help="Seconds between conductor polls (default 30)")
    parser.add_argument("--ad-duration", type=int, default=30,
                        help="Seconds to wait for real ad to finish")
    parser.add_argument("--log", help="Log file path")
    args = parser.parse_args()

    bot = OSMConductorBot(
        dump_dir=args.dump,
        headless=args.headless,
        watcher_tabs=args.watcher_tabs,
        poll_interval=args.poll_interval,
        ad_duration=args.ad_duration,
        log_file=args.log,
    )

    signal.signal(signal.SIGINT, bot.shutdown)
    signal.signal(signal.SIGTERM, bot.shutdown)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass
    finally:
        bot.print_summary()
        if bot.log_file and hasattr(bot, '_log_fp'):
            bot._log_fp.close()


if __name__ == "__main__":
    main()
