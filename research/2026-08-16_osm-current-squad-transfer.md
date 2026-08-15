# OSM Güncel Kadroya Göre Transfer Analizi

**Date:** 2026-08-16
**Topic:** osm-current-squad-transfer

## Summary

Canlı yenilemede bütçe 24.078.317 BossCoin, kadro 22 oyuncu ve pazarda 83 dış aday (86 kayıt, 3 kendi oyuncusu) bulundu. 4-3-3 ilk 11 eşikleri GK 43, DEF 54, MID 83 ve ATT 60; en verimli gerçek yükseltme savunmada M. Nunes oldu. M. Nunes (DEF/RB, OVR 65, yaş 27) 16.533.172 fiyatla ilk 11 savunma eşiğini 54'ten 65'e çıkarıyor (+11) ve 7.545.145 bırakıyor.

## Findings

### Canlı kadro ve bütçe

| Mevki | Oyuncu sayısı | En iyi OVR | 4-3-3 ilk 11 eşiği | Değerlendirme |
|---|---:|---:|---:|---|
| GK | 2 | 43 | 43 | Çok zayıf |
| DEF | 8 | 65 | 54 | Çok zayıf |
| MID | 6 | 86 | 83 | Orta |
| ATT | 6 | 71 | 60 | Zayıf |

Mevcut ilk 11 toplamı 727 OVR. En zayıf savunma starter'ı Rothe (54); kaleci eşiği Rönnow (43), orta saha eşiği Skov (83), hücum eşiği D. Doué (60) belirliyor.

### Önerilen transfer

**M. Nunes — DEF/RB, OVR 65, yaş 27, Manchester City, 16.533.172**

- Rothe'nin 54 OVR'lik ilk 11 slotunu 65 ile değiştirir: **+11 ilk 11 OVR**.
- 27 yaş, mevcut savunmayı güçlendirirken yaş açısından dengeli.
- Transfer sonrası bütçe: **7.545.145**.
- Bu bütçeyle ikinci bir gerçek ilk 11 yükseltmesi sığmıyor; en ucuz ikinci olumlu adaylarla bile toplam 24.08M sınırı aşılıyor.

### Alternatifler

| Öncelik | Oyuncu | Fiyat | İlk 11 etkisi | Kalan |
|---|---|---:|---:|---:|
| Bütçeyi koru | Dalot (DEF/RB, 61, yaş 27) | 12.443.293 | +7 | 11.635.024 |
| Genç orta saha | Anderson (MID/CM, 87, yaş 23) | 22.444.096 | +4 | 1.634.221 |
| Hücum için bekle | Barcola (ATT/W, 62, yaş 23) | 25.564.145 | +2 | Bütçe 1.485.828 eksik |
| Kaleci düzeltmesi | D. Costa (GK, 45, yaş 26) | 18.846.054 | +2 | 5.232.263 |

Kaleci zayıf görünse de mevcut pazarda kaleci hamlesi yalnızca +1/+2 getiriyor; bu nedenle M. Nunes savunma hamlesine göre daha düşük değer üretiyor. De Bruyne (86, yaş 35, 16.889.388) +3 verse de yaş ve mevki önceliği nedeniyle tercih edilmedi.

### Sonuç

Bu bütçeyle benim sıralamam: **1) M. Nunes, 2) Dalot, 3) bütçeyi 1.49M daha biriktirip Barcola**. Fiili transfer yapılmadı; bu yalnızca canlı pazar ve kadro verisine dayalı öneridir. Storage dump içindeki tokenler yalnızca canlı yenileme sırasında bellekte kullanıldı ve rapora/koda yazılmadı.

## Sources

- `/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-12T16-52-10-428Z.zip` — canlı storage dump kaynağı; 2026-08-16 yenilemesi.
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py` — storage dump'tan tokenleri bellekte kullanarak canlı kadro, finans ve transfer listesini yenileme.
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py` — 4-3-3 ilk 11 eşiği, OVR yükseltmesi ve bütçe uygunluğu hesabı.
