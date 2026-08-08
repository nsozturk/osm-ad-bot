#!/usr/bin/env python3
"""OSM canli veri cekici — kendi token'inla.

HAR snapshot'i yerine OSM web-api'sinden TAZE veri ceker (guncel para, kadro,
transfer listesi), data/ klasorune yazar ve dogrudan oneriyi basar.

Token nasil alinir (Chrome HAR export'u auth header'ini sildigi icin gerekli):
  1. https://en.onlinesoccermanager.com adresinde oturum acikken F12 -> Console.
  2. Sunu yapistir:  copy(document.cookie.match(/access_token=([^;]+)/)[1])
     (token panoya kopyalanir; access_token httpOnly=False oldugu icin calisir)
  3. Buraya ver:
       python3 transfer-advisor/live_fetch.py --token "<yapistir>"
     ya da:
       export OSM_TOKEN="<yapistir>"; python3 transfer-advisor/live_fetch.py

Istege bagli otomatik yenileme:  --refresh-token "<refresh_token>"
(token ~birkac dk'da expire olursa yeniden almak yerine refresh kullanir).

Lig/takim varsayilani HAR'dan: lig 254009482, takim 2 (--league/--team ile degistir).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recommend

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://web-api.onlinesoccermanager.com/api"
# tokenRefresh icin OSM web istemci kimligi (ads HAR'indan; public client)
CLIENT_ID = "jPs3vVbg4uYnxGoyunSiNf1nIqUJmSFnpqJSVgWrJleu6Ak7Ga"
# Rotasyonlu tokenlarin saklandigi yer (data/ gitignore'lu)
TOKEN_FILE = os.path.join(HERE, "data", ".token")
REFRESH_FILE = os.path.join(HERE, "data", ".refresh")
SECRET_FILE = os.path.join(HERE, "data", ".client_secret")


def _read(path):
    try:
        return open(path).read().strip()
    except OSError:
        return ""


def _write(path, val):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(val or "")


def discover_client_secret():
    """client_secret'i once cache'ten, yoksa ads HAR'indaki tokenRefresh govdesinden al."""
    cached = _read(SECRET_FILE)
    if cached:
        return cached
    for har in ("osm-ads-timelimited.har", "osm-kadro.har", "osm-transfer-list.har"):
        path = os.path.join(os.path.dirname(HERE), har)
        if not os.path.exists(path):
            continue
        try:
            data = json.load(open(path))
        except Exception:
            continue
        for e in data.get("log", {}).get("entries", []):
            if "tokenRefresh" in e["request"]["url"] and e["request"]["method"] == "POST":
                body = e["request"].get("postData", {}).get("text", "")
                f = urllib.parse.parse_qs(body)
                if f.get("client_secret"):
                    _write(SECRET_FILE, f["client_secret"][0])
                    return f["client_secret"][0]
    return ""

BASE_HEADERS = {
    "accept": "application/json; charset=utf-8",
    "content-type": "application/json; charset=utf-8",
    "appversion": "3.251.0",
    "platformid": "13",
    "origin": "https://en.onlinesoccermanager.com",
    "referer": "https://en.onlinesoccermanager.com/",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"),
}


def _norm_token(tok):
    tok = (tok or "").strip().strip('"').strip("'")
    if tok.lower().startswith("bearer "):
        tok = tok[7:]
    return tok


def _get(url, token):
    hdr = dict(BASE_HEADERS)
    hdr["authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=hdr)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def refresh_access_token(refresh_token, client_secret=None):
    """refresh_token -> yeni access_token (OAuth2 refresh grant, secret zorunlu).

    Donen yeni access_token + (rotasyonlu) refresh_token data/ altina yazilir,
    boylece sonraki calistirmalar token sormadan kendini yeniler.
    """
    client_secret = client_secret or discover_client_secret()
    body = {"grant_type": "refresh_token", "client_id": CLIENT_ID,
            "client_secret": client_secret, "refresh_token": refresh_token}
    data = urllib.parse.urlencode(body).encode()
    hdr = dict(BASE_HEADERS)
    hdr["content-type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = urllib.request.Request(API + "/tokenRefresh", data=data, headers=hdr)
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.loads(r.read().decode("utf-8", "replace"))
    if j.get("access_token"):
        _write(TOKEN_FILE, j["access_token"])
    if j.get("refresh_token"):
        _write(REFRESH_FILE, j["refresh_token"])  # rotasyon: yenisini sakla
    return j


def fetch_all(token, league, team):
    base = f"{API}/v1/leagues/{league}/teams/{team}"
    finances = _get(f"{base}/finances/balanceandsavings", token)
    squad = _get(f"{base}/players", token)
    transfers = _get(f"{base}/transferplayers/0", token)
    return squad, transfers, finances


def main(argv=None):
    parser = recommend.build_argparser()
    parser.add_argument("--token", help="OSM access_token (env OSM_TOKEN da olur)")
    parser.add_argument("--refresh-token", help="OSM refresh_token (env OSM_REFRESH); access_token expire olursa yeniler")
    parser.add_argument("--client-secret", help="tokenRefresh icin client_secret (gerekirse)")
    parser.add_argument("--league", default="168272433", help="lig id")
    parser.add_argument("--team", default="10", help="takim id")
    parser.add_argument("--no-recommend", action="store_true", help="sadece data/ yaz, oneri basma")
    args = parser.parse_args(argv)

    # Oncelik: bayrak > env > kalici dosya (rotasyonlu)
    token = _norm_token(args.token or os.environ.get("OSM_TOKEN", "") or _read(TOKEN_FILE))
    refresh = (args.refresh_token or os.environ.get("OSM_REFRESH", "") or _read(REFRESH_FILE))

    if not token and refresh:
        print("[live] access_token yok, refresh_token ile aliniyor…", file=sys.stderr)
        try:
            token = refresh_access_token(refresh, args.client_secret).get("access_token", "")
        except urllib.error.HTTPError as e:
            print(f"[live] refresh basarisiz: {e.code} {e.read(200).decode('utf-8','replace')}", file=sys.stderr)
            return 2
    if not token:
        print("HATA: token yok. --token ile ver ya da OSM_TOKEN ayarla. "
              "(Console: copy(document.cookie.match(/access_token=([^;]+)/)[1]) )", file=sys.stderr)
        return 2

    try:
        squad, transfers, finances = fetch_all(token, args.league, args.team)
    except urllib.error.HTTPError as e:
        if e.code == 401 and refresh:
            print("[live] 401 — token expire, refresh ile yenileniyor…", file=sys.stderr)
            try:
                token = refresh_access_token(refresh, args.client_secret).get("access_token", "")
                squad, transfers, finances = fetch_all(token, args.league, args.team)
            except Exception as e2:
                print(f"[live] yenileme/cekme basarisiz: {e2}", file=sys.stderr)
                return 2
        elif e.code == 401:
            print("HATA 401: token gecersiz/expire. Tarayicidan TAZE access_token al "
                  "(birkac dk omurlu) ya da --refresh-token ver.", file=sys.stderr)
            return 2
        else:
            print(f"HATA {e.code}: {e.read(200).decode('utf-8','replace')}", file=sys.stderr)
            return 2
    except Exception as e:
        print(f"HATA: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    out = os.path.join(HERE, "data")
    os.makedirs(out, exist_ok=True)
    json.dump(squad, open(os.path.join(out, "squad.json"), "w"), ensure_ascii=False, indent=2)
    json.dump(transfers, open(os.path.join(out, "transfers.json"), "w"), ensure_ascii=False, indent=2)
    json.dump(finances or {}, open(os.path.join(out, "finances.json"), "w"), ensure_ascii=False, indent=2)
    bal = (finances or {}).get("balance", 0)
    print(f"[live] TAZE cekildi ✓  kadro={len(squad)}  transfer={len(transfers)}  "
          f"balance={bal:,}  -> {out}/")

    if args.no_recommend:
        return 0
    args.from_json = out  # recommend'i taze veriyle calistir
    print()
    return recommend.run(args)


if __name__ == "__main__":
    sys.exit(main())
