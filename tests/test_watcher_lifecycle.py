import asyncio
import unittest
from unittest.mock import patch

from osm_ad_bot_conductor import OSMConductorBot


class FakePage:
    def __init__(self, *, goto_error=None, selector_error=None, url="https://en.onlinesoccermanager.com/Training"):
        self.goto_error = goto_error
        self.selector_error = selector_error
        self.url = url
        self.closed = False
        self.close_calls = 0

    async def goto(self, *_args, **_kwargs):
        if self.goto_error:
            raise self.goto_error

    async def wait_for_selector(self, *_args, **_kwargs):
        if self.selector_error:
            raise self.selector_error

    async def close(self):
        self.close_calls += 1
        self.closed = True

    def is_closed(self):
        return self.closed


class FakeContext:
    def __init__(self, pages):
        self._pages = list(pages)
        self._new_pages = list(pages)

    async def new_page(self):
        return self._new_pages.pop(0)

    @property
    def pages(self):
        return [page for page in self._pages if not page.closed]


def make_bot(context, *, watcher_tabs=1, conductor=None):
    bot = object.__new__(OSMConductorBot)
    bot.context = context
    bot.conductor_page = conductor
    bot.watcher_tabs = watcher_tabs
    bot.watcher_pages = []
    bot._watcher_tasks = []
    bot.logs = []
    bot._log = bot.logs.append
    return bot


class WatcherOpenLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_creation_timeout_does_not_block_remaining_slots(self):
        class HangingContext:
            async def new_page(self):
                await asyncio.Event().wait()

        bot = make_bot(HangingContext())

        await bot._open_watchers(page_create_timeout=0.01)

        self.assertEqual(bot.watcher_pages, [])
        self.assertEqual(bot._watcher_tasks, [])
        self.assertTrue(any("Tab 0 failed" in line for line in bot.logs))

    async def test_navigation_failure_closes_untracked_page(self):
        page = FakePage(goto_error=RuntimeError("navigation failed"))
        bot = make_bot(FakeContext([page]))

        await bot._open_watchers()

        self.assertTrue(page.closed)
        self.assertEqual(page.close_calls, 1)
        self.assertEqual(bot.watcher_pages, [])
        self.assertEqual(bot._watcher_tasks, [])

    async def test_selector_failure_closes_untracked_page(self):
        page = FakePage(selector_error=RuntimeError("content missing"))
        bot = make_bot(FakeContext([page]))

        with patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None):
            await bot._open_watchers()

        self.assertTrue(page.closed)
        self.assertEqual(page.close_calls, 1)
        self.assertEqual(bot.watcher_pages, [])

    async def test_successful_open_transfers_page_to_watcher_task(self):
        page = FakePage()
        bot = make_bot(FakeContext([page]))

        class FakeTask:
            pass

        def create_task(coroutine):
            coroutine.close()
            return FakeTask()

        with (
            patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None),
            patch("osm_ad_bot_conductor.asyncio.create_task", side_effect=create_task),
        ):
            await bot._open_watchers()

        self.assertFalse(page.closed)
        self.assertEqual(bot.watcher_pages, [page])
        self.assertEqual(len(bot._watcher_tasks), 1)

    async def test_all_pages_are_prepared_before_any_watcher_task_starts(self):
        pages = [FakePage(), FakePage()]
        bot = make_bot(FakeContext(pages), watcher_tabs=2)
        prepared_counts = []

        class FakeTask:
            pass

        def create_task(coroutine):
            coroutine.close()
            prepared_counts.append(len(bot.watcher_pages))
            return FakeTask()

        with (
            patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None),
            patch("osm_ad_bot_conductor.asyncio.create_task", side_effect=create_task),
        ):
            await bot._open_watchers()

        self.assertEqual(prepared_counts, [2, 2])


class ConductorStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_readiness_failure_retries_once_with_a_fresh_page(self):
        timed_out = FakePage(selector_error=TimeoutError("page content not ready"))
        ready = FakePage()
        bot = make_bot(FakeContext([timed_out, ready]))
        bot._record_daily_metric = lambda _event: None

        async def dismiss_consent(*_args):
            return None

        bot._dismiss_consent = dismiss_consent

        with patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None):
            await bot._open_conductor()

        self.assertTrue(timed_out.closed)
        self.assertIs(bot.conductor_page, ready)
        self.assertTrue(any("retrying once" in line for line in bot.logs))

    async def test_login_redirect_does_not_retry(self):
        logged_out = FakePage(
            selector_error=TimeoutError("page content not ready"),
            url="https://en.onlinesoccermanager.com/login",
        )
        bot = make_bot(FakeContext([logged_out]))
        bot._record_daily_metric = lambda _event: None

        with self.assertRaisesRegex(RuntimeError, "StorageDump session is no longer valid"):
            await bot._open_conductor()

        self.assertFalse(logged_out.closed)


class WatcherCleanupLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_timeout_does_not_cancel_background_cleanup(self):
        started = asyncio.Event()
        allow_close = asyncio.Event()

        class SlowClosePage(FakePage):
            async def close(self):
                self.close_calls += 1
                started.set()
                await allow_close.wait()
                self.closed = True

        page = SlowClosePage()
        bot = make_bot(FakeContext([page]))

        close_result = await bot._close_page_bounded(
            page, "slow close", timeout=0.01
        )

        self.assertFalse(close_result)
        await started.wait()
        self.assertFalse(page.closed)
        allow_close.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(page.closed)
        self.assertEqual(bot._pending_page_close_tasks, set())

    async def test_hanging_page_close_times_out_without_blocking(self):
        class HangingClosePage(FakePage):
            async def close(self):
                self.close_calls += 1
                await asyncio.Event().wait()

        page = HangingClosePage()
        bot = make_bot(FakeContext([page]))

        closed = await bot._close_page_bounded(page, "hanging test", timeout=0.01)

        self.assertFalse(closed)
        self.assertEqual(page.close_calls, 1)
        self.assertTrue(any("hanging test close timeout" in line for line in bot.logs))

    async def test_hanging_ad_attempt_times_out_without_blocking(self):
        page = FakePage()
        bot = make_bot(FakeContext([page]))
        bot.ad_duration = 120

        async def hang_forever(*_args):
            await asyncio.Event().wait()

        bot._watch_single_ad = hang_forever

        watched = await bot._watch_single_ad_bounded(page, 99, timeout=0.01)

        self.assertFalse(watched)
        self.assertTrue(any("ad attempt timeout" in line for line in bot.logs))

    async def test_cleanup_awaits_tasks_closes_tracked_and_stray_pages(self):
        conductor = FakePage()
        tracked = FakePage()
        stray = FakePage()
        context = FakeContext([conductor, tracked, stray])
        bot = make_bot(context, conductor=conductor)
        bot.watcher_pages = [tracked]
        task = asyncio.create_task(asyncio.Event().wait())
        bot._watcher_tasks = [task]

        with patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None):
            await bot._close_all_watchers()

        self.assertTrue(task.done())
        self.assertTrue(task.cancelled())
        self.assertTrue(tracked.closed)
        self.assertTrue(stray.closed)
        self.assertFalse(conductor.closed)
        self.assertEqual(context.pages, [conductor])
        self.assertEqual(bot.watcher_pages, [])
        self.assertEqual(bot._watcher_tasks, [])
        self.assertTrue(any("pages before=3" in line for line in bot.logs))
        self.assertTrue(any("after=1" in line for line in bot.logs))

    async def test_repeated_cleanup_preserves_conductor_only_baseline(self):
        conductor = FakePage()
        context = FakeContext([conductor])
        bot = make_bot(context, conductor=conductor)

        with patch("osm_ad_bot_conductor.asyncio.sleep", return_value=None):
            await bot._close_all_watchers()
            await bot._close_all_watchers()

        self.assertFalse(conductor.closed)
        self.assertEqual(context.pages, [conductor])

    async def test_inject_storage_refreshes_expiring_token(self):
        bot = object.__new__(OSMConductorBot)
        bot.logs = []
        bot._log = bot.logs.append
        bot.context = object()

        class FakeStorage:
            def __init__(self):
                self.cookies = [{"name": "access_token", "value": "old_expired"}]
                self.injected_context = None

            async def inject(self, context):
                self.injected_context = context

        bot.storage = FakeStorage()

        refresh_called = []
        async def fake_refresh(force=False):
            refresh_called.append(force)
            return "new_refreshed_token"

        bot._refresh_access_token = fake_refresh

        with patch("osm_ad_bot_conductor._token_expiring", return_value=True):
            await bot._inject_storage()

        self.assertEqual(refresh_called, [True])
        self.assertIs(bot.storage.injected_context, bot.context)
        self.assertTrue(any("Pre-emptively refreshed" in line for line in bot.logs))


if __name__ == "__main__":
    unittest.main()
