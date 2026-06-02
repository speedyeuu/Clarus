import asyncio
from dotenv import load_dotenv

load_dotenv()

from backend.scheduler.daily_update import run_daily_update

if __name__ == "__main__":
    asyncio.run(run_daily_update(pair="USDJPY"))
