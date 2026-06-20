import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    res = db.table("indicator_readings").select("indicator_name, date, raw_score").eq("pair", "GBPUSD").limit(5).execute()
    print("GBPUSD readings:")
    for r in res.data:
        print(r)

asyncio.run(check())
