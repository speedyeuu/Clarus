import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    pairs = ["EURUSD", "GBPUSD", "USDJPY", "EURNZD", "EURJPY", "XAUUSD"]
    for p in pairs:
        res = db.table("daily_scores").select("date", count="exact").eq("pair", p).execute()
        print(f"{p}: {res.count} records")

asyncio.run(check())
