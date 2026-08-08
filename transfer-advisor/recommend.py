#!/usr/bin/env python3
"""OSM transfer onerici.

Kadromu + transfer listesini + elimdeki parayi okuyup, paramin yettigi ve
kadromu en cok gelistirecek oyunculari siralar; ayrica toplam butceye sigan
bir "alisveris plani" cikarir.

Skor mantigi (her aday transfer oyuncusu icin):

  * XI yukseltmesi : aday OVR - o pozisyondaki en zayif ilk-11 oyuncum.
                     Pozitifse adam direkt ilk-11'i guclendirir. (ana etken)
  * Pozisyon ihtiyaci: zayif/eksik pozisyonlar (zayif kaleci, bos defans...) agirlikli.
  * Kalite          : adamin mutlak OVR'si.
  * Genclik         : 24 yas alti potansiyel/deger primi, 30+ cezasi.
  * Para verimliligi: harcanan para basina kazanilan OVR.

NOT: Bu ligde transfer fiyati her zaman ~2.5 x oyuncu degeri oldugundan, fiyat
pazarligi adaylar arasinda ayirt edici degildir; gercek ayrim ihtiyac + OVR +
yas + butceye sigma uzerinden olur.

Calistirma:
    python3 recommend.py                       # ./osm-kadro.har + ./osm-transfer-list.har
    python3 recommend.py --budget 20000000     # parayi elle gir
    python3 recommend.py --position DEF --top 15
    python3 recommend.py --from-json data       # onceden ayiklanmis JSON'dan
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import har_extract
from positions import POSITION, POSITION_ORDER, coarse_label, specific_label

# --- skor agirliklari (sezgisel, README'de aciklandi) -------------------------
W_UPGRADE = 3.0     # ilk-11 OVR yukseltmesi (ana etken)
W_NEED = 1.4        # pozisyon zayifligi / bosluk
W_QUALITY = 0.6     # mutlak OVR
W_YOUTH = 1.0       # genclik primi
W_EFFIC = 1.2       # para basina OVR verimliligi

# Varsayilan formasyon: 4-3-3 (GK her zaman 1)
DEFAULT_FORMATION = "4-3-3"

# kaba pozisyon -> formasyondaki anahtar
POS_KEY = {4: "GK", 3: "DEF", 2: "MID", 1: "ATT"}


@dataclass
class Player:
    id: int
    name: str
    position: int          # 1..4 kaba
    specific: int          # ince
    ovr: int
    att: int
    dfn: int
    age: int
    value: int
    # transfer adaylarinda dolu olan alanlar
    price: int = 0
    team_name: str = ""
    in_squad: bool = False
    # hesaplanan
    score: float = 0.0
    xi_upgrade: int = 0
    open_slot: bool = False
    meaningful: bool = False
    reasons: list = field(default_factory=list)

    @property
    def pos_label(self):
        return coarse_label(self.position)

    @property
    def role(self):
        return specific_label(self.position, self.specific)


def _player_from_raw(p, price=0, team_name="", in_squad=False):
    return Player(
        id=p["id"],
        name=p.get("name") or p.get("fullName") or str(p["id"]),
        position=p["position"],
        specific=p.get("specificPosition", 0),
        ovr=p.get("statOvr", 0),
        att=p.get("statAtt", 0),
        dfn=p.get("statDef", 0),
        age=p.get("age", 0),
        value=p.get("value", 0),
        price=price,
        team_name=team_name,
        in_squad=in_squad,
    )


def parse_squad(raw_squad):
    return [_player_from_raw(p, in_squad=True) for p in raw_squad]


def parse_transfers(raw_transfers, my_ids):
    out = []
    for entry in raw_transfers:
        p = entry.get("player") or {}
        if not p:
            continue
        out.append(
            _player_from_raw(
                p,
                price=entry.get("price", 0),
                team_name=(entry.get("team") or {}).get("name", ""),
                in_squad=p.get("id") in my_ids,
            )
        )
    return out


# --- formasyon & kadro analizi ------------------------------------------------
def parse_formation(text):
    """'4-3-3' -> {4:1(GK), 3:4(DEF), 2:3(MID), 1:3(ATT)} (kaba pozisyon -> ilk-11 sayisi)."""
    try:
        parts = [int(x) for x in text.split("-")]
    except ValueError:
        parts = [4, 3, 3]
    if len(parts) == 3:
        d, m, a = parts
    elif len(parts) == 4:  # ornek 4-2-3-1 -> DEF=4, MID=2+3=5, ATT=1
        d, m1, m2, a = parts
        m = m1 + m2
    else:
        d, m, a = 4, 3, 3
    return {4: 1, 3: d, 2: m, 1: a}


def analyze_squad(squad, formation):
    """Pozisyon basina derinlik / kalite ozeti + ilk-11 esigi.

    Dondurur: pos -> dict(count, best, avg, starters_needed, marginal, verdict)
    'marginal' = o pozisyondaki en zayif ilk-11 oyuncunun OVR'si (eksikse 0).
    """
    summary = {}
    for pos in POSITION_ORDER:
        players = sorted((p for p in squad if p.position == pos),
                         key=lambda x: -x.ovr)
        need = formation[pos]
        ovrs = [p.ovr for p in players]
        if len(players) >= need:
            marginal = ovrs[need - 1]
        else:
            marginal = 0  # acik kadro slotu
        best = ovrs[0] if ovrs else 0
        avg = round(sum(ovrs) / len(ovrs), 1) if ovrs else 0
        # verdict: ilk-11 esigi + derinlik
        if marginal == 0:
            verdict = "ACIK SLOT"
        elif marginal < 60:
            verdict = "cok zayif"
        elif marginal < 75:
            verdict = "zayif"
        elif marginal < 85:
            verdict = "orta"
        else:
            verdict = "guclu"
        summary[pos] = dict(
            count=len(players), best=best, avg=avg, starters_needed=need,
            marginal=marginal, verdict=verdict, players=players,
        )
    return summary


def _need_weight(marginal, count, need):
    """Pozisyon ihtiyaci 0..~50 arasi. Dusuk marginal + ince kadro -> yuksek."""
    quality_gap = max(0, 85 - marginal)        # 85 OVR'lik saglikli ilk-11 hedefi
    depth_gap = max(0, (need + 1) - count) * 8  # yedek dahil ince kadro cezasi
    return quality_gap + depth_gap


def _youth_bonus(age):
    if age <= 0:
        return 0
    if age <= 21:
        return 14
    if age <= 24:
        return 8
    if age <= 27:
        return 2
    if age <= 30:
        return -2
    return -8


def _efficiency(ovr, price):
    """Para basina OVR (milyon basina). Ucuz + iyi oyuncu yuksek alir."""
    if price <= 0:
        return 0.0
    return ovr / (price / 1_000_000)


# --- skorlama -----------------------------------------------------------------
def score_candidates(candidates, squad_summary, budget):
    scored = []
    for c in candidates:
        if c.in_squad:
            continue  # kendi oyuncum (zaten listede satilik) — atla
        info = squad_summary.get(c.position)
        if not info:
            continue
        marginal = info["marginal"]
        xi_upgrade = c.ovr - marginal
        open_slot = info["count"] < info["starters_needed"]
        # Anlamli alim: ya ilk-11'i guclendirir (OVR > en zayif starter) ya da
        # acik bir kadro slotunu doldurur. Aksi halde mevcut oyuncularimdan
        # dusuk bir yedek -> oneri DEGIL.
        meaningful = xi_upgrade > 0 or open_slot
        need = _need_weight(marginal, info["count"], info["starters_needed"])
        youth = _youth_bonus(c.age)
        effic = _efficiency(c.ovr, c.price)

        score = (
            W_UPGRADE * max(0, xi_upgrade)
            + W_NEED * need
            + W_QUALITY * c.ovr
            + W_YOUTH * youth
            + W_EFFIC * effic
        )
        if not meaningful:
            score -= 1000  # downgrade'leri en dibe at

        reasons = []
        if xi_upgrade > 0:
            reasons.append(f"ilk-11'i +{xi_upgrade} OVR guclendirir ({info['marginal']}->{c.ovr})")
        elif open_slot:
            reasons.append(f"{POS_KEY[c.position]} acik slotunu doldurur")
        else:
            reasons.append(f"yedek — mevcut ilk-11'in altinda (OVR {c.ovr} < {info['marginal']})")
        if c.age <= 24:
            reasons.append(f"genc ({c.age})")
        if c.price > budget:
            reasons.append("BUTCE ASIYOR")
        c.score = round(score, 1)
        c.xi_upgrade = xi_upgrade
        c.open_slot = open_slot
        c.meaningful = meaningful
        c.reasons = reasons
        scored.append(c)
    scored.sort(key=lambda x: -x.score)
    return scored


def build_shopping_plan(scored, squad_summary, formation, budget):
    """Toplam butceye sigan, ilk-11'i iteratif gelistiren alisveris sepeti.

    Her pozisyon icin mevcut ilk-11 OVR'lerini tutar (acik slot = 0). Skor
    sirasiyla ilerler; bir oyuncuyu yalnizca (a) fiyati kalan butceye siar VE
    (b) o pozisyondaki en zayif starter'dan daha iyiyse alir. Alinca o starter'i
    degistirir, dolayisiyla ayni pozisyon guclendikce yeni alimlar daha yuksek
    esik gerektirir -> ne downgrade onerir ne de gereksiz yiginma yapar.
    """
    starters = {}
    for pos in POSITION_ORDER:
        info = squad_summary[pos]
        ovrs = sorted((p.ovr for p in info["players"]), reverse=True)
        slots = ovrs[: info["starters_needed"]]
        slots += [0] * (info["starters_needed"] - len(slots))  # acik slotlar
        starters[pos] = slots

    remaining = budget
    basket = []
    for c in scored:
        if c.price <= 0 or c.price > remaining:
            continue
        slots = starters.get(c.position)
        if not slots:
            continue
        weakest = min(slots)
        if c.ovr > weakest:  # ilk-11'i gercekten iyilestirir (acik slot dahil)
            basket.append(c)
            remaining -= c.price
            slots[slots.index(weakest)] = c.ovr
    return basket, remaining


# --- raporlama ----------------------------------------------------------------
def fmt_money(n):
    if n is None:
        return "?"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def print_squad_report(squad_summary):
    print("=" * 70)
    print("KADRO ANALIZI  (ilk-11 esigi = o mevkideki en zayif ilk-11 OVR)")
    print("=" * 70)
    print(f"{'Mevki':5} {'Adet':>4} {'EnIyi':>5} {'Ort':>5} {'IlkXIesik':>9}  Durum")
    for pos in POSITION_ORDER:
        i = squad_summary[pos]
        print(f"{POS_KEY[pos]:5} {i['count']:>4} {i['best']:>5} {i['avg']:>5} "
              f"{i['marginal']:>9}  {i['verdict']}")
    print()


def print_recommendations(scored, top, position_filter=None):
    label = f" ({position_filter})" if position_filter else ""
    print("=" * 70)
    print(f"EN IYI {top} ONERI{label}  (skor = ihtiyac + OVR yukseltmesi + genclik + verim)")
    print("=" * 70)
    rows = scored
    if position_filter:
        want = {v: k for k, v in POS_KEY.items()}.get(position_filter.upper())
        rows = [c for c in rows if c.position == want]
    for i, c in enumerate(rows[:top], 1):
        afford = "" if c.price <= 0 else ("  [PAHALI]" if "BUTCE ASIYOR" in c.reasons else "")
        print(f"{i:>2}. {c.name:<18} {c.role:<3} OVR{c.ovr:<3} "
              f"yas{c.age:<2} {c.team_name[:16]:<16} "
              f"fiyat {fmt_money(c.price):>7}  skor {c.score:>6}{afford}")
        if c.reasons:
            print(f"     -> " + "; ".join(c.reasons))
    print()


def print_shopping_plan(basket, remaining, budget):
    print("=" * 70)
    print(f"ALISVERIS PLANI  (butce {fmt_money(budget)} — kadromu en cok gelistiren sepet)")
    print("=" * 70)
    if not basket:
        print("  Butceye sigan, kadroyu gelistiren uygun oyuncu bulunamadi.")
        print()
        return
    spent = 0
    for c in basket:
        spent += c.price
        note = c.reasons[0] if c.reasons else ""
        print(f"  - {c.name:<18} {c.role:<3} OVR{c.ovr:<3} yas{c.age:<2} "
              f"{fmt_money(c.price):>7}   {note}")
    print("-" * 70)
    print(f"  Toplam harcama : {fmt_money(spent)}   ({spent:,})")
    print(f"  Kalan butce    : {fmt_money(remaining)}   ({remaining:,})")
    print()


def print_budget_gap(upgrades_any_price, budget, covered=None):
    """Butceye sigmayan pozisyonlar icin: en ucuz gercek yukseltme ne kadar tutar."""
    covered = covered or set()
    over = [c for c in upgrades_any_price if c.price > budget and c.position not in covered]
    if not over:
        return
    print("=" * 70)
    print(f"BUTCE USTU — sepete giremeyen mevkilerde en ucuz gercek yukseltmeler")
    print("=" * 70)
    seen = set()
    for c in over:
        if c.position in seen:
            continue  # pozisyon basina en ucuzu
        seen.add(c.position)
        gap = c.price - budget
        print(f"  {POS_KEY[c.position]:4} {c.name:<18} OVR{c.ovr:<3} "
              f"fiyat {fmt_money(c.price):>7}  (+{fmt_money(gap)} daha gerekli)  +{c.xi_upgrade} OVR")
    print()


# --- yukleme ------------------------------------------------------------------
def load_inputs(args):
    """HAR'lardan ya da onceden ayiklanmis JSON'dan ham veriyi yukler."""
    if args.from_json:
        d = args.from_json
        raw_squad = json.load(open(os.path.join(d, "squad.json")))
        raw_transfers = json.load(open(os.path.join(d, "transfers.json")))
        finances = json.load(open(os.path.join(d, "finances.json")))
    else:
        raw_squad = har_extract.load_squad(args.kadro)
        raw_transfers = har_extract.load_transfers(args.transfers)
        finances = (har_extract.load_finances(args.kadro)
                    or har_extract.load_finances(args.transfers) or {})
    return raw_squad, raw_transfers, finances


def run(args):
    raw_squad, raw_transfers, finances = load_inputs(args)
    if not raw_squad:
        print("HATA: kadro bulunamadi (HAR yolu / endpoint dogru mu?).", file=sys.stderr)
        return 1
    if not raw_transfers:
        print("HATA: transfer listesi bulunamadi.", file=sys.stderr)
        return 1

    squad = parse_squad(raw_squad)
    my_ids = {p.id for p in squad}
    candidates = parse_transfers(raw_transfers, my_ids)

    # butce: kullanici verdiyse o, yoksa balance + savings
    if args.budget is not None:
        budget = args.budget
    else:
        budget = finances.get("balance", 0) + finances.get("savings", 0)

    formation = parse_formation(args.formation)
    squad_summary = analyze_squad(squad, formation)
    scored = score_candidates(candidates, squad_summary, budget)

    # ek filtreler
    if not args.include_depth:
        # varsayilan: yalnizca gercek ilk-11 yukseltmesi / acik slot dolduran oyuncular
        scored = [c for c in scored if c.meaningful]
    if args.max_age:
        scored = [c for c in scored if c.age <= args.max_age]
    if args.min_upgrade:
        scored = [c for c in scored if c.xi_upgrade >= args.min_upgrade]
    # butce ustu de olsa tum gercek yukseltmeler (fiyat bosluk ipucu icin)
    upgrades_any_price = sorted(
        (c for c in scored if c.xi_upgrade > 0 or c.open_slot),
        key=lambda x: x.price)
    affordable = [c for c in scored if c.price <= budget]
    if not args.show_all:
        scored = affordable

    if args.json:
        out = {
            "budget": budget,
            "formation": args.formation,
            "squad_summary": {POS_KEY[p]: {k: v for k, v in i.items() if k != "players"}
                              for p, i in squad_summary.items()},
            "recommendations": [
                dict(name=c.name, role=c.role, position=c.pos_label, ovr=c.ovr,
                     att=c.att, dfn=c.dfn, age=c.age, value=c.value, price=c.price,
                     team=c.team_name, score=c.score, xi_upgrade=c.xi_upgrade,
                     reasons=c.reasons)
                for c in scored[: args.top]
            ],
        }
        basket, remaining = build_shopping_plan(scored, squad_summary, formation, budget)
        out["shopping_plan"] = {
            "players": [dict(name=c.name, role=c.role, ovr=c.ovr, age=c.age,
                             price=c.price) for c in basket],
            "remaining": remaining,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"Butce: {fmt_money(budget)} ({budget:,})   |   Formasyon: {args.formation}"
          f"   |   Transfer adayi: {len(candidates)} (kendi 2 oyuncum haric)")
    print()
    print_squad_report(squad_summary)
    basket, remaining = build_shopping_plan(scored, squad_summary, formation, budget)
    print_shopping_plan(basket, remaining, budget)
    print_budget_gap(upgrades_any_price, budget, covered={c.position for c in basket})
    print_recommendations(scored, args.top, args.position)
    return 0


def build_argparser():
    ap = argparse.ArgumentParser(description="OSM transfer onerici")
    ap.add_argument("--kadro", default="osm-kadro.har", help="kadro HAR yolu")
    ap.add_argument("--transfers", default="osm-transfer-list.har", help="transfer HAR yolu")
    ap.add_argument("--from-json", help="HAR yerine bu klasordeki ayiklanmis JSON'dan oku")
    ap.add_argument("--budget", type=int, help="elle butce (varsayilan: balance+savings)")
    ap.add_argument("--formation", default=DEFAULT_FORMATION, help="ornek 4-3-3, 4-4-2, 4-2-3-1")
    ap.add_argument("--top", type=int, default=12, help="kac oneri gosterilsin")
    ap.add_argument("--position", choices=["GK", "DEF", "MID", "ATT"], help="sadece bu mevki")
    ap.add_argument("--max-age", type=int, help="bu yastan buyukleri ele")
    ap.add_argument("--min-upgrade", type=int, help="en az bu kadar OVR ilk-11 yukseltmesi")
    ap.add_argument("--include-depth", action="store_true",
                    help="ilk-11'in altindaki yedek/downgrade adaylari da goster")
    ap.add_argument("--show-all", action="store_true", help="butceyi asanlari da goster")
    ap.add_argument("--json", action="store_true", help="JSON cikti")
    return ap


if __name__ == "__main__":
    sys.exit(run(build_argparser().parse_args()))
