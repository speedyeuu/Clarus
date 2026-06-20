import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scheduler.daily_update import run_daily_update

async def run():
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "EURNZD", "EURJPY", "XAUUSD"]
    for pair in pairs:
        print(f"Spouštím update pro {pair}...")
        try:
            await run_daily_update(pair)
            print(f"Hotovo pro {pair}")
        except Exception as e:
            print(f"Chyba u {pair}: {e}")

if __name__ == "__main__":
    asyncio.run(run())
