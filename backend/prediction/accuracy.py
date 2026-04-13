from loguru import logger
from datetime import datetime
from db.client import get_supabase

async def evaluate_predictions_accuracy():
    """
    Tato funkce by měla běžet v rámci Daily Pipeline PO VÝPOČTU aktuálního skóre.
    Vezme dnešní datum, najde všechny minulé predikce, které mířily na dnešek,
    porovná je s reálným (dnes spočítaným) skóre a zapíše `accuracy_score`.
    """
    db = get_supabase()
    today_str = datetime.now().date().isoformat()
    
    logger.info(f"Vyhodnocuji zpětně přesnost minulých predikcí mířících na {today_str}...")
    
    try:
        # Získáme reálné dnešní skóre, které zrovna prošlo enginem
        res_today = db.table("daily_scores").select("total_score").eq("date", today_str).single().execute()
        if not res_today.data:
            logger.warning(f"Chybí dnešní skóre pro vyhodnocení přesnosti predikcí.")
            return
            
        actual_score = res_today.data["total_score"]
        
        # Najdeme všechny neověřené predikce, které ukázaly na dnešek
        res_preds = db.table("predictions").select("*").eq("prediction_date", today_str).is_("actual_score", "null").execute()
        unverified = res_preds.data or []
        
        if not unverified:
            logger.info("Zádné neověřené predikce pro dnešek nenalezeny.")
            return
            
        for p in unverified:
            predicted_mid = float(p.get("predicted_score_mid", 0))
            
            # Jak blízko byla predikce (mid) od reálného skóre?
            # Škála je 6 bodů (-3 až +3). Rozdíl může být ulet maximálně 6 (nebo minimum 0).
            # Čím blíž nule, tím blíž 100% accuracy.
            error = abs(actual_score - predicted_mid)
            
            # Linear map error -> accuracy (0 až 1)
            # Pokud se trefíme na <= 0.2 bodů, bereme to jako téměř 100% přesnost
            accuracy = 1.0 - (error / 3.0) # Víc než polovina škály odchylka (3 b. úlet) = 0% přesné
            accuracy = max(0.0, min(1.0, accuracy))
            
            # Update databáze
            update_data = {
                "actual_score": round(actual_score, 2),
                "accuracy_score": round(accuracy, 2)
            }
            db.table("predictions").update(update_data).eq("id", p["id"]).execute()
            
        logger.info(f"Ověřeno a oznámkováno {len(unverified)} dřívějších predikcí.")

    except Exception as e:
        logger.error(f"Nepodařilo se vyhodnotit přesnost predikcí: {e}")
