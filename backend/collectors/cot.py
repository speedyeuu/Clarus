import httpx
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel

class COTData(BaseModel):
    base_net_position: int
    quote_net_position: int
    base_history_52w: List[int]
    quote_history_52w: List[int]

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

async def fetch_cot_data(pair: str = "EURUSD") -> Optional[COTData]:
    """
    Stáhne páteční COT (Commitment of Traders) report pro danou měnu a Dolar najednou.
    Vrací dnešní pozici a 52-týdenní historii ke zkalibrovaní extrémů.
    """
    logger.info(f"Stahuji čerstvý COT report z vládních serverů CFTC.gov pro {pair}...")
    
    CFTC_MAP = {
        "EUR": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
        "GBP": "BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE",
        "JPY": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
        "AUD": "AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "NZD": "NEW ZEALAND DOLLAR - CHICAGO MERCANTILE EXCHANGE",
        "XAU": "GOLD - COMMODITY EXCHANGE INC.",
        "USD": "USD INDEX - ICE FUTURES U.S."
    }

    base = pair[:3]
    quote = pair[3:]

    base_cftc_name = CFTC_MAP.get(base, CFTC_MAP["EUR"])
    quote_cftc_name = CFTC_MAP.get(quote, CFTC_MAP["USD"])
    
    base_history = await fetch_cftc_symbol_data(base_cftc_name, 52)
    quote_history = await fetch_cftc_symbol_data(quote_cftc_name, 52)
    
    if not base_history or not quote_history:
        logger.warning("CFTC vrátil prázdná data. Páteční COT report zřejmě ještě nevyšel nebo probíhá oprava serverů.")
        return None
        
    return COTData(
        base_net_position=base_history[0],
        quote_net_position=quote_history[0],
        base_history_52w=base_history,
        quote_history_52w=quote_history
    )
