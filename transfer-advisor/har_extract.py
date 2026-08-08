#!/usr/bin/env python3
"""HAR -> yapilandirilmis veri.

OSM web arayuzunun yaptigi API cagrilarini iki HAR dosyasindan ayiklar:

  * Kadrom            : GET .../leagues/<lig>/teams/<takim>/players
  * Transfer listesi  : GET .../leagues/<lig>/teams/<takim>/transferplayers/0
  * Para durumu       : GET .../finances/balanceandsavings

Bagimsiz calistirilabilir:

    python3 har_extract.py --kadro osm-kadro.har --transfers osm-transfer-list.har --out data

ya da bir modul olarak ``load_squad`` / ``load_transfers`` / ``load_finances``
fonksiyonlariyla import edilir.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Aranan API yollari (URL'de substring olarak gecer)
EP_SQUAD = "/teams/2/players"
EP_TRANSFERS = "/transferplayers/0"
EP_FINANCES = "/finances/balanceandsavings"
# Lig/takim id'lerinden bagimsiz, daha genel kaliplar (yedek):
EP_SQUAD_ANY = "/players"
EP_TRANSFERS_ANY = "/transferplayers/"
EP_FINANCES_ANY = "/balanceandsavings"


def _entry_text(entry):
    """Bir HAR entry'sinin response govdesini cozer (base64 olabilir)."""
    content = entry.get("response", {}).get("content", {})
    text = content.get("text")
    if not text:
        return None
    if content.get("encoding") == "base64":
        try:
            text = base64.b64decode(text).decode("utf-8", "replace")
        except Exception:
            return None
    return text


def _iter_json_responses(har_path, url_substr):
    """url_substr iceren tum entry'lerin parse edilmis JSON govdelerini verir."""
    with open(har_path, "r", encoding="utf-8") as fh:
        har = json.load(fh)
    for entry in har.get("log", {}).get("entries", []):
        url = entry.get("request", {}).get("url", "")
        if url_substr not in url:
            continue
        text = _entry_text(entry)
        if not text:
            continue
        try:
            yield json.loads(text)
        except json.JSONDecodeError:
            continue


def _best_list(har_path, primary_substr, fallback_substr=None):
    """En cok ogeye sahip JSON liste yanitini dondurur (duplikeleri ele)."""
    best = []
    for substr in (primary_substr, fallback_substr):
        if not substr:
            continue
        for data in _iter_json_responses(har_path, substr):
            if isinstance(data, list) and len(data) >= len(best):
                best = data
        if best:
            break
    return best


def load_squad(har_path):
    """Kadromdaki oyuncularin ham listesi (her biri bir player dict)."""
    return _best_list(har_path, EP_SQUAD, EP_SQUAD_ANY)


def load_transfers(har_path):
    """Transfer listesindeki ham kayitlar (her biri {player, price, team, ...})."""
    return _best_list(har_path, EP_TRANSFERS, EP_TRANSFERS_ANY)


def load_finances(har_path):
    """Para durumu: {'balance':..., 'savings':..., 'fixedIncome':...} ya da None."""
    last = None
    for substr in (EP_FINANCES, EP_FINANCES_ANY):
        for data in _iter_json_responses(har_path, substr):
            if isinstance(data, dict) and "balance" in data:
                last = data
        if last:
            break
    return last


def _main(argv=None):
    ap = argparse.ArgumentParser(description="OSM HAR dosyalarindan veri ayikla")
    ap.add_argument("--kadro", default="osm-kadro.har", help="kadro HAR yolu")
    ap.add_argument("--transfers", default="osm-transfer-list.har", help="transfer listesi HAR yolu")
    ap.add_argument("--out", default="data", help="JSON ciktilarinin yazilacagi klasor")
    args = ap.parse_args(argv)

    squad = load_squad(args.kadro)
    finances = load_finances(args.kadro) or load_finances(args.transfers)
    transfers = load_transfers(args.transfers)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "squad.json"), "w", encoding="utf-8") as fh:
        json.dump(squad, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "transfers.json"), "w", encoding="utf-8") as fh:
        json.dump(transfers, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "finances.json"), "w", encoding="utf-8") as fh:
        json.dump(finances or {}, fh, ensure_ascii=False, indent=2)

    bal = (finances or {}).get("balance", 0)
    print(f"[har_extract] kadro      : {len(squad)} oyuncu        -> {args.out}/squad.json")
    print(f"[har_extract] transferler: {len(transfers)} kayit       -> {args.out}/transfers.json")
    print(f"[har_extract] para        : balance={bal:,}  -> {args.out}/finances.json")


if __name__ == "__main__":
    _main()
