import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    res = db.table("daily_scores").select("date, total_score").eq("pair", "GBPUSD").order("date", desc=True).limit(18).execute()
    for r in res.data:
        print(f"GBPUSD | {r['date']} | {r['total_score']}")

asyncio.run(check())
