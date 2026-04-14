from loguru import logger
from datetime import datetime, date, timedelta
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

from scoring.normalizer import get_normalization_stats, parse_forex_factory_value
from scheduler.update_normalization_stats import update_normalization_stats
from scoring.indicators import score_ff_event, score_sentiment, score_trend, score_seasonality
from scoring.cot_combined import score_cot_combined
from scoring.engine import calculate_total_score

# ============================================================
# CARRY-FORWARD KONFIGURACE
# ============================================================
# Každý indikátor má:
#   max_days  ... kolik dní je hodnota platná (pak se nuluje)
#   decay     ... True = lineární pokles k 0; False = plná hodnota až do konce

CARRY_FORWARD_CONFIG = {
    # FLAT — platí naplno, pak 0 (sazba je fyzická realita, COT přijde nový za týden...)
    "interest_rates":   {"max_days": 45, "decay": False},
    "cot":              {"max_days": 7,  "decay": False},
    "retail_sentiment": {"max_days": 3,  "decay": False},
    "seasonality":      {"max_days": 30, "decay": False},
    # DECAY — lineárně klesá k 0 (surprise stárne, trh ho přehodnocuje)
    "inflation":        {"max_days": 30, "decay": True},
    "gdp":              {"max_days": 60, "decay": True},
    "labor":            {"max_days": 30, "decay": True},
    "spmi":             {"max_days": 30, "decay": True},
    "mpmi":             {"max_days": 30, "decay": True},
    "retail_sales":     {"max_days": 30, "decay": True},
    # trend → NO CARRY: přepočítává se každý den čerstvě z cen
}


async def fetch_previous_scores(pair: str = "EURUSD") -> dict:
    """
    Natáhne poslední platné skóre z tabulky daily_scores pro každý indikátor
    a aplikuje carry-forward logiku:
      - FLAT indikátory: plná hodnota po celou dobu max_days
      - DECAY indikátory: lineární pokles z plné hodnoty na 0 za max_days dní

    Výsledný dict slouží jako baseline pro dnešní výpočet.
    Dnešní FF eventy (CPI, NFP...) pak přepíší příslušné klíče čerstvými hodnotami.
    """
    db = get_supabase()
    today = date.today()

    # Stáhneme max 61 dní zpět (GDP carry je nejdelší = 60 dní)
    cutoff = (today - timedelta(days=61)).isoformat()

    try:
        result = (
            db.table("daily_scores")
            .select(
                "date, score_interest_rates, score_inflation, score_gdp, "
                "score_labor, score_cot, score_spmi, score_mpmi, "
                "score_retail_sales, score_retail_sentiment, score_seasonality"
            )
            .eq("pair", pair)
            .gte("date", cutoff)
            .order("date", desc=True)
            .execute()
        )
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst carry-forward skóre: {e}")
        return {}

    if not result.data:
        logger.info("Žádná historická data pro carry-forward — začínám od nuly.")
        return {}

    scores = {}

    for indicator, config in CARRY_FORWARD_CONFIG.items():
        col_name = f"score_{indicator}"
        max_days = config["max_days"]
        use_decay = config["decay"]

        # Procházíme záznamy od nejčerstvějšího; hledáme první nenulový
        for row in result.data:
            val = row.get(col_name)
            if val is None:
                continue  # Tento den neměl data, zkusíme starší

            row_date = date.fromisoformat(row["date"])
            age_days = (today - row_date).days

            if age_days > max_days:
                # Data jsou příliš stará → nepoužijeme, zůstane 0.0
                logger.debug(f"Carry-forward [{indicator}]: data stará {age_days}d > limit {max_days}d → skipped")
                break

            if use_decay:
                # Lineární decay: plná hodnota v den 0, nula v den max_days
                decay_factor = max(0.0, 1.0 - (age_days / max_days))
                carried = round(val * decay_factor, 4)
                logger.info(f"Carry-forward [{indicator}]: {val:.2f} × {decay_factor:.2f} (age {age_days}d) = {carried:.2f}")
            else:
                # Flat: plná hodnota po celou dobu
                carried = val
                logger.info(f"Carry-forward [{indicator}]: {val:.2f} flat (age {age_days}d / max {max_days}d)")

            scores[indicator] = carried
            break

    return scores

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
    # Načteme poslední platné hodnoty z DB jako baseline (carry-forward)
    # Dnešní FF eventy je pak přepíší pro příslušné indikátory
    scores = await fetch_previous_scores(pair)
    logger.info(f"Carry-forward baseline načten: {len(scores)} indikátorů")
    
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
        
        # Parsujeme actual/forecast jako floaty, aby se dala počítat surprise
        actual_float = parse_forex_factory_value(ev.actual)
        forecast_float = parse_forex_factory_value(ev.forecast)
        previous_float = parse_forex_factory_value(ev.previous) if ev.previous else None
        surprise_float = (
            round(actual_float - forecast_float, 6)
            if actual_float is not None and forecast_float is not None
            else None
        )

        ff_readings_to_save.append({
            "date": today_date,
            "indicator_name": ev.indicator_key,
            "pair": pair,
            "actual": actual_float,
            "forecast": forecast_float,
            "previous": previous_float,
            "surprise": surprise_float,
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

    # ---------------------------------------------------------
    # KROK 7: PŘEPOČET NORMALIZAČNÍCH STATISTIK
    # ---------------------------------------------------------
    # Spustí se automaticky po každém pipeline runu.
    # Přepočítá mean_surprise + std_surprise pro indikátory s >= 10 vzorky.
    try:
        await update_normalization_stats(pair)
    except Exception as e:
        logger.error(f"Chyba při aktualizaci normalizačních statistik: {e}")

    logger.info("=== Daily Update dokončen ===")

if __name__ == "__main__":
    # Skript se dá nyní spouštět z linuxového crontabu (nebo Windows Task Scheduleru) např. jako:
    # 0 19 * * * cd /cesta/k/projektu && python backend/scheduler/daily_update.py
    asyncio.run(run_daily_update())
