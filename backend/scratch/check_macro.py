import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    res = db.table("daily_scores").select("*").eq("pair", "GBPUSD").order("date", desc=True).limit(5).execute()
    for r in res.data:
        print(f"{r['date']} | gdp: {r.get('score_gdp')} | labor: {r.get('score_labor')} | inflation: {r.get('score_inflation')}")

asyncio.run(check())
