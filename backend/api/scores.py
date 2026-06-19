from fastapi import APIRouter, HTTPException
from db.client import get_supabase
from typing import Optional

router = APIRouter()


@router.get("/latest")
async def get_latest_score(pair: str = "EURUSD"):
    """Vrátí dnešní (nebo poslední dostupné) denní skóre pro daný pár."""
    db = get_supabase()
    result = (
        db.table("daily_scores")
        .select("*")
        .eq("pair", pair)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Žádná data zatím nejsou k dispozici.")
    return result.data[0]


@router.get("/history")
async def get_score_history(days: int = 30, pair: str = "EURUSD"):
    """Vrátí historii skóre za posledních N dní pro daný pár."""
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    db = get_supabase()
    result = (
        db.table("daily_scores")
        .select("pair, date, total_score, label, score_interest_rates, score_inflation, score_gdp, score_labor, score_cot, score_spmi, score_mpmi, score_retail_sales, score_trend, score_retail_sentiment, score_seasonality, weights")
        .eq("pair", pair)
        .gte("date", cutoff)
        .order("date", desc=False)
        .execute()
    )
    return result.data


@router.get("/technical")
async def get_technical_analysis(pair: str = "EURUSD"):
    """
    Vrátí technickou analýzu pro swing trading panel.

    Vypočítá z aktuálních D1 OHLC dat:
      - RSI(14): momentum a přeprodanost/překoupenost
      - EMA20, EMA50: vzdálenost a alignment
      - ADX(14): síla trendu
      - entry_signal: kombinovaný vstupní signál pro swing tradera

    Kombinuje s dnešním fundamentálním total_score pro entry timing.
    """
    from collectors.price import fetch_historical_ohlc
    from scoring.indicators import calculate_rsi, get_entry_signal, _ema, _adx
    from db.client import get_supabase

    db = get_supabase()

    # Stáhneme OHLC data (60 dní stačí pro EMA50 + RSI14)
    df = await fetch_historical_ohlc(days=60, pair=pair)
    if df is None or len(df) < 20:
        raise HTTPException(status_code=503, detail="Cennová data nejsou dostupná.")

    # Získáme dnešní total_score pro entry signal
    total_score = 0.0
    try:
        res = (
            db.table("daily_scores")
            .select("total_score")
            .eq("pair", pair)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            total_score = float(res.data[0]["total_score"])
    except Exception:
        pass

    # Výpočty — musíme resetovat index aby _adx() vrátila správnou délku
    df_calc = df.copy().reset_index(drop=True)
    df_calc["EMA_20"] = _ema(df_calc["close"], 20)
    df_calc["EMA_50"] = _ema(df_calc["close"], 50)
    adx_series = _adx(df_calc, 14)
    df_calc["ADX_14"] = adx_series.values[:len(df_calc)]

    last = df_calc.iloc[-1]
    close = float(last["close"])
    ema20 = float(last["EMA_20"])
    ema50 = float(last["EMA_50"])
    adx   = float(last["ADX_14"])

    rsi = calculate_rsi(df_calc)

    # Vzdálenosti v procentech
    dist_from_ema20_pct = round((close - ema20) / ema20 * 100, 3)
    dist_from_ema50_pct = round((close - ema50) / ema50 * 100, 3)
    ema_cross_pct       = round((ema20 - ema50) / ema50 * 100, 3)

    # Entry signal
    entry = get_entry_signal(rsi, total_score, adx)

    return {
        "pair": pair,
        "close": round(close, 5),
        "rsi": round(rsi, 1),
        "ema20": round(ema20, 5),
        "ema50": round(ema50, 5),
        "adx": round(adx, 1),
        "dist_from_ema20_pct": dist_from_ema20_pct,
        "dist_from_ema50_pct": dist_from_ema50_pct,
        "ema_cross_pct": ema_cross_pct,
        "ema20_above_ema50": ema20 > ema50,
        "price_above_ema50": close > ema50,
        "total_score": round(total_score, 2),
        "entry_signal": entry,
        "rsi_zone": (
            "oversold" if rsi < 30 else
            "overbought" if rsi > 70 else
            "normal"
        ),
    }

