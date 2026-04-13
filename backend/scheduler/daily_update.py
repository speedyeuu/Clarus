from loguru import logger
from datetime import datetime
import asyncio
import sys
import os

# Povolí spouštění tohoto skriptu samostatně z terminálu
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_supabase
from collectors.forex_factory import fetch_forex_factory_week, filter_today_events
from collectors.cot import fetch_cot_data
from collectors.sentiment import fetch_retail_sentiment
from collectors.price import fetch_historical_ohlc
from collectors.polymarket import fetch_polymarket_economics, extract_signal_from_polymarket

from scoring.normalizer import get_normalization_stats
from scoring.indicators import score_ff_event, score_sentiment, score_trend, score_seasonality
from scoring.cot_combined import score_cot_combined
from scoring.engine import calculate_total_score

async def run_daily_update(pair: str = "EURUSD"):
    """
    Hlavní Pipeline aplikace (Fáze 3). Spouští se každý den v 19:00 UTC pro každý aktivní pár.
    Kroky:
    1. Sbírá data z collectorů pro specifikovaný pár.
    2. Počítá dílčí scores.
    3. Posíla vše do obřího agregátoru (Engine).
    4. Ukládá čerstvý výsledek a raw data do Supabase.
    """
    today_date = datetime.now().date().isoformat()
    logger.info(f"=== Spouštím Daily Update Pipeline pro {pair} ({today_date}) ===")
    
    db = get_supabase()
    
    # Slovník pro posbíraná skóre (scale: -3.0 to +3.0)
    scores = {}
    
    # ---------------------------------------------------------
    # KROK 1: KONTINUÁLNÍ INDIKÁTORY
    # ---------------------------------------------------------
    
    # 1A. Sezónnost (záleží jen na aktuálním měsíci)
    scores["seasonality"] = score_seasonality()
    logger.info(f"Seasonality score: {scores['seasonality']}")
    
    # 1B. Trend (Cenový akce z OANDA / Alpha Vantage)
    df_ohlc = await fetch_historical_ohlc(days=60)
    if df_ohlc is not None:
        scores["trend"] = score_trend(df_ohlc)
    logger.info(f"Trend score: {scores.get('trend', 0.0)}")
    
    # 1C. Retail Sentiment (OANDA)
    sentiment_data = await fetch_retail_sentiment()
    if sentiment_data:
        scores["retail_sentiment"] = score_sentiment(sentiment_data.long_pct, sentiment_data.short_pct)
    logger.info(f"Retail sentiment score: {scores.get('retail_sentiment', 0.0)}")
        
    # ---------------------------------------------------------
    # KROK 2: TÝDENNÍ / PRAVIDELNÁ DATA (COT z Nasdaqu)
    # ---------------------------------------------------------
    cot_data = await fetch_cot_data()
    if cot_data:
        scores["cot"] = score_cot_combined(
            eur_net=cot_data.eur_net_position,
            dxy_net=cot_data.dxy_net_position,
            eur_lookback=cot_data.eur_history_52w,
            dxy_lookback=cot_data.dxy_history_52w
        )
    logger.info(f"COT score: {scores.get('cot', 0.0)}")
        
    # ---------------------------------------------------------
    # KROK 3: FOREX FACTORY KALENDÁŘ (Dnešní Surprise události)
    # ---------------------------------------------------------
    # Stáhneme celý týden a vyfiltrujeme jen dnešek
    ff_week = await fetch_forex_factory_week()
    ff_today = await filter_today_events(ff_week)
    
    # Pamatujeme si raw surprise data, která potom uložíme do indicator_readings
    ff_readings_to_save = []
    
    for ev in ff_today:
        if not ev.indicator_key or not ev.actual or not ev.forecast:
            # Nevíme o jaký indikátor jde (nenastavený klíč), nebo chybí data k porovnání
            continue
            
        stats = await get_normalization_stats(ev.indicator_key)
        
        # Některá makro data mají inverzní charakter (Vysoká Inflace v USD/Unemployment v USD -> medvědí dopad pro EUR/USD)
        # NNF a podobné - zde bude zjednodušená logika pro určení inverze
        invert = False
        if ev.country == "USD":
            # Dobré zprávy pro USD = Špatné pro EUR/USD (=> Invert)
            # Např: vyšší NFP, GDP, CPI znamená silnější USD, a proto EURUSD padá. Takže musíme převrátit znaménko.
            invert = True
            # Výjimka: Nezaměstnanost v USD (vyšší je BAD pro Dolar -> BULLISH pro EUR)
            if "unemployment" in ev.indicator_key.lower():
                invert = False
        elif ev.country == "EUR":
            # Dobré zprávy pro EUR = Dobré pro EUR/USD
            invert = False
            if "unemployment" in ev.indicator_key.lower():
                invert = True
                
        # Získání normalizovaného skóre (už je clamped na -3 až +3)
        event_score = score_ff_event(ev.actual, ev.forecast, stats, invert=invert)
        
        # Skóre události přepíše (nebo se přičte? - zatím přepíše) výchozí hodnocení pro dnešní den
        # Pro případ, že by ve stejný den bylo víc reports stejné kategorie, uděláme průměr (zjednodušeně si ponecháme poslední)
        scores[ev.indicator_key] = event_score
        
        ff_readings_to_save.append({
            "date": today_date,
            "indicator_name": ev.indicator_key,
            "pair": pair,
            "actual": ev.actual,
            "forecast": ev.forecast,
            "previous": ev.previous,
            "raw_score": event_score,
            "source": "forex_factory"
        })
        logger.info(f"FF Event [{ev.title}] -> Score: {event_score}")

    # ---------------------------------------------------------
    # KROK 4: PŘÍPRAVA BUDOUCÍCH UDÁLOSTÍ PRO PREDIKCE
    # ---------------------------------------------------------
    poly_markets = await fetch_polymarket_economics()
    upcoming_events_to_save = []
    
    # Vyfiltrujeme nadcházející události z celého FF týdne (všechny dny větší než dnešek)
    for ev in ff_week:
        if ev.date > today_date:
            poly_signal = extract_signal_from_polymarket(ev.title, poly_markets)
            
            upcoming_events_to_save.append({
                "event_date": ev.date,
                "title": ev.title,
                "country": ev.country,
                "impact": ev.impact,
                "indicator_key": ev.indicator_key,
                "forecast": ev.forecast,
                "previous": ev.previous,
                "polymarket_yes_prob": poly_signal,
                "euribor_signal": None # Možno doplnit přes euribor sběrač obdobně
            })
            
    # ---------------------------------------------------------
    # KROK 5: SOUČET (Weighted Score) PŘES ENGINE
    # ---------------------------------------------------------
    # calculate_total_score stáhne váhy z databáze a vyprodukuje finální float score a label
    daily_model = await calculate_total_score(scores)
    logger.info(f"--- DNEŠNÍ SKÓRE: {daily_model.total:.2f} ({daily_model.label}) ---")
    
    # ---------------------------------------------------------
    # KROK 6: ULOŽENÍ VÝSLEDKŮ DO SUPABASE DATABÁZE
    # ---------------------------------------------------------
    try:
        # A) Uložit raw indikátory (ze kterých pak engine normalizátor bere historii)
        for reading in ff_readings_to_save:
            # Zkusíme upsert
            db.table("indicator_readings").upsert(reading).execute()
            
        # B) Uložit finální skóre
        score_record = {
            "date": today_date,
            "pair": pair,
            "score_interest_rates": daily_model.scores.get("interest_rates"),
            "score_inflation": daily_model.scores.get("inflation"),
            "score_gdp": daily_model.scores.get("gdp"),
            "score_labor": daily_model.scores.get("labor"),
            "score_cot": daily_model.scores.get("cot"),
            "score_spmi": daily_model.scores.get("spmi"),
            "score_mpmi": daily_model.scores.get("mpmi"),
            "score_retail_sales": daily_model.scores.get("retail_sales"),
            "score_trend": daily_model.scores.get("trend"),
            "score_retail_sentiment": daily_model.scores.get("retail_sentiment"),
            "score_seasonality": daily_model.scores.get("seasonality"),
            "weights": daily_model.weights,
            "total_score": daily_model.total,
            "label": daily_model.label
        }
        
        db.table("daily_scores").upsert(score_record).execute()
        logger.info("Úspěšně zapsáno do tabulky daily_scores.")

    except Exception as e:
        # Tady by to mohlo spadnout, pokud Service Role klíč chybí v `.env`
        logger.error(f"Nepodařilo se uložit data do databáze. Zkontrolujte Supabase Service klíče! Chyba: {e}")

    # C) Uložit nadcházející události a generovat predikci
    try:
        if upcoming_events_to_save:
            # Smaže starší a nahraje nové (jen se upsertnou, pokud mají unique)
            db.table("upcoming_events").upsert(upcoming_events_to_save).execute()
            
        # Poté spustit samotný generátor pásmové predikce (Fáze 4), co udělá těch 7 svíček forecastu
        from prediction.generator import generate_7day_prediction
        from prediction.accuracy import evaluate_predictions_accuracy
        
        await generate_7day_prediction(daily_model.total, daily_model.weights)
        await evaluate_predictions_accuracy()
        
    except Exception as e:
        logger.error(f"Nepodařilo se dokončit predikce nebo uložit nadcházející události: {e}")

    logger.info("=== Daily Update dokončen ===")

if __name__ == "__main__":
    # Skript se dá nyní spouštět z linuxového crontabu (nebo Windows Task Scheduleru) např. jako:
    # 0 19 * * * cd /cesta/k/projektu && python backend/scheduler/daily_update.py
    asyncio.run(run_daily_update())
