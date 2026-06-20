"""
bond_yields.py
--------------
Stahuje historii 2letých výnosů státních dluhopisů USA a Německa z FRED.

Zdroje (bezplatné, bez API klíče):
  - US 2Y: FRED serie DGS2 (US Treasury 2-Year Constant Maturity)
  - DE 2Y: FRED serie IRDE2YD156N (Germany 2-Year Government Bond Yield)

Vrací slovník {datum: hodnota_v_procentech} pro každý market.
"""

import httpx
from loguru import logger
from typing import Optional, Dict, Tuple
from datetime import date, timedelta
import pandas as pd
from config import get_settings
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
async def _fetch_fred_history(series_id: str, lookback_days: int = 90) -> Dict[str, float]:
    """
    Stáhne historii hodnot z FRED (CSV endpoint) za posledních N dní.
    Vrací dict {YYYY-MM-DD: float_hodnota}.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning(f"FRED {series_id}: HTTP {r.status_code}")
                return {}

            text = r.text.strip()
            if "<html" in text.lower():
                logger.warning(f"FRED {series_id}: vrátil HTML místo CSV (rate limit nebo chyba)")
                return {}

            result = {}
            lines = text.split("\n")[1:]  # přeskočit header
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    date_str = parts[0].strip()
                    val_str = parts[1].strip()
                    if val_str and val_str not in (".", "NA", ""):
                        try:
                            result[date_str] = float(val_str)
                        except ValueError:
                            pass

            logger.info(f"FRED {series_id}: staženo {len(result)} záznamů od {start}")
            return result

    except Exception as e:
        logger.warning(f"FRED {series_id} fetch error: {e}")
        return {}


async def _fetch_de2y_ecb_fallback() -> Dict[str, float]:
    """
    Záloha pro DE 2Y výnos přes ECB SDMX yield curve dataset.
    Vrací historii jako dict {YYYY-MM-DD: float}.
    """
    url = (
        "https://data-api.ecb.europa.eu/service/data/"
        "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
        "?lastNObservations=100"
    )
    result = {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers={"Accept": "text/csv"})
            if r.status_code == 200 and "<html" not in r.text.lower():
                import csv
                from io import StringIO
                reader = csv.DictReader(StringIO(r.text))
                for row in reader:
                    date_str = row.get("TIME_PERIOD", "")
                    val = row.get("OBS_VALUE", "").strip()
                    if date_str and val:
                        result[date_str] = float(val)
                logger.info(f"ECB YC DE 2Y (fallback): staženo {len(result)} historických záznamů.")
    except Exception as e:
        logger.warning(f"ECB YC DE 2Y fallback failed: {e}")
    return result


async def _fetch_uk2y_eodhd(lookback_days: int = 90) -> Dict[str, float]:
    """
    Stáhne historii UK 2Y Gilts z EODHD (ticker GB2Y.GBOV).
    Volitelný placený zdroj — pokud API klíč chybí, vrátí prázdný dict.
    Vrací dict {YYYY-MM-DD: float_hodnota}.
    """
    settings = get_settings()
    if not settings.eodhd_api_key or settings.eodhd_api_key == "your-eodhd-key":
        logger.info("EODHD API klíč není nastaven — UK 2Y Gilts přeskočeny, bude použit fallback na policy rates.")
        return {}

    url = f"https://eodhd.com/api/eod/GB2Y.BOND?api_token={settings.eodhd_api_key}&fmt=json&limit={lookback_days}&period=d"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            if not isinstance(data, list) or not data:
                logger.error("EODHD nevrátil platná data pro UK 2Y Gilts.")
                return {}
                
            result = {}
            for item in data:
                date_str = item.get("date")
                val_str = item.get("close")
                if date_str and val_str is not None:
                    result[date_str] = float(val_str)
                    
            logger.info(f"EODHD UK 2Y: staženo {len(result)} záznamů")
            return result
    except Exception as e:
        logger.info(f"Error fetching UK 2Y from EODHD: {e} - falling back to policy rates")
        return {}


async def fetch_2y_yield_histories(
    lookback_days: int = 90,
    pair: str = "EURUSD",
) -> Optional[Tuple[Dict[str, float], Dict[str, float]]]:
    """
    Stáhne historii US 2Y a 2Y výnosů pro Base měnu za posledních N dní.

    Vrací (us_2y_dict, base_2y_dict) kde klíče jsou 'YYYY-MM-DD' a hodnoty jsou procenta.
    """
    logger.info(f"Stahuji Quote 2Y a Base 2Y výnosy pro {pair}...")

    # Policy rates pro dummy fallback
    policy_rates = {"GBPUSD": 5.25, "EURNZD": 5.50, "EURJPY": 0.25, "USDJPY": 0.25}

    if pair == "EURNZD":
        logger.info(f"Denní NZD dluhopisy nejsou přes FRED k dispozici. Aplikuji dummy policy rate pro udržení dynamického spreadu.")
        base_hist = await _fetch_de2y_ecb_fallback()
        if not base_hist:
            return None
        quote_hist = {d: policy_rates["EURNZD"] for d in base_hist.keys()}
        return quote_hist, base_hist

    # EURJPY: EUR je Base (DE 2Y), JPY je Quote
    if pair == "EURJPY":
        de_hist = await _fetch_de2y_ecb_fallback()
        jp_hist = await _fetch_fred_history("IRLTLT01JPM156N", lookback_days)
        if not de_hist:
            return None
        
        base_hist = de_hist
        # JPY 10Y je z FRED velmi řídký, tak ho raději obohatíme policy ratem,
        # pokud má méně než 5 společných dní, aby se Z-score nerozbilo.
        common_test = set(jp_hist.keys()) & set(de_hist.keys()) if jp_hist else set()
        if len(common_test) < 5:
            logger.info("JP výnosy nedostatečné — použiji dummy policy rate (0.25) pro JPY k udržení dynamiky.")
            quote_hist = {d: policy_rates["EURJPY"] for d in de_hist.keys()}
        else:
            quote_hist = jp_hist
            
        return quote_hist, base_hist


    # Pro většinu párů je Quote = USD (EURUSD, GBPUSD).
    # Pro USDJPY je Quote = JPY, ale používáme US 2Y jako proxy pro DXY.
    if pair == "USDJPY":
        # Pro USDJPY: USD je Base, JPY je Quote
        jp_hist = await _fetch_fred_history("IRLTLT01JPM156N", lookback_days)
        us_hist_for_base = await _fetch_fred_history("DGS2", lookback_days)
        if not us_hist_for_base:
            return None
            
        base_hist = us_hist_for_base
        common_test = set(jp_hist.keys()) & set(us_hist_for_base.keys()) if jp_hist else set()
        if len(common_test) < 5:
            logger.info("JP výnosy nedostatečné — použiji dummy policy rate (0.25) pro JPY k udržení dynamiky.")
            quote_hist = {d: policy_rates["USDJPY"] for d in us_hist_for_base.keys()}
        else:
            quote_hist = jp_hist
            
        return quote_hist, base_hist
    else:
        # Pro ostatní páry: USD je Quote
        quote_hist = await _fetch_fred_history("DGS2", lookback_days)
        if not quote_hist:
            logger.error("US 2Y výnosy nedostupné — bond spread scoring přeskočen.")
            return None
    
    if pair == "EURUSD":
        # DE 2Y primární zdroj
        base_hist = await _fetch_de2y_ecb_fallback()
        if not base_hist:
            return None
    elif pair == "GBPUSD":
        base_hist = await _fetch_uk2y_eodhd(lookback_days)
        if not base_hist:
            logger.info("UK 2Y výnosy nedostupné z EODHD — použiji dummy policy rate (5.25) pro GBP k udržení dynamiky.")
            base_hist = {d: policy_rates["GBPUSD"] for d in quote_hist.keys()}
    elif pair == "XAUUSD":
        base_hist = {d: 0.0 for d in quote_hist.keys()}
    else:
        logger.warning(f"Pro pár {pair} nejsou bond yields naimplementované.")
        return None

    # Logging spreadu
    common = set(quote_hist.keys()) & set(base_hist.keys())
    current_quote = quote_hist.get(max(quote_hist.keys())) if quote_hist else None
    current_base = base_hist.get(max(base_hist.keys())) if base_hist else None
    spread = current_quote - current_base if current_quote is not None and current_base is not None else None

    if spread is not None:
        logger.info(
            f"Bond yields: Quote={current_quote:.3f}%, Base={current_base:.3f}%, "
            f"spread={spread:.3f}% (n_common={len(common)})"
        )

    return quote_hist, base_hist
