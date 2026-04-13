from fastapi import APIRouter, HTTPException
from db.client import get_supabase
from datetime import date

router = APIRouter()


@router.get("/")
async def get_predictions(pair: str = "EURUSD"):
    """Vrátí aktuální 7denní predikci (vytvořenou naposledy)."""
    db = get_supabase()
    today = date.today().isoformat()
    result = (
        db.table("predictions")
        .select("*")
        .eq("pair", pair)
        .eq("created_date", today)
        .order("prediction_date", desc=False)
        .execute()
    )
    if not result.data:
        # Fallback: poslední dostupná predikce
        result = (
            db.table("predictions")
            .select("*")
            .eq("pair", pair)
            .gte("prediction_date", today)
            .order("prediction_date", desc=False)
            .limit(7)
            .execute()
        )
    return result.data


@router.get("/accuracy")
async def get_prediction_accuracy(days: int = 30, pair: str = "EURUSD"):
    """Vrátí historii přesnosti predikcí pro daný pár."""
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    db = get_supabase()
    result = (
        db.table("predictions")
        .select("created_date, prediction_date, predicted_score_mid, actual_score, accuracy_score")
        .eq("pair", pair)
        .gte("created_date", cutoff)
        .not_.is_("actual_score", "null")
        .order("prediction_date", desc=False)
        .execute()
    )
    return result.data
