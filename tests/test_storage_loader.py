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


if __name__ == "__main__":
    unittest.main()
