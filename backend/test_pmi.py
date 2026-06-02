from db.client import get_supabase

db = get_supabase()
res = db.table("indicator_readings").select("*").eq("pair", "EURUSD").execute()
for r in res.data:
    if 'pmi' in str(r.get('indicator_name', '')).lower():
        print(r)
