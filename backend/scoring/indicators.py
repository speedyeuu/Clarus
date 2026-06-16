import pandas as pd
import numpy as np
import statistics
from datetime import datetime
from typing import Dict, Optional, Tuple
from .normalizer import NormalizationStats, normalize_surprise_to_score, parse_forex_factory_value


def score_bond_spread(
    quote_2y_history: Dict[str, float],
    base_2y_history: Dict[str, float],
    pair: str = "EURUSD"
) -> float:
    """
    Vypočítá skóre z US-DE 2Y dluhopisového spreadu.

    Logika:
      - Spread = US 2Y výnos - DE 2Y výnos
      - Větší spread → USD dluhopisy platí víc → USD atraktivnější → EUR/USD klesá → záporné skóre
      - Menší/záporný spread → EUR atraktivnější → EUR/USD roste → kladné skóre

    Normalizace: 90denní Z-score spreadu (self-calibrating, nepotřebuje hardcoded hranice).
      - Z-score = (aktuální_spread - průměr_90d) / std_90d
      - Score = clamp(-10, +10, -z_score × 3.33)
      - Z-score -3 → score +10 (spread se zúžil extrémně, EUR silný)
      - Z-score +3 → score -10 (spread se rozšířil extrémně, USD silný)

    Průměrná denní změna spreadu je ~4-5 bps → průměrný denní skok skóre ~±0.26.
    Extrémní den (12 bps) → skok ~±0.69. Žádné divoké výkyvy.
    """
    common_dates = sorted(set(quote_2y_history.keys()) & set(base_2y_history.keys()))

    if len(common_dates) < 5:
        return 0.0

    spreads = [quote_2y_history[d] - base_2y_history[d] for d in common_dates]
    current_spread = spreads[-1]

    if len(spreads) >= 2:
        mean_s = statistics.mean(spreads)
        std_s = statistics.stdev(spreads) if len(spreads) > 1 else 0.1
        std_s = max(std_s, 0.01)  # záchrana před dělením nulou
        z_score = (current_spread - mean_s) / std_s
    else:
        # Jen jeden datový bod — nemůžeme počítat Z-score, použijeme přímou normalizaci
        # Historický rozsah US-DE 2Y spreadu: ~0% až ~3.5%, střed ~1.5%
        z_score = (current_spread - 1.5) / 1.0

    # Normalizace Z-score do bodů
    # Běžně: Kladný Z-score (spread se rozšiřuje, US výnos roste nad Base) = USD silnější.
    if pair.startswith("USD"):
        # USD je Base: Silný USD = Pár roste (Bullish) → Kladné skóre
        raw_score = z_score * 3.33
    else:
        # USD je Quote (EURUSD, GBPUSD): Silný USD = Pár klesá (Bearish) → Záporné skóre
        raw_score = -z_score * 3.33
        
    return float(max(-10.0, min(10.0, raw_score)))


def score_combined_interest_rates(
    quote_2y_history: Dict[str, float],
    base_2y_history: Dict[str, float],
    quote_rate: float,
    base_rate: float,
    pair: str = "EURUSD"
) -> Tuple[float, float, float, str]:
    """
    Kombinuje bond spread (70%) a policy rate differential (30%) do jednoho skóre.

    Proč 70/30:
      - 2Y spread odráží tržní očekávání (mění se každý den) → dynamická složka
      - Policy rate differential je strukturální kotva (mění se 8× ročně) → stabilní složka
      - Pro swing tradera je dynamická složka důležitější

    Vrací: (combined_score, bond_spread_score, policy_score, log_zprava)
    """
    if quote_2y_history and base_2y_history:
        bond_score = score_bond_spread(quote_2y_history, base_2y_history, pair)
    else:
        bond_score = 0.0

    # 2. Policy rate differential
    # Score by mělo být KLADNÉ (Bullish), pokud Base měna platí více než Quote měna.
    rate_diff = base_rate - quote_rate
        
    # Kladný rate_diff znamená, že Base měna je úrokově atraktivnější -> Kladné skóre
    policy_score = float(max(-10.0, min(10.0, rate_diff * 2.0)))

    # --- Kombinace: 70% tržní signál + 30% strukturální kotva ---
    combined = 0.70 * bond_score + 0.30 * policy_score
    combined = float(max(-10.0, min(10.0, combined)))

    # Aktuální spread pro logging
    common = sorted(set(quote_2y_history.keys()) & set(base_2y_history.keys()))
    if common:
        current_spread = quote_2y_history[common[-1]] - base_2y_history[common[-1]]
        us_val = quote_2y_history[common[-1]]
        de_val = base_2y_history[common[-1]]
        log_msg = (
            f"Bond spread (Quote 2Y={us_val:.3f}%, Base 2Y={de_val:.3f}%, "
            f"spread={current_spread:.3f}%) → bond_score={bond_score:.2f} | "
            f"Policy diff (Quote={quote_rate:.2f}%, Base={base_rate:.2f}%) → policy_score={policy_score:.2f} | "
            f"Combined (70/30): {combined:.4f}"
        )
    else:
        log_msg = f"Bond spread data chybí, fallback na policy score={policy_score:.2f}"

    return combined, bond_score, policy_score, log_msg


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
    Pokud je 80% retailu Long -> je to extrémně BEARISH pro pár. (-10.0)
    Pokud je 20% retailu Long -> je to extrémně BULLISH. (+10.0)
    
    Předpokládáme že "neutrální" stav je cca 50/50.
    Rozptyl typicky lítá 30 % - 70 %.

    Vstup: long_pct a short_pct jsou vždy podíly 0.0–1.0
    (collector je zodpovědný za normalizaci).
    """
    if long_pct is None or short_pct is None:
        return 0.0

    # Collector (sentiment.py) VŽDY posílá podíl 0.0–1.0 (např. 0.60 a 0.40).
    # Převedeme na procentuální delta: 0.60 - 0.40 = 0.20 → 20 procentních bodů.
    delta_pct = (long_pct - short_pct) * 100.0
    
    # Škálování: ±60 pctbodů delta → ±10 skóre (kontraindikátor → záporné znaménko)
    score = delta_pct / -6.0
    return float(max(-10.0, min(10.0, score)))


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
    Hodnotí technický makro-trend EUR/USD podle D1 OHLC dat.
    Počítá EMA 20, EMA 50 a ADX čistě přes pandas/numpy.

    OPRAVA: Místo binárního ±3.33 skoku používáme proporcionalitu vzdálenosti od EMA.
    - Vzdálenost od EMA50 (v %) → normalizovaný score
    - EMA20 vs EMA50 alignment → potvrzení nebo oslabení signálu
    - ADX → koeficient síly trendu (slabý ranging trh snižuje důvěru)

    Příklady:
      Cena 2% nad EMA50, EMA20>EMA50, ADX=30 → silný bullish signal
      Cena 0.1% nad EMA50, EMA20<EMA50, ADX=15 → neurčité, score blízko 0
      Cena 3% pod EMA50, EMA20<EMA50, ADX=40 → silný bearish signal
    """
    if df is None or len(df) < 50:
        return 0.0

    try:
        df = df.copy()
        df["EMA_20"] = _ema(df["close"], 20)
        df["EMA_50"] = _ema(df["close"], 50)
        df["ADX_14"] = _adx(df, 14).values

        last = df.iloc[-1]
        close  = last["close"]
        ema20  = last["EMA_20"]
        ema50  = last["EMA_50"]
        adx    = last["ADX_14"]

        # --- Složka 1: Proporcionalní vzdálenost ceny od EMA50 ---
        # Normalizace: ±2.5% od EMA50 = ±10 (plný rozsah)
        dist_pct = (close - ema50) / ema50 * 100.0
        dist_score = float(max(-10.0, min(10.0, dist_pct * 4.0)))

        # --- Složka 2: EMA crossover (potvrzení trendu) ---
        # EMA20 nad EMA50 = bullish setup; pod = bearish
        cross_pct = (ema20 - ema50) / ema50 * 100.0
        ema_aligned = 1.0 if cross_pct > 0 else -1.0

        # Pokud cena a EMA alignment ukazují stejný směr → boost, jinak penalty
        same_direction = (dist_score > 0 and ema_aligned > 0) or (dist_score < 0 and ema_aligned < 0)
        alignment_factor = 1.15 if same_direction else 0.75

        # --- Složka 3: ADX – síla trendu ---
        # Slabý ranging trh (ADX < 20) = snižuje důvěru
        if adx >= 35:
            adx_factor = 1.0   # silný trend
        elif adx >= 20:
            adx_factor = 0.75  # střední trend
        else:
            adx_factor = 0.40  # ranging, nespolehlivé

        raw_score = dist_score * alignment_factor * adx_factor
        return float(max(-10.0, min(10.0, raw_score)))

    except Exception:
        return 0.0


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """
    Vypočítá RSI(14) z D1 OHLC dat.

    RSI měří momentum a přeprodanost/překoupenost ceny.
    Hodnoty: 0-100
      < 30 = přeprodáno (oversold) → potenciální obrat nahoru
      > 70 = překoupeno (overbought) → potenciální obrat dolů
      30-70 = normální rozsah
    """
    if df is None or len(df) < period + 1:
        return 50.0  # neutrální fallback

    try:
        delta = df["close"].diff()
        gain  = delta.where(delta > 0, 0.0)
        loss  = (-delta).where(delta < 0, 0.0)

        # Wilder's smoothing (ekvivalent EWM com=period-1)
        avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

        rs  = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return float(round(rsi.iloc[-1], 2))

    except Exception:
        return 50.0


def get_entry_signal(rsi: float, total_score: float, adx: float) -> dict:
    """
    Kombinuje fundamentální skóre s RSI a ADX pro entry timing signal.

    Logika pro swing tradera (1-7 dní):
      - Fundamentální skóre říká SMĚR (bullish/bearish EUR/USD)
      - RSI říká KDY vstoupit (není přeprodáno/překoupeno?)
      - ADX říká JAK SILNÝ je trend (vyplatí se vůbec vstoupit?)

    Vrací dict s: signal (klíč), label (text), color (barva), description
    """
    is_bullish = total_score > 1.5
    is_bearish = total_score < -1.5
    strong_trend = adx >= 25

    if is_bullish and strong_trend:
        if rsi < 50:
            return {
                "signal": "GOOD_LONG",
                "label": "✅ Dobrý vstup LONG",
                "color": "bullish",
                "description": f"Bullish fundamenty + RSI {rsi:.0f} (prostor pro růst)"
            }
        elif rsi > 65:
            return {
                "signal": "WAIT_PULLBACK",
                "label": "⏳ Čekej na pullback",
                "color": "neutral",
                "description": f"Bullish fundamenty, ale RSI {rsi:.0f} — trh přehřátý, vyčkej"
            }
        else:
            return {
                "signal": "WEAK_LONG",
                "label": "🟡 Slabý long setup",
                "color": "mild_bullish",
                "description": f"Bullish fundamenty, RSI {rsi:.0f} (normální pásmo)"
            }

    elif is_bearish and strong_trend:
        if rsi > 50:
            return {
                "signal": "GOOD_SHORT",
                "label": "✅ Dobrý vstup SHORT",
                "color": "bearish",
                "description": f"Bearish fundamenty + RSI {rsi:.0f} (prostor pro pokles)"
            }
        elif rsi < 35:
            return {
                "signal": "WAIT_PULLBACK",
                "label": "⏳ Čekej na pullback",
                "color": "neutral",
                "description": f"Bearish fundamenty, ale RSI {rsi:.0f} — přeprodáno, vyčkej"
            }
        else:
            return {
                "signal": "WEAK_SHORT",
                "label": "🟡 Slabý short setup",
                "color": "mild_bearish",
                "description": f"Bearish fundamenty, RSI {rsi:.0f} (normální pásmo)"
            }

    elif not strong_trend:
        return {
            "signal": "RANGING",
            "label": "↔️ Ranging trh",
            "color": "neutral",
            "description": f"ADX {adx:.0f} — trh nemá jasný trend, vyhni se vstupu"
        }
    else:
        return {
            "signal": "NEUTRAL",
            "label": "⚪ Neutrální",
            "color": "neutral",
            "description": f"Smíšené signály (score {total_score:.1f}, RSI {rsi:.0f})"
        }




def score_seasonality(pair: str = "EURUSD") -> float:
    """
    Vrací historickou průměrnou sílu Base měny vůči USD v daném měsíci.
    """
    month = datetime.now().month
    
    # Odhad sezónnosti pro EUR/USD a GBP/USD.
    seasonality_maps = {
        "EURUSD": {
            1: -3.0, 2: -2.0, 3: -5.0, 4: 3.0, 5: -3.0, 6: 0.0,
            7: 2.0, 8: -3.0, 9: -2.0, 10: 3.0, 11: -2.0, 12: 8.0
        },
        "GBPUSD": {
            1: -2.0, 2: -3.0, 3: -4.0, 4: 6.0, 5: -2.0, 6: -1.0,
            7: 3.0, 8: -3.0, 9: -2.0, 10: 1.0, 11: 2.0, 12: 4.0
        },
        "USDJPY": {
            # Březen/Duben jsou typicky silné pro JPY kvůli repatriaci kapitálu, což znamená Bearish pro USDJPY
            1: 2.0, 2: 1.0, 3: -3.0, 4: -2.0, 5: 1.0, 6: 0.0,
            7: -1.0, 8: -1.0, 9: 2.0, 10: 1.0, 11: 2.0, 12: -2.0
        },
        "EURNZD": {
            1: -1.0, 2: -1.0, 3: 0.0, 4: 2.0, 5: 1.0, 6: 0.0,
            7: 1.0, 8: 1.0, 9: 1.0, 10: -1.0, 11: -1.0, 12: -1.0
        }
    }
    
    pair_map = seasonality_maps.get(pair, seasonality_maps["EURUSD"])
    return float(pair_map.get(month, 0.0))
