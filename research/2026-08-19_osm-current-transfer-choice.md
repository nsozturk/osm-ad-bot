# OSM Güncel Transfer Seçimi

**Date:** 2026-08-19
**Topic:** osm-current-transfer-choice

## Summary

Canlı OSM verisinde kullanılabilir bütçe 37.638.010, kadro 23 oyuncu ve transfer listesi 72 oyuncu. Bellingham kadroya katılmış durumda; 27 yaş ve altı, bütçeye sığan oyuncular arasında ilk 11'i yükselten tek aday Chalobah olsa da 22.718.650 karşılığındaki +3 savunma katkısı mevcut genç oyuncu Rothe'nin gelişimi düşünüldüğünde yeterince verimli değil. Güncel pazarda en mantıklı karar transfer yapmadan para biriktirmek.

## Findings

### Güncel ilk 11 eşikleri

- Kaleci: Donnarumma, DEF 94
- Savunma: Timber 94, R. James 92, Querfeld 91, Rothe 88
- Orta saha: Bellingham 97, Kemlein 96, Pedri 96
- Hücum: Yıldız 102, D. Doué 101, Gakpo 95

### Alınabilecek tek anlamlı aday

- Oyuncu: Chalobah
- Yaş: 27
- Rol: CB
- Savunma gücü: 91
- Fiyat: 22.718.650
- Kadro katkısı: Rothe'nin 88'lik slotuna göre +3
- Alımdan sonra kalan: 14.919.360

### Neden şimdi alınmamalı

- Chalobah yaş sınırının üst ucunda ve antrenman getirisi genç oyunculara göre düşük.
- Rothe 21 yaşında, otomatik antrenmanda aktif biçimde gelişiyor ve güncel gücü 88'e ulaştı.
- 22,72 milyonluk maliyet yalnızca +3 geçici katkı veriyor; Rothe geliştikçe fark daha da küçülecek.
- Mevcut pazarda bütçeye sığan başka bir 27 yaş altı oyuncu ilk 11 eşiğini aşmıyor.

### Karar

Bu pazarda transfer yapılmamalı. Sonraki listede tercihen 25 yaş veya altında, CB rolünde DEF 94 ve üzeri bir oyuncu beklenmeli. Alternatif olarak hücumda ATT 98+, kalede DEF 97+ veya orta sahada OVR 98+ gelmeden büyük bütçe harcanmamalı. Kullanıcı hemen transfer yapmak isterse mevcut listenin tek seçeneği Chalobah'tır; ancak ana öneri beklemektir.

## Sources

- OSM canlı finans, kadro ve transfer listesi API yanıtları; 2026-08-19 tarihinde çalışma zamanı kimlik bilgileri yalnızca bellekte kullanılarak yenilendi.
- `/Users/ns0bj/Development/Fun/osm/osm_ad_bot_conductor.py`
- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
