"""Load and inject browser storage dumps into a Playwright context."""
import json
import urllib.parse
from pathlib import Path
from typing import Any

class StorageLoader:
    """Parses a StorageDump export and applies cookies/local/session storage."""

    def __init__(self, dump_dir: str):
        self.dump_dir = Path(dump_dir)
        self.cookies: list[dict] = []
        self.local_storage: list[dict] = []
        self.session_storage: list[dict] = []
        self._parse()

    def _parse(self):
        cookies_path = self.dump_dir / "cookies.json"
        local_path = self.dump_dir / "local.json"
        session_path = self.dump_dir / "session.json"

        if cookies_path.exists():
            with open(cookies_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("data", []):
                    meta = item.get("metadata", {})
                    def normalize_same_site(val):
                        if not val or val.lower() in ("unspecified", ""):
                            return "Lax"
                        if val.lower() == "no_restriction":
                            return "None"
                        if val.lower() in ("strict", "lax", "none"):
                            return val.capitalize()
                        return "Lax"

                    cookie = {
                        "name": item["key"],
                        "value": item["value"],
                        "domain": meta.get("domain", ""),
                        "path": meta.get("path", "/"),
                        "httpOnly": meta.get("httpOnly", False),
                        "secure": meta.get("secure", False),
                        "sameSite": normalize_same_site(meta.get("sameSite")),
                    }
                    exp = meta.get("expirationDate")
                    if exp:
                        cookie["expires"] = exp
                    if meta.get("session", False):
                        cookie.pop("expires", None)
                    self.cookies.append(cookie)

        def parse_storage(path: Path):
            items = []
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("data", []):
                        origin = item.get("metadata", {}).get("origin", "https://en.onlinesoccermanager.com")
                        key = item["key"]
                        value = item["value"]
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value)
                        else:
                            value = str(value)
                        items.append({"origin": origin, "key": key, "value": value})
            return items

        self.local_storage = parse_storage(local_path)
        self.session_storage = parse_storage(session_path)

    async def inject(self, context):
        """Inject cookies and storage into a Playwright BrowserContext."""
        if self.cookies:
            await context.add_cookies(self.cookies)

        # Group storage items by origin to minimise page creation
        origins_local: dict[str, list[dict]] = {}
        for item in self.local_storage:
            origins_local.setdefault(item["origin"], []).append(item)

        for origin, items in origins_local.items():
            if not origin or origin == "null":
                continue
            try:
                page = await context.new_page()
                await page.goto(origin, wait_until="domcontentloaded")
                script = ""
                for it in items:
                    k = json.dumps(it["key"])
                    v = json.dumps(it["value"])
                    script += f"try {{ localStorage.setItem({k}, {v}); }} catch(e) {{}}\n"
                await page.evaluate(script)
                await page.close()
            except Exception as e:
                print(f"[!] localStorage inject error for {origin}: {e}")

        origins_session: dict[str, list[dict]] = {}
        for item in self.session_storage:
            origins_session.setdefault(item["origin"], []).append(item)

        for origin, items in origins_session.items():
            if not origin or origin == "null":
                continue
            try:
                page = await context.new_page()
                await page.goto(origin, wait_until="domcontentloaded")
                script = ""
                for it in items:
                    k = json.dumps(it["key"])
                    v = json.dumps(it["value"])
                    script += f"try {{ sessionStorage.setItem({k}, {v}); }} catch(e) {{}}\n"
                await page.evaluate(script)
                await page.close()
            except Exception as e:
                print(f"[!] sessionStorage inject error for {origin}: {e}")
