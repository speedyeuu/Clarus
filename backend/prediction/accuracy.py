from loguru import logger
from datetime import datetime, timedelta
from db.client import get_supabase


async def evaluate_predictions_accuracy():
    """
    Vyhodnotí přesnost minulých predikcí mířících na dnešek.
    Spouští se v rámci Daily Pipeline PO výpočtu aktuálního skóre.

    Kombinovaná metrika přesnosti (50/50):
      1. Distanční složka: jak blízko byl mid predikce od reality (1 - error/20)
      2. Směrová složka:  predikoval model správný směr pohybu oproti včerejšku?

    Tato kombinace je odolná vůči triviálnímu modelu, který vždy predikuje
    dnešní hodnotu → samotná distanční složka by dávala falešně vysokou přesnost.

    Po evaluaci automaticky spustí adaptaci vah přes gradient descent
    (scoring/weight_adapter.py) — tak se model učí ze svých chyb.
    """
    db = get_supabase()
    today_str = datetime.now().date().isoformat()
    yesterday_str = (datetime.now().date() - timedelta(days=1)).isoformat()

    logger.info(f"Vyhodnocuji zpětně přesnost minulých predikcí mířících na {today_str}...")

    pair = "EURUSD"

    try:
        # Získáme reálné dnešní skóre (výsledek dnešního pipeline)
        res_today = (
            db.table("daily_scores")
            .select("total_score")
            .eq("date", today_str)
            .eq("pair", pair)
            .single()
            .execute()
        )
        if not res_today.data:
            logger.warning("Chybí dnešní skóre pro vyhodnocení přesnosti predikcí.")
            return

        actual_score = float(res_today.data["total_score"])

        # Včerejší skóre pro výpočet směrové složky
        res_yesterday = (
            db.table("daily_scores")
            .select("total_score")
            .eq("date", yesterday_str)
            .eq("pair", pair)
            .single()
            .execute()
        )
        yesterday_score = float(res_yesterday.data["total_score"]) if res_yesterday.data else None

        # Skutečný směr pohybu (dnešek vs včerejšek)
        if yesterday_score is not None:
            actual_direction = 1 if actual_score > yesterday_score else (-1 if actual_score < yesterday_score else 0)
        else:
            actual_direction = None

        # Najdeme všechny neověřené predikce mířící na dnešek
        res_preds = (
            db.table("predictions")
            .select("*")
            .eq("prediction_date", today_str)
            .eq("pair", pair)
            .is_("actual_score", "null")
            .execute()
        )
        unverified = res_preds.data or []

        if not unverified:
            logger.info("Žádné neověřené predikce pro dnešek nenalezeny.")
        else:
            for p in unverified:
                predicted_mid = float(p.get("predicted_score_mid", 0))

                # --- 1. Distanční složka ---
                # Měří jak daleko byl mid od reality (max chyba = 20, tj. -10 vs +10)
                error = abs(actual_score - predicted_mid)
                distance_accuracy = max(0.0, 1.0 - (error / 20.0))

                # --- 2. Směrová složka ---
                # Predikoval model správný směr pohybu oproti včerejšku?
                # Tato složka trestá triviální modely, které vždy predikují blízko dnešní hodnoty.
                if actual_direction is not None and actual_direction != 0 and yesterday_score is not None:
                    pred_direction = 1 if predicted_mid > yesterday_score else (-1 if predicted_mid < yesterday_score else 0)
                    directional_accuracy = 1.0 if pred_direction == actual_direction else 0.0
                else:
                    # Pokud se včera a dnes skóre nelišilo, nebo nemáme včerejší data,
                    # použijeme jen distanční složku
                    directional_accuracy = distance_accuracy

                # --- Kombinovaná metrika (50% distance + 50% direction) ---
                accuracy = 0.5 * distance_accuracy + 0.5 * directional_accuracy
                accuracy = max(0.0, min(1.0, accuracy))

                logger.info(
                    f"Predikce {p.get('created_date')}→{today_str}: "
                    f"predicted={predicted_mid:.2f}, actual={actual_score:.2f} "
                    f"(dist_acc={distance_accuracy:.2f}, dir_acc={directional_accuracy:.2f} "
                    f"[pred_dir={'↑' if (predicted_mid > (yesterday_score or 0)) else '↓'}, "
                    f"actual_dir={'↑' if actual_direction == 1 else '↓' if actual_direction == -1 else '→'}]) "
                    f"→ combined_accuracy={accuracy:.2f}"
                )

                update_data = {
                    "actual_score": round(actual_score, 4),
                    "accuracy_score": round(accuracy, 4),
                }
                db.table("predictions").update(update_data).eq("id", p["id"]).execute()

            logger.info(f"Ověřeno a oznámkováno {len(unverified)} dřívějších predikcí.")

    except Exception as e:
        logger.error(f"Nepodařilo se vyhodnotit přesnost predikcí: {e}")
        return

    # ------------------------------------------------------------------
    # Adaptivní učení — gradient descent na vahách indikátorů.
    # Spustí se i když dnes nebyly nové predikce k evaluaci,
    # protože může pracovat se staršími evaluovanými daty.
    # ------------------------------------------------------------------
    try:
        from scoring.weight_adapter import adapt_weights_from_predictions
        await adapt_weights_from_predictions(pair=pair)
    except Exception as e:
        logger.error(f"Adaptace vah selhala (nezastaví pipeline): {e}")
