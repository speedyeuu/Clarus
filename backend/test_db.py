import asyncio
import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.client import get_supabase

async def test_conn():
    try:
        db = get_supabase()
        print("✅ Připojení k Supabase úspěšné.")
        
        res = db.table("weight_settings").select("*").execute()
        if res.data:
            print(f"✅ Načteny váhy: {res.data[0]['id']}")
        else:
            print("⚠️ Tabulky byly založeny, ale nenašly se výchozí váhy.")
            
        res_stats = db.table("normalization_stats").select("*").execute()
        if res_stats.data:
            print(f"✅ Načteno normalizačních záznamů: {len(res_stats.data)}")
        else:
            print("⚠️ Tabulka stats je prázdná.")
            
    except Exception as e:
        print(f"❌ Chyba připojení: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
