"""OSM oyuncu pozisyon kodlarinin cozumlenmesi.

OSM API'sinde her oyuncunun iki pozisyon alani var:

* ``position``          -> kaba rol (1..4). Cok guvenilir, recommender bunu kullanir.
* ``specificPosition``  -> daha ince rol (CB / LB / DM / ST ...). Asagidaki harita
  HAR verisindeki taninan oyunculardan cikarilan *best-effort* bir eslemedir;
  yalnizca ekranda etiket gostermek icin kullanilir, skorlamayi etkilemez.
"""

# --- Kaba pozisyon (position) -------------------------------------------------
# Veriden dogrulandi: 1=hucum, 2=orta saha, 3=defans, 4=kaleci
POSITION = {
    1: "ATT",   # Forward / hucum
    2: "MID",   # Midfield / orta saha
    3: "DEF",   # Defender / defans
    4: "GK",    # Goalkeeper / kaleci
}

# Recommender ve formasyon mantigi icin sira (saha dizilimi: GK -> DEF -> MID -> ATT)
POSITION_ORDER = [4, 3, 2, 1]

# --- Ince pozisyon (specificPosition) — best-effort ---------------------------
# (kaba_pozisyon, ince_pozisyon) -> etiket. Taninan oyunculardan cikarildi:
#   Horkas/Kelleher=(4,6)GK  Pacho/Ozcan=(3,3)CB  Carreras=(3,9)LB  Dalot=(3,12)RB
#   Bellingham=(2,2)CM  Lerma/Garcia=(2,5)DM  Paz=(2,1)AM
#   Pavlidis/Zirkzee=(1,4)ST  Okafor/Ballet=(1,8)W  Yamal=(1,11)W
SPECIFIC_POSITION = {
    (4, 6): "GK",
    (3, 3): "CB",
    (3, 7): "RB",   # best-effort (sag bek/kanat bek)
    (3, 9): "LB",
    (3, 12): "RB",
    (2, 1): "AM",
    (2, 2): "CM",
    (2, 5): "DM",
    (1, 4): "ST",
    (1, 8): "W",
    (1, 10): "W",
    (1, 11): "W",
}


def coarse_label(position):
    """1..4 -> 'ATT'/'MID'/'DEF'/'GK'."""
    return POSITION.get(position, f"P{position}")


def specific_label(position, specific):
    """Ince pozisyon etiketi; bilinmiyorsa kaba etikete duser."""
    lbl = SPECIFIC_POSITION.get((position, specific))
    if lbl:
        return lbl
    return f"{coarse_label(position)}{specific}"
