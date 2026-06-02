import httpx
from loguru import logger
import pandas as pd
from typing import Optional
from config import get_settings

async def fetch_historical_ohlc(days: int = 60, pair: str = "EURUSD") -> Optional[pd.DataFrame]:
    """
    Stáhne denní (Daily) OHLC data pro zadaný pár (např. EURUSD).

    Pořadí zdrojů (podle kvality dat):
      1. EODHD       — nejpřesnější, aktuální data do dnes, daily limit vysoký
      2. Alpha Vantage — free tier má 3denní zpoždění a 25 req/den limit
      3. OANDA       — záložní, pokud oba výše selžou
    """
    df = await _fetch_from_eodhd(days, pair)
    if df is not None:
        return df
    df = await _fetch_from_alpha_vantage(days, pair)
    if df is not None:
        return df
    return await _fetch_from_oanda(days, pair)

async def _fetch_from_eodhd(days: int, pair: str) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.eodhd_api_key or settings.eodhd_api_key == "your-eodhd-key":
        logger.error("EODHD API klíč není nastaven!")
        return None

    url = f"https://eodhd.com/api/eod/{pair}.FOREX?api_token={settings.eodhd_api_key}&fmt=json&limit={days}&period=d"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list) or not data:
                logger.error("EODHD nevrátil platná data.")
                return None
                
            records = []
            for item in data:
                records.append({
                    "date": pd.to_datetime(item.get("date")),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                })
                
            df = pd.DataFrame(records)
            if df.empty: return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            return df
            
    except Exception as e:
        logger.error(f"Error fetching price from EODHD: {e}")
        return None

async def _fetch_from_oanda(days: int, pair: str) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.oanda_api_token or settings.oanda_api_token == "your-oanda-token":
        logger.error("OANDA API token není nastaven!")
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
                    continue # Ignorujeme nedokončenou dnešní svíčku, pokud potřebujeme striktně close (volitelné)
                    
                mid = c.get("mid", {})
                records.append({
                    "date": pd.to_datetime(c.get("time")),
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                })
                
            df = pd.DataFrame(records)
            if df.empty: return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            return df
            
    except Exception as e:
        logger.error(f"Error fetching price from OANDA: {e}")
        return None

async def _fetch_from_alpha_vantage(days: int, pair: str) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.alpha_vantage_key or settings.alpha_vantage_key == "your-alpha-vantage-key":
        logger.error("Alpha Vantage API klíč není nastaven!")
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
                logger.error(f"Alpha Vantage neobsahuje daily time series. Možný limit API: {data}")
                return None
                
            timeseries = data[ts_key]
            records = []
            
            # Alpha vantage vrací dict kde keys jsou YYYY-MM-DD
            for day_str, values in list(timeseries.items())[:days]:
                records.append({
                    "date": pd.to_datetime(day_str),
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                })
                
            df = pd.DataFrame(records)
            if df.empty: return None
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            # Protože jsme iterovali od nejnovějšího, teď jsme to srovnali chronologicky
            return df
            
    except Exception as e:
        logger.error(f"Error fetching price from Alpha Vantage: {e}")
        return None
