import asyncio
from backend.scheduler.daily_update import run_daily_update

async def main():
    await run_daily_update(pair="GBPUSD")

if __name__ == "__main__":
    asyncio.run(main())
