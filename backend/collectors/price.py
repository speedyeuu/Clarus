import asyncio
import httpx
from loguru import logger
import pandas as pd
from typing import Optional
from config import get_settings

# Mapování interních symbolů na Yahoo Finance tickers
_YFINANCE_SYMBOLS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "EURNZD": "EURNZD=X",
    "EURJPY": "EURJPY=X",
    "XAUUSD": "GC=F",   # Gold Futures — nejlepší volně dostupný ekvivalent XAUUSD
}

async def fetch_historical_ohlc(days: int = 60, pair: str = "EURUSD") -> Optional[pd.DataFrame]:
    """
    Stáhne denní (Daily) OHLC data pro zadaný pár (např. EURUSD).

    Pořadí zdrojů (podle dostupnosti):
      1. yfinance   — zcela zdarma, bez API klíče, aktuální data
      2. EODHD      — placený fallback (pokud je nastaven API klíč)
      3. Alpha Vantage — free tier má 3denní zpoždění a 25 req/den limit
      4. OANDA      — záložní, pokud vše výše selže
    """
    df = await _fetch_from_yfinance(days, pair)
    if df is not None:
        return df
    df = await _fetch_from_eodhd(days, pair)
    if df is not None:
        return df
    df = await _fetch_from_alpha_vantage(days, pair)
    if df is not None:
        return df
    return await _fetch_from_oanda(days, pair)


async def _fetch_from_yfinance(days: int, pair: str) -> Optional[pd.DataFrame]:
    """
    Stáhne OHLC data přes knihovnu yfinance (Yahoo Finance).
    Zcela zdarma, bez API klíče, podporuje forex páry i zlato.
    """
    symbol = _YFINANCE_SYMBOLS.get(pair)
    if not symbol:
        logger.warning(f"yfinance: Neznámý pár '{pair}', chybí mapování symbolu.")
        return None

    try:
        import yfinance as yf

        # Stáhneme o ~30% více dní kvůli víkendům a svátkům
        fetch_days = int(days * 1.4) + 5
        period_str = f"{fetch_days}d"

        def _blocking_fetch():
            ticker = yf.Ticker(symbol)
            return ticker.history(period=period_str, interval="1d")

        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, _blocking_fetch)

        if df is None or df.empty:
            logger.warning(f"yfinance: Prázdná odpověď pro {pair} (symbol: {symbol}).")
            return None

        # Normalizace sloupců
        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
        })
        df = df[["open", "high", "low", "close"]]

        # Normalizace indexu — TimeZone-naive DatetimeIndex pojmenovaný "date"
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index.name = "date"
        df.sort_index(inplace=True)

        # Ořezat na posledních `days` řádků
        df = df.iloc[-days:]

        logger.info(f"yfinance: Staženo {len(df)} řádků pro {pair} (symbol: {symbol})")
        return df

    except Exception as e:
        logger.warning(f"yfinance: Chyba při stahování {pair}: {e}")
        return None


async def _fetch_from_eodhd(days: int, pair: str) -> Optional[pd.DataFrame]:
    """
    Placený fallback — stahuje z EODHD, pouze pokud je nastaven API klíč.
    """
    settings = get_settings()
    if not settings.eodhd_api_key or settings.eodhd_api_key == "your-eodhd-key":
        return None

    from datetime import date, timedelta
    from_date = (date.today() - timedelta(days=days + 5)).isoformat()
    eodhd_symbol = f"{pair}.FOREX"
    url = f"https://eodhd.com/api/eod/{eodhd_symbol}?api_token={settings.eodhd_api_key}&fmt=json&from={from_date}&period=d"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list) or not data:
                logger.warning("EODHD: Nevrátil platná data.")
                return None

            records = [
                {
                    "date": pd.to_datetime(item.get("date")),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                }
                for item in data
            ]

            df = pd.DataFrame(records)
            if df.empty:
                return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            logger.info(f"EODHD (fallback): Staženo {len(df)} řádků pro {pair}")
            return df.iloc[-days:]

    except Exception as e:
        logger.warning(f"EODHD: Chyba při stahování {pair}: {e}")
        return None


async def _fetch_from_oanda(days: int, pair: str) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.oanda_api_token or settings.oanda_api_token == "your-oanda-token":
        return None

    # OANDA formát: EUR_USD
    oanda_instrument = f"{pair[:3]}_{pair[3:]}"
    url = f"https://api-fxtrade.oanda.com/v3/instruments/{oanda_instrument}/candles?count={days}&price=M&granularity=D"
    headers = {
        "Authorization": f"Bearer {settings.oanda_api_token}",
        "Accept-Datetime-Format": "RFC3339"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            candles = data.get("candles", [])
            if not candles:
                return None

            records = []
            for c in candles:
                if not c.get("complete", False):
                    continue
                mid = c.get("mid", {})
                records.append({
                    "date": pd.to_datetime(c.get("time")),
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                })

            df = pd.DataFrame(records)
            if df.empty:
                return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            return df

    except Exception as e:
        logger.warning(f"OANDA: Chyba při stahování {pair}: {e}")
        return None


async def _fetch_from_alpha_vantage(days: int, pair: str) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.alpha_vantage_key or settings.alpha_vantage_key == "your-alpha-vantage-key":
        return None

    from_sym = pair[:3]
    to_sym = pair[3:]
    url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_sym}&to_symbol={to_sym}&apikey={settings.alpha_vantage_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            ts_key = "Time Series FX (Daily)"
            if ts_key not in data:
                logger.warning(f"Alpha Vantage: Chybí daily time series. Odpověď: {data}")
                return None

            timeseries = data[ts_key]
            records = []

            for day_str, values in list(timeseries.items())[:days]:
                records.append({
                    "date": pd.to_datetime(day_str),
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                })

            df = pd.DataFrame(records)
            if df.empty:
                return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            return df

    except Exception as e:
        logger.warning(f"Alpha Vantage: Chyba při stahování {pair}: {e}")
        return None
