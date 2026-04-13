import httpx
from datetime import datetime
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel

class COTData(BaseModel):
    eur_net_position: int
    dxy_net_position: int
    eur_history_52w: List[int]
    dxy_history_52w: List[int]

# CFTC SODA API (Socrata) - Public Government Open Data, no API Key needed!
CFTC_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

async def fetch_cftc_symbol_data(market_name: str, weeks: int = 52) -> List[int]:
    """
    Získá historii COT dat (Non-Commercial Long vs Short) pro daný symbol 
    přímo z amerického vládního reportu (CFTC REST API).
    """
    # Konstrukce SoQL dotazu – omezíme to rovnou na "N" posledních pátků
    params = {
        "$where": f"market_and_exchange_names='{market_name}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(weeks)
    }
    
    net_positions = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(CFTC_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            for row in data:
                # Rozdíl mezi velkými spekulanty co sází na růst (Long) a pokles (Short)
                long_pos = int(row.get("noncomm_positions_long_all", 0))
                short_pos = int(row.get("noncomm_positions_short_all", 0))
                net = long_pos - short_pos
                net_positions.append(net)
                
            return net_positions
    except Exception as e:
        logger.error(f"Chyba při stahování vládních dat CFTC pro {market_name}: {e}")
        return []

async def fetch_cot_data() -> Optional[COTData]:
    """
    Stáhne páteční COT (Commitment of Traders) report pro Euro i Dolar najednou.
    Vrací dnešní pozici a 52-týdenní historii ke zkalibrovaní extrémů.
    """
    logger.info("Stahuji čerstvý COT report z vládních serverů CFTC.gov...")
    
    # "EURO FX - CHICAGO MERCANTILE EXCHANGE"
    # "USD INDEX - ICE FUTURES U.S." (Změněno v 2022 z U.S. DOLLAR INDEX)
    
    eur_history = await fetch_cftc_symbol_data("EURO FX - CHICAGO MERCANTILE EXCHANGE", 52)
    dxy_history = await fetch_cftc_symbol_data("USD INDEX - ICE FUTURES U.S.", 52)
    
    if not eur_history or not dxy_history:
        logger.warning("CFTC vrátil prázdná data. Páteční COT report zřejmě ještě nevyšel nebo probíhá oprava serverů.")
        return None
        
    return COTData(
        eur_net_position=eur_history[0],  # Ten nultý element je nejčerstvější dnešní!
        dxy_net_position=dxy_history[0],
        eur_history_52w=eur_history,      # Celé pole historie (pro výpočet 80/20 percentilu extrémů)
        dxy_history_52w=dxy_history
    )
