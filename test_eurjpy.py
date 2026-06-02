import asyncio
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from backend.scheduler.daily_update import run_daily_update
from loguru import logger

async def test_eurjpy():
    logger.info("Spouštím testovací run_daily_update pro pár EURJPY...")
    await run_daily_update("EURJPY")
    logger.info("Testovací run_daily_update dokončen.")

if __name__ == "__main__":
    asyncio.run(test_eurjpy())
