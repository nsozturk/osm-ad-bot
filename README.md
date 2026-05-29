# OSM Ad Bot
Automated BossCoin farming bot for Online Soccer Manager using Playwright.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Export your OSM browser session (cookies + localStorage + sessionStorage). Install the **StorageDump** extension:
   - [Chrome Web Store](https://chromewebstore.google.com/detail/storagedump/kihoghfekemdccfnpjefmggehpgnjnab)
   - Open OSM, click the StorageDump icon, export all storages, save as JSON.

3. Save the dump to a directory (e.g. `~/my-osm-session/`). This directory should contain:
- `cookies.json`
- `local.json` (optional)
- `session.json` (optional)

4. Set the required environment variable for the OSM API client credentials:
```bash
export OSM_CLIENT_ID="your-client-id"
export OSM_CLIENT_SECRET="your-client-secret"
```

Or create a `.env` file (copy from `.env.example`).

## Usage

```bash
# Headless mode (recommended for background)
python3 osm_ad_bot_conductor.py \
  --dump ~/my-osm-session/ \
  --headless \
  --watcher-tabs 8

# Headed mode (visible browser, for debugging)
python3 osm_ad_bot_conductor.py \
  --dump ~/my-osm-session/ \
  --watcher-tabs 1
```

### Convenience scripts
```bash
# 8 watchers, headless
./run.sh ~/my-osm-session/

# 1 watcher, visible browser
./run_conductor_headed.sh ~/my-osm-session/
```

## ⚠️ Security Warning
- **Never commit your storage dump** — it contains authentication tokens.
- **Never commit `.env`** — it contains API credentials.
- The dump directory is already ignored by `.gitignore`.

## How it works
- 1 permanent "conductor" tab monitors server rate limits via API.
- 8 "watcher" tabs open only when the conductor confirms no rate limit.
- Each watcher watches one ad, then closes its tab.
- The bot waits for server cooldowns automatically.

## Disclaimer
This tool is for educational purposes. Use at your own risk. Respect OSM's Terms of Service.
