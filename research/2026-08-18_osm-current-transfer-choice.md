# OSM Güncel Transfer Seçimi

**Date:** 2026-08-18
**Topic:** osm-current-transfer-choice

## Summary

Canlı OSM verisinde kullanılabilir bütçe 38.138.603, kadro 23 oyuncu ve transfer listesi 68 oyuncu. 27 yaş ve altı, bütçeye sığan adaylar arasında en mantıklı doğrudan ilk 11 transferi 37.779.206 bedelli Bellingham; mevcut orta saha ilk 11 tabanını 87'den 94'e çıkararak +7 katkı sağlıyor.

## Findings

### Güncel kadro eşikleri

- Bütçe: 38.138.603
- Kaleci ilk 11 gücü: 92
- Dört savunmacı içindeki en düşük güç: 87
- Üç orta saha içindeki en düşük OVR: 87
- Üç hücumcu içindeki en düşük hücum gücü: 95

### Birinci tercih: Bellingham

- Yaş: 23
- Rol: AM
- OVR / ATT / DEF: 94 / 94 / 94
- Fiyat: 37.779.206
- İlk 11 katkısı: +7; Olmo'nun 87 OVR'lik slotunu yükseltir
- Alımdan sonra kalan: 359.397

Bellingham mevcut listedeki en büyük ilk 11 artışını sağlıyor. Olmo ile aynı AM rolüne oturduğu için pozisyon yığılması yaratmıyor; 23 yaşında olması da antrenman ve ilerideki kadro değeri açısından avantajlı.

### Alternatifler

1. van Hecke — 26 yaş, CB, DEF 92, fiyat 25.573.828. Savunma ilk 11'ine +5 güç ekler ve 12.564.775 bırakır. Bütçeyi tamamen tüketmeden güçlenmek için en iyi seçenek.
2. Petrovic — 26 yaş, GK, DEF 97, fiyat 34.476.271. Donnarumma'nın 92 seviyesine göre +5 katkı verir ve 3.662.332 bırakır.
3. Hakimi — 27 yaş, RB, DEF 90, fiyat 33.246.956. +3 katkı verir; R. James ve Timber bulunduğundan rol yığılması riski taşır.

### Elenmesi gerekenler

- Bütçe içindeki hücumcuların hiçbiri mevcut ATT 95 ilk 11 tabanını aşmıyor.
- Tonali yalnızca +1 katkı sağlarken 37.131.732 istiyor.
- D. Costa yalnızca mevcut kaleci seviyesinin altında kaldığı için ilk 11 transferi değil.

### Karar

Maksimum kadro gücü hedefinde Bellingham alınmalı. Yaklaşık 12,5 milyon nakit korumak isteniyorsa van Hecke ikinci ve daha temkinli tercihtir. Bu değerlendirme yalnızca öneridir; otomatik satın alma işlemi yapılmadı.

## Sources

- OSM canlı finans, kadro ve transfer listesi API yanıtları; 2026-08-18 tarihinde çalışma zamanı kimlik bilgileri diske veya rapora yazılmadan yenilendi.
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
