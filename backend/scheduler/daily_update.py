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
    "retail_sentiment": {"max_days": 7,  "decay": False},
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
    
    # 1A. Sezónnost (záleží jen na aktuálním měsíci a měnovém páru)
    scores["seasonality"] = score_seasonality(pair=pair)
    indicator_ages["seasonality"] = 0  # konstantní — vždy dnešní
    logger.info(f"Seasonality score: {scores['seasonality']}")

    # 1B. Trend (Cenový akce z OANDA / Alpha Vantage / EODHD) + VIX Risk Sentiment
    df_ohlc = await fetch_historical_ohlc(days=60, pair=pair)
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
    
    # 1C. Retail Sentiment (MyFXBook)
    sentiment_data = await fetch_retail_sentiment(pair=pair)
    if sentiment_data:
        scores["retail_sentiment"] = score_sentiment(sentiment_data.long_pct, sentiment_data.short_pct)
        indicator_ages["retail_sentiment"] = 0  # denní data z OANDA = vždy čerstvá
    logger.info(f"Retail sentiment score: {scores.get('retail_sentiment', 0.0)}")

    # ---------------------------------------------------------
    # KROK 2: TÝDENNÍ / PRAVIDELNÁ DATA (COT z Nasdaqu)
    # ---------------------------------------------------------
    cot_data = await fetch_cot_data(pair=pair)
    if cot_data:
        scores["cot"] = score_cot_combined(
            base_net=cot_data.base_net_position,
            quote_net=cot_data.quote_net_position,
            base_lookback=cot_data.base_history_52w,
            quote_lookback=cot_data.quote_history_52w,
            pair=pair
        )
        indicator_ages["cot"] = 0  # čerstvě stažená COT data
    logger.info(f"COT score: {scores.get('cot', 0.0)}")

        
    # ---------------------------------------------------------
    # KROK 3: FOREX FACTORY KALENDÁŘ (Dnešní Surprise události)
    # ---------------------------------------------------------
    # Stáhneme celý týden a vyfiltrujeme jen dnešek
    ff_week = await fetch_forex_factory_week(pair=pair)
    ff_today = await filter_today_events(ff_week)
    
    # Pamatujeme si raw surprise data, která potom uložíme do indicator_readings
    ff_readings_to_save = []
    fresh_scores_today = {}
    
    # Načteme poslední úrokové sazby z databáze jako baseline
    RATE_KEYS = {
        "EUR": "ecb_rate",
        "GBP": "boe_rate",
        "JPY": "boj_rate",
        "USD": "fed_rate",
        "AUD": "rba_rate",
        "NZD": "rbnz_rate"
    }
    base_rate_key = RATE_KEYS.get(pair[:3], "ecb_rate")
    quote_rate_key = RATE_KEYS.get(pair[3:], "fed_rate")

    try:
        res_quote = db.table("indicator_readings").select("actual").eq("indicator_name", quote_rate_key).eq("pair", pair).order("date", desc=True).limit(1).execute()
        res_base = db.table("indicator_readings").select("actual").eq("indicator_name", base_rate_key).eq("pair", pair).order("date", desc=True).limit(1).execute()
        latest_quote = res_quote.data[0]["actual"] if res_quote.data else 5.25
        latest_base = res_base.data[0]["actual"] if res_base.data else 4.25
    except Exception as e:
        logger.warning(f"Nepodařilo se načíst baseline úrokové sazby z DB: {e}")
        latest_quote = 5.25
        latest_base = 4.25

    SPECIFIC_TO_GENERIC = {
        "cpi_us":           "inflation",
        "cpi_eu":           "inflation",
        "cpi_uk":           "inflation",
        "pce_us":           "inflation",
        "pce_eu":           "inflation",
        "pce_uk":           "inflation",
        "nfp_us":           "labor",
        "nfp_eu":           "labor",
        "nfp_uk":           "labor",
        "unemployment_us":  "labor",
        "unemployment_eu":  "labor",
        "unemployment_uk":  "labor",
        "gdp_flash_us":     "gdp",
        "gdp_flash_eu":     "gdp",
        "gdp_flash_uk":     "gdp",
        "mpmi_us":          "mpmi",
        "mpmi_eu":          "mpmi",
        "mpmi_uk":          "mpmi",
        "spmi_us":          "spmi",
        "spmi_eu":          "spmi",
        "spmi_uk":          "spmi",
        "retail_sales_us":  "retail_sales",
        "retail_sales_eu":  "retail_sales",
        "retail_sales_uk":  "retail_sales",
        # Rate decisions musí aktualizovat interest_rates score
        "fed_rate":         "interest_rates",
        "ecb_rate":         "interest_rates",
        "boe_rate":         "interest_rates",
        "boc_rate":         "interest_rates",
    }

    for ev in ff_today:
        if not ev.indicator_key or not ev.actual or not ev.forecast:
            # Nevíme o jaký indikátor jde (nenastavený klíč), nebo chybí data k porovnání
            continue
            
        stats = await get_normalization_stats(ev.indicator_key)
        
        # Dynamická detekce, zda událost pochází od Base nebo Quote měny
        base_currency = pair[:3]
        quote_currency = pair[3:]
        
        invert = False
        if ev.country == base_currency:
            # Dobré zprávy pro Base měnu = Pár roste (Bullish) → Invert=False
            invert = False
            # Výjimka: Nezaměstnanost (vyšší je BAD pro měnu -> BEARISH pro pár)
            if "unemployment" in ev.indicator_key.lower():
                invert = True
        elif ev.country == quote_currency:
            # Dobré zprávy pro Quote měnu = Pár klesá (Bearish) → Invert=True
            invert = True
            # Výjimka: Nezaměstnanost (vyšší je BAD pro Quote měnu -> BULLISH pro pár)
            if "unemployment" in ev.indicator_key.lower():
                invert = False
        else:
            # Fallback pro třetí země
            invert = False
                
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
        if ev.indicator_key == quote_rate_key and actual_float is not None:
            latest_quote = actual_float
        elif ev.indicator_key == base_rate_key and actual_float is not None:
            latest_base = actual_float

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

    bond_histories = await fetch_2y_yield_histories(lookback_days=90, pair=pair)

    if bond_histories:
        us_hist, de_hist = bond_histories
        combined_ir, bond_score, policy_score, ir_log = score_combined_interest_rates(
            quote_2y_history=us_hist, 
            base_2y_history=de_hist, 
            quote_rate=latest_quote, 
            base_rate=latest_base,
            pair=pair
        )
        scores["interest_rates"] = combined_ir
        indicator_ages["interest_rates"] = 0  # denní bond spread = vždy čerstvý
        logger.info(f"Interest Rates (kombinovane): {ir_log}")
    else:
        # Fallback: pouze policy rate differential (původní chování)
        # diff je kladný, pokud Base platí víc než Quote -> Bullish pro pár
        rate_diff = latest_base - latest_quote
        
        # Ošetření: Pro páry začínající na USD (USDJPY), Base je USD. diff = fed - boj. To je kladné.
        # Pro EURNZD: Base je EUR. diff = ecb - rbnz.
        # Obecně: policy_score = rate_diff * 2.0
        scores["interest_rates"] = float(max(-10.0, min(10.0, rate_diff * 2.0)))
        
        indicator_ages["interest_rates"] = 0  # počítáme denně (fallback)
        logger.warning(
            f"Bond yields nedostupné — fallback na policy rate: "
            f"QuoteRate={latest_quote:.2f}%, BaseRate={latest_base:.2f}%, "
            f"diff={rate_diff:.2f}% → score={scores['interest_rates']:.4f}"
        )

    # ---------------------------------------------------------
    # KROK 4: PŘÍPRAVA BUDOUCÍCH UDÁLOSTÍ PRO PREDIKCE
    # ---------------------------------------------------------
    poly_markets = await fetch_polymarket_economics()
    
    # Získáme Euribor/OIS pravděpodobnosti pro zasedání ECB
    euribor_data = await fetch_euribor_signal(current_ecb_rate=latest_base, pair=pair)
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
        
        db.table("daily_scores").upsert(score_record, on_conflict="date,pair").execute()
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
        
        await generate_7day_prediction(daily_model.total, daily_model.weights, pair=pair)
        await evaluate_predictions_accuracy(pair=pair)
        
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
