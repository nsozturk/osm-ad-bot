# OSM Transfer Advisor

OSM (Online Soccer Manager) için **kadromu + transfer listesini + elimdeki parayı**
HAR dosyalarından okuyup, paramın yettiği ve kadromu en çok geliştirecek
oyuncuları öneren script seti. Saf Python 3 (stdlib), ek bağımlılık yok.

## Hızlı başlangıç

Proje kökünde (`osm/`) iki HAR dosyası dururken tek komut:

```bash
python3 transfer-advisor/advisor.py
```

Bu; HAR'ları okur → veriyi `transfer-advisor/data/` altına ayıklar →
kadro analizi + alışveriş planı + en iyi öneri listesini basar.

## Scriptler (her biri bağımsız çalışır)

| Dosya | Görev |
|---|---|
| `advisor.py` | **Ana giriş.** Ayıklama + öneriyi tek komutta zincirler. |
| `har_extract.py` | HAR → `data/squad.json`, `data/transfers.json`, `data/finances.json`. |
| `recommend.py` | Skorlama + alışveriş planı + rapor motoru. |
| `positions.py` | OSM pozisyon kodlarının çözümlenmesi (1=ATT, 2=MID, 3=DEF, 4=GK). |

Hangi API çağrılarından okunduğu:

- **Kadrom** → `…/leagues/<lig>/teams/<takım>/players`
- **Transfer listesi** → `…/teams/<takım>/transferplayers/0`
- **Para** → `…/finances/balanceandsavings` (`balance` + `savings`)

## Kullanım

```bash
# Varsayılan (bütçe = balance + savings, formasyon 4-3-3)
python3 transfer-advisor/advisor.py

# Bütçeyi elle ver (örn. kasada birikenle birlikte planla)
python3 transfer-advisor/advisor.py --budget 25000000

# Sadece bir mevki, daha uzun liste
python3 transfer-advisor/advisor.py --position DEF --top 20

# Bütçeyi aşan hedefleri de göster (neye ne kadar lazım)
python3 transfer-advisor/advisor.py --show-all

# Farklı formasyon (DEF-MID-ATT ya da 4 haneli)
python3 transfer-advisor/advisor.py --formation 4-2-3-1

# Genç odaklı: 24 yaş ve altı
python3 transfer-advisor/advisor.py --max-age 24

# JSON çıktı (başka araçlara beslemek için)
python3 transfer-advisor/recommend.py --json

# Önce ayıkla, sonra HAR'a dokunmadan tekrar tekrar çalıştır
python3 transfer-advisor/har_extract.py
python3 transfer-advisor/recommend.py --from-json transfer-advisor/data --budget 40000000
```

Tüm bayraklar için: `python3 transfer-advisor/recommend.py --help`

## Skor mantığı

Her transfer adayı, kaba mevkisindeki **en zayıf ilk-11 oyuncuma** göre değerlendirilir:

- **XI yükseltmesi** (ana etken): aday OVR − o mevkideki en zayıf ilk-11 OVR'm.
  Pozitifse adam doğrudan ilk-11'i güçlendirir.
- **Pozisyon ihtiyacı**: zayıf/eksik mevkiler (zayıf kaleci, açık slot…) ağırlıklı.
- **Kalite**: adamın mutlak OVR'si.
- **Gençlik**: ≤24 yaş primi, ≥30 yaş cezası.
- **Para verimliliği**: harcanan para başına kazanılan OVR.

**Asla downgrade önermez:** Mevcut ilk-11'imin altında kalan (oynamayacak) bir
oyuncu varsayılan listede gösterilmez. Onları da görmek için `--include-depth`.

**Alışveriş planı**, toplam bütçeye sığan ve ilk-11'i iteratif geliştiren bir
sepet kurar: bir oyuncuyu alınca o mevkideki en zayıf oyuncuyu "değiştirir",
böylece aynı mevkiye gereksiz yığılma olmaz ve bütçe en yüksek OVR kazanımına gider.

## Bu veri setindeki durum (örnek)

- **Takım**: Antalyaspor, **bütçe ≈ 11.87M**.
- Orta saha **çok güçlü** (Bellingham 95, Fernández 93, Paz 90); **kaleci/defans/forvet zayıf**.
- 11.87M ile tek gerçek yükseltme: **Frankowski (DEF 62, +14 OVR)**. Kaleci için
  ~35M (Courtois), forvet için ~25M (Barcola) gerekir — araç bunu açıkça raporlar.

## Notlar / sınırlar

- **Fiyat = 2.5 × değer** bu ligde sabit; dolayısıyla "pazarlık" adaylar arasında
  ayırt edici değil — gerçek ayrım ihtiyaç + OVR + yaş + bütçeye sığma üzerinden.
- Alışveriş planı **kaba mevkiye** (GK/DEF/MID/ATT) göre gruplar. Geniş bütçede
  "4 defans" ihtiyacını 3 sağ-bekle doldurabilir; alt-rolü (CB/LB/RB) seçmek için
  `--position DEF` ile listeye bakıp kendin karar ver.
- İnce pozisyon etiketleri (CB/LB/DM…) best-effort; skorlamayı etkilemez.
- Kendi transfer listene koyduğun oyuncular öneriden otomatik çıkarılır.
- HAR'lar `.gitignore`'da (oturum/kimlik token'ı içerir); `data/` de derived olduğu
  için ignore'lu.

## Yeni veri çekmek için

OSM'i tarayıcıda aç → DevTools → Network → kadro ve transfer listesi sayfalarını
gez → ilgili sekmeyi **"Save all as HAR"** ile kaydet → bu klasöre (ya da `--kadro`
/ `--transfers` ile verdiğin yola) koy.
