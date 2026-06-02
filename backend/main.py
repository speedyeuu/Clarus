from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

from api import scores, predictions, events, cron
from config import get_settings

# ============================================================
# AKTIVNÍ PÁRY — pipeline se spustí pro každý
# ============================================================
def get_active_pairs() -> list[str]:
    """Načte aktivní páry z configu (ACTIVE_PAIRS v .env, default EURUSD)."""
    settings = get_settings()
    raw = getattr(settings, "active_pairs", "EURUSD")
    return [p.strip().upper() for p in raw.split(",") if p.strip()]


# ============================================================
# SCHEDULER — denní pipeline ve 19:05 UTC (po close US trhů)
# ============================================================
scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_daily_update():
    """Wrapper pro denní pipeline — spustí se pro všechny aktivní páry."""
    from scheduler.daily_update import run_daily_update
    pairs = get_active_pairs()
    logger.info(f"=== SCHEDULER: Spouštím denní pipeline pro páry: {pairs} ===")
    for pair in pairs:
        try:
            logger.info(f"--- Pipeline: {pair} ---")
            await run_daily_update(pair=pair)
            logger.info(f"--- Pipeline: {pair} ✅ ---")
        except Exception as e:
            logger.error(f"--- Pipeline: {pair} ❌: {e} ---")
    logger.info("=== SCHEDULER: Všechny páry dokončeny ===")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    scheduler.add_job(
        _scheduled_daily_update,
        CronTrigger(hour=19, minute=5, timezone="UTC"),
        id="daily_update",
        replace_existing=True,
        misfire_grace_time=600,   # toleruje 10 min zpoždění (server sleep na free tier)
    )
    scheduler.start()
    next_run = scheduler.get_job("daily_update").next_run_time
    logger.info(f"Server started. Scheduler aktivní — příští pipeline: {next_run}")

    yield

    # --- Shutdown ---
    scheduler.shutdown(wait=False)
    logger.info("Server stopped")


app = FastAPI(
    title="Clarus API",
    description="Backend pro Clarus – fundamentální scoring EUR/USD páru",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://clarus-production.up.railway.app",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routery
app.include_router(scores.router,       prefix="/api/score",        tags=["Scores"])
app.include_router(predictions.router,  prefix="/api/predictions",  tags=["Predictions"])
app.include_router(events.router,       prefix="/api/events",       tags=["Events"])
app.include_router(cron.router,         prefix="/api/cron",         tags=["Cron"])


@app.get("/health")
async def health_check():
    job = scheduler.get_job("daily_update")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {
        "status": "ok",
        "version": "1.0.0",
        "scheduler": "running" if scheduler.running else "stopped",
        "next_pipeline": next_run,
    }
