from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from loguru import logger
from typing import Optional
from config import get_settings
from scheduler.daily_update import run_daily_update

router = APIRouter()


def _get_active_pairs() -> list[str]:
    settings = get_settings()
    raw = getattr(settings, "active_pairs", "EURUSD")
    return [p.strip().upper() for p in raw.split(",") if p.strip()]


async def _run_pipeline_safe(pairs: list[str]):
    """Wrapper — spustí pipeline pro každý aktivní pár."""
    for pair in pairs:
        try:
            logger.info(f"=== CRON: Pipeline start [{pair}] ===")
            await run_daily_update(pair=pair)
            logger.info(f"=== CRON: Pipeline dokončen [{pair}] — data zapsána do Supabase ===")
        except Exception as e:
            logger.error(f"=== CRON: Pipeline selhal [{pair}]: {e} ===")


@router.post("/update")
async def trigger_daily_update(
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
    pair: Optional[str] = None,  # volitelně jen jeden pár
):
    """Cron endpoint — volán z cron-job.org každý den. Podporuje ?pair=GBPUSD pro konkrétní pár."""
    settings = get_settings()

    token = (
        authorization.split("Bearer ")[-1]
        if authorization and "Bearer " in authorization
        else authorization
    )

    if not settings.cron_secret or token != settings.cron_secret:
        logger.warning("Cron zablokován — neplatný nebo chybějící klíč (CRON_SECRET).")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Pokud je specifikován konkrétní pár, spustíme jen pro něj; jinak všechny aktivní
    pairs_to_run = [pair.upper()] if pair else _get_active_pairs()
    logger.info(f"Cron autorizován — spouštím pipeline pro páry: {pairs_to_run}")
    background_tasks.add_task(_run_pipeline_safe, pairs_to_run)

    return {"status": "success", "message": f"Pipeline spuštěn pro páry: {pairs_to_run}"}
