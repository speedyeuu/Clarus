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


async def _fetch_de2y_ecb_fallback() -> Optional[float]:
    """
    Záloha pro DE 2Y výnos přes ECB SDMX yield curve dataset.
    Vrací aktuální hodnotu nebo None.
    """
    url = (
        "https://data-api.ecb.europa.eu/service/data/"
        "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y"
        "?lastNObservations=5"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers={"Accept": "text/csv"})
            if r.status_code == 200 and "<html" not in r.text.lower():
                import csv
                from io import StringIO
                reader = csv.DictReader(StringIO(r.text))
                for row in reader:
                    val = row.get("OBS_VALUE", "").strip()
                    if val:
                        result = float(val)
                        logger.info(f"ECB YC DE 2Y (fallback): {result:.3f}%")
                        return result
    except Exception as e:
        logger.warning(f"ECB YC DE 2Y fallback failed: {e}")
    return None


async def _fetch_uk2y_eodhd(lookback_days: int = 90) -> Dict[str, float]:
    """
    Stáhne historii UK 2Y Gilts z EODHD (ticker GB2Y.GBOV).
    Vrací dict {YYYY-MM-DD: float_hodnota}.
    """
    settings = get_settings()
    if not settings.eodhd_api_key or settings.eodhd_api_key == "your-eodhd-key":
        logger.error("EODHD API klíč není nastaven pro bond_yields!")
        return {}

    url = f"https://eodhd.com/api/eod/GB2Y.GBOV?api_token={settings.eodhd_api_key}&fmt=json&limit={lookback_days}&period=d"
    
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
        logger.warning(f"Error fetching UK 2Y from EODHD: {e}")
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

    if pair == "EURNZD":
        logger.warning(f"Denní NZD dluhopisy nejsou přes FRED k dispozici. Použije se automaticky fallback na úrokové sazby centrálních bank.")
        return None

    # EURJPY: EUR je Base (DE 2Y), JPY je Quote — zpracujeme samostatně dříve než
    # začneme stahovat DGS2 (USD), který pro EURJPY nepotřebujeme.
    if pair == "EURJPY":
        de_hist = await _fetch_fred_history("IRDE2YD156N", lookback_days)
        jp_hist = await _fetch_fred_history("IRLTLT01JPM156N", lookback_days)
        if not de_hist or not jp_hist:
            logger.error("DE nebo JP výnosy nedostupné — bond spread scoring přeskočen pro EURJPY.")
            return None
        quote_hist = jp_hist
        base_hist = de_hist
        common = set(quote_hist.keys()) & set(base_hist.keys())
        if len(common) < 5:
            logger.warning(f"Příliš málo společných dní pro EURJPY bond yields ({len(common)}).")
        current_quote = quote_hist.get(max(quote_hist.keys()))
        current_base = base_hist.get(max(base_hist.keys()))
        spread = current_quote - current_base if current_quote and current_base else None
        if spread is not None:
            logger.info(
                f"EURJPY Bond yields: JP 2Y={current_quote:.3f}%, DE 2Y={current_base:.3f}%, "
                f"spread={spread:.3f}% (n_common={len(common)})"
            )
        return quote_hist, base_hist


    # Pro většinu párů je Quote = USD (EURUSD, GBPUSD).
    # Pro USDJPY je Quote = JPY, ale používáme US 2Y jako proxy pro DXY.
    if pair == "USDJPY":
        # Pro USDJPY: USD je Base, JPY je Quote
        # quote_hist = JP yields, base_hist = US yields
        jp_hist = await _fetch_fred_history("IRLTLT01JPM156N", lookback_days)
        us_hist_for_base = await _fetch_fred_history("DGS2", lookback_days)
        if not jp_hist or not us_hist_for_base:
            logger.error("JP nebo US výnosy nedostupné — bond spread scoring přeskočen.")
            return None
        quote_hist = jp_hist
        base_hist = us_hist_for_base
    else:
        # Pro ostatní páry: USD je Quote
        quote_hist = await _fetch_fred_history("DGS2", lookback_days)
        if not quote_hist:
            logger.error("US 2Y výnosy nedostupné — bond spread scoring přeskočen.")
            return None
    
    if pair == "EURUSD":
        # DE 2Y (primární zdroj: FRED IRDE2YD156N)
        base_hist = await _fetch_fred_history("IRDE2YD156N", lookback_days)

        # DE 2Y fallback: ECB SDMX
        if not base_hist:
            logger.warning("DE 2Y z FRED nedostupné, zkouším ECB SDMX fallback...")
            de_val = await _fetch_de2y_ecb_fallback()
            if de_val is not None:
                base_hist = {d: de_val for d in quote_hist.keys()}
                logger.info(f"DE 2Y ECB fallback: {de_val:.3f}% aplikováno na {len(base_hist)} dní Quote historie")
            else:
                logger.error("DE 2Y výnosy nedostupné ani z ECB — bond spread scoring přeskočen.")
                return None
    elif pair == "GBPUSD":
        base_hist = await _fetch_uk2y_eodhd(lookback_days)
        if not base_hist:
            logger.error("UK 2Y výnosy nedostupné z EODHD — bond spread scoring přeskočen.")
            return None
    elif pair == "XAUUSD":
        # Zlato (XAU) nenese žádný úrok (yield = 0.0%)
        # Vracíme nulový výnos pro všechny dny, pro které máme USD historii
        base_hist = {d: 0.0 for d in quote_hist.keys()}
        logger.info(f"Aplikován nulový výnos (0.0%) pro zlato na {len(base_hist)} dní Quote historie.")
    else:
        logger.warning(f"Pro pár {pair} nejsou bond yields naimplementované. Používám empty spread.")
        return None



    # Zkontrolujeme dostatek překrývajících se dní pro Z-score
    common = set(quote_hist.keys()) & set(base_hist.keys())
    if len(common) < 5:
        logger.warning(
            f"Příliš málo společných dní pro bond yields ({len(common)}) — "
            f"Z-score normalizace nebude přesná."
        )

    current_quote = quote_hist.get(max(quote_hist.keys()))
    current_base = base_hist.get(max(base_hist.keys()))
    spread = current_quote - current_base if current_quote and current_base else None

    if spread is not None:
        logger.info(
            f"Bond yields: Quote 2Y={current_quote:.3f}%, Base 2Y={current_base:.3f}%, "
            f"spread={spread:.3f}% (n_common={len(common)})"
        )

    return quote_hist, base_hist
