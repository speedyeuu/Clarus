from loguru import logger
from typing import Dict
import json
from db.client import get_supabase

# Data class z lib/types.ts zrcadlená v Pythonu
class DailyScoreModel:
    def __init__(self, scores: dict, weights: dict, total: float, label: str):
        self.scores = scores
        self.weights = weights
        self.total = total
        self.label = label

def get_label_for_score(score: float) -> str:
    """Převod celkového skóre na trend label dle plan.md."""
    if score >= 2.0: return "Strong Bullish"
    if score >= 1.0: return "Bullish"
    if score >= 0.33: return "Mildly Bullish"
    if score > -0.33: return "Neutral"
    if score > -1.0: return "Mildly Bearish"
    if score > -2.0: return "Bearish"
    return "Strong Bearish"

async def fetch_current_weights() -> Dict[str, float]:
    """Stáhne aktuálně schválené váhy z databáze weight_settings, fallback na defaults."""
    db = get_supabase()
    
    # Výchozí váhy definované v plan.md
    default_weights = {
        "interest_rates": 0.22,
        "inflation": 0.20,
        "gdp": 0.13,
        "labor": 0.12,
        "cot": 0.11,
        "spmi": 0.08,
        "mpmi": 0.06,
        "retail_sales": 0.05,
        "trend": 0.05,
        "retail_sentiment": 0.04,
        "seasonality": 0.02
    }
    
    try:
        res = db.table("weight_settings").select("weights").eq("id", "current").single().execute()
        if res.data and "weights" in res.data:
            return res.data["weights"]
    except Exception as e:
        logger.warning(f"Nepodařilo se stáhnout vlastní váhy, použiji fallback: {e}")
        
    return default_weights

async def calculate_total_score(scores: Dict[str, float]) -> DailyScoreModel:
    """
    Vezme surové hodnoty z jednotlivých sub-analýz (už převedené na naši -3 až +3 škálu),
    stáhne váhy z DB, provede weighted sum a omezí do bezpečných hranic.
    
    Povolené klíče param 'scores':
    interest_rates, inflation, gdp, labor, cot, spmi, mpmi, retail_sales, 
    trend, retail_sentiment, seasonality
    """
    weights = await fetch_current_weights()
    
    # Ověříme, zda součet vah dává 1.0 (resp. blízko kvůli plovoucí čárce)
    total_w = sum(weights.values())
    if not (0.95 <= total_w <= 1.05):
        logger.warning(f"Součet aktuálních vah {total_w} nedává 1.0! Může to deformovat score.")

    total_score = 0.0
    for key, weight in weights.items():
        # Pokud nějaký indikátor dnes nemá skóre (např. se nestahuje / chybí data),
        # použijeme 0.0 -> žádný odklon od neutrálu
        sub_score = scores.get(key, 0.0)
        total_score += (sub_score * weight)

    # Zajištění, že skóre nepřesáhne tvrdý limit
    # Např. pokud by se sešlo několik z-score +3 a váhy byly špatně definované
    final_score = max(-3.0, min(3.0, total_score))
    
    label = get_label_for_score(final_score)
    
    return DailyScoreModel(
        scores=scores,
        weights=weights,
        total=final_score,
        label=label
    )
