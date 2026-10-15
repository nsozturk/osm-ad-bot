# run.sh Reklam İzlemenin Durma İncelemesi

**Date:** 2026-08-16
**Topic:** runsh-ad-watching-stop

## Summary

Reklam izleme normal rate-limit beklemesinde değildir; conductor süreci artık çalışmıyor. PID dosyasında 62441 kalmış olmasına rağmen bu PID mevcut değil, `run.sh` ve `tail -f` süreçleri ise yaşamaya devam ettiği için terminal açık ama log hareketsiz görünüyor.

## Findings

### Son başarılı durum

- 13:26'da yeni reklam döngüsü başladı.
- Scout reklamı dahil toplam sayaç 87'ye çıktı.
- Sekiz watcher reklamları tamamladı ve sayaç 95'e ulaştı.
- 13:29:01'de OSM tarafından 46 dakika 48 saniyelik normal rate-limit bildirildi.

### Arıza kanıtı

- Son log satırı 14:14:34; cooldown bitimine 1 dakika 18 saniye kalmıştı.
- İnceleme saati 18:53 olmasına rağmen log mtime değeri 14:14'te kaldı.
- PID dosyası 62441 gösteriyor fakat bu süreç mevcut değil.
- Python traceback, `FATAL`, `Shutdown signal received`, final summary veya crash report yok.
- Mac 8 Ağustos'tan beri yeniden başlatılmadı; 16 Ağustos 14:14 civarında uyku/reboot olayı bulunmadı.
- `run.sh` ve yalnızca logu izleyen `tail -f` süreçleri hâlâ çalışıyor. Bu nedenle kullanıcı arayüzü aktifmiş gibi görünse de asıl bot yok.

### Muhtemel neden

Conductor 01:42 civarında Codex tarafından açılan PTY oturumunda başlatıldı ve log yaklaşık 12 saat 32 dakika sonra kesildi. Aynı anda Playwright/Chromium ses context'leri de sistem kayıtlarında serbest bırakıldı. Botun kendi hata/çıkış kaydı olmadığı için en güçlü açıklama PTY veya süreç grubunun dışarıdan sert biçimde temizlenmesi; mevcut `nohup` komutu child süreci bu gruptan tam ayırmamış.

### Geçici toparlama

Mevcut log takibinde Ctrl+C ile yalnızca `tail` kapatılıp `./run.sh` yeniden çalıştırıldığında stale PID geçilerek yeni conductor başlatılır. Kalıcı çözüm için conductor'ın macOS `launchd` altında `KeepAlive` ile çalıştırılması veya `run.sh` içine child-exit watchdog eklenmesi gerekir.

## Sources

- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log`
- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.pid`
- `/Users/ns0bj/Development/Fun/osm/run.sh`
- macOS `ps`, `pgrep`, `uptime`, `last reboot`, `pmset -g log` ve unified log salt-okunur kontrolleri
