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
from collectors.euribor import fetch_euribor_signal

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
    # FLAT — platí naplno, pak 0 (sazba je fyzická realita, sezónnost je konstantní v daném měsíci)
    "interest_rates":   {"max_days": 45, "decay": False},
    # COT: report vychází jednou týdně (pátek), data mají 3denní zpoždění.
    # Nejstarší data mohou být ~10 dní stará → 14 dní s decay správně modeluje postupné stárnutí pozic.
    "cot":              {"max_days": 14, "decay": True},
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


async def fetch_previous_scores(pair: str = "EURUSD") -> tuple[dict, dict]:
    """
    Natáhne poslední platné skóre z tabulky daily_scores pro každý indikátor
    a aplikuje carry-forward logiku.

    Vrací tuple (scores, ages) kde:
      - scores: dict {indicator: hodnota} po aplikaci carry-forward a decay
      - ages: dict {indicator: age_days} — kolik dní stará je hodnota

    Věk (age) se použije v engine.py pro freshness multiplier:
      - age=0  → plná váha indikátoru (čerstvé čtení dnes)
      - age=7  → snížená váha (zpráva před týdnem)
      - age=30 → minimální váha (měsíc stará data)
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
        return {}, {}

    if not result.data:
        logger.info("Žádná historická data pro carry-forward — začínám od nuly.")
        return {}, {}

    scores = {}
    ages: dict[str, int] = {}  # věk každého indikátoru ve dnech

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
                carried = val * decay_factor
                logger.info(f"Carry-forward [{indicator}]: {val:.4f} × {decay_factor:.4f} (age {age_days}d) = {carried:.4f}")
            else:
                # Flat: plná hodnota po celou dobu
                carried = val
                logger.info(f"Carry-forward [{indicator}]: {val:.2f} flat (age {age_days}d / max {max_days}d)")

            scores[indicator] = carried
            ages[indicator] = age_days
            break

    return scores, ages

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
    scores, indicator_ages = await fetch_previous_scores(pair)
    logger.info(f"Carry-forward baseline načten: {len(scores)} indikátorů")
    
    # ---------------------------------------------------------
    # KROK 1: KONTINUÁLNÍ INDIKÁTORY
    # ---------------------------------------------------------
    
    # 1A. Sezónnost (záleží jen na aktuálním měsíci)
    scores["seasonality"] = score_seasonality()
    indicator_ages["seasonality"] = 0  # konstantní — vždy dnešní
    logger.info(f"Seasonality score: {scores['seasonality']}")

    # 1B. Trend (Cenový akce z OANDA / Alpha Vantage) + VIX Risk Sentiment
    df_ohlc = await fetch_historical_ohlc(days=60)
    tech_trend_score = score_trend(df_ohlc) if df_ohlc is not None else 0.0

    # VIX Risk Sentiment: vysoký VIX = tržní strach = USD safe haven = bearish EUR/USD
    # Blend: 60% technický trend (EMA/ADX) + 40% VIX (risk environment)
    from collectors.vix import fetch_vix_score as fetch_vix
    vix_score = await fetch_vix(lookback_days=90)
    if vix_score is not None:
        scores["trend"] = 0.60 * tech_trend_score + 0.40 * vix_score
        logger.info(
            f"Trend score: EMA/ADX={tech_trend_score:.4f} (60%) + VIX={vix_score:.4f} (40%) "
            f"→ combined={scores['trend']:.4f}"
        )
    else:
        scores["trend"] = tech_trend_score
        logger.info(f"Trend score (VIX nedostupný, jen EMA/ADX): {scores['trend']:.4f}")
    indicator_ages["trend"] = 0  # denní výpočet z cen = vždy čerstvý
    
    # 1C. Retail Sentiment (OANDA)
    sentiment_data = await fetch_retail_sentiment()
    if sentiment_data:
        scores["retail_sentiment"] = score_sentiment(sentiment_data.long_pct, sentiment_data.short_pct)
        indicator_ages["retail_sentiment"] = 0  # denní data z OANDA = vždy čerstvá
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
        indicator_ages["cot"] = 0  # čerstvě stažená COT data
    logger.info(f"COT score: {scores.get('cot', 0.0)}")

        
    # ---------------------------------------------------------
    # KROK 3: FOREX FACTORY KALENDÁŘ (Dnešní Surprise události)
    # ---------------------------------------------------------
    # Stáhneme celý týden a vyfiltrujeme jen dnešek
    ff_week = await fetch_forex_factory_week()
    ff_today = await filter_today_events(ff_week)
    
    # Pamatujeme si raw surprise data, která potom uložíme do indicator_readings
    ff_readings_to_save = []
    fresh_scores_today = {}
    
    # Načteme poslední úrokové sazby z databáze jako baseline
    try:
        res_fed = db.table("indicator_readings").select("actual").eq("indicator_name", "fed_rate").eq("pair", pair).order("date", desc=True).limit(1).execute()
        res_ecb = db.table("indicator_readings").select("actual").eq("indicator_name", "ecb_rate").eq("pair", pair).order("date", desc=True).limit(1).execute()
        latest_fed = res_fed.data[0]["actual"] if res_fed.data else 5.25
        latest_ecb = res_ecb.data[0]["actual"] if res_ecb.data else 4.25
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst baseline úrokové sazby z DB: {e}")
        latest_fed = 5.25
        latest_ecb = 4.25

    SPECIFIC_TO_GENERIC = {
        "cpi_us": "inflation",
        "cpi_eu": "inflation",
        "pce_us": "inflation",
        "nfp_us": "labor",
        "unemployment_us": "labor",
        "gdp_flash_us": "gdp",
        "gdp_flash_eu": "gdp",
        "mpmi_us": "mpmi",
        "mpmi_eu": "mpmi",
        "spmi_us": "spmi",
        "spmi_eu": "spmi",
        "retail_sales_us": "retail_sales",
        "retail_sales_eu": "retail_sales",
    }

    for ev in ff_today:
        if not ev.indicator_key or not ev.actual or not ev.forecast:
            # Nevíme o jaký indikátor jde (nenastavený klíč), nebo chybí data k porovnání
            continue
            
        stats = await get_normalization_stats(ev.indicator_key)
        
        # Některá makro data mají inverzní charakter (Vysoká Inflace v USD/Unemployment v USD -> medvědí dopad pro EUR/USD)
        invert = False
        if ev.country == "USD":
            # Dobré zprávy pro USD = Špatné pro EUR/USD (=> Invert)
            invert = True
            # Výjimka: Nezaměstnanost v USD (vyšší je BAD pro Dolar -> BULLISH pro EUR)
            if "unemployment" in ev.indicator_key.lower():
                invert = False
        elif ev.country == "EUR":
            # Dobré zprávy pro EUR = Dobré pro EUR/USD
            invert = False
            if "unemployment" in ev.indicator_key.lower():
                invert = True
                
        # Získání normalizovaného skóre (už bez zaokrouhlování na celé číslo)
        event_score = score_ff_event(ev.actual, ev.forecast, stats, invert=invert)
        
        # Parsujeme actual/forecast jako floaty, aby se dala počítat surprise
        actual_float = parse_forex_factory_value(ev.actual)
        forecast_float = parse_forex_factory_value(ev.forecast)
        previous_float = parse_forex_factory_value(ev.previous) if ev.previous else None
        surprise_float = (
            actual_float - forecast_float
            if actual_float is not None and forecast_float is not None
            else None
        )

        # Pokud se jedná o změnu úrokové sazby, zachytíme její novou úroveň
        if ev.indicator_key == "fed_rate" and actual_float is not None:
            latest_fed = actual_float
        elif ev.indicator_key == "ecb_rate" and actual_float is not None:
            latest_ecb = actual_float

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
        logger.info(f"FF Event [{ev.title}] ({ev.indicator_key}) -> Score: {event_score:.4f}")

        # Agregace do generického klíče
        generic_key = SPECIFIC_TO_GENERIC.get(ev.indicator_key)
        if generic_key:
            fresh_scores_today.setdefault(generic_key, []).append(event_score)

    # 1. Zprůměrování a uložení dnešních zpráv pro obecné indikátory
    for gen_key, val_list in fresh_scores_today.items():
        if val_list:
            avg_score = sum(val_list) / len(val_list)
            scores[gen_key] = avg_score
            indicator_ages[gen_key] = 0  # dnešní čtení = věk 0 dní (plná váha)

    # 2. Výpočet úrokových sazeb: 70% bond spread (2Y US-DE) + 30% policy rate differential
    #    - Bond spread se mění každý obchodní den (reaguje na změny očekávání trhu)
    #    - Policy rate differential je strukturální kotva (mění se jen na CB meetinzích)
    #    - Pro swing tradera je dynamická složka (bond spread) podstatnější
    from collectors.bond_yields import fetch_2y_yield_histories
    from scoring.indicators import score_combined_interest_rates

    bond_histories = await fetch_2y_yield_histories(lookback_days=90)

    if bond_histories:
        us_hist, de_hist = bond_histories
        combined_ir, bond_score, policy_score, ir_log = score_combined_interest_rates(
            us_hist, de_hist, latest_fed, latest_ecb
        )
        scores["interest_rates"] = combined_ir
        indicator_ages["interest_rates"] = 0  # denní bond spread = vždy čerstvý
        logger.info(f"Interest Rates (kombinovane): {ir_log}")
    else:
        # Fallback: pouze policy rate differential (původní chování)
        diff = latest_fed - latest_ecb
        scores["interest_rates"] = float(max(-10.0, min(10.0, diff * -2.0)))
        indicator_ages["interest_rates"] = 0  # počítáme denně (fallback)
        logger.warning(
            f"Bond yields nedostupné — fallback na policy rate: "
            f"Fed={latest_fed:.2f}%, ECB={latest_ecb:.2f}%, "
            f"diff={diff:.2f}% → score={scores['interest_rates']:.4f}"
        )


    # ---------------------------------------------------------
    # KROK 4: PŘÍPRAVA BUDOUCÍCH UDÁLOSTÍ PRO PREDIKCE
    # ---------------------------------------------------------
    poly_markets = await fetch_polymarket_economics()
    
    # Získáme Euribor/OIS pravděpodobnosti pro zasedání ECB
    euribor_data = await fetch_euribor_signal(current_ecb_rate=latest_ecb)
    euribor_prob = None
    if euribor_data:
        # Převedeme pravděpodobnosti na signál: 1.0 = hike, 0.5 = hold, 0.0 = cut
        euribor_prob = float(euribor_data.prob_hike + 0.5 * euribor_data.prob_hold)
        logger.info(f"Euribor futures implied probability for ECB: {euribor_prob:.4f} (Hike: {euribor_data.prob_hike}, Hold: {euribor_data.prob_hold}, Cut: {euribor_data.prob_cut})")
        
    upcoming_events_to_save = []
    
    # Vyfiltrujeme nadcházející události z celého FF týdne (všechny dny větší než dnešek)
    for ev in ff_week:
        # ev.date může být datetime nebo date objekt — převedeme na ISO string pro srovnání
        ev_date_str = ev.date.date().isoformat() if hasattr(ev.date, "date") else str(ev.date)[:10]
        if ev_date_str > today_date:
            poly_signal = extract_signal_from_polymarket(ev.title, poly_markets)
            
            # Pokud se jedná o úrokové sazby v EU, přiřadíme Euribor signál
            ev_euribor_signal = None
            if ev.country == "EUR" and ev.indicator_key == "ecb_rate":
                ev_euribor_signal = euribor_prob
            
            upcoming_events_to_save.append({
                "event_date": ev_date_str,
                "title": ev.title,
                "country": ev.country,
                "impact": ev.impact,
                "indicator_key": ev.indicator_key,
                "forecast": ev.forecast,
                "previous": ev.previous,
                "polymarket_yes_prob": poly_signal,
                "euribor_signal": ev_euribor_signal
            })
            
    # ---------------------------------------------------------
    # KROK 5: SOUČET (Weighted Score) PŘES ENGINE
    # ---------------------------------------------------------
    # calculate_total_score stáhne váhy z databáze a vyprodukuje finální float score a label
    # Předáme i věk každého indikátoru pro freshness multiplier
    daily_model = await calculate_total_score(scores, indicator_ages)
    logger.info(f"--- DNEŠNÍ SKÓRE: {daily_model.total:.2f} ({daily_model.label}) ---")
    
    # ---------------------------------------------------------
    # KROK 6: ULOŽENÍ VÝSLEDKŮ DO SUPABASE DATABÁZE
    # ---------------------------------------------------------
    try:
        # A) Uložit raw indikátory (ze kterých pak engine normalizátor bere historii)
        for reading in ff_readings_to_save:
            # Zkusíme upsert s definovaným konfliktem
            db.table("indicator_readings").upsert(reading, on_conflict="date,indicator_name,pair").execute()
            
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
        
        db.table("daily_scores").upsert(score_record, on_conflict="date").execute()
        logger.info("Úspěšně zapsáno do tabulky daily_scores.")

    except Exception as e:
        # Tady by to mohlo spadnout, pokud Service Role klíč chybí v `.env`
        logger.error(f"Nepodařilo se uložit data do databáze. Zkontrolujte Supabase Service klíče! Chyba: {e}")

    # C) Uložit nadcházející události a generovat predikci
    try:
        if upcoming_events_to_save:
            # Smaže starší a nahraje nové (jen se upsertnou, pokud mají unique)
            db.table("upcoming_events").upsert(upcoming_events_to_save, on_conflict="event_date,title,country").execute()
            
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
