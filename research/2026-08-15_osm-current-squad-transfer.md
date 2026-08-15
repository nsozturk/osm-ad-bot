# OSM Güncel Kadroya Göre Transfer Analizi

**Date:** 2026-08-15
**Topic:** osm-current-squad-transfer

## Summary

Canlı bütçe 69.700.493 ve birikim hesabı 0. Kadronun 4-3-3 ilk 11'inde en acil açıklar OVR 48 üçüncü hücumcu, OVR 51 dördüncü savunmacı ve OVR 42 kaleci; orta saha eşiği OVR 78 ile daha iyi durumda. En dengeli uzun vadeli paket D. Doué + Dimarco + Olmo, en yüksek anlık ilk-11 artışı ise B. Fernandes + Dalot + Dimarco + Iwobi paketidir.

## Findings

### Güncel durum

- Nakit: 69.700.493; birikim: 0.
- Kadro: 20 oyuncu.
- Transfer pazarı: 78 dış aday; satışta kendi oyuncusu yok.
- 4-3-3 ilk-11 eşikleri: GK 42, DEF 51, MID 78, ATT 48.
- Hücumun güçlü iki ismi Yıldız OVR 69 ve Gakpo OVR 67; üçüncü hücumcu Burcu OVR 48.
- Savunmanın ilk dört seviyesi 57, 55, 54 ve 51.
- Kaleciler OVR 42 ve 36; pazardaki gerçek büyük sıçrama Courtois OVR 55 fakat fiyatı 92.314.503 ve mevcut bütçeyi 22.614.010 aşıyor.

### Önerilen dengeli paket

1. D. Doué — W, OVR 59, yaş 21, fiyat 28.832.598: hücum ilk 11'ine +11.
2. Dimarco — LB, OVR 65, yaş 28, fiyat 16.760.685: savunma ilk 11'ine +14.
3. Olmo — AM, OVR 86, yaş 28, fiyat 17.383.033: orta saha ilk 11'ine +8.

- Toplam maliyet: 62.976.316.
- Toplam ilk-11 artışı: +33 OVR.
- Kalan para: 6.724.177.
- Üç oyuncunun da yaşı gelişim/değer koruma açısından Iwobi ve B. Fernandes ağırlıklı maksimum paketten daha uygun.

### Maksimum anlık güç paketi

1. B. Fernandes — AM, OVR 89, yaş 31, fiyat 20.356.647.
2. Dalot — RB, OVR 61, yaş 27, fiyat 12.866.496.
3. Dimarco — LB, OVR 65, yaş 28, fiyat 16.760.685.
4. Iwobi — W, OVR 59, yaş 30, fiyat 19.377.929.

- Toplam maliyet: 69.361.757.
- Gerçek birleşik ilk-11 artışı: +43 OVR.
- Kalan para: 338.736.
- Bu paket kısa vadede en güçlü sonuçtur fakat kasayı bitirir ve iki kritik hücum/orta saha alımı 30 yaş üzeridir.

### Daha temkinli seçenekler

- Dimarco + Dalot: 29.627.181 maliyet, savunmada birleşik +21 OVR, 40.073.312 para kalır. Piyasayı ve güçlü kaleci fırsatını beklemek için en güvenli seçenek.
- Dimarco + Olmo + Iwobi: 53.521.647 maliyet, +33 OVR, 16.178.846 para kalır. D. Doué paketine göre aynı anlık artışı daha ucuza verir fakat Iwobi 30 yaşındadır.
- D. Doué + Dimarco + B. Fernandes: 65.949.930 maliyet, +36 OVR, 3.750.563 para kalır. Olmo yerine daha yüksek anlık orta saha katkısı verir fakat yaş ortalaması yükselir.

### Tek oyuncu fiyat/performans sırası

- Dimarco: 16.760.685 karşılığında +14 OVR; açık ara en iyi tek alım.
- Dalot: 12.866.496 karşılığında +10 OVR.
- Iwobi: 19.377.929 karşılığında +11 OVR; iyi anlık değer, zayıf uzun vadeli yaş profili.
- B. Fernandes: 20.356.647 karşılığında +11 OVR; güçlü fakat orta saha savunma ve üçüncü hücumcu kadar acil değil.
- D. Doué: 28.832.598 karşılığında +11 OVR; pahalı fakat 21 yaşında ve uzun vadeli paket için en uygun hücum tercihi.

### Karar

Benim önerim D. Doué + Dimarco + Olmo paketidir. Bu paket hücum, savunma ve orta sahayı aynı anda geliştirir, +33 OVR getirir ve yaş profili maksimum güç paketinden daha sağlıklıdır. Yalnızca kısa vadeli maç gücü hedefleniyorsa maksimum +43 paket seçilebilir; kasayı tamamen boşaltmak istenmiyorsa ilk adım olarak yalnız Dimarco + Dalot alınmalıdır. Mevcut uygun kalecilere 15–24 milyon harcamak yalnız +2 ila +4 OVR sağladığı için mantıklı değildir.

## Sources

- Canlı OSM kadro, transfer pazarı ve finans endpoint'leri; `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py` üzerinden 2026-08-15 tarihinde salt okunur yenilendi.
- Yenilenmiş, Git tarafından yok sayılan yerel JSON verileri üzerinde 1–6 oyunculu tüm anlamlı ve bütçeye uyan kombinasyonlar 4-3-3 ilk-11 toplamı kullanılarak karşılaştırıldı.
- StorageDump kimlik bilgileri yalnız bellekte kullanıldı; rapora veya takip edilen dosyalara yazılmadı.
