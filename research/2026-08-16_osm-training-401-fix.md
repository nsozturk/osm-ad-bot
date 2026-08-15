# OSM Training 401 Düzeltme İncelemesi

**Date:** 2026-08-16
**Topic:** osm-training-401-fix

## Summary

Otomatik training döngüsündeki HTTP 401 hatasının nedeni, çalışan botun eski StorageDump erişim belirtecini kullanmaya devam etmesi ve süresi dolduğunda mevcut, git tarafından yok sayılan istemci gizlisiyle yenileme yapmamasıydı. Bot artık farklı veya daha güncel dump seçildiğinde güvenli biçimde yeniden başlıyor, kısa ömürlü erişim belirtecini süresi dolmadan yalnızca bellekte yeniliyor ve reklam izleme ile training yöneticisini aynı süreçte çalıştırıyor.

## Findings

### Kök neden

- Eski çalışan süreç 12 Ağustos dump'ını kullanırken `run.sh`, 15 Ağustos dump'ı verilse bile sadece eski sürecin loguna bağlanıyordu.
- Eski erişim belirteci training gibi korumalı uçlarda HTTP 401 döndürdü; aynı hesabın taze dump'ındaki erişim belirteciyle salt-okunur training uçları HTTP 200 verdi.
- Conductor yenileme akışı sadece ortam değişkenlerini okuyordu. Repoda zaten bulunan ve git tarafından yok sayılan yerel istemci gizlisi bu akışta kullanılmıyordu.
- Sağlanan HAR, training başlatma isteğinin JSON yerine `application/x-www-form-urlencoded` kullandığını gösterdi.

### Uygulanan düzeltmeler

- `run.sh`, seçilen dump çalışan sürecinkinden farklıysa eski süreci SIGTERM ile kontrollü kapatıp yeni dump ile yeniden başlatıyor.
- Bot `nohup` ile terminal oturumundan ayrılıyor; log takibinin kapanması botu kapatmıyor.
- Erişim belirteci süresi yerel JWT bilgisinden kontrol ediliyor; yenileme eşzamanlı API istekleri arasında kilitlenerek refresh-token yarışları önleniyor.
- Yenilenen erişim ve refresh değerleri yalnızca çalışma belleği, Playwright context'i ve tarayıcı depolamasında tutuluyor; kaynak dosyalara veya loglara yazılmıyor.
- Training POST gövdesi canlı HAR ile aynı form kodlamasına geçirildi.
- Training yöneticisi ilk başarılı uzlaşmayı ve hata sonrası toparlanmayı açıkça logluyor.

### Doğrulama

- Shell syntax, Python bytecode derleme ve `git diff --check` başarılı.
- Birim test paketi 24/24 başarılı.
- 15 Ağustos dump'ıyla doğrudan salt-okunur training API kontrolü HTTP 200 döndürdü.
- Güncel dump'la başlatılan birleşik süreçte training ilk uzlaşmayı `reconciliation healthy` olarak tamamladı.
- Dump erişim belirtecinin doğal bitiş penceresinden sonraki training turunda yeni HTTP 401 veya fatal hata oluşmadı; süreç canlı kaldı.
- Aynı süreç reklam scout döngüsünü başlattı; önceki canlı kontrolde reklam ödülü ve rate-limit algılama doğrulandı.
- Süreç, `run.sh` log takip oturumu kapatıldıktan sonra parent PID 1 altında çalışmaya devam etti.

## Sources

- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/run.sh`
- `/Users/ns0bj/Development/Fun/osm/tests/test_auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/en.onlinesoccermanager.com-training.har` (yerel, git tarafından yok sayılan oturum kaydı; kimlik bilgileri rapora alınmadı)
- `/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-15T22-20-37-575Z.zip` (yerel, git dışı oturum girdisi; değerler rapora alınmadı)
- `/Users/ns0bj/Development/Fun/osm/tmp/osm-runtime/conductor.log` (yerel çalışma kanıtı; git dışında)
