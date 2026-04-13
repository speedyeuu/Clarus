import httpx
from loguru import logger
import pandas as pd
from typing import Optional
from config import get_settings

async def fetch_historical_ohlc(days: int = 60) -> Optional[pd.DataFrame]:
    """
    Stáhne denní (Daily) OHLC data pro EUR/USD z Alpha Vantage.
    (OANDA bylo odstraněno kvůli EU omezením - přesunuto na MyFXBook jen pro Sentiment)
    Vrací pandas DataFrame s indexem Date a sloupci open, high, low, close.
    """
    return await _fetch_from_alpha_vantage(days)

async def _fetch_from_oanda(days: int) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.oanda_api_token or settings.oanda_api_token == "your-oanda-token":
        logger.error("OANDA API token není nastaven!")
        return None

    # M = Midpoint (mid price)
    url = f"https://api-fxtrade.oanda.com/v3/instruments/EUR_USD/candles?count={days}&price=M&granularity=D"
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

async def _fetch_from_alpha_vantage(days: int) -> Optional[pd.DataFrame]:
    settings = get_settings()
    if not settings.alpha_vantage_key or settings.alpha_vantage_key == "your-alpha-vantage-key":
        logger.error("Alpha Vantage API klíč není nastaven!")
        return None

    url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={settings.alpha_vantage_key}"
    
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
