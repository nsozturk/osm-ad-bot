import unittest

from osm_ad_bot_conductor import OSMConductorBot


class FakePage:
    def __init__(self, read_results=None, install_result=True):
        self.url = "https://en.onlinesoccermanager.com/Training"
        self.closed = False
        self.read_results = list(read_results or [])
        self.install_result = install_result
        self.scripts = []
        self.goto_calls = []

    def is_closed(self):
        return self.closed

    async def evaluate(self, script):
        self.scripts.append(script)
        if "const q = window.__osm_toast_queue" in script:
            result = self.read_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        if isinstance(self.install_result, Exception):
            raise self.install_result
        return self.install_result

    async def goto(self, url):
        self.goto_calls.append(url)
        self.url = url


def make_bot(page):
    bot = object.__new__(OSMConductorBot)
    bot.conductor_page = page
    bot.context = None
    bot.logs = []
    bot._log = bot.logs.append
    bot._dom_check_warning_active = False
    bot._dom_observer_warning_active = False
    bot.auto_training = False
    return bot


class ConductorDomQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_park_keeps_osm_page_awake_for_automatic_training(self):
        page = FakePage()
        bot = make_bot(page)
        bot.auto_training = True

        await bot._park_conductor()

        self.assertEqual(page.goto_calls, [])
        self.assertTrue(page.url.startswith("https://en.onlinesoccermanager.com"))

    async def test_park_uses_blank_page_without_automatic_training(self):
        page = FakePage()
        bot = make_bot(page)

        await bot._park_conductor()

        self.assertEqual(page.goto_calls, ["about:blank"])
        self.assertEqual(page.url, "about:blank")

    async def test_missing_queue_reinstalls_observer_without_crashing(self):
        page = FakePage([{"ready": False, "value": None}])
        bot = make_bot(page)

        self.assertIsNone(await bot._read_dom_cooldown())

        self.assertEqual(len(page.scripts), 2)
        self.assertIn("MutationObserver", page.scripts[1])
        self.assertTrue(any("restored after page reload" in line for line in bot.logs))

    async def test_empty_queue_returns_none_without_reinstall(self):
        page = FakePage([{"ready": True, "value": None}])
        bot = make_bot(page)

        self.assertIsNone(await bot._read_dom_cooldown())
        self.assertEqual(len(page.scripts), 1)

    async def test_populated_queue_returns_maximum_and_read_script_clears_it(self):
        page = FakePage([{"ready": True, "value": 13}])
        bot = make_bot(page)

        self.assertEqual(await bot._read_dom_cooldown(), 13)
        self.assertIn("q.length = 0", page.scripts[0])
        self.assertIn("Math.max", page.scripts[0])

    async def test_transient_evaluate_error_is_nonfatal_and_self_heals(self):
        page = FakePage([RuntimeError("Execution context was destroyed")])
        bot = make_bot(page)

        self.assertIsNone(await bot._read_dom_cooldown())

        self.assertEqual(len(page.scripts), 2)
        self.assertIn("MutationObserver", page.scripts[1])
        self.assertTrue(any("self-healing" in line for line in bot.logs))

    async def test_observer_install_is_idempotent_in_javascript_contract(self):
        page = FakePage()
        bot = make_bot(page)

        self.assertTrue(await bot._start_mutation_observer())
        self.assertTrue(await bot._start_mutation_observer())

        for script in page.scripts:
            self.assertIn("existing.disconnect()", script)
            self.assertIn("Array.isArray(window.__osm_toast_queue)", script)
            self.assertIn("window.__osm_toast_observer = observer", script)
            self.assertIn("window.__osm_toast_observer_body = document.body", script)

    async def test_observer_install_error_is_nonfatal(self):
        page = FakePage(install_result=RuntimeError("navigation interrupted"))
        bot = make_bot(page)

        self.assertFalse(await bot._start_mutation_observer())
        self.assertTrue(any("observer unavailable" in line for line in bot.logs))


if __name__ == "__main__":
    unittest.main()
