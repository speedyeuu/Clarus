from loguru import logger
from typing import Dict

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
    if score >= 7.0:
        return "Strong Bullish"
    if score >= 3.0:
        return "Bullish"
    if score >= 1.0:
        return "Mildly Bullish"
    if score > -1.0:
        return "Neutral"
    if score > -3.0:
        return "Mildly Bearish"
    if score > -7.0:
        return "Bearish"
    return "Strong Bearish"


def get_freshness_multiplier(age_days: int) -> float:
    """
    Vrátí multiplikátor váhy (0.0 - 1.0) podle stáří posledního čtení.

    Nová logika (Schodovitý graf):
      - age 0 až 35 → 1.00 (držíme plnou váhu po dobu jednoho měsíce do další zprávy)
      - age 36 až 60 → 0.80 (mírný pokles, pokud report zmeškáme)
      - age 61+ → 0.50 (dlouhodobý fallback, ale nikdy nespadne úplně na 0)

    Proč:
      Chceme vytvářet "schodovité" grafy, kde fundament drží svou hodnotu 
      až do doby, než přijde nová událost, a pak prudce uskočí na novou úroveň.
    """
    if age_days <= 35:
        return 1.0
    if age_days <= 60:
        return 0.8
    return 0.5


async def fetch_current_weights(pair: str = "EURUSD") -> Dict[str, float]:
    """
    Získá aktuální makroekonomický režim a vrátí dynamicky vypočítané váhy fundamentů.
    Toto nahrazuje dřívější statické váhy z DB weight_settings.
    """
    from prediction.regime import detect_market_regime, get_regime_weights

    regime = await detect_market_regime()
    base_curr = pair[:3]
    quote_curr = pair[3:]
    
    regime_weights = get_regime_weights(regime, base_curr, quote_curr)
    
    # Můžeme to stále zkoušet skloubit s user-defined DB vahami,
    # ale pro plný ML režim použijeme nativní Regime weights.
    return regime_weights


async def calculate_total_score(
    scores: Dict[str, float],
    indicator_ages: Dict[str, int] | None = None,
    pair: str = "EURUSD",
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
    weights = await fetch_current_weights(pair)
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
