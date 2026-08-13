# OSM Ad Bot
Automated BossCoin farming bot for Online Soccer Manager using Playwright.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Export your OSM browser session (cookies + localStorage + sessionStorage) **after your latest login**. Install the **StorageDump** extension:
   - [Chrome Web Store](https://chromewebstore.google.com/detail/storagedump/kihoghfekemdccfnpjefmggehpgnjnab)
   - Open OSM, click the StorageDump icon, export all storages, save as JSON.

3. Keep the exported ZIP as-is, or save the dump to a directory (e.g. `~/my-osm-session/`). A directory should contain:
- `cookies.json`
- `local.json` (optional)
- `session.json` (optional)

4. Optional fallback for explicit token refresh calls:
```bash
export OSM_CLIENT_ID="your-client-id"
export OSM_CLIENT_SECRET="your-client-secret"
```

The normal browser flow uses the live cookies from StorageDump. Client credentials are not required when the OSM page refreshes its own cookie successfully.

## Usage

```bash
# Headless mode (recommended for background)
python3 osm_ad_bot_conductor.py \
  --dump ~/Downloads/storagedump_en.onlinesoccermanager.com_latest.zip \
  --headless \
  --watcher-tabs 8 \
  --auto-training \
  --training-har-profile ./en.onlinesoccermanager.com-training.har

# Headed mode (visible browser, for debugging)
python3 osm_ad_bot_conductor.py \
  --dump ~/my-osm-session/ \
  --watcher-tabs 1
```

### Convenience scripts
```bash
# Select the newest StorageDump automatically; 8 watchers + auto-training
./run.sh

# Or use an explicit post-login directory/ZIP
./run.sh ~/Downloads/storagedump_en.onlinesoccermanager.com_latest.zip

# 1 watcher, visible browser
./run_conductor_headed.sh ~/my-osm-session/
```

If the bot is already active, running `./run.sh` again attaches to the existing live log instead of starting a duplicate process. Pressing Ctrl+C stops only log following; use the printed `kill` command when you want to stop the bot itself.

## Automatic training

With `--auto-training`, the conductor runs a separate, failure-isolated training manager:

- Claims completed training sessions before refilling slots.
- Fills attacker, midfielder, defender, and goalkeeper trainers with matching players.
- Uses `forecast` for normal trainers and `forecastUniversal` for the universal trainer.
- Randomly selects from up to five players within 85% of the best current forecast, weighted toward the higher forecast. A player whose yield drops after repeated training naturally loses priority.
- Excludes injured players, players already training, max-level players, and players listed for transfer.
- Never buys a universal trainer, boosts a timer, converts Boss Coins, buys a player, or changes a transfer listing.

The optional Training HAR is a non-secret settings profile. Chrome HAR exports omit usable Authorization and cookie values, so a HAR cannot replace a fresh post-login StorageDump.

## ⚠️ Security Warning
- **Never commit your storage dump** — it contains authentication tokens.
- **Never commit HAR files** — they are local diagnostics even when Chrome has redacted their auth headers.
- **Never commit `.env`** — it contains API credentials.
- The dump directory is already ignored by `.gitignore`.

## How it works
- 1 permanent "conductor" tab monitors server rate limits via API.
- 8 "watcher" tabs open only when the conductor confirms no rate limit.
- Each watcher watches one ad, then closes its tab.
- The bot waits for server cooldowns automatically.

## Disclaimer
This tool is for educational purposes. Use at your own risk. Respect OSM's Terms of Service.
