import asyncio
import os
import sys

# Povolí spouštění z terminálu
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from db.client import get_supabase
from scoring.normalizer import get_normalization_stats
from scoring.indicators import score_ff_event

# Zjistíme zemi podle klíče indikátoru (stejná logika jako ve forex_factory.py)
COUNTRY_SUFFIX = {
    "us": "USD",
    "eu": "EUR",
    "uk": "GBP",
    "jpy": "JPY",
    "nzd": "NZD",
    "jp": "JPY"
}

RATE_TO_COUNTRY = {
    "fed_rate": "USD",
    "ecb_rate": "EUR",
    "boe_rate": "GBP",
    "boj_rate": "JPY",
    "rbnz_rate": "NZD",
    "rba_rate": "AUD",
    "boc_rate": "CAD",
    "xau_rate": "XAU"
}

async def backfill():
    db = get_supabase()
    pairs = ["GBPUSD", "USDJPY", "EURNZD", "EURJPY", "XAUUSD"]
    
    logger.info("Načítám historická data EURUSD z indicator_readings...")
    res = db.table("indicator_readings").select("*").eq("pair", "EURUSD").execute()
    
    if not res.data:
        logger.info("Žádná data pro EURUSD nenalezena.")
        return
        
    records_to_insert = []
    
    for row in res.data:
        # Původní hodnoty
        ind_key = row["indicator_name"]
        actual = row.get("actual")
        forecast = row.get("forecast")
        
        if actual is None or forecast is None:
            continue
            
        # Zjistit zemi
        country = None
        if ind_key in RATE_TO_COUNTRY:
            country = RATE_TO_COUNTRY[ind_key]
        else:
            parts = ind_key.split("_")
            if len(parts) > 1:
                suffix = parts[-1].lower()
                country = COUNTRY_SUFFIX.get(suffix, suffix.upper())
                
        if not country:
            logger.warning(f"Neznámá země pro indikátor {ind_key}")
            continue
            
        # Načíst statistiky pro výpočet skóre
        stats = await get_normalization_stats(ind_key)
        
        for pair in pairs:
            base_currency = pair[:3]
            quote_currency = pair[3:]
            
            # Je událost relevantní pro tento pár?
            if country != base_currency and country != quote_currency:
                continue
                
            # Logika inverze (kopie z daily_update.py)
            invert = False
            if country == base_currency:
                invert = False
                if "unemployment" in ind_key.lower(): invert = True
            elif country == quote_currency:
                invert = True
                if "unemployment" in ind_key.lower(): invert = False
                
            # Vypočítat nové skóre pro daný pár
            event_score = score_ff_event(str(actual), str(forecast), stats, invert=invert)
            
            # Vytvořit nový záznam
            new_record = row.copy()
            del new_record["id"] # odstraníme ID, ať se vytvoří nové
            del new_record["created_at"]
            new_record["pair"] = pair
            new_record["raw_score"] = event_score
            
            records_to_insert.append(new_record)
            
    if records_to_insert:
        logger.info(f"Vkládám {len(records_to_insert)} chybějících záznamů do indicator_readings...")
        # Vložit v batchích po 100
        for i in range(0, len(records_to_insert), 100):
            batch = records_to_insert[i:i+100]
            try:
                db.table("indicator_readings").upsert(batch, on_conflict="date,indicator_name,pair").execute()
            except Exception as e:
                logger.error(f"Chyba při vkládání: {e}")
        logger.info("Backfill dokončen.")
    else:
        logger.info("Nebyly nalezeny žádné záznamy k backfillu.")

if __name__ == "__main__":
    asyncio.run(backfill())
