# OSM İki Oyunculu Transfer Seçenekleri

**Date:** 2026-08-21
**Topic:** osm-two-player-transfer-options

## Summary

Canlı bütçe 42.971.676 ve transfer listesi 72 oyuncu. Bütçeye sığan ikililer içinde ilk 11'i yükselten tek kombinasyon Murillo ile çok ucuz bir yedekten oluşuyor; en yüksek potansiyelli seçenek Murillo + Mlacic olsa da Mlacic'in seviyesi mevcut kadroya göre fazla düşük. Bu nedenle iki oyuncu alma zorunluluğu yoksa yalnızca Murillo alınmalı.

## Findings

### Zorunlu iki oyuncu seçimi

1. Murillo — 24 yaş, CB, DEF 98, fiyat 36.743.190; savunma ilk 11'ine +4 katkı.
2. Mlacic — 19 yaş, CB, DEF 73, fiyat 5.735.474; ilk 11 katkısı yok.

- Toplam maliyet: 42.478.664
- Kalan bütçe: 493.012
- Toplam ilk 11 katkısı: +4; katkının tamamı Murillo'dan geliyor.

### Neden ideal değil

- Mlacic, mevcut en düşük savunmacı Rothe'nin 94 seviyesinden 21 puan geride.
- Çok genç olmasına rağmen seviyesi, verimli antrenman hedefi sayılmayacak kadar düşük.
- İkinci oyuncu için 5,74 milyon harcamak kadroyu veya rotasyonu anlamlı biçimde güçlendirmiyor.
- Murillo tek başına alınırsa yaklaşık 6,23 milyon nakit korunur.

### Diğer ikili yaklaşımı

N. Paz (21 yaş, MID 85) + Lukeba (23 yaş, DEF 83) toplam 37.144.004 tutuyor ve daha dengeli iki genç oyuncu sunuyor; ancak ikisi de mevcut ilk 11 eşiklerini aşmadığı için anlık kadro katkıları sıfır. D. Costa + N. Paz gibi alternatifler de aynı nedenle elendi.

### Karar

İki oyuncu almak kesin şartsa Murillo + Mlacic, bütçe içindeki en yüksek toplam ilk 11 katkısını verir. Ancak gerçek öneri Murillo'yu tek başına almak ve kalan parayı sonraki listeye saklamaktır. İkinci transfer için en az orta saha OVR 96+, savunma DEF 90+ veya hücum ATT 96+ seviyesinde genç ve uygun fiyatlı bir oyuncu beklenmeli. Otomatik satın alma yapılmadı.

## Sources

- OSM canlı finans, kadro ve transfer listesi API yanıtları; 2026-08-21 tarihinde çalışma zamanı kimlik bilgileri yalnızca bellekte kullanılarak yenilendi.
- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
