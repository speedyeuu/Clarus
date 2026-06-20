import asyncio
from db.client import get_supabase

async def check():
    db = get_supabase()
    res = db.table("daily_scores").select("*").limit(5).execute()
    for row in res.data:
        print(row)

asyncio.run(check())
