import asyncio
import unittest
from unittest.mock import patch

from osm_ad_bot_conductor import OSMConductorBot


class FakePage:
    def __init__(self, *, goto_error=None, selector_error=None):
        self.goto_error = goto_error
        self.selector_error = selector_error
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


class WatcherCleanupLifecycleTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
