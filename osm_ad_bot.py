#!/usr/bin/env python3
"""
OSM Ad Watcher Bot — Continuous Scheduler Edition
==================================================
- Always-on daemon that adjusts timing based on server rate-limit responses.
- All tabs share a single global cooldown tracker.
- Tabs are muted and can run in headless or headed mode.
- Supports up to 9 parallel tabs (browser allows 9 concurrent videos).
"""
import argparse
import asyncio
import base64
import json
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page, Response

from storage_loader import StorageLoader

# Configuration
OSM_ORIGIN = "https://en.onlinesoccermanager.com"
OSM_TRAINING = f"{OSM_ORIGIN}/Training"
API_BASE = "https://web-api.onlinesoccermanager.com/api"

SELECTORS = {
    "wallet_container": ".wallet-container.bosscoin-wallet",
    "shop_modal": "#products-partial",
    "watch_ad_btn": ".product-free",
    "watch_ad_text": ".payment-option-price",
    "ad_modal": ".modal-dialog",
    "ad_video_container": "#applixir_vanishing_div",
}


@dataclass
class CapStatus:
    is_cap_reached: bool = True
    is_claimable: bool = False
    timestamp_until_unreached: Optional[int] = None
    current_count: int = 0
    threshold: int = 10

    @property
    def cooldown_seconds(self) -> int:
        if self.timestamp_until_unreached:
            return max(0, self.timestamp_until_unreached - int(time.time()))
        return 0

    def __str__(self) -> str:
        if self.is_cap_reached:
            mins, secs = divmod(self.cooldown_seconds, 60)
            return f"CAP ({self.current_count}/{self.threshold}) — next in {mins}m {secs}s"
        return f"OK ({self.current_count}/{self.threshold})"


class CooldownTracker:
    """Shared cooldown state across all tabs."""
    def __init__(self):
        self._until: int = 0          # Unix timestamp when cooldown ends
        self._lock = asyncio.Lock()

    async def wait_if_needed(self, shutdown_check):
        async with self._lock:
            now = int(time.time())
            if self._until > now:
                wait = self._until - now
        if self._until > now:
            mins, secs = divmod(wait, 60)
            print(f"[SYNC] Global cooldown active — sleeping {mins}m {secs}s ...")
            while wait > 0 and not shutdown_check():
                chunk = min(10, wait)
                await asyncio.sleep(chunk)
                wait -= chunk
                async with self._lock:
                    if self._until <= int(time.time()):
                        break

    async def set(self, timestamp: int):
        async with self._lock:
            if timestamp > self._until:
                self._until = timestamp
                print(f"[SYNC] Global cooldown updated until {datetime.fromtimestamp(timestamp).isoformat()}")

    def is_active(self) -> bool:
        return self._until > int(time.time())


class OSMAdBot:
    def __init__(self, dump_dir: str, headless: bool = False, tabs: int = 1,
                 ad_duration: int = 30, log_file: Optional[str] = None):
        self.dump_dir = dump_dir
        self.headless = headless
        self.max_tabs = min(tabs, 9)
        self.ad_duration = ad_duration
        self.log_file = log_file
        self.context: Optional[BrowserContext] = None
        self.pages: list[Page] = []
        self.storage = StorageLoader(dump_dir)
        # Account id derived from the loaded dump's token — never hardcoded.
        self.user_id = self._extract_user_id()
        self.stats = {"watched": 0, "errors": 0, "cooldowns": 0}
        self._shutdown = False
        self._cooldown = CooldownTracker()
        self._last_report = 0

        # Logging
        if log_file:
            self._log_fp = open(log_file, "a", buffering=1)
            sys.stdout = self._log_fp
            sys.stderr = self._log_fp

    def _should_stop(self) -> bool:
        return self._shutdown

    async def _on_response(self, response: Response):
        url = response.url
        try:
            if "/api/v1.1/user/videos/start" in url:
                body = await response.json()
                print(f"[API] videos/start -> {json.dumps(body, ensure_ascii=False)}")
            elif "/user/caps/actions/" in url:
                body = await response.json()
                print(f"[API] caps/actions -> {json.dumps(body, ensure_ascii=False)}")
            elif "/user/caps/counters/" in url:
                body = await response.json()
                print(f"[API] caps/counters -> {json.dumps(body, ensure_ascii=False)}")
        except Exception:
            pass

    async def _create_context(self, playwright):
        print("[+] Launching browser...")
        browser = await playwright.chromium.launch(
            headless=self.headless,
            args=["--mute-audio", "--no-sandbox"]
        )
        print(f"[+] Browser launched (headless={self.headless}, audio=muted, tabs={self.max_tabs})")
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            locale="en-GB",
        )
        context.on("response", lambda r: asyncio.create_task(self._on_response(r)))
        return context

    async def _inject_storage(self):
        print("[+] Injecting cookies & storage...")
        try:
            await self.storage.inject(self.context)
            print("[+] Cookies & storage injected successfully")
        except Exception as e:
            print(f"[!] Storage injection error: {e}")
            raise

    async def _open_training(self, page: Page, tab_id: int):
        print(f"[Tab{tab_id}] Opening {OSM_TRAINING}")
        await page.goto(OSM_TRAINING, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#page-content", timeout=30000)
        await asyncio.sleep(3)
        print(f"[Tab{tab_id}] Training page ready")

    def _get_refresh_token(self) -> Optional[str]:
        for c in self.storage.cookies:
            if c["name"] == "refresh_token":
                return c["value"]
        return None

    async def _refresh_access_token(self) -> Optional[str]:
        import httpx
        refresh = self._get_refresh_token()
        if not refresh:
            print("[!] No refresh_token cookie found")
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://web-api.onlinesoccermanager.com/api/tokenRefresh",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": "jPs3vVbg4uYnxGoyunSiNf1nIqUJmSFnpqJSVgWrJleu6Ak7Ga",
                        "client_secret": "ePOVDMfAvU8zcyfaxLMtqYSmND3n6vmmKx9ZlVnNGjGkzucMCt",
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
                    # Update internal cookie store
                    found = False
                    for c in self.storage.cookies:
                        if c["name"] == "access_token":
                            c["value"] = new_token
                            found = True
                            break
                    if not found:
                        self.storage.cookies.append({
                            "name": "access_token",
                            "value": new_token,
                            "domain": "en.onlinesoccermanager.com",
                            "path": "/",
                            "httpOnly": False,
                            "secure": True,
                            "sameSite": "None",
                        })
                    # Update browser
                    await self.context.add_cookies([{
                        "name": "access_token",
                        "value": new_token,
                        "domain": "en.onlinesoccermanager.com",
                        "path": "/",
                        "httpOnly": False,
                        "secure": True,
                        "sameSite": "None",
                    }])
                    print("[+] Access token refreshed")
                    return new_token
                else:
                    print(f"[!] Token refresh failed: {data}")
                    return None
        except Exception as e:
            print(f"[!] Token refresh error: {e}")
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
            "AppVersion": "3.248.3",
            "PlatformId": "13",
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

    async def _get_cap_status(self) -> CapStatus:
        body = await self._api_get("/api/v1/user/caps/actions/Shop/0")
        print(f"[API] caps/actions -> {json.dumps(body, ensure_ascii=False)}")
        if "error" in body:
            print(f"[!] Cap check API error: {body}")
            return CapStatus(True, False, None, 0, 10)
        return CapStatus(
            is_cap_reached=body.get("isCapReached", True),
            is_claimable=body.get("isClaimable", False),
            timestamp_until_unreached=body.get("timestampUntilUnreached"),
            current_count=body.get("currentCount", body.get("current", 0)),
            threshold=body.get("threshold", 10),
        )

    async def _open_shop(self, page: Page, tab_id: int):
        body = await page.query_selector("body.modal-open")
        if body:
            return
        wallet = await page.query_selector(SELECTORS["wallet_container"])
        if not wallet:
            raise RuntimeError("Wallet container not found")
        await wallet.click()
        try:
            await page.wait_for_selector("body.modal-open", timeout=15000)
            print(f"[Tab{tab_id}] Shop opened")
        except Exception:
            try:
                await page.wait_for_selector(".modal.fade.in .modal-dialog", timeout=5000)
            except Exception:
                pass
        await asyncio.sleep(2)

    async def _find_watch_ad_buttons(self, page: Page) -> list:
        buttons = await page.query_selector_all(SELECTORS["watch_ad_btn"])
        print(f"[+] Found {len(buttons)} 'Watch ad' button(s)")
        return buttons

    async def _click_watch_ad(self, page: Page, button) -> bool:
        try:
            await button.click()
            await asyncio.sleep(2)
            return True
        except Exception as e:
            print(f"[!] Click failed: {e}")
            return False

    def _extract_user_id(self) -> str:
        """Derive the logged-in account id from the dump's token (JWT `sub`),
        so no account id is ever hardcoded. Stable even if the token expired."""
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

    async def _attempt_fake_ad_completion(self, page: Page) -> bool:
        try:
            result = await page.evaluate("""
                (uid) => {
                    const results = [];
                    if (window.invokeApplixirVideoUnit) {
                        try {
                            window.invokeApplixirVideoUnit({zoneId: 1989, devId: 2999, gameId: 4074,
                                userId: uid, status: 'ad-watched', reward: true});
                            results.push('invokeApplixirVideoUnit called');
                        } catch(e) { results.push('invokeApplixirVideoUnit error: ' + e.message); }
                    }
                    if (window.adinplay && window.adinplay.rewardedVideo) {
                        try {
                            window.adinplay.rewardedVideo.onAdRewarded();
                            results.push('adinplay.rewardedVideo.onAdRewarded called');
                        } catch(e) { results.push('adinplay error: ' + e.message); }
                    }
                    if (window.googletag && window.googletag.apiReady) {
                        try {
                            window.googletag.pubads().setTargeting('reward', 'granted');
                            results.push('googletag reward targeting set');
                        } catch(e) { results.push('googletag error: ' + e.message); }
                    }
                    if (window.appViewModel) {
                        try {
                            if (typeof window.appViewModel.completeVideo === 'function') {
                                window.appViewModel.completeVideo();
                                results.push('appViewModel.completeVideo called');
                            }
                            if (typeof window.appViewModel.onVideoCompleted === 'function') {
                                window.appViewModel.onVideoCompleted();
                                results.push('appViewModel.onVideoCompleted called');
                            }
                            if (typeof window.appViewModel.claimWatchAdsReward === 'function') {
                                window.appViewModel.claimWatchAdsReward();
                                results.push('appViewModel.claimWatchAdsReward called');
                            }
                        } catch(e) { results.push('appViewModel error: ' + e.message); }
                    }
                    const events = ['applixirAdCompleted', 'adCompleted', 'rewardedAdCompleted', 'videoFinished'];
                    events.forEach(evtName => {
                        try { document.dispatchEvent(new Event(evtName, { bubbles: true }));
                              results.push('dispatched ' + evtName); } catch(e) {}
                    });
                    return results;
                }
            """, self.user_id)
            print(f"[JS] {result}")
            await asyncio.sleep(3)
            return True
        except Exception as e:
            print(f"[!] Fake completion failed: {e}")
            return False

    async def _wait_for_reward_confirmation(self, page: Page, timeout: int = 15) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                reward_modal = await page.query_selector(".modal-dialog .reward-container, .consumable-image-tile")
                if reward_modal:
                    return True
                wallet_el = await page.query_selector(".wallet-amount span.pull-left")
                if wallet_el:
                    await wallet_el.inner_text()
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def _close_any_modal(self, page: Page):
        try:
            for btn in await page.query_selector_all(".modal-dialog .close, .modal-header .close"):
                await btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

    async def _watch_single_ad(self, page: Page, tab_id: int = 0) -> bool:
        prefix = f"[Tab{tab_id}]"
        print(f"{prefix} === Cycle start ===")

        if self._should_stop():
            return False

        # Shared cooldown check
        await self._cooldown.wait_if_needed(self._should_stop)
        if self._should_stop():
            return False

        # Server cap check
        cap = await self._get_cap_status()
        print(f"{prefix} Server says: {cap}")
        if cap.is_cap_reached and not cap.is_claimable:
            self.stats["cooldowns"] += 1
            if cap.timestamp_until_unreached:
                await self._cooldown.set(cap.timestamp_until_unreached)
            return False

        try:
            await self._open_shop(page, tab_id)
        except Exception as e:
            print(f"{prefix} Shop open error: {e}")
            return False

        buttons = await self._find_watch_ad_buttons(page)
        if not buttons:
            print(f"{prefix} No 'Watch ad' button found")
            await self._close_any_modal(page)
            return False

        if not await self._click_watch_ad(page, buttons[0]):
            await self._close_any_modal(page)
            return False

        await asyncio.sleep(5)

        # Try fake
        await self._attempt_fake_ad_completion(page)
        if await self._wait_for_reward_confirmation(page, timeout=10):
            self.stats["watched"] += 1
            print(f"{prefix} [SUCCESS] Reward confirmed (fake)")
            await self._close_any_modal(page)
            return True

        # Wait real ad
        print(f"{prefix} Waiting {self.ad_duration}s for real ad...")
        await asyncio.sleep(self.ad_duration)

        # Try fake again
        await self._attempt_fake_ad_completion(page)
        if await self._wait_for_reward_confirmation(page, timeout=10):
            self.stats["watched"] += 1
            print(f"{prefix} [SUCCESS] Reward confirmed after wait")
            await self._close_any_modal(page)
            return True

        print(f"{prefix} [FAIL] No reward")
        await self._close_any_modal(page)
        self.stats["errors"] += 1
        return False

    async def _tab_worker(self, page: Page, tab_id: int):
        """Continuous worker for a single tab."""
        while not self._should_stop():
            try:
                ok = await self._watch_single_ad(page, tab_id)
                if not ok:
                    # If no success, short retry after shared cooldown is handled inside _watch_single_ad
                    await asyncio.sleep(5)
                else:
                    # Small pause between successful watches
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"[Tab{tab_id}] Loop error: {e}")
                self.stats["errors"] += 1
                await asyncio.sleep(10)

    async def _reporter(self):
        """Periodic status report every 5 minutes."""
        while not self._should_stop():
            await asyncio.sleep(300)
            if self._should_stop():
                break
            watched = self.stats["watched"]
            cooldowns = self.stats["cooldowns"]
            errors = self.stats["errors"]
            print(f"\n[REPORT] watched={watched} | cooldowns={cooldowns} | errors={errors} | cooldown_active={self._cooldown.is_active()}\n")

    async def run(self):
        async with async_playwright() as p:
            self.context = await self._create_context(p)
            await self._inject_storage()

            # Spawn tabs
            print(f"[+] Spawning {self.max_tabs} tab(s)...")
            for i in range(self.max_tabs):
                page = await self.context.new_page()
                await self._open_training(page, i)
                self.pages.append(page)
                await asyncio.sleep(1)

            # Run workers + reporter concurrently
            tasks = [self._tab_worker(page, i) for i, page in enumerate(self.pages)]
            tasks.append(self._reporter())
            await asyncio.gather(*tasks)

    def print_summary(self):
        print("\n=== OSM Ad Bot Summary ===")
        print(f"Ads watched : {self.stats['watched']}")
        print(f"Cooldowns   : {self.stats['cooldowns']}")
        print(f"Errors      : {self.stats['errors']}")
        print(f"Time        : {datetime.now().isoformat()}")

    def shutdown(self, signum, frame):
        print("\n[!] Shutdown signal received, stopping...")
        self._shutdown = True


def main():
    parser = argparse.ArgumentParser(description="OSM Ad Watcher Bot — Continuous Scheduler")
    parser.add_argument("--dump", required=True, help="Path to StorageDump directory")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--tabs", type=int, default=1, help="Number of tabs (max 9)")
    parser.add_argument("--ad-duration", type=int, default=30, help="Seconds to wait for ad finish")
    parser.add_argument("--log", help="Log file path (optional)")
    args = parser.parse_args()

    bot = OSMAdBot(args.dump, headless=args.headless, tabs=args.tabs,
                   ad_duration=args.ad_duration, log_file=args.log)

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
