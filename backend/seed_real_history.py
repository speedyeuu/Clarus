import asyncio
from loguru import logger
import sys
import os

# Povolí spouštění z terminálu
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import get_settings
from collectors.price import fetch_historical_ohlc
from collectors.cot import fetch_cot_data
from collectors.bond_yields import fetch_2y_yield_histories
from scheduler.daily_update import run_daily_update

def get_active_pairs() -> list[str]:
    """Načte aktivní páry z configu."""
    settings = get_settings()
    raw = getattr(settings, "active_pairs", "EURUSD")
    return [p.strip().upper() for p in raw.split(",") if p.strip()]

async def seed_history():
    """
    Inicializační skript pro stažení historie (cen, COT, FRED).
    Navíc spustí první denní pipeline pro všechny páry.
    """
    logger.info("=== Spouštím inicializaci historie pro Clarus ===")
    
    pairs = get_active_pairs()
    logger.info(f"Nalezeny aktivní páry k inicializaci: {pairs}")
    
    for pair in pairs:
        logger.info(f"\n--- Stahování historie pro pár {pair} ---")
        
        # 1. Ceny (pro trend indikátor a technickou analýzu)
        logger.info("Stahuji historii cen (OHLC)...")
        await fetch_historical_ohlc(days=90, pair=pair)
        
        # 2. COT reporty
        logger.info("Stahuji COT reporty...")
        await fetch_cot_data(pair=pair)
        
        # 3. FRED/ECB výnosy dluhopisů
        logger.info("Stahuji historii výnosů dluhopisů (FRED/ECB)...")
        await fetch_2y_yield_histories(lookback_days=90, pair=pair)
        
        # 4. První spuštění pipeline pro aktuální skóre
        logger.info(f"Spouštím prvotní daily update pro {pair}...")
        try:
            await run_daily_update(pair=pair)
            logger.info(f"Inicializace pro {pair} úspěšně dokončena. ✅")
        except Exception as e:
            logger.error(f"Daily update pro {pair} selhal: {e} ❌")
            
    logger.info("\n=== Inicializace historie je kompletní! ===")
    logger.info("Nyní můžete spustit API server: python3 -m uvicorn main:app --reload")

if __name__ == "__main__":
    asyncio.run(seed_history())
