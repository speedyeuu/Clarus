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
# SCHEDULER — interní záloha (primární trigger je cron-job.org)
# ============================================================
# Cron-job.org volá /api/cron/update každý den v 21:00 CET.
# Interní scheduler slouží jako záloha pro případ výpadku cron-job.org.
# 19:00 UTC = 21:00 CEST (léto, UTC+2) = primární letní čas
# V zimě (CET, UTC+1) je 21:00 CET = 20:00 UTC → záloha běží hodinu dřív,
# ale to nevadí — cron-job.org je primár a pipeline je idempotentní (upsert).
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


async def _cold_start_catchup():
    """
    Cold-start detekce: spustí se 15 sekund po startu serveru.
    Zkontroluje, zda dnes již pipeline proběhla (záznam v daily_scores).
    Pokud ne (např. server restartoval po 19:00 UTC), spustí ji.
    Tím se předejde mezerám v datech po Railway deploy/restartu.
    """
    import asyncio
    from datetime import date
    from db.client import get_supabase

    await asyncio.sleep(15)  # Počkáme 15s na plný startup

    try:
        db = get_supabase()
        today = date.today().isoformat()
        pairs = get_active_pairs()

        missing_pairs = []
        for pair in pairs:
            res = (
                db.table("daily_scores")
                .select("date")
                .eq("pair", pair)
                .eq("date", today)
                .limit(1)
                .execute()
            )
            if not res.data:
                missing_pairs.append(pair)

        if missing_pairs:
            logger.warning(
                f"Cold-start: Chybí dnešní pipeline výsledky pro páry: {missing_pairs}. "
                f"Spouštím catch-up pipeline..."
            )
            await _scheduled_daily_update()
        else:
            logger.info(f"Cold-start: Pipeline pro všechny páry dnes ({today}) již proběhla — OK.")
    except Exception as e:
        logger.warning(f"Cold-start check selhal (nezastaví server): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    scheduler.add_job(
        _scheduled_daily_update,
        CronTrigger(hour=19, minute=0, timezone="UTC"),  # 19:00 UTC = 21:00 CEST (záloha za cron-job.org)
        id="daily_update",
        replace_existing=True,
        misfire_grace_time=3600,  # toleruje 1h zpoždění (pokryje restart i free tier sleep)
        max_instances=1,          # blokuje paralelní běh, pokud předchozí pipeline ještě neskončila
        coalesce=True,            # pokud scheduler zmeškal více spuštění (restart), spustí jen jednou
    )
    scheduler.start()
    next_run = scheduler.get_job("daily_update").next_run_time
    logger.info(f"Server started. Scheduler aktivní (záloha) — příští pipeline: {next_run}")

    # Spustit cold-start detekci v pozadí
    asyncio.create_task(_cold_start_catchup())

    yield

    # --- Shutdown ---
    scheduler.shutdown(wait=False)
    logger.info("Server stopped")


from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title="Clarus API",
    description="Backend pro Clarus – fundamentální scoring EUR/USD páru",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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
