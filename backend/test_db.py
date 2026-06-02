from db.client import get_supabase

db = get_supabase()
res = db.table("daily_scores").select("*").eq("pair", "GBPUSD").execute()
print(res.data)
