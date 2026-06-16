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


@router.get("/week-summary")
async def get_week_summary(pair: str = "EURUSD"):
    """
    Vrátí lidsky čitelný týdenní přehled predikce.

    Obsahuje:
      - direction_label: slovní popis (📈 Bullish / 📉 Bearish / ⚪ Neutrální)
      - score_start / score_end_expected: odkud kam půjde skóre
      - key_catalyst: nejdůležitější událost týdne
      - scenarios: beat vs miss analýza pro každý den s eventy
      - scenario_beat/miss: trajektorie skóre pro oba scénáře

    Vypočítáno z dnešních predikcí v DB.
    """
    db = get_supabase()
    today = date.today().isoformat()

    # Načteme dnešní predikce — s fallbackem pokud sloupce ještě neexistují v DB
    BASE_SELECT = "prediction_date, predicted_score_mid, predicted_score_low, predicted_score_high, confidence, upcoming_events"
    FULL_SELECT = BASE_SELECT + ", scenario_beat, scenario_miss, mean_reversion_applied"

    def _query(select_cols: str, date_filter: str, date_value: str):
        q = db.table("predictions").select(select_cols).eq("pair", pair)
        if date_filter == "eq":
            q = q.eq("created_date", date_value)
        else:
            q = q.gte("prediction_date", date_value).limit(7)
        return q.order("prediction_date", desc=False).execute()

    try:
        result = _query(FULL_SELECT, "eq", today)
        if not result.data:
            result = _query(FULL_SELECT, "gte", today)
        has_scenarios = True
    except Exception:
        # Sloupce scenario_beat/miss zatím neexistují — fallback na základní select
        result = _query(BASE_SELECT, "eq", today)
        if not result.data:
            result = _query(BASE_SELECT, "gte", today)
        has_scenarios = False

    preds = result.data

    # Dnešní skóre
    latest_score_res = (
        db.table("daily_scores")
        .select("total_score, label")
        .eq("pair", pair)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    current_score = latest_score_res.data[0]["total_score"] if latest_score_res.data else 0.0
    current_label = latest_score_res.data[0]["label"] if latest_score_res.data else "Neutral"

    # Konec týdne
    end_pred = preds[-1]
    end_score = end_pred["predicted_score_mid"]
    score_change = end_score - current_score

    # Direction label
    pair_label = f"{pair[:3]}/{pair[3:]}"
    if end_score > 3.0:
        direction_label = f"📈 Bullish {pair_label}"
    elif end_score > 1.0:
        direction_label = f"🟢 Mírně Bullish {pair_label}"
    elif end_score > -1.0:
        direction_label = f"⚪ Neutrální {pair_label}"
    elif end_score > -3.0:
        direction_label = f"🟡 Mírně Bearish {pair_label}"
    else:
        direction_label = f"📉 Bearish {pair_label}"

    # Dny se scénáři (beat vs miss)
    scenario_days = []
    for p in preds:
        events = p.get("upcoming_events") or []
        if events and p.get("scenario_beat") is not None:
            beat = p.get("scenario_beat", p["predicted_score_mid"])
            miss = p.get("scenario_miss", p["predicted_score_mid"])
            scenario_days.append({
                "date": p["prediction_date"],
                "events": events,
                "baseline": round(p["predicted_score_mid"], 2),
                "beat": round(beat, 2),
                "miss": round(miss, 2),
                "band_low": round(p["predicted_score_low"], 2),
                "band_high": round(p["predicted_score_high"], 2),
                "confidence": p.get("confidence"),
                "mean_reversion_applied": p.get("mean_reversion_applied", True),
            })

    return {
        "pair": pair,
        "current_score": round(current_score, 2),
        "current_label": current_label,
        "direction_label": direction_label,
        "score_end_expected": round(end_score, 2),
        "score_change": round(score_change, 2),
        "change_description": f"{score_change:+.2f} bodu" if abs(score_change) > 0.1 else "bez velké změny",
        "scenario_days": scenario_days,
        "total_prediction_days": len(preds),
    }


