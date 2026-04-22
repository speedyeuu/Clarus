"""
Adaptivní učení vah indikátorů (Weight Adapter)
================================================
Každý den po vyhodnocení přesnosti predikcí tato funkce:

1. Vezme posledních N evaluovaných predikcí (kde víme actual_score)
2. Pro každou predikci zjistí indikátorové skóre platné v den vzniku predikce
3. Spočítá gradient chyby: grad_k = mean(error × score_k)
   - error = actual - predicted  (pozitivní = byl jsme příliš bearish)
   - score_k = říká, jakým směrem táhl daný indikátor v ten den
4. Váhy se posunou ve směru gradientu (malý learning rate)
5. Nové váhy se normalizují na součet = 1.0 a clamped do bezpečných hranic
6. Uloží se zpět do `weight_settings` → FROM NEXT DAY ENGINE USES THEM

Learning rate: 0.003 (velmi konzervativní, aby nedošlo k overfitting)
Min vzorků: 5 (pod touto hranicí se učení nespustí)
Clamp vah: 0.01 – 0.40 (žádná váha nemůže zmizet ani dominovat)
"""

from loguru import logger
from datetime import datetime
from typing import Dict
from db.client import get_supabase

# Hyperparametry
LEARNING_RATE = 0.003
MIN_SAMPLES = 5
WINDOW_DAYS = 30
WEIGHT_MIN = 0.01
WEIGHT_MAX = 0.40

# Mapování sloupců daily_scores → klíče indikátorů
INDICATOR_COLS = {
    "score_interest_rates": "interest_rates",
    "score_inflation":      "inflation",
    "score_gdp":            "gdp",
    "score_labor":          "labor",
    "score_cot":            "cot",
    "score_spmi":           "spmi",
    "score_mpmi":           "mpmi",
    "score_retail_sales":   "retail_sales",
    "score_trend":          "trend",
    "score_retail_sentiment": "retail_sentiment",
    "score_seasonality":    "seasonality",
}


async def adapt_weights_from_predictions(pair: str = "EURUSD") -> None:
    """
    Spustí jeden krok gradientního sestupu na vahách indikátorů
    na základě chyb predikcí z posledního období.
    
    Volá se automaticky po evaluate_predictions_accuracy() v daily pipeline.
    Výsledek se projeví při DALŠÍM denním výpočtu score (nikoliv okamžitě).
    """
    db = get_supabase()

    # ------------------------------------------------------------------ #
    # 1. Načteme evaluované predikce (kde known actual_score)
    # ------------------------------------------------------------------ #
    try:
        pred_res = (
            db.table("predictions")
            .select("created_date, prediction_date, predicted_score_mid, actual_score")
            .eq("pair", pair)
            .not_.is_("actual_score", "null")
            .order("prediction_date", desc=True)
            .limit(WINDOW_DAYS)
            .execute()
        )
        predictions = pred_res.data or []
    except Exception as e:
        logger.warning(f"[WeightAdapter] Nelze načíst predikce: {e}")
        return

    if len(predictions) < MIN_SAMPLES:
        logger.info(
            f"[WeightAdapter] Pouze {len(predictions)} evaluovaných predikcí "
            f"(min. {MIN_SAMPLES}) — učení přeskočeno."
        )
        return

    # ------------------------------------------------------------------ #
    # 2. Načteme aktuální váhy
    # ------------------------------------------------------------------ #
    try:
        w_res = (
            db.table("weight_settings")
            .select("weights")
            .eq("id", "current")
            .single()
            .execute()
        )
        current_weights: Dict[str, float] = w_res.data["weights"]
    except Exception:
        # Fallback — defaultní váhy (musí odpovídat engine.py)
        current_weights = {
            "interest_rates": 0.22, "inflation": 0.20, "gdp": 0.13,
            "labor": 0.12, "cot": 0.11, "spmi": 0.08, "mpmi": 0.06,
            "retail_sales": 0.05, "trend": 0.05,
            "retail_sentiment": 0.04, "seasonality": 0.02,
        }

    indicator_keys = list(current_weights.keys())

    # ------------------------------------------------------------------ #
    # 3. Akumulujeme gradienty přes všechna evaluovaná okna
    # ------------------------------------------------------------------ #
    gradients: Dict[str, float] = {k: 0.0 for k in indicator_keys}
    valid_samples = 0

    for pred in predictions:
        created_date = pred.get("created_date")
        predicted_mid = pred.get("predicted_score_mid")
        actual = pred.get("actual_score")

        if created_date is None or predicted_mid is None or actual is None:
            continue

        # Chyba predikce: (+) = byli jsme příliš bearish, (−) = příliš bullish
        error = float(actual) - float(predicted_mid)

        # Zjistíme indikátorové skóre platné v den vzniku predikce
        score_cols = ", ".join(INDICATOR_COLS.keys())
        try:
            scores_res = (
                db.table("daily_scores")
                .select(score_cols)
                .eq("date", created_date)
                .eq("pair", pair)
                .execute()
            )
        except Exception:
            continue

        if not scores_res.data:
            continue

        day_scores = scores_res.data[0]

        # grad_k = error × s_k
        # Pokud indikátor tlačil špatným směrem (chyba i skóre jsou záporné = přispěl k over-bearish)
        # bude gradient záporný → váha se sníží
        for col, key in INDICATOR_COLS.items():
            s_k = float(day_scores.get(col) or 0.0)
            gradients[key] += error * s_k

        valid_samples += 1

    if valid_samples == 0:
        logger.info("[WeightAdapter] Žádná využitelná data pro gradient — přeskočeno.")
        return

    # Průměrování
    for k in gradients:
        gradients[k] /= valid_samples

    # ------------------------------------------------------------------ #
    # 4. Update vah: w_k ← w_k + lr × grad_k
    # ------------------------------------------------------------------ #
    new_weights: Dict[str, float] = {}
    for k in indicator_keys:
        updated = current_weights[k] + LEARNING_RATE * gradients[k]
        new_weights[k] = max(WEIGHT_MIN, min(WEIGHT_MAX, updated))

    # ------------------------------------------------------------------ #
    # 5. Normalizace: součet = 1.0
    # ------------------------------------------------------------------ #
    total = sum(new_weights.values())
    for k in new_weights:
        new_weights[k] = round(new_weights[k] / total, 5)

    # ------------------------------------------------------------------ #
    # 6. Uložení do weight_settings
    # ------------------------------------------------------------------ #
    try:
        db.table("weight_settings").upsert({
            "id": "current",
            "weights": new_weights,
            "updated_at": datetime.now().isoformat(),
            "adapted_from_samples": valid_samples,
        }).execute()
    except Exception as e:
        logger.error(f"[WeightAdapter] Nepodařilo se uložit nové váhy: {e}")
        return

    # ------------------------------------------------------------------ #
    # 7. Log — zobrazíme co se změnilo
    # ------------------------------------------------------------------ #
    changes = {
        k: f"{current_weights[k]:.4f} → {new_weights[k]:.4f} (Δ{new_weights[k]-current_weights[k]:+.4f})"
        for k in indicator_keys
    }
    logger.info(
        f"[WeightAdapter] Váhy adaptovány (lr={LEARNING_RATE}, n={valid_samples} vzorků):\n"
        + "\n".join(f"  {k}: {v}" for k, v in changes.items())
    )
