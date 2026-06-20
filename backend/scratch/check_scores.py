import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    res = db.table("daily_scores").select("date, pair, total_score").order("date", desc=True).limit(50).execute()
    for r in res.data:
        print(f"{r['date']} | {r['pair']} | {r['total_score']}")

asyncio.run(check())
