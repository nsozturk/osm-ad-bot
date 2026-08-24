import json
import unittest
import zipfile
from pathlib import Path

from storage_loader import StorageLoader


class StorageLoaderZipTests(unittest.TestCase):
    def test_zip_layout_loads_without_extracting_credentials(self):
        root = Path("tmp")
        root.mkdir(exist_ok=True)
        archive_path = root / "test-storage-loader.zip"
        cookies = {
            "data": [{
                "key": "access_token",
                "value": "test-value-never-logged",
                "metadata": {
                    "domain": "en.onlinesoccermanager.com",
                    "path": "/",
                    "secure": True,
                },
            }]
        }
        local = [{
            "key": "TeamTrainings_123_4",
            "value": {"example": True},
            "metadata": {"origin": "https://en.onlinesoccermanager.com"},
        }]
        try:
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("cookies.json", json.dumps(cookies))
                archive.writestr("local/part-0.json", json.dumps(local))
            loader = StorageLoader(str(archive_path))
        finally:
            archive_path.unlink(missing_ok=True)

        self.assertEqual(len(loader.cookies), 1)
        self.assertEqual(loader.cookies[0]["name"], "access_token")
        self.assertEqual(loader.local_storage[0]["key"], "TeamTrainings_123_4")
        self.assertFalse((root / "cookies.json").exists())


class FakeInjectionPage:
    def __init__(self, error):
        self.error = error
        self.closed = False

    async def goto(self, *_args, **_kwargs):
        raise self.error

    async def evaluate(self, _script):
        raise AssertionError("evaluate must not run after navigation failure")

    async def close(self):
        self.closed = True


class FakeInjectionContext:
    def __init__(self, pages):
        self.pages = list(pages)
        self.new_page_calls = 0

    async def add_cookies(self, _cookies):
        return None

    async def new_page(self):
        self.new_page_calls += 1
        return self.pages.pop(0)


class StorageLoaderInjectionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_osm_storage_origins_are_skipped_without_opening_pages(self):
        context = FakeInjectionContext([])
        loader = object.__new__(StorageLoader)
        loader.cookies = []
        loader.local_storage = [{
            "origin": "https://www.google.com",
            "key": "local-key",
            "value": "local-value",
        }]
        loader.session_storage = [{
            "origin": "https://doubleclick.net",
            "key": "session-key",
            "value": "session-value",
        }]

        await loader.inject(context)

        self.assertEqual(context.new_page_calls, 0)

    async def test_failed_local_and_session_origins_close_temporary_pages(self):
        local_page = FakeInjectionPage(RuntimeError("local navigation failed"))
        session_page = FakeInjectionPage(RuntimeError("session navigation failed"))
        context = FakeInjectionContext([local_page, session_page])
        loader = object.__new__(StorageLoader)
        loader.cookies = []
        loader.local_storage = [{
            "origin": "https://local.onlinesoccermanager.com",
            "key": "local-key",
            "value": "local-value",
        }]
        loader.session_storage = [{
            "origin": "https://session.onlinesoccermanager.com",
            "key": "session-key",
            "value": "session-value",
        }]

        await loader.inject(context)

        self.assertTrue(local_page.closed)
        self.assertTrue(session_page.closed)


if __name__ == "__main__":
    unittest.main()
