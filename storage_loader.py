"""Load and inject browser storage dumps into a Playwright context."""
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

class StorageLoader:
    """Parses a StorageDump export and applies cookies/local/session storage."""

    def __init__(self, dump_dir: str):
        self.dump_dir = Path(dump_dir)
        self.cookies: list[dict] = []
        self.local_storage: list[dict] = []
        self.session_storage: list[dict] = []
        self._parse()

    def _parse(self):
        archive = None
        if self.dump_dir.is_file():
            try:
                archive = zipfile.ZipFile(self.dump_dir)
            except zipfile.BadZipFile as exc:
                raise ValueError("StorageDump is not a valid ZIP archive") from exc
            names = set(archive.namelist())

            def exists(name: str) -> bool:
                return name in names

            def read_json(name: str, max_bytes: int) -> Any:
                info = archive.getinfo(name)
                if info.file_size > max_bytes:
                    raise ValueError(f"StorageDump member is unexpectedly large: {name}")
                with archive.open(info) as fh:
                    return json.load(fh)

            def storage_parts(name: str) -> list[str]:
                return [item for item in names if item.startswith(name + "/part-") and item.endswith(".json")]
        elif self.dump_dir.is_dir():
            def exists(name: str) -> bool:
                return (self.dump_dir / name).exists()

            def read_json(name: str, max_bytes: int) -> Any:
                path = self.dump_dir / name
                if path.stat().st_size > max_bytes:
                    raise ValueError(f"StorageDump member is unexpectedly large: {name}")
                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh)

            def storage_parts(name: str) -> list[str]:
                directory = self.dump_dir / name
                return [str(path.relative_to(self.dump_dir)) for path in directory.glob("part-*.json")] if directory.is_dir() else []
        else:
            raise ValueError(f"StorageDump path not found: {self.dump_dir}")

        try:
            if exists("cookies.json"):
                data = read_json("cookies.json", 5 * 1024 * 1024)
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

            def parse_storage(name: str):
                # Supports two StorageDump layouts:
                #   - old:  <name>.json           -> {"data": [ ... ]}
                #   - new:  <name>/part-*.json    -> list or {"data": [...]}
                items = []
                raw_entries = []

                single = f"{name}.json"
                parts = storage_parts(name)
                if exists(single):
                    data = read_json(single, 20 * 1024 * 1024)
                    raw_entries.extend(data.get("data", []) if isinstance(data, dict) else data)
                elif parts:
                    def _part_key(member: str):
                        digits = "".join(ch for ch in Path(member).stem if ch.isdigit())
                        return int(digits) if digits else 0
                    for part in sorted(parts, key=_part_key):
                        data = read_json(part, 10 * 1024 * 1024)
                        raw_entries.extend(data.get("data", []) if isinstance(data, dict) else data)

                for item in raw_entries:
                    meta = item.get("metadata", {}) or {}
                    origin = meta.get("origin", "https://en.onlinesoccermanager.com")
                    key = item["key"]
                    value = item["value"]
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value)
                    else:
                        value = str(value)
                    items.append({"origin": origin, "key": key, "value": value})
                return items

            self.local_storage = parse_storage("local")
            self.session_storage = parse_storage("session")
        finally:
            if archive is not None:
                archive.close()

    @staticmethod
    def _is_osm_origin(origin: str) -> bool:
        """Only OSM web storage is needed to restore the authenticated SPA."""
        try:
            hostname = (urlparse(origin).hostname or "").lower()
        except ValueError:
            return False
        return (
            hostname == "onlinesoccermanager.com"
            or hostname.endswith(".onlinesoccermanager.com")
        )

    async def inject(self, context):
        """Inject cookies and storage into a Playwright BrowserContext."""
        if self.cookies:
            await context.add_cookies(self.cookies)

        # Install storage before any OSM page JavaScript runs. Opening one
        # temporary page per origin caused navigation stalls and leaked tabs
        # whenever an ad-provider origin became unresponsive.
        origins_local: dict[str, list[dict]] = {}
        for item in self.local_storage:
            if not self._is_osm_origin(item["origin"]):
                continue
            origins_local.setdefault(item["origin"], []).append({
                "key": item["key"], "value": item["value"]
            })

        origins_session: dict[str, list[dict]] = {}
        for item in self.session_storage:
            if not self._is_osm_origin(item["origin"]):
                continue
            origins_session.setdefault(item["origin"], []).append({
                "key": item["key"], "value": item["value"]
            })

        if not origins_local and not origins_session:
            return

        local_json = json.dumps(origins_local, separators=(",", ":"))
        session_json = json.dumps(origins_session, separators=(",", ":"))
        script = f"""
            (() => {{
                const localByOrigin = {local_json};
                const sessionByOrigin = {session_json};
                for (const item of (localByOrigin[location.origin] || [])) {{
                    try {{ localStorage.setItem(item.key, item.value); }} catch (_) {{}}
                }}
                for (const item of (sessionByOrigin[location.origin] || [])) {{
                    try {{ sessionStorage.setItem(item.key, item.value); }} catch (_) {{}}
                }}
            }})();
        """
        await context.add_init_script(script=script)
