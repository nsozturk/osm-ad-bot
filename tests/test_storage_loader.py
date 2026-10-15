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


class FakeInjectionContext:
    def __init__(self):
        self.new_page_calls = 0
        self.init_scripts = []

    async def add_cookies(self, _cookies):
        return None

    async def new_page(self):
        self.new_page_calls += 1
        raise AssertionError("storage injection must not open temporary pages")

    async def add_init_script(self, *, script):
        self.init_scripts.append(script)


class StorageLoaderInjectionLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_osm_storage_origins_are_skipped_without_opening_pages(self):
        context = FakeInjectionContext()
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
        self.assertEqual(context.init_scripts, [])

    async def test_osm_storage_uses_init_script_without_temporary_pages(self):
        context = FakeInjectionContext()
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

        self.assertEqual(context.new_page_calls, 0)
        self.assertEqual(len(context.init_scripts), 1)
        self.assertIn("local-key", context.init_scripts[0])
        self.assertIn("session-key", context.init_scripts[0])
        self.assertIn("localStorage.setItem", context.init_scripts[0])
        self.assertIn("sessionStorage.setItem", context.init_scripts[0])

    async def test_wzrk_keys_are_filtered_from_local_storage(self):
        context = FakeInjectionContext()
        loader = object.__new__(StorageLoader)
        loader.cookies = []
        loader.local_storage = [{
            "origin": "https://en.onlinesoccermanager.com",
            "key": "WZRK_INBOX",
            "value": "corrupt_data",
        }, {
            "origin": "https://en.onlinesoccermanager.com",
            "key": "valid_key",
            "value": "valid_value",
        }]
        loader.session_storage = []

        await loader.inject(context)

        self.assertEqual(len(context.init_scripts), 1)
        self.assertNotIn("WZRK_INBOX", context.init_scripts[0])
        self.assertIn("valid_key", context.init_scripts[0])


if __name__ == "__main__":
    unittest.main()
