from loguru import logger
from datetime import datetime
import json
from google import genai
from google.genai import types

from db.client import get_supabase
from config import get_settings

async def run_weight_optimization():
    """
    Autoresearch modul.
    Zanalyzuje přesnost predikcí za posledních X dní a pošle request na Google Gemini API.
    Gemini provede hlubokou analýzu (reasoning) a navrhne upravené váhy indikátorů.
    Návrh uloží do autoresearch_log jako pending status (čeká na schválení adminem).
    """
    settings = get_settings()
    if not settings.gemini_api_key or settings.gemini_api_key == "your-gemini-key":
        logger.error("Gemini API klíč chybí. Nelze spustit Autoresearch.")
        return

    db = get_supabase()
    
    # Získáme aktuální váhy
    try:
        res = db.table("weight_settings").select("weights").eq("id", "current").single().execute()
        current_weights = res.data["weights"] if res.data else {}
    except Exception:
        logger.error("Chyba při čtení aktuálních vah v Autoresearch.")
        return

    # Získáme průměrnou accuracy predikcí z nedávné doby
    try:
        res_acc = db.table("predictions").select("accuracy_score").not_.is_("accuracy_score", "null").order("prediction_date", desc=True).limit(30).execute()
        accuracy_records = res_acc.data or []
        
        if not accuracy_records:
            logger.warning("Nedostatek dat pro optimalizaci vah (málo historických accuracy score).")
            return
            
        avg_acc = sum(r["accuracy_score"] for r in accuracy_records) / len(accuracy_records)
    except Exception as e:
        logger.error(f"Chyba při zjišťování přesnosti modelů: {e}")
        return

    # Pokud je accuracy hodně dobrá (> 0.85), systém funguje skvěle, není důvod optimalizovat.
    if avg_acc >= 0.85:
        logger.info(f"Model má vysokou úspěšnost ({avg_acc*100:.1f} %). Optimalizace není nutná.")
        return

    prompt = f"""
    You are an expert forex macro quantitative analyst. We are running an automated EUR/USD scoring system based on 11 fundamental indicators.
    Recently, our 7-day prediction accuracy score has been {avg_acc*100:.1f}%.
    
    Our current indicator weights summing up to 1.0 are:
    {json.dumps(current_weights, indent=2)}
    
    Your task:
    1. Analyze the macroeconomic landscape for EUR and USD.
    2. Adjust the weights to better predict the market. Give more weight to currently leading macro drivers.
    3. Ensure the output new_weights strictly sum up precisely to exactly 1.0.
    
    Return the response as a valid json adhering to this structure:
    {{
       "reasoning": "Detailed explanation of why these macro shifts make sense right now...",
       "improvement_notes": "Short tl;dr string what changes you made.",
       "new_weights": {{
          "interest_rates": float,
          "inflation": float,
          "gdp": float,
          "labor": float,
          "manufacturing_pmi": float,
          "services_pmi": float,
          "retail_sales": float,
          "retail_sentiment": float,
          "cot": float,
          "trend": float,
          "seasonality": float
       }},
       "confidence": float between 0.0 and 1.0
    }}
    """

    logger.info("Konfiguruji Google Gemini 2.0 Flash AI pro návrh nových vah...")
    client = genai.Client(api_key=settings.gemini_api_key)
    
    try:
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                system_instruction="You are an automated quant module. You return only valid JSON."
            )
        )
        
        reply_str = response.text
        data = json.loads(reply_str)
        
        # Validace navržených vah
        suggested_weights = data["new_weights"]
        sum_w = sum(suggested_weights.values())
        if not (0.95 <= sum_w <= 1.05):
            logger.error(f"Gemini vrátil nevalidní váhy (součet {sum_w} != 1.0). Ruším.")
            return

        # Zapsat pending návrh
        log_entry = {
            "run_date": datetime.now().date().isoformat(),
            "old_weights": current_weights,
            "new_weights": suggested_weights,
            "improvement_notes": data.get("improvement_notes", "Bez popisu"),
            "reasoning": data.get("reasoning", ""),
            "accuracy_before": round(avg_acc, 3),
            "confidence": data.get("confidence", 0.5),
            "applied": False,
            "rejected": False
        }
        
        db.table("autoresearch_log").insert(log_entry).execute()
        logger.info("Gemini úspěšně vygeneroval nový návrh vah. Čeká se na schválení v UI.")

    except Exception as e:
        logger.error(f"Chyba při komunikaci s Google Gemini API (Autoresearch): {e}")
