import pandas as pd
import numpy as np
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


def _ema(series: pd.Series, length: int) -> pd.Series:
    """Exponenciální klouzavý průměr — náhrada za pandas_ta.ema()."""
    return series.ewm(span=length, adjust=False).mean()


def _adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """
    Výpočet ADX (Average Directional Index) bez externích závislostí.
    Vrací Series s hodnotami ADX pro každý řádek.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Directional Movement
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smoothed with EWM (Wilder's smoothing ≈ ewm com=length-1)
    atr = pd.Series(tr).ewm(com=length - 1, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm).ewm(com=length - 1, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).ewm(com=length - 1, adjust=False).mean() / atr

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)
    adx = dx.ewm(com=length - 1, adjust=False).mean()
    return adx


def score_trend(df: pd.DataFrame) -> float:
    """
    Hodnotí technický makro-trend EUR/USD podle zadané denní (D1) struktury.
    Počítá EMA 20, EMA 50 a ADX čistě přes pandas/numpy (bez pandas-ta).

    Pokud je cena nad 20 EMA, a 20 EMA > 50 EMA, trend je UP (+).
    Síla (ADX) skóre násobí (max 3.0).
    """
    if df is None or len(df) < 50:
        return 0.0

    try:
        df = df.copy()
        df["EMA_20"] = _ema(df["close"], 20)
        df["EMA_50"] = _ema(df["close"], 50)
        df["ADX_14"] = _adx(df, 14).values

        last_row = df.iloc[-1]

        close = last_row["close"]
        ema_20 = last_row["EMA_20"]
        ema_50 = last_row["EMA_50"]
        adx = last_row["ADX_14"]

        # Directional rozlišení
        dir_score = 0.0
        if close > ema_20:
            dir_score += 1.0
        else:
            dir_score -= 1.0

        if ema_20 > ema_50:
            dir_score += 1.0
        else:
            dir_score -= 1.0

        # Síla trendu přes ADX
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
