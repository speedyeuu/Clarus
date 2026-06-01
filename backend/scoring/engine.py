from loguru import logger
from typing import Dict
import json
from db.client import get_supabase

# Data class z lib/types.ts zrcadlená v Pythonu
class DailyScoreModel:
    def __init__(self, scores: dict, weights: dict, total: float, label: str,
                 effective_weights: dict | None = None):
        self.scores = scores
        self.weights = weights
        self.total = total
        self.label = label
        # Efektivní váhy po aplikaci freshness multiplikátoru (pro debugging)
        self.effective_weights = effective_weights or weights

def get_label_for_score(score: float) -> str:
    """Převod celkového skóre na trend label dle plan.md na škále -10 až +10."""
    if score >= 7.0: return "Strong Bullish"
    if score >= 3.0: return "Bullish"
    if score >= 1.0: return "Mildly Bullish"
    if score > -1.0: return "Neutral"
    if score > -3.0: return "Mildly Bearish"
    if score > -7.0: return "Bearish"
    return "Strong Bearish"


def get_freshness_multiplier(age_days: int) -> float:
    """
    Vrátí multiplikátor váhy (0.0 - 1.0) podle stáří posledního čtení.

    Logika:
      - age 0   → 1.00 (čerstvé dnešní čtení, plná váha)
      - age 3   → 0.90 (3 dny stará data – stále relevantní)
      - age 7   → 0.75 (týden starý report)
      - age 14  → 0.50 (dva týdny – výrazně zastaralý)
      - age 21  → 0.30 (tři týdny)
      - age 30  → 0.15 (měsíc starý report – téměř ignorovaný)
      - age 45+ → 0.05 (čtvrtletní data – minimální vliv)
      - age 60+ → 0.02 (starší než 2 měsíce – takřka nulový vliv)

    Proč ne lineárně:
      Trh reaguje nejsilněji na čerstvé zprávy. Po prvním týdnu
      se surprise začíná "trávit" a další dva týdny jsou stále
      relevantní ale méně. Starší data jsou prakticky zapomenutá.

    Tato křivka je záměrně agresivnější pro stará data
    než starý decay v carry-forward (který byl jen lineární).
    """
    if age_days <= 0:
        return 1.00
    elif age_days <= 3:
        return 1.00 - (age_days * 0.033)   # 0 → 1.00, 3 → 0.90
    elif age_days <= 7:
        return 0.90 - ((age_days - 3) * 0.037)  # 3 → 0.90, 7 → 0.75
    elif age_days <= 14:
        return 0.75 - ((age_days - 7) * 0.036)  # 7 → 0.75, 14 → 0.50
    elif age_days <= 21:
        return 0.50 - ((age_days - 14) * 0.029) # 14 → 0.50, 21 → 0.30
    elif age_days <= 30:
        return 0.30 - ((age_days - 21) * 0.017) # 21 → 0.30, 30 → 0.15
    elif age_days <= 45:
        return 0.15 - ((age_days - 30) * 0.007) # 30 → 0.15, 45 → 0.05
    elif age_days <= 60:
        return 0.05 - ((age_days - 45) * 0.002) # 45 → 0.05, 60 → 0.02
    else:
        return 0.02  # Starší než 2 měsíce → minimální vliv


async def fetch_current_weights() -> Dict[str, float]:
    """Stáhne aktuálně schválené váhy z databáze weight_settings, fallback na defaults."""
    db = get_supabase()

    # Výchozí váhy — optimalizováno pro EUR/USD swing trading
    # labor↑ (NFP je nejdůležitější týdenní event pro FX)
    # spmi↑  (Services PMI > Manufacturing PMI pro moderní ekonomiky)
    # mpmi↓  (Manufacturing < 20% GDP, trh reaguje méně než na services)
    default_weights = {
        "interest_rates": 0.20,
        "inflation":      0.18,
        "gdp":            0.11,
        "labor":          0.12,   # ↑ bylo 0.10 — NFP/unemployment dominantní pro USD
        "cot":            0.11,
        "spmi":           0.09,   # ↑ bylo 0.08 — Services PMI relevantní pro FX
        "mpmi":           0.03,   # ↓ bylo 0.06 — Manufacturing méně relevantní pro EUR/USD
        "retail_sales":   0.05,
        "trend":          0.05,
        "retail_sentiment": 0.04,
        "seasonality":    0.02
    }

    try:
        res = db.table("weight_settings").select("weights").eq("id", "current").single().execute()
        if res.data and "weights" in res.data:
            return res.data["weights"]
    except Exception as e:
        logger.warning(f"Nepodařilo se stáhnout vlastní váhy, použiji fallback: {e}")

    return default_weights


async def calculate_total_score(
    scores: Dict[str, float],
    indicator_ages: Dict[str, int] | None = None,
) -> DailyScoreModel:
    """
    Vezme surové hodnoty z jednotlivých sub-analýz (škála -10 až +10),
    stáhne váhy z DB a provede FRESHNESS-WEIGHTED sum.

    Nová logika (Freshness Multiplier):
    ====================================
    Místo prosté weighted sum (score × weight), každý indikátor dostane
    efektivní váhu upravenou podle stáří posledního čtení:

        effective_weight = base_weight × freshness_multiplier(age_days)

    Čerstvé čtení (age=0) → plná váha.
    Měsíc starý report (age=30) → 15 % původní váhy.

    Po výpočtu se efektivní váhy RENORMALIZUJÍ na součet 1.0 — systém tak
    vždy využívá 100 % vah, ale čerstvé indikátory dominují.

    VÝSLEDEK:
    - NFP report dnes → labor dostane efektivní váhu 10 % (plnou)
    - NFP z před 25 dní → labor dostane ~4 % efektivní váhy
    - Trh citlivěji reaguje na dnešní eventy

    Povolené klíče param 'scores':
    interest_rates, inflation, gdp, labor, cot, spmi, mpmi, retail_sales,
    trend, retail_sentiment, seasonality

    Parametry:
      scores: {indicator_key: float} — surové skóre -10 až +10
      indicator_ages: {indicator_key: int} — věk čtení ve dnech (None = unknown → 30d)
    """
    weights = await fetch_current_weights()
    ages = indicator_ages or {}

    # Ověříme, zda součet vah dává 1.0
    total_w = sum(weights.values())
    if not (0.95 <= total_w <= 1.05):
        logger.warning(f"Součet aktuálních vah {total_w} nedává 1.0! Může to deformovat score.")

    # --- FRESHNESS-WEIGHTED SUM ---
    # Krok 1: Výpočet efektivních (nezrenormalizovaných) vah
    effective_weights_raw: Dict[str, float] = {}
    for key, base_weight in weights.items():
        age = ages.get(key, 30)  # Neznámý věk → předpokládáme 30 dní (konzervativní)
        freshness = get_freshness_multiplier(age)
        effective_weights_raw[key] = base_weight * freshness

    # Krok 2: Renormalizace — efektivní váhy musí dát dohromady 1.0
    total_effective = sum(effective_weights_raw.values())
    if total_effective > 0:
        effective_weights = {k: v / total_effective for k, v in effective_weights_raw.items()}
    else:
        effective_weights = weights  # Krajní případ — fallback na původní váhy

    # Krok 3: Výpočet weighted sum s efektivními váhami
    total_score = 0.0
    for key, eff_weight in effective_weights.items():
        sub_score = scores.get(key, 0.0)
        contribution = sub_score * eff_weight
        total_score += contribution

        base_w = weights.get(key, 0.0)
        age = ages.get(key, 30)
        freshness = get_freshness_multiplier(age)
        logger.debug(
            f"  [{key}] age={age}d fresh={freshness:.2f} "
            f"base_w={base_w:.3f} → eff_w={eff_weight:.3f} "
            f"score={sub_score:.4f} contrib={contribution:.4f}"
        )

    # Clamp na bezpečné hranice ±10
    final_score = float(max(-10.0, min(10.0, total_score)))

    # Log přehled efektivních vah (klíčové pro debugging)
    top_fresh = sorted(effective_weights.items(), key=lambda x: x[1], reverse=True)[:4]
    top_str = ", ".join(f"{k}:{v:.3f}(age={ages.get(k, '?')}d)" for k, v in top_fresh)
    logger.info(
        f"Freshness-weighted sum → {final_score:.4f} | "
        f"Top efektivní váhy: {top_str}"
    )

    label = get_label_for_score(final_score)

    return DailyScoreModel(
        scores=scores,
        weights=weights,
        total=final_score,
        label=label,
        effective_weights=effective_weights,
    )
