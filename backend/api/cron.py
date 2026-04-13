from fastapi import APIRouter, Depends, HTTPException, Header
from loguru import logger
from typing import Optional
from config import get_settings
from scheduler.daily_update import run_daily_update
import asyncio

router = APIRouter()

@router.post("/update")
async def trigger_daily_update(authorization: Optional[str] = Header(None)):
    """
    Bezpečný endpoint pro spuštění denní aktualizace z cloudových časovačů.
    Vyžaduje např. Vercel Cron nebo službu cron-job.org, která pošle hlavičku Authorization: Bearer <TvojeTajneHeslo>
    """
    settings = get_settings()
    
    # 1. Zkontrolujeme bezpecnost
    # Pokud v hlavicce ulozili 'Bearer XYZ', vezmeme si jen XYZ
    token = authorization.split("Bearer ")[-1] if authorization and "Bearer " in authorization else authorization
    
    if token != settings.cron_secret:
         logger.warning("Spuštění Cronu bylo zablokováno – neplatný tajný klíč.")
         raise HTTPException(status_code=401, detail="Unauthorized Cron Execution")

    # 2. Spustime hlavni pipeline proces odděleně od vlákna, ať se neblokne připojení
    logger.info("Spouštím dálkově řízený cloudový daily update!")
    
    # Spustíme úlohu na pozadí pŕes asyncio create_task
    # Tím ušetříme timeout na cloud services (např Vercel odsekne script po 10s čakaní na response)
    asyncio.create_task(run_daily_update())
    
    return {"status": "success", "message": "Daily update trigger received and processing in background."}
