"""
vix.py
------
Stahuje VIX (CBOE Volatility Index) z FRED (série VIXCLS).

VIX a EUR/USD korelace:
  - VIX vysoký (> 20-25) = tržní strach = risk-off = USD safe haven = EUR/USD klesá
  - VIX nízký (< 15) = klid = risk-on = EUR může posilovat

Normalizace: 90denní Z-score, invertovaný.
  - Z-score +2 (VIX extrémně vysoký) → score -6.66 (bearish EUR)
  - Z-score -2 (VIX extrémně nízký) → score +6.66 (bullish EUR)
  - Z-score 0 (VIX na svém průměru) → score 0 (neutrální)
"""

import httpx
from loguru import logger
from typing import Optional
from datetime import date, timedelta
import statistics


async def fetch_vix_score(lookback_days: int = 90) -> Optional[float]:
    """
    Stáhne historii VIX z FRED a vrátí normalizované skóre na škále -10 až +10.

    Vrací None pokud data nejsou dostupná.
    """
    history = await _fetch_vix_history(lookback_days)
    if not history or len(history) < 5:
        return None

    values = list(history.values())
    current_vix = values[-1]

    mean_v = statistics.mean(values)
    std_v = statistics.stdev(values) if len(values) > 1 else 1.0
    std_v = max(std_v, 0.01)

    z_score = (current_vix - mean_v) / std_v

    # Invertujeme: vysoký VIX = strach = bearish EUR = záporné skóre
    raw_score = -z_score * 3.33
    score = float(max(-10.0, min(10.0, raw_score)))

    logger.info(
        f"VIX: current={current_vix:.2f}, mean_90d={mean_v:.2f}, std={std_v:.2f} "
        f"→ z={z_score:.2f} → score={score:.4f}"
    )
    return score


async def fetch_vix_current() -> Optional[float]:
    """Vrátí aktuální VIX hodnotu (číslo, ne skóre)."""
    history = await _fetch_vix_history(10)
    if not history:
        return None
    return list(history.values())[-1]


async def _fetch_vix_history(lookback_days: int) -> dict:
    """
    Stáhne historii VIX z FRED (série VIXCLS) za posledních N dní.
    Vrací dict {YYYY-MM-DD: float}.
    """
    start = (date.today() - timedelta(days=lookback_days)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd={start}"

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning(f"FRED VIXCLS: HTTP {r.status_code}")
                return {}

            text = r.text.strip()
            if "<html" in text.lower():
                logger.warning("FRED VIXCLS: vrátil HTML místo CSV (rate limit)")
                return {}

            result = {}
            lines = text.split("\n")[1:]
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) == 2:
                    val_str = parts[1].strip()
                    if val_str and val_str not in (".", "NA", ""):
                        try:
                            result[parts[0].strip()] = float(val_str)
                        except ValueError:
                            pass

            logger.info(f"FRED VIXCLS: staženo {len(result)} záznamů od {start}")
            return result

    except Exception as e:
        logger.warning(f"VIX fetch error: {e}")
        return {}
