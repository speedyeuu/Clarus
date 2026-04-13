from fastapi import APIRouter, HTTPException
from db.client import get_supabase
from typing import Optional

router = APIRouter()


@router.get("/latest")
async def get_latest_score(pair: str = "EURUSD"):
    """Vrátí dnešní (nebo poslední dostupné) denní skóre pro daný pár."""
    db = get_supabase()
    result = (
        db.table("daily_scores")
        .select("*")
        .eq("pair", pair)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Žádná data zatím nejsou k dispozici.")
    return result.data[0]


@router.get("/history")
async def get_score_history(days: int = 30, pair: str = "EURUSD"):
    """Vrátí historii skóre za posledních N dní pro daný pár."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    db = get_supabase()
    result = (
        db.table("daily_scores")
        .select("date, total_score, label, score_interest_rates, score_inflation, score_gdp, score_labor, score_cot, score_spmi, score_mpmi, score_retail_sales, score_trend, score_retail_sentiment, score_seasonality")
        .eq("pair", pair)
        .gte("date", cutoff)
        .order("date", desc=False)
        .execute()
    )
    return result.data
