from enum import Enum
from typing import Dict
from loguru import logger
from collectors.vix import fetch_vix_current

class MarketRegime(Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"

async def detect_market_regime() -> MarketRegime:
    """
    Detekuje aktuální makroekonomický režim trhu primárně podle VIX volatility.
    
    Risk-On: VIX < 15 (Klid na trzích, chuť riskovat, carry trades).
    Risk-Off: VIX > 25 (Panika, útěk do bezpečí, USD/CHF/JPY posiluje).
    Neutral: VIX 15 - 25.
    """
    vix = await fetch_vix_current()
    if vix is None:
        logger.warning("VIX nedostupný, vracím Neutral režim.")
        return MarketRegime.NEUTRAL

    if vix > 25.0:
        logger.info(f"[Regime Detection] VIX = {vix:.2f} -> RISK_OFF")
        return MarketRegime.RISK_OFF
    elif vix < 15.0:
        logger.info(f"[Regime Detection] VIX = {vix:.2f} -> RISK_ON")
        return MarketRegime.RISK_ON
    else:
        logger.info(f"[Regime Detection] VIX = {vix:.2f} -> NEUTRAL")
        return MarketRegime.NEUTRAL

def get_regime_weights(regime: MarketRegime, base_currency: str, quote_currency: str) -> Dict[str, float]:
    """
    Vrací sadu vah fundamentů specifickou pro daný režim.
    V Risk-Off dominuje Trend, Sazby a COT (bezpečné útočiště).
    V Risk-On dominuje HDP, Služby, Trh práce (růst).
    """
    # Standardní neutrální váhy
    weights = {
        "interest_rates": 0.20,
        "inflation": 0.18,
        "labor": 0.12,
        "gdp": 0.11,
        "cot": 0.11,
        "spmi": 0.09,
        "retail_sales": 0.05,
        "trend": 0.05,
        "retail_sentiment": 0.04,
        "mpmi": 0.03,
        "seasonality": 0.02
    }

    if regime == MarketRegime.RISK_OFF:
        # V panice investoři ignorují dlouhodobá makro data (HDP) a řeší jen sazby, trend a pozicování
        weights = {
            "interest_rates": 0.35,  # Kdo dává větší výnos v krizi?
            "trend": 0.20,           # Momentum je vše
            "cot": 0.15,             # Instituce zavírají pozice
            "inflation": 0.10,
            "labor": 0.05,
            "gdp": 0.03,
            "spmi": 0.03,
            "retail_sales": 0.02,
            "retail_sentiment": 0.04,
            "mpmi": 0.02,
            "seasonality": 0.01
        }
    elif regime == MarketRegime.RISK_ON:
        # V době růstu se řeší skutečná síla ekonomiky (HDP, Práce, Služby)
        weights = {
            "gdp": 0.20,
            "labor": 0.15,
            "inflation": 0.15,
            "interest_rates": 0.15,
            "spmi": 0.10,
            "mpmi": 0.05,
            "retail_sales": 0.05,
            "cot": 0.05,
            "trend": 0.05,
            "retail_sentiment": 0.03,
            "seasonality": 0.02
        }

    # Normalizace na 1.0 (pro jistotu)
    total = sum(weights.values())
    return {k: round(v / total, 4) for k, v in weights.items()}
