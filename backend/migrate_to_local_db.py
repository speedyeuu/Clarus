import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Načteme stávající konfiguraci z backend/.env (kde jsou cloudové přihlašovací údaje)
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

OLD_URL = os.getenv("SUPABASE_URL")
OLD_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not OLD_URL or not OLD_KEY or "supabase.co" not in OLD_URL:
    print("Chyba: V souboru backend/.env nebyly nalezeny platné údaje pro cloudový Supabase.")
    sys.exit(1)

print("--- PŘÍPRAVA MIGRACE DAT ---")
print(f"Zdrojová databáze (Cloud): {OLD_URL}")
print("-" * 30)

# Zeptáme se uživatele na údaje pro novou lokální databázi
new_url = input("Zadejte URL vaší nové databáze na Ubuntu (např. http://123.45.67.89:8001): ").strip()
new_key = input("Zadejte nový SERVICE_ROLE_KEY (vygenerovaný skriptem): ").strip()

if not new_url or not new_key:
    print("Chyba: Musíte zadat URL i klíč pro novou databázi.")
    sys.exit(1)

# Inicializace klientů
try:
    print("\nPřipojování ke cloudovému Supabase...")
    old_client = create_client(OLD_URL, OLD_KEY)
    
    print("Připojování k novému self-hosted Supabase...")
    new_client = create_client(new_url, new_key)
except Exception as e:
    print(f"Chyba při připojování: {e}")
    sys.exit(1)

# Seznam tabulek k migraci
TABLES = [
    "normalization_stats",
    "weight_settings",
    "indicator_readings",
    "daily_scores",
    "upcoming_events",
    "predictions",
    "autoresearch_log"
]

print("\nSpouštím migraci dat...")

for table in TABLES:
    print(f"\nMigruji tabulku: {table}...")
    try:
        # 1. Stažení dat ze staré databáze
        # Používáme limit 1000 pro případné stránkování, ale tabulky jsou malé
        res = old_client.table(table).select("*").execute()
        data = res.data
        
        if not data:
            print(f"-> Tabulka {table} je na cloudu prázdná, přeskakuji.")
            continue
            
        print(f"-> Nalezeno {len(data)} záznamů. Zapisuji do nové databáze...")
        
        # 2. Zápis do nové databáze
        # Používáme upsert, abychom přepsali případné duplicity
        new_client.table(table).upsert(data).execute()
        print(f"-> Tabulka {table} úspěšně migrována ({len(data)} záznamů).")
        
    except Exception as e:
        print(f"Chyba při migraci tabulky {table}: {e}")
        print("Ujistěte se, že jste v SQL editoru na novém serveru spustil soubory 001_initial.sql a 002_unique_constraints.sql!")

print("\n=== MIGRACE DOKONČENA ===")
print("Pokud vše proběhlo bez chyb, vaše data jsou na novém serveru.")
print("Nyní můžete v backend/.env změnit hodnoty na novou URL a nový klíč.")
