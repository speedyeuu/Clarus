import httpx
from io import StringIO
from loguru import logger
from typing import Optional
from pydantic import BaseModel

class EuriborSignal(BaseModel):
    implied_rate: float          # Implikovaná sazba z trhů (nebo €STR jako proxy)
    current_ecb_rate: float      # Skutečná aktuální sazba ECB (deposit facility)
    prob_cut: float              # Pravděpodobnost snížení sazby
    prob_hike: float             # Pravděpodobnost zvýšení sazby
    prob_hold: float             # Pravděpodobnost ponechání sazby
    source: str = "ecb_estr"    # Zdroj dat


def _calculate_probabilities(implied_rate: float, current_ecb_rate: float) -> tuple[float, float, float]:
    """
    Vypočítá pravděpodobnosti pohybu ECB sazby z odchylky implikované sazby.
    
    Logika:
      divergence = implied_rate - current_rate
      Pokud je implied 2.00 a current 2.25 → divergence = -0.25 → 100% šance na cut
      Pokud je implied 2.30 a current 2.25 → divergence = +0.05 → 20% šance na hike
    
    Jeden krok ECB = 25 bps (0.25 procentního bodu).
    """
    divergence = implied_rate - current_ecb_rate

    prob_cut = 0.0
    prob_hike = 0.0
    prob_hold = 1.0

    if divergence <= -0.25:
        # Implikováno jedno nebo více snížení
        prob_cut = min(1.0, abs(divergence) / 0.25)
        prob_hold = max(0.0, 1.0 - prob_cut)
    elif divergence < 0:
        # Částečná pravděpodobnost snížení
        prob_cut = abs(divergence) / 0.25
        prob_hold = 1.0 - prob_cut
    elif divergence >= 0.25:
        # Implikováno jedno nebo více zvýšení
        prob_hike = min(1.0, divergence / 0.25)
        prob_hold = max(0.0, 1.0 - prob_hike)
    elif divergence > 0:
        # Částečná pravděpodobnost zvýšení
        prob_hike = divergence / 0.25
        prob_hold = 1.0 - prob_hike

    return round(prob_cut, 2), round(prob_hike, 2), round(prob_hold, 2)


async def _fetch_estr_rate() -> Optional[float]:
    """
    Stáhne €STR (Euro Short-Term Rate) z ECB SDMX API.
    €STR je overnight sazba ECB - velmi blízká deposit facility rate.
    
    Zdroj: ECB Data API (bez klíče, zdarma)
    Endpoint: https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT
    """
    url = (
        "https://data-api.ecb.europa.eu/service/data/EST/"
        "B.EU000A2X2A25.WT?lastNObservations=1"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"Accept": "text/csv"})
            if response.status_code != 200:
                logger.warning(f"ECB €STR API vrátilo status {response.status_code}")
                return None

            # Parsování CSV: KEY,FREQ,...,TIME_PERIOD,OBS_VALUE,...
            import csv
            reader = csv.DictReader(StringIO(response.text))
            for row in reader:
                val_str = row.get("OBS_VALUE", "").strip()
                if val_str:
                    rate = float(val_str)
                    logger.info(f"ECB €STR: {rate:.3f}%")
                    return rate

    except Exception as e:
        logger.warning(f"Chyba při stahování €STR z ECB: {e}")

    return None


async def _fetch_euribor3m_fred() -> Optional[float]:
    """
    Primární zdroj: Euribor 3M z FRED (Federal Reserve St. Louis).
    Serie ID: IR3TIB01EZM156N — Euribor 3M Monthly Average
    FRED vrací data bezplatně bez API klíče.
    """
    from datetime import date, timedelta
    start = (date.today() - timedelta(days=90)).isoformat()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=IR3TIB01EZM156N&cosd={start}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(f"FRED Euribor 3M vrátilo status {response.status_code}")
                return None
            lines = response.text.strip().split("\n")
            if len(lines) < 2:
                return None
            # Vezme poslední platný řádek (nejnovější data)
            for line in reversed(lines[1:]):
                parts = line.strip().split(",")
                if len(parts) == 2 and parts[1].strip() not in (".", "", "NA"):
                    rate = float(parts[1].strip())
                    logger.info(f"Euribor 3M (FRED IR3TIB01EZM156N): {rate:.3f}%")
                    return rate
    except Exception as e:
        logger.warning(f"Chyba při stahování Euribor 3M z FRED: {e}")

    return None


async def fetch_euribor_signal(current_ecb_rate: float = 3.25, pair: str = "EURUSD") -> Optional[EuriborSignal]:
    """
    Hlavní vstupní bod pro Euribor OIS signál.
    Funguje pouze pro EURUSD.
    
    Interpretace:
    - Euribor 3M = tržní sazba pro 3měsíční mezibankovní půjčky v EUR
    - Pokud je Euribor 3M níže než aktuální ECB sazba → trh čeká snížení
    - Divergence o 0.25% = 100% šance na jeden pohyb (cut nebo hike)
    """
    if pair != "EURUSD":
        logger.info(f"OIS Signál (Euribor) je podporován jen pro EURUSD, přeskočeno pro {pair}.")
        return None
        
    logger.info("Zjišťuji tržní očekávání na sazby (Euribor/OIS)...")

    # --- 1. Primární: Euribor 3M z FRED ---
    euribor_3m = await _fetch_euribor3m_fred()
    if euribor_3m is not None:
        prob_cut, prob_hike, prob_hold = _calculate_probabilities(euribor_3m, current_ecb_rate)
        logger.info(
            f"Euribor Signal [FRED] (Euribor 3M={euribor_3m:.3f}%, ECB={current_ecb_rate:.2f}%) "
            f"→ Cut:{prob_cut:.0%} Hold:{prob_hold:.0%} Hike:{prob_hike:.0%}"
        )
        return EuriborSignal(
            implied_rate=round(euribor_3m, 3),
            current_ecb_rate=current_ecb_rate,
            prob_cut=prob_cut,
            prob_hike=prob_hike,
            prob_hold=prob_hold,
            source="fred_euribor3m",
        )

    # --- 2. Záložní: €STR z ECB SDMX ---
    estr = await _fetch_estr_rate()
    if estr is not None:
        # €STR je overnight sazba — přidáme typický spread overnight→3M (~7 bps)
        euribor_proxy = estr + 0.07
        prob_cut, prob_hike, prob_hold = _calculate_probabilities(euribor_proxy, current_ecb_rate)
        logger.info(
            f"Euribor Signal [ECB €STR proxy] (proxy={euribor_proxy:.3f}%, ECB={current_ecb_rate:.2f}%) "
            f"→ Cut:{prob_cut:.0%} Hold:{prob_hold:.0%} Hike:{prob_hike:.0%}"
        )
        return EuriborSignal(
            implied_rate=round(euribor_proxy, 3),
            current_ecb_rate=current_ecb_rate,
            prob_cut=prob_cut,
            prob_hike=prob_hike,
            prob_hold=prob_hold,
            source="ecb_estr_proxy",
        )

    # --- 3. Fallback ---
    logger.error("Nepodařilo se stáhnout žádná tržní data pro Euribor/€STR signal. Vracím None.")
    return None
