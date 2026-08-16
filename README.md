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
# Select the newest StorageDump, start the user LaunchAgent, and follow logs
./run.sh

# Or use an explicit post-login directory/ZIP
./run.sh ~/Downloads/storagedump_en.onlinesoccermanager.com_latest.zip

# Start without following logs
./run.sh start

# Lifecycle controls
./run.sh status
./run.sh restart
./run.sh stop
./run.sh logs

# 1 watcher, visible browser
./run_conductor_headed.sh ~/my-osm-session/
```

On macOS, `run.sh` installs a per-user LaunchAgent at `~/Library/LaunchAgents/dev.nsozturk.osm-ad-bot.plist`. launchd owns the conductor process with `RunAtLoad` and `KeepAlive`, so a terminal, Codex session, or `tail -f` ending cannot take the bot down. The job does **not** use `caffeinate` and does not prevent system sleep; macOS pauses it during sleep and launchd resumes supervision after wake.

Because background LaunchAgents do not inherit Terminal's Downloads-folder privacy grant, `run.sh` stages the selected StorageDump as a mode-`0600` runtime copy under ignored `tmp/osm-runtime/`. Only that copy's path reaches launchd; token values are never written to the plist or logs and the runtime directory is never tracked by git.

If the bot is already active with the same StorageDump, running `./run.sh` again attaches to its live log instead of starting a duplicate. Selecting a newer/different dump restarts the LaunchAgent with that dump. Pressing Ctrl+C stops only log following. A direct `kill <pid>` is intentionally restarted by KeepAlive; use `./run.sh stop` for a persistent stop. Set `OSM_USE_LAUNCHD=0` only when you explicitly need the legacy direct-background fallback.

## Automatic training

With `--auto-training`, the conductor runs a separate, failure-isolated training manager:

- Claims completed training sessions before refilling slots.
- Fills attacker, midfielder, defender, and goalkeeper trainers with matching players.
- Uses `forecast` for normal trainers and `forecastUniversal` for the universal trainer.
- Scores candidates as `forecast × age multiplier`: `1.25` through age 21, `1.15` for 22–24, `1.00` for 25–28, `0.80` for 29–31, and `0.60` from age 32 onward.
- Randomly selects from up to five players within 90% of the best current priority score, weighted toward the higher score. A player whose yield drops after repeated training naturally loses priority.
- Excludes outfield players below main stat 50 and goalkeepers below 40, even when they are very young; these floors are never relaxed as a fallback.
- Excludes injured players, players already training, max-level players, and players listed for transfer.
- Keeps the OSM conductor page awake during ad cooldowns so the frontend continues rotating the short-lived token required by automatic training.
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
