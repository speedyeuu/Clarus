from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from loguru import logger
from typing import Optional
from config import get_settings
from scheduler.daily_update import run_daily_update

router = APIRouter()

async def _run_pipeline_safe():
    """Wrapper — zachytí výjimky a zapíše je do Railway logů."""
    try:
        logger.info("=== CRON: Pipeline start ===")
        await run_daily_update()
        logger.info("=== CRON: Pipeline dokončen — data zapsána do Supabase ===")
    except Exception as e:
        logger.error(f"=== CRON: Pipeline selhal: {e} ===")

@router.post("/update")
async def trigger_daily_update(
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Cron endpoint — volán z cron-job.org každý den."""
    settings = get_settings()

    token = (
        authorization.split("Bearer ")[-1]
        if authorization and "Bearer " in authorization
        else authorization
    )

    if token != settings.cron_secret:
        logger.warning("Cron zablokován — neplatný klíč.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    logger.info("Cron autorizován — spouštím pipeline.")
    # FastAPI nativně podporuje async funkce v BackgroundTasks
    background_tasks.add_task(_run_pipeline_safe)

    return {"status": "success", "message": "Pipeline spuštěn."}


