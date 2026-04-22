from loguru import logger
from datetime import datetime
from db.client import get_supabase

async def evaluate_predictions_accuracy():
    """
    Tato funkce by měla běžet v rámci Daily Pipeline PO VÝPOČTU aktuálního skóre.
    Vezme dnešní datum, najde všechny minulé predikce, které mířily na dnešek,
    porovná je s reálným (dnes spočítaným) skóre a zapíše `accuracy_score`.
    
    Po evaluaci automaticky spustí adaptaci vah přes gradient descent
    (scoring/weight_adapter.py) — tak se model učí ze svých chyb.
    """
    db = get_supabase()
    today_str = datetime.now().date().isoformat()
    
    logger.info(f"Vyhodnocuji zpětně přesnost minulých predikcí mířících na {today_str}...")
    
    pair = "EURUSD"
    
    try:
        # Získáme reálné dnešní skóre, které zrovna prošlo enginem
        res_today = db.table("daily_scores").select("total_score").eq("date", today_str).eq("pair", pair).single().execute()
        if not res_today.data:
            logger.warning(f"Chybí dnešní skóre pro vyhodnocení přesnosti predikcí.")
            return
            
        actual_score = res_today.data["total_score"]
        
        # Najdeme všechny neověřené predikce, které ukázaly na dnešek
        res_preds = db.table("predictions").select("*").eq("prediction_date", today_str).eq("pair", pair).is_("actual_score", "null").execute()
        unverified = res_preds.data or []
        
        if not unverified:
            logger.info("Žádné neověřené predikce pro dnešek nenalezeny.")
        else:
            for p in unverified:
                predicted_mid = float(p.get("predicted_score_mid", 0))
                
                # Jak blízko byla predikce (mid) od reálného skóre?
                error = abs(actual_score - predicted_mid)
                accuracy = 1.0 - (error / 3.0)
                accuracy = max(0.0, min(1.0, accuracy))
                
                update_data = {
                    "actual_score": round(actual_score, 2),
                    "accuracy_score": round(accuracy, 2)
                }
                db.table("predictions").update(update_data).eq("id", p["id"]).execute()
                
            logger.info(f"Ověřeno a oznámkováno {len(unverified)} dřívějších predikcí.")

    except Exception as e:
        logger.error(f"Nepodařilo se vyhodnotit přesnost predikcí: {e}")
        return

    # ------------------------------------------------------------------
    # Adaptivní učení — gradient descent na vahách indikátorů
    # Spustí se i když dnes nebyly nové predikce k evaluaci,
    # protože může pracovat se staršími evaluovanými daty.
    # ------------------------------------------------------------------
    try:
        from scoring.weight_adapter import adapt_weights_from_predictions
        await adapt_weights_from_predictions(pair=pair)
    except Exception as e:
        logger.error(f"Adaptace vah selhala (nezastaví pipeline): {e}")

