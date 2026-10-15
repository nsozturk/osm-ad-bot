# OSM 27 Yaş Altı Canlı Transfer Önerileri

**Date:** 2026-08-16
**Topic:** osm-u27-transfer-options

## Summary

Canlı OSM verisinde kullanılabilir bütçe 74.881.803, kadro 20 oyuncu ve transfer listesi 86 kayıt olarak doğrulandı. En dengeli satın alma paketi R. James, Pedri ve Gvardiol: üçü de 27 yaş sınırının altında, savunmada iki farklı rolü ve orta sahayı güçlendiriyor; toplam maliyet 71.873.536 ve kalan bütçe 3.008.267.

## Findings

### Canlı durum

- Bütçe: 74.881.803
- Kadro: 20 oyuncu
- Transfer listesi: 86 kayıt; 85 harici aday
- Varsayılan kadro değerlendirmesi: 4-3-3
- Mevcut ana güç değerleri mevkiye göre değerlendirildi: kaleci ve savunmada DEF, orta sahada dengeli OVR, hücumda ATT.

### Birinci tercih: dengeli üçlü

| Oyuncu | Yaş | Rol | Mevki gücü | Fiyat | Gerekçe |
|---|---:|---|---:|---:|---|
| R. James | 26 | RB | DEF 91 | 25.660.566 | Kadrodaki mevcut RB kalitesini belirgin yükseltir; listedeki en güçlü genç savunmacı. |
| Pedri | 23 | CM | ATT 90 / DEF 90 | 30.188.211 | Orta saha ilk 11 tabanını yaklaşık 83 OVR'dan 90'a taşır; yaş/kalite dengesi en iyi aday. |
| Gvardiol | 24 | CB | DEF 85 | 16.024.759 | İkinci sağ bek yerine stoper rolü sağlar; savunma rol dengesini korur. |

- Toplam: 71.873.536
- Kalan: 3.008.267
- Satın alma sırası: R. James → Pedri → Gvardiol

### Daha ekonomik alternatif

R. James yerine M. Nunes alınırsa paket M. Nunes + Pedri + Gvardiol olur.

- M. Nunes: 27 yaş, RB, DEF 85, fiyat 16.313.465
- Toplam: 62.526.435
- Kalan: 12.355.368
- Avantaj: 9.347.101 daha ucuz.
- Dezavantaj: R. James'e göre savunma gücü 6 puan daha düşük.

### Şimdilik ertelenecekler

- Osimhen: 27 yaş, ST, ATT 94, 36.576.101. Güçlü aday; ancak mevcut hücum üçlüsünde ATT 100/92/90 bulunduğu için artış savunma ve orta saha kadar büyük değil.
- Petrovic: 26 yaş, GK, DEF 97, 40.210.086. Kaleciyi yükseltir fakat bütçenin yarısından fazlasını tek pozisyona bağlar.
- D. Costa: 26 yaş, GK, DEF 91, 18.595.611. Mevcut Donnarumma DEF 89'a göre yalnızca 2 puanlık artış sağlar.
- Hakimi: 27 yaş, RB, DEF 90, 33.246.956. R. James'ten daha pahalı ve 1 puan daha düşük.
- Dalot: 27 yaş, RB, DEF 82, 12.277.936. Ucuz fakat R. James/M. Nunes sonrasında aynı role yığılma yaratır.
- Barcola ve Olise: Hücum ATT değerleri mevcut ilk 11 tabanını anlamlı yükseltmiyor.

### Uygulama notu

Transfer listesi canlı değiştiği için oyuncular sırayla alınmalı ve her alımdan sonra bütçe ile market yeniden çekilmelidir. Ham danışmanın aynı kaba DEF kategorisinde üç sağ bek önermesi rol dengesini bozduğundan nihai paket RB + CB + CM olarak elle dengelendi.

## Sources

- OSM Web API canlı finans, oyuncu ve transfer listesi uçları; 2026-08-16 tarihinde yalnızca bellekte tutulan güncel oturum değerleriyle sorgulandı.
- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
- `/Users/ns0bj/Downloads/storagedump_en.onlinesoccermanager.com_2026-08-15T22-20-37-575Z.zip` (yerel oturum girdisi; token değerleri rapora alınmadı)
