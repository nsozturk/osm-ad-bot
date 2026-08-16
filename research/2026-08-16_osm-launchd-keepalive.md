# OSM Launchd KeepAlive Uygulama İncelemesi

**Date:** 2026-08-16
**Topic:** osm-launchd-keepalive

## Summary

OSM reklam ve otomatik training conductor'ı kullanıcı seviyesinde bir macOS LaunchAgent altına alındı. `RunAtLoad` ve `KeepAlive` etkin; bot terminal veya Codex PTY kapanmasından bağımsız çalışıyor, sistem uykusunu engellemiyor ve process sonlanırsa launchd tarafından yeniden başlatılıyor.

## Findings

### Mimari

- LaunchAgent etiketi: `dev.nsozturk.osm-ad-bot`
- Kurulu plist: `/Users/ns0bj/Library/LaunchAgents/dev.nsozturk.osm-ad-bot.plist`
- Repository runner: `/Users/ns0bj/Development/Fun/osm/launchd/osm-ad-bot-runner.sh`
- `run.sh` komutları: varsayılan start+log takibi, `start`, `restart`, `stop`, `status`, `logs`
- Runner, shell içinde watchdog tutmak yerine `exec` ile doğrudan Python conductor'a dönüşüyor; böylece launchd gerçek bot PID'sini supervise ediyor.
- `OSM_USE_LAUNCHD=0` eski doğrudan arka plan yolunu koruyor.

### Uyku ve yaşam döngüsü

- Plist'te `RunAtLoad=true`, `KeepAlive=true`, `ProcessType=Background`, `ThrottleInterval=15` doğrulandı.
- `caffeinate` kullanılmıyor; normal macOS uykusu engellenmiyor.
- Uyku sırasında süreç macOS tarafından duraklatılır; uyanıştan sonra launchd supervision devam eder.
- Kalıcı durdurma `./run.sh stop` ile LaunchAgent bootout edilerek yapılır. Doğrudan PID kill edilirse KeepAlive yeniden başlatır.

### StorageDump güvenliği ve TCC

- LaunchAgent, Terminal'in Downloads klasörü privacy iznini devralmadığı için doğrudan Downloads ZIP'ini açarken bloklandı.
- `run.sh` seçilen dump'ı git tarafından yok sayılan `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/launchd-storage-dump.zip` konumuna stage ediyor.
- Runtime kopyası `0600` modunda doğrulandı.
- Plist yalnızca dosya yolları içeriyor; access token, refresh token, Authorization değeri veya client secret içermiyor.

### Canlı doğrulama

- Shell ve Python kontrolleriyle 28/28 test başarılı.
- LaunchAgent PID 96563 sonlandırıldı; launchd 10 saniye içinde PID 96819 ile yeniden başlattı.
- `./run.sh stop` job unload ve process exit tamamlanana kadar bekleyecek biçimde doğrulandı.
- Servis son kez PID 97555 ile çalışır bırakıldı.
- Son süreçte `CONDUCTOR STARTED`, training `reconciliation healthy` ve reklam `REWARD CONFIRMED` görüldü.
- Son canlı cooldown 47 dakika 54 saniye olarak algılandı; bu normal OSM rate-limit beklemesidir.

## Sources

- `/Users/ns0bj/Development/Fun/osm/run.sh`
- `/Users/ns0bj/Development/Fun/osm/launchd/osm-ad-bot-runner.sh`
- `/Users/ns0bj/Development/Fun/osm/tests/test_launchd_contract.py`
- `/Users/ns0bj/Development/Fun/osm/docs/superpowers/specs/2026-08-16-osm-launchd-keepalive-design.md`
- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log`
- macOS `launchctl`, `plutil`, `ps`, `lsof` ve process lifecycle kontrolleri
