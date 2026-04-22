from fastapi import APIRouter, HTTPException
from db.client import get_supabase
from datetime import date, timedelta

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


@router.get("/accuracy-summary")
async def get_accuracy_summary(pair: str = "EURUSD"):
    """
    Vrátí průměrnou přesnost predikcí za posledních 7 a 30 dní.
    Používá se pro zobrazení v Score History headeru.
    """
    db = get_supabase()
    today = date.today()
    cutoff_7d  = (today - timedelta(days=7)).isoformat()
    cutoff_30d = (today - timedelta(days=30)).isoformat()

    def avg_accuracy(rows: list) -> float | None:
        scores = [r["accuracy_score"] for r in rows if r.get("accuracy_score") is not None]
        return round(sum(scores) / len(scores), 4) if scores else None

    try:
        res_30 = (
            db.table("predictions")
            .select("accuracy_score")
            .eq("pair", pair)
            .gte("prediction_date", cutoff_30d)
            .not_.is_("accuracy_score", "null")
            .execute()
        )
        all_30 = res_30.data or []

        res_7 = (
            db.table("predictions")
            .select("accuracy_score")
            .eq("pair", pair)
            .gte("prediction_date", cutoff_7d)
            .not_.is_("accuracy_score", "null")
            .execute()
        )
        all_7 = res_7.data or []

        return {
            "week_avg":    avg_accuracy(all_7),
            "month_avg":   avg_accuracy(all_30),
            "week_count":  len(all_7),
            "month_count": len(all_30),
        }
    except Exception as e:
        return {"week_avg": None, "month_avg": None, "week_count": 0, "month_count": 0}

