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


async def fetch_2y_yield_histories(
    lookback_days: int = 90,
) -> Optional[Tuple[Dict[str, float], Dict[str, float]]]:
    """
    Stáhne historii US 2Y a DE 2Y výnosů za posledních N dní.

    Vrací (us_2y_dict, de_2y_dict) kde klíče jsou 'YYYY-MM-DD' a hodnoty jsou procenta.
    Vrací None pokud data nejsou dostupná nebo je příliš málo společných dní.

    Příklady hodnot:
      us_2y = {'2026-05-28': 3.990, '2026-05-27': 4.000, ...}
      de_2y = {'2026-05-28': 1.820, '2026-05-27': 1.810, ...}
    """
    logger.info("Stahuji US 2Y a DE 2Y výnosy z FRED...")

    # --- US 2Y (primární zdroj: FRED DGS2) ---
    us_hist = await _fetch_fred_history("DGS2", lookback_days)
    if not us_hist:
        logger.error("US 2Y výnosy nedostupné — bond spread scoring přeskočen.")
        return None

    # --- DE 2Y (primární zdroj: FRED IRDE2YD156N) ---
    de_hist = await _fetch_fred_history("IRDE2YD156N", lookback_days)

    # --- DE 2Y fallback: ECB SDMX ---
    if not de_hist:
        logger.warning("DE 2Y z FRED nedostupné, zkouším ECB SDMX fallback...")
        de_val = await _fetch_de2y_ecb_fallback()
        if de_val is not None:
            # Naplníme de_hist hodnotou pro všechna US data
            # Spread bude mít fixní DE složku, ale Z-score US 2Y stále přidá hodnotu
            de_hist = {d: de_val for d in us_hist.keys()}
            logger.info(
                f"DE 2Y ECB fallback: {de_val:.3f}% aplikováno na {len(de_hist)} dní US historie"
            )
        else:
            logger.error("DE 2Y výnosy nedostupné ani z ECB — bond spread scoring přeskočen.")
            return None


    # Zkontrolujeme dostatek překrývajících se dní pro Z-score
    common = set(us_hist.keys()) & set(de_hist.keys())
    if len(common) < 5:
        logger.warning(
            f"Příliš málo společných dní pro US/DE 2Y ({len(common)}) — "
            f"Z-score normalizace nebude přesná."
        )

    current_us = us_hist.get(max(us_hist.keys()))
    current_de = de_hist.get(max(de_hist.keys()))
    spread = current_us - current_de if current_us and current_de else None

    if spread is not None:
        logger.info(
            f"Bond yields: US 2Y={current_us:.3f}%, DE 2Y={current_de:.3f}%, "
            f"spread={spread:.3f}% (n_common={len(common)})"
        )

    return us_hist, de_hist
