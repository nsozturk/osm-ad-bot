# OSM Güncel Transfer Seçenekleri

**Date:** 2026-08-21
**Topic:** osm-current-transfer-options

## Summary

Canlı OSM verisinde kullanılabilir bütçe 42.971.676, kadro 23 oyuncu ve transfer listesi 69 oyuncu. Önceden belirlenen 27 yaş sınırı altında, bütçeye sığan ve ilk 11'i gerçekten yükselten tek oyuncu Murillo; bu nedenle anlamlı bir çoklu transfer sepeti oluşmuyor.

## Findings

### Güncel ilk 11 eşikleri

- Kaleci: Donnarumma, DEF 99
- Savunma: Querfeld 95, R. James 95, Timber 95, Rothe 94
- Orta saha: Bellingham 102, Kemlein 101, Pedri 100
- Hücum: Yıldız 106, Güther 104, D. Doué 103

### En mantıklı transfer: Murillo

- Yaş: 24
- Rol: CB
- Savunma gücü: 98
- Fiyat: 36.989.788
- İlk 11 katkısı: Rothe'nin 94'lük savunma slotuna göre +4
- Alımdan sonra kalan: 5.981.888
- Mevcut kulüp: Nottingham Forest

Savunma, takımın diğer hatlarına göre en düşük ilk 11 eşiğine sahip. Murillo hem doğrudan +4 artış sağlıyor hem de 24 yaşında olduğu için antrenman değeri taşıyor.

### Çoklu transfer değerlendirmesi

Mevcut 69 kişilik transfer listesinde 27 yaş ve altında, bütçe içindeki başka hiçbir oyuncu kaleci 99, savunma 94, orta saha 100 veya hücum 103 ilk 11 eşiklerinden birini aşmıyor. Bu nedenle iki veya daha fazla oyuncudan oluşan anlamlı bir sepet yok; yedek veya daha zayıf oyuncu almak kadro gücünü artırmayacak.

### Karar

Şimdi transfer yapılacaksa Murillo alınmalı. Birden fazla oyuncu almak için mevcut pazarda bütçeyi harcamak mantıklı değil. Murillo alınmayacaksa para korunup sonraki listede DEF 98+, ATT 104+, MID 102+ veya GK 100+ genç oyuncu beklenmeli. Otomatik satın alma işlemi yapılmadı.

## Sources

- OSM canlı finans, kadro ve transfer listesi API yanıtları; 2026-08-21 tarihinde çalışma zamanı kimlik bilgileri yalnızca bellekte kullanılarak yenilendi.
- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
