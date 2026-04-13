import asyncio
import os
import sys
from datetime import datetime, timedelta
import random

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db.client import get_supabase

async def seed_mock_database():
    db = get_supabase()
    print("🧹 Čistím stará seed data...")
    # Smažeme staré data ať tam nevzniká bodel, pokud by se to spustilo víckrát
    # Supabase Python klient nemá přímo truncate all pro RLS bypass bez filters u neidentifikovanych keys, 
    # takže raději nahrajeme nová jako upserts s jasnými keys.

    today = datetime.now().date()
    
    print("🌱 Připravuji se na zápis 30 dní Score historie do Supabase...")
    
    weights = {
        "interest_rates": 0.22, "inflation": 0.20, "gdp": 0.13,
        "labor": 0.12, "cot": 0.11, "spmi": 0.08, "mpmi": 0.06,
        "retail_sales": 0.05, "trend": 0.05, "retail_sentiment": 0.04, "seasonality": 0.02
    }

    # Generování HISTORY (posledních 30 dní)
    scores_to_insert = []
    base_score = -0.3
    
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        base_score = max(-3.0, min(3.0, base_score + (random.random() - 0.48) * 0.4))
        
        scores_to_insert.append({
            "date": d.isoformat(),
            "pair": "EURUSD",
            "score_interest_rates": -1.2,
            "score_inflation": -0.8,
            "score_gdp": 0.4,
            "score_labor": -1.5,
            "score_cot": 1.8,
            "score_spmi": -0.6,
            "score_mpmi": -0.3,
            "score_retail_sales": -0.9,
            "score_trend": -1.0,
            "score_retail_sentiment": 0.5,
            "score_seasonality": 0.2,
            "weights": weights,
            "total_score": round(base_score, 2),
            "label": "Neutral"
        })
        
    print(f"📦 Nahrávám {len(scores_to_insert)} záznamů do daily_scores...")
    # Supabase limits upsert array sizes sometimes, but 30 is fine
    res = db.table("daily_scores").upsert(scores_to_insert).execute()

    print("🌱 Připravuji se na zápis 7 dní logiky predikčního pásma...")
    # Generování PREDIKcí (7 dní)
    preds_to_insert = []
    mid = base_score
    for i in range(1, 8):
        d = today + timedelta(days=i)
        mid = max(-3.0, min(3.0, mid + (random.random() - 0.5) * 0.35))
        
        preds_to_insert.append({
            "created_date": today.isoformat(),
            "prediction_date": d.isoformat(),
            "pair": "EURUSD",
            "predicted_score_mid": round(mid, 2),
            "predicted_score_low": round(mid - 0.6, 2),
            "predicted_score_high": round(mid + 0.6, 2),
            "confidence": 0.72,
            "actual_score": None,
            "accuracy_score": None
        })
        
    res = db.table("predictions").upsert(preds_to_insert).execute()

    print("🌱 Nasazování mock Událostí (Events) pro Forex Factory...")
    # MOCK EVENTS
    events = [
        {"event_date": (today + timedelta(days=1)).isoformat(), "title": "US CPI m/m", "country": "USD", "impact": "High", "forecast": "0.3%", "previous": "0.3%", "polymarket_yes_prob": 0.34},
        {"event_date": (today + timedelta(days=2)).isoformat(), "title": "ECB Rate Decision", "country": "EUR", "impact": "High", "forecast": "Hold (2.65%)", "previous": "2.65%", "euribor_signal": 0.12},
        {"event_date": (today + timedelta(days=3)).isoformat(), "title": "German Manufacturing PMI", "country": "EUR", "impact": "Medium", "forecast": "46.8", "previous": "46.5"},
        {"event_date": (today + timedelta(days=4)).isoformat(), "title": "US Retail Sales m/m", "country": "USD", "impact": "Medium", "forecast": "0.2%", "previous": "-0.1%", "polymarket_yes_prob": 0.51},
        {"event_date": (today + timedelta(days=5)).isoformat(), "title": "US Initial Jobless Claims", "country": "USD", "impact": "Medium", "forecast": "215K", "previous": "219K"}
    ]
    db.table("upcoming_events").upsert(events).execute()

    print("✅ Seedování je u konce. Db tabulky mají testovací data!")

if __name__ == "__main__":
    asyncio.run(seed_mock_database())
