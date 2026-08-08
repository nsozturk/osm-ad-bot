#!/usr/bin/env python3
"""OSM Transfer Advisor — tek komutluk giris.

HAR dosyalarini okur, veriyi data/ klasorune ayiklar (kayit), sonra kadroma +
parama gore transfer onerisi + alisveris plani basar.

    python3 advisor.py
    python3 advisor.py --budget 25000000 --formation 4-2-3-1
    python3 advisor.py --position DEF --top 20

Tum bayraklar recommend.py'ye gecer (--help icin oraya bakin).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import har_extract
import recommend

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    parser = recommend.build_argparser()
    parser.add_argument("--no-extract", action="store_true",
                        help="data/ klasorune JSON yazma adimini atla")
    args = parser.parse_args(argv)

    # Varsayilan HAR yollari: once CWD, yoksa proje kokunde (transfer-advisor'in ustu)
    for attr in ("kadro", "transfers"):
        p = getattr(args, attr)
        if not os.path.exists(p):
            alt = os.path.join(os.path.dirname(HERE), p)
            if os.path.exists(alt):
                setattr(args, attr, alt)

    # Veriyi data/ klasorune ayikla (kayit/denetim icin) — JSON ciktida sessiz kal
    if not args.no_extract and not args.from_json and not args.json:
        try:
            har_extract._main(["--kadro", args.kadro, "--transfers", args.transfers,
                               "--out", os.path.join(HERE, "data")])
            print()
        except Exception as e:  # ayiklama hatasi oneriyi engellemesin
            print(f"[uyari] data/ ayiklama atlandi: {e}", file=sys.stderr)

    return recommend.run(args)


if __name__ == "__main__":
    sys.exit(main())
