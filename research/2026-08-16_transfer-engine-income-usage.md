# Transfer Motorunun Gelen Parayı Kullanması

**Date:** 2026-08-16
**Topic:** transfer-engine-income-usage

## Summary

Transfer öneri motoru canlı çalıştırıldığında finans endpoint'inden güncel `balance` ve `savings` değerlerini alıp ikisini bütçe olarak toplar. Bu nedenle hesaba geçmiş satış ve reklam gelirleri bir sonraki canlı öneriye dahil edilir; ancak mevcut `run.sh` transfer motorunu periyodik çalıştırmaz ve otomatik satın alma yapmaz.

## Findings

- `live_fetch.py`, her canlı öneri koşumunda `/finances/balanceandsavings` endpoint'ini kadro ve transfer listesiyle birlikte çağırır.
- `recommend.py`, elle `--budget` verilmemişse `balance + savings` toplamını kullanır.
- Daha önce kaydedilmiş JSON/HAR verisiyle yalnızca `recommend.py` çalıştırılırsa bütçe o snapshot'a ait olabilir; yeni para için yeniden canlı çekim gerekir.
- `run.sh` yalnızca reklam conductor'ını ve otomatik training yöneticisini başlatır.
- Kodda transfer satın alma endpoint'ine istek atan otomatik bir motor bulunmuyor; mevcut özellik öneri ve alışveriş planı üretir.

## Sources

- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/live_fetch.py`
- `/Users/ns0bj/Development/Fun/osm/transfer-advisor/recommend.py`
- `/Users/ns0bj/Development/Fun/osm/run.sh`
- `/Users/ns0bj/Development/Fun/osm/auto_training.py`
