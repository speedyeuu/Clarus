import httpx
from loguru import logger
from typing import Optional
from pydantic import BaseModel
from config import get_settings

class EuriborSignal(BaseModel):
    implied_rate: float
    current_ecb_rate: float # Předpokládaná současná sazba
    prob_cut: float
    prob_hike: float
    prob_hold: float

async def fetch_euribor_signal(current_ecb_rate: float = 3.25) -> Optional[EuriborSignal]:
    """
    Snaží se získat implikovanou pravděpodobnost pohybu sazeb ECB z EODHD API.
    Jako proxy využíváme 3-Month Euribor Futures (symbol ER.EU, příp. konkrétní expirace jako ERH25.EU).
    
    Z futures ceny se dá odvodit předpokládaná úroková sazba: 100 - Cena_Future = Implikovaná Sazba.
    Pokud je například cena futures na 96.50, trh cení sazbu na 3.50%.
    Z této odchylky vůči současné sazbě potom Scoring Engine vypočítá pravděpodobnost (Cut, Hold).
    """
    settings = get_settings()
    if not settings.eodhd_api_key or settings.eodhd_api_key == "your-eodhd-key":
        logger.error("EODHD API klíč není nastaven!")
        return None

    # Místo live futures feedu můžeme stáhnout End-Of-Day pro symbol EURIBOR futures, 
    # pro demonstraci s EODHD
    # Symbol "ER.EU" může mít suffixy (nyní pseudo kód pre API feed)
    symbol = "ER.EU"
    url = f"https://eodhd.com/api/real-time/{symbol}?api_token={settings.eodhd_api_key}&fmt=json"
    
    try:
        logger.info("Fetching EURIBOR futures from EODHD API...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            # Pokud EOD nezná symbol nebo je token invalid, spadne (nebo vrati json error)
            data = response.json()
            
            # TODO: Přesný parsing záleží na tom odkud EOD bere ERH24 apod..
            # Zjednodušená logika pro Fázi 1:
            close_price = data.get("close")
            if not close_price or close_price == "NA":
                logger.warning(f"Nedostupná cena pro EURIBOR: {data}")
                return None
                
            close_price = float(close_price)
            implied_rate = 100.0 - close_price
            
            # Výpočet pravděpodobností – jedna změna o 0.25 (25 bps)
            # Odchylka = Implied Rate - Current Rate
            # Pokud je implied 3.00 a current 3.25 -> rate divergence je -0.25
            # To odpovídá 100% šanci na jeden rate cut.
            divergence = implied_rate - current_ecb_rate
            
            prob_cut = 0.0
            prob_hike = 0.0
            prob_hold = 1.0
            
            if divergence <= -0.25:
                prob_cut = 1.0
                prob_hold = 0.0
            elif divergence < 0:
                prob_cut = abs(divergence) / 0.25
                prob_hold = 1.0 - prob_cut
            elif divergence >= 0.25:
                prob_hike = 1.0
                prob_hold = 0.0
            elif divergence > 0:
                prob_hike = divergence / 0.25
                prob_hold = 1.0 - prob_hike

            return EuriborSignal(
                implied_rate=round(implied_rate, 3),
                current_ecb_rate=current_ecb_rate,
                prob_cut=round(prob_cut, 2),
                prob_hike=round(prob_hike, 2),
                prob_hold=round(prob_hold, 2),
            )
            
    except Exception as e:
        logger.error(f"Error fetching EURIBOR rates: {e}")
        return None
