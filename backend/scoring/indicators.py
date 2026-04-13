import pandas as pd
import pandas_ta as ta
from datetime import datetime
from .normalizer import NormalizationStats, normalize_surprise_to_score, parse_forex_factory_value

def score_ff_event(actual_str: str, forecast_str: str, stats: NormalizationStats, invert: bool = False) -> float:
    """Hodnotí událost z kalendáře. Wrapper kolem normalizeru."""
    actual = parse_forex_factory_value(actual_str)
    forecast = parse_forex_factory_value(forecast_str)
    
    if actual is None or forecast is None:
        return 0.0
        
    return normalize_surprise_to_score(actual, forecast, stats, invert)


def score_sentiment(long_pct: float, short_pct: float) -> float:
    """
    OANDA Retail Sentiment je KONTRAINDIKÁTOR.
    Pokud je 80% retailu Long -> je to extrémně BEARISH pro pár. (-3.0)
    Pokud je 20% retailu Long -> je to extrémně BULLISH. (+3.0)
    
    Předpokládáme že "neutrální" stav je cca 50/50.
    Rozptyl typicky lítá 30 % - 70 %.
    """
    if long_pct is None or short_pct is None:
        return 0.0

    # Rozdíl (pokud 80 - 20 = +60, extrémně long retail)
    # Rozdíl chceme preložit na škálu -3 až 3
    # Extrémní long retail (+60 delta) by měl dát -3.
    # Takže dělíme -20 (aby +60 / -20 dalo -3.0).
    delta = long_pct - short_pct
    
    score = delta / -20.0
    return max(-3.0, min(3.0, score))


def score_trend(df: pd.DataFrame) -> float:
    """
    Hodnotí technický makro-trend EUR/USD podle zadané denní (D1) struktury.
    Používá pandas-ta k výpočtu EMA 20, EMA 50 a ADX z OHLC dat.

    Pokud je cena nad 20 EMA, a 20 EMA > 50 EMA, trend je UP (+).
    Síla (ADX) skóre násobí (max 3.0).
    """
    if df is None or len(df) < 50:
        return 0.0

    try:
        # Vypočítáme přes pandas-ta
        df.ta.ema(length=20, append=True)
        df.ta.ema(length=50, append=True)
        # ADX počítá ADX, D+ a D-, default length=14
        df.ta.adx(length=14, append=True)

        last_row = df.iloc[-1]
        
        close = last_row["close"]
        ema_20 = last_row["EMA_20"]
        ema_50 = last_row["EMA_50"]
        
        # ADX jméno sloupce se generuje automaticky (typicky ADX_14)
        adx_cols = [c for c in df.columns if c.startswith("ADX_")]
        if not adx_cols:
            return 0.0
            
        adx = last_row[adx_cols[0]]

        # Directional rozlišení
        # +1 za close > ema20
        # +1 za ema20 > ema50
        dir_score = 0.0
        
        if close > ema_20:
            dir_score += 1.0
        else:
            dir_score -= 1.0
            
        if ema_20 > ema_50:
            dir_score += 1.0
        else:
            dir_score -= 1.0

        # Máme dir_score od -2 do +2
        # Pokud je ADX nízké (pod 20), trh je v rangi a trend nemá sílu
        # Pokud je ADX > 40, trend je hodně silný, násobíme dir_score víc
        multiplier = 0.5
        if adx >= 40:
            multiplier = 1.5
        elif adx >= 25:
            multiplier = 1.0

        final_trend_score = dir_score * multiplier
        
        return max(-3.0, min(3.0, final_trend_score))
        
    except Exception:
        return 0.0


def score_seasonality() -> float:
    """
    Vrací historickou průměrnou sílu EUR v daném měsíci (historicky nejlepší prosinec).
    Vycházíme z plan.md.
    """
    month = datetime.now().month
    
    # Odhad sezónnosti pro EUR/USD převzatý z plánu a reálných tabulek.
    # Např. prosinec +2.5 (extrémně silný EUR), březen -1.5, apod.
    seasonality_map = {
        1: -1.0,  # Leden: Typicky silnější USD
        2: -0.5,
        3: -1.5,  # Březen mívá silný USD (repatriace)
        4: 1.0,   # Duben: Tradičně dobrý měsíc pro EUR
        5: -1.0,
        6: 0.0,
        7: 0.5,
        8: -1.0,
        9: -0.5,
        10: 1.0,
        11: -0.5,
        12: 2.5   # Prosinec: Fenomén "End of Year EUR rally", slabý USD
    }
    
    return float(seasonality_map.get(month, 0.0))
