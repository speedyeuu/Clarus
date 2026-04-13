from loguru import logger
from datetime import datetime, timedelta
from typing import List, Dict
from db.client import get_supabase

# Budeme potřebovat kalendář z FF (už stažený a uložený do DB nebo stažený z netu)
# Polymarket probability a OIS signals

def calculate_confidence(events_count: int) -> float:
    """Čím více událostí se na daný den podílí na predikci, tím je model sebevědomější."""
    if events_count == 0:
        return 0.3 # Jen drift, žádné zprávy = nízká jistota ohledně budoucích pohybů
    elif events_count == 1:
        return 0.6
    elif events_count == 2:
        return 0.75
    return 0.85

def map_probability_to_score_shift(probability: float, indicator_weight: float, invert: bool = False) -> float:
    """
    Polymarket/Euribor nám řekne například: 
    80% šance na Rate Cut (probability = 0.8)
    Očekávaná hodnota score_shift = pravděpodobnost * maximální možný úder.
    
    Tento vzorec je hrubý odhad (MVP faza), jak se šance na trhu propsá do změny našeho skóre.
    """
    # Max úder indikátoru = weight * 3.0 (jelikož max hodnota indikátoru je 3.0)
    max_impact = indicator_weight * 3.0
    
    # Expected Value = (Prob * Max_Impact) - ((1 - Prob) * Max_Impact)
    # Tzn pokud je to 50/50, očekávaný drift je 0.
    shift = (probability * max_impact) - ((1.0 - probability) * max_impact)
    
    if invert:
        shift = -shift
        
    return shift

async def generate_7day_prediction(current_total_score: float, current_weights: dict):
    """
    Vygeneruje odhad skóre na dalších 7 dní a zapíše do tabulky predictions.
    """
    db = get_supabase()
    today_date = datetime.now().date()
    today_str = today_date.isoformat()
    
    logger.info("Generování 7denní predikce...")
    
    # Získat budoucí události z databáze 
    # (Předpoklad: události pro nadcházející týden se průběžně scrapují, např. přes events API)
    cutoff = (today_date + timedelta(days=7)).isoformat()
    try:
        res = db.table("upcoming_events").select("*").gt("event_date", today_str).lte("event_date", cutoff).execute()
        upcoming = res.data or []
    except Exception as e:
        logger.warning(f"Nelze přečíst nadcházející události: {e}")
        upcoming = []
        
    # Seskupit podle data
    events_by_date = {}
    for ev in upcoming:
        date_key = ev["event_date"]
        if date_key not in events_by_date:
            events_by_date[date_key] = []
        events_by_date[date_key].append(ev)

    # Autoregressní složka: fundament má tendenci "vyvanout" - plynulý návrat k průměru (mean_reversion drift), pokud nejsou zprávy
    mean_reversion_daily = 0.05 # Skóre se přirozeně blíží nule o 0.05 bodu denně

    running_score = current_total_score
    predictions_to_save = []

    for i in range(1, 8):
        pred_date = today_date + timedelta(days=i)
        pred_str = pred_date.isoformat()
        
        day_events = events_by_date.get(pred_str, [])
        daily_shift_sum = 0.0
        
        # Mean reversion (driftujeme skóre o kousek zpet do neutrálna)
        if running_score > 0:
            running_score -= min(running_score, mean_reversion_daily)
        elif running_score < 0:
            running_score += min(abs(running_score), mean_reversion_daily)
            
        # Zpracovat všechny významné zprávy ze daný den 
        for ev in day_events:
            indicator_key = ev.get("indicator_key")
            country = ev.get("country")
            weight = current_weights.get(indicator_key, 0.0) if indicator_key else 0.0
            
            prob = None
            if ev.get("polymarket_yes_prob") is not None:
                prob = ev["polymarket_yes_prob"]
            elif ev.get("euribor_signal") is not None:
                prob = ev["euribor_signal"]
            else:
                # Pokud nemáme live probabilities z Polymarketu/Euriboru, použijeme "čistý neutrál" (0.5), což nedá shift,
                # Nebo hrubý odhad přes konsensus. Zjednodušeně to necháme být na trhu, dokud není surprise.
                prob = 0.5 
                
            invert = False
            if country == "USD":
                invert = True
                if indicator_key and "unemployment" in indicator_key.lower():
                    invert = False
            elif country == "EUR":
                if indicator_key and "unemployment" in indicator_key.lower():
                    invert = True

            event_shift = map_probability_to_score_shift(prob, weight, invert)
            daily_shift_sum += event_shift
            
        # Aplikace shiftu na running_score pre dany den
        running_score += daily_shift_sum
        running_score = max(-3.0, min(3.0, running_score))
        
        # Odhad pásem (High/Low)
        confidence = calculate_confidence(len(day_events))
        # Nízká jistota = širší pásmo uncertainty
        band_width = 0.5 * (1.1 - confidence) 
        
        record = {
            "created_date": today_str,
            "prediction_date": pred_str,
            "pair": "EURUSD",
            "predicted_score_mid": round(running_score, 2),
            "predicted_score_low": round(max(-3.0, running_score - band_width), 2),
            "predicted_score_high": round(min(3.0, running_score + band_width), 2),
            "confidence": confidence,
            "upcoming_events": [ev["title"] for ev in day_events]
        }
        predictions_to_save.append(record)

    # Uložit do db
    try:
        for p in predictions_to_save:
            # Ujistíme se, že mažeme všechny staré predikce pro daný den, vytvořené DNES (zajistí unique constraints)
            db.table("predictions").upsert(p).execute()
        logger.info(f"Úspěšně vytvořeno a uloženo {len(predictions_to_save)} predikcí.")
    except Exception as e:
        logger.error(f"Nepodařilo se uložit predikce: {e}")
