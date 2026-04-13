"""
Komplexní testovací script pro EUR/USD Fundamental Analyzer.
Testuje všechna napojení: Supabase, ForexFactory, CFTC, Alpha Vantage, EODHD, MyFXBook, Gemini.
Spustit: python backend/test_all_apis.py
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from loguru import logger

# Přepneme logger do čistého konzolového módu
logger.remove()
logger.add(sys.stderr, format="<level>{level}</level> | {message}", colorize=True)

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

results = {}

# ─────────────────────────────────────────────────────────────
# TEST 1: Supabase
# ─────────────────────────────────────────────────────────────
async def test_supabase():
    print("\n══ TEST 1: Supabase připojení ══")
    try:
        from db.client import get_supabase
        db = get_supabase()
        result = db.table("daily_scores").select("id").limit(1).execute()
        count = len(result.data)
        print(f"{PASS} Supabase DB dostupná. Záznamy v daily_scores: {count}")
        results["supabase"] = True
    except Exception as e:
        print(f"{FAIL} Supabase selhalo: {e}")
        results["supabase"] = False

# ─────────────────────────────────────────────────────────────
# TEST 2: Forex Factory Calendar
# ─────────────────────────────────────────────────────────────
async def test_forex_factory():
    print("\n══ TEST 2: Forex Factory Calendar ══")
    try:
        from collectors.forex_factory import fetch_forex_factory_week
        events = await fetch_forex_factory_week()
        if len(events) > 0:
            print(f"{PASS} ForexFactory vrátil {len(events)} událostí tohoto týdne.")
            for ev in events[:3]:
                print(f"     → [{ev.country}] {ev.date.strftime('%m-%d')} - {ev.title} (Impact: {ev.impact})")
        else:
            print(f"{WARN} ForexFactory vrátil 0 událostí (možná víkend nebo prázdný týden).")
        results["forex_factory"] = True
    except Exception as e:
        print(f"{FAIL} ForexFactory selhalo: {e}")
        results["forex_factory"] = False

# ─────────────────────────────────────────────────────────────
# TEST 3: CFTC Open Data (COT - bez API klíče)
# ─────────────────────────────────────────────────────────────
async def test_cftc():
    print("\n══ TEST 3: CFTC.gov COT Report (vládní API) ══")
    try:
        from collectors.cot import fetch_cot_data
        cot = await fetch_cot_data()
        if cot:
            print(f"{PASS} CFTC COT stažen.")
            print(f"     → EUR Net Position: {cot.eur_net_position:+,} kontraktů")
            print(f"     → USD Index Net Position: {cot.dxy_net_position:+,} kontraktů")
            print(f"     → Historie: {len(cot.eur_history_52w)} týdnů EUR dat")
        else:
            print(f"{WARN} CFTC vrátilo prázdná data. Páteční COT report ještě nemusel vyjít.")
        results["cftc"] = True
    except Exception as e:
        print(f"{FAIL} CFTC selhalo: {e}")
        results["cftc"] = False

# ─────────────────────────────────────────────────────────────
# TEST 4: Alpha Vantage (Cena EUR/USD)
# ─────────────────────────────────────────────────────────────
async def test_alpha_vantage():
    print("\n══ TEST 4: Alpha Vantage (Cena EUR/USD) ══")
    try:
        from collectors.price import fetch_historical_ohlc
        df = await fetch_historical_ohlc(days=5)
        if df is not None and len(df) > 0:
            latest_close = df["close"].iloc[-1]
            print(f"{PASS} Alpha Vantage funguje. Staženo {len(df)} svíček.")
            print(f"     → Poslední cena EUR/USD: {latest_close:.5f}")
        else:
            print(f"{FAIL} Alpha Vantage vrátil prázdná data.")
            results["alpha_vantage"] = False
            return
        results["alpha_vantage"] = True
    except Exception as e:
        print(f"{FAIL} Alpha Vantage selhalo: {e}")
        results["alpha_vantage"] = False

# ─────────────────────────────────────────────────────────────
# TEST 5: EODHD (Makroekonomická data)
# ─────────────────────────────────────────────────────────────
async def test_eodhd():
    print("\n══ TEST 5: EODHD (Historická makro data) ══")
    try:
        from config import get_settings
        settings = get_settings()
        # Testujeme EUR/USD FOREX endpoint (funguje na EOD Historical plan $19.99)
        url = f"https://eodhd.com/api/eod/EURUSD.FOREX?api_token={settings.eodhd_api_key}&fmt=json&limit=5&period=d"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    print(f"{PASS} EODHD funguje! Vrátil {len(data)} EUR/USD svíček.")
                    print(f"     → Poslední: {data[-1].get('date')} close={data[-1].get('close')}")
                else:
                    print(f"{WARN} EODHD vrátil prázdný seznam.")
            else:
                print(f"{FAIL} EODHD HTTP {r.status_code}: {r.text[:150]}")
                results["eodhd"] = False
                return
        results["eodhd"] = True
    except Exception as e:
        print(f"{FAIL} EODHD selhalo: {e}")
        results["eodhd"] = False

# ─────────────────────────────────────────────────────────────
# TEST 6: MyFXBook (Retail Sentiment)
# ─────────────────────────────────────────────────────────────
async def test_myfxbook():
    print("\n══ TEST 6: MyFXBook Community Sentiment ══")
    try:
        from collectors.sentiment import fetch_retail_sentiment
        sentiment = await fetch_retail_sentiment()
        if sentiment:
            print(f"{PASS} MyFXBook funguje!")
            print(f"     → EUR/USD Long: {sentiment.long_pct*100:.1f}%")
            print(f"     → EUR/USD Short: {sentiment.short_pct*100:.1f}%")
            interpretation = "Dav kupuje → Kontraindikátor BEARISH pro EUR" if sentiment.long_pct > 0.6 else \
                           "Dav prodává → Kontraindikátor BULLISH pro EUR" if sentiment.short_pct > 0.6 else \
                           "Dav je neutrální"
            print(f"     → Interpretace: {interpretation}")
        else:
            print(f"{FAIL} MyFXBook vrátil prázdná data. Zkontroluj email/heslo v .env")
            results["myfxbook"] = False
            return
        results["myfxbook"] = True
    except Exception as e:
        print(f"{FAIL} MyFXBook selhalo: {e}")
        results["myfxbook"] = False

# ─────────────────────────────────────────────────────────────
# TEST 7: Google Gemini (AI Autoresearch)
# ─────────────────────────────────────────────────────────────
async def test_gemini():
    print("\n══ TEST 7: Google Gemini AI (Autoresearch) ══")
    try:
        from config import get_settings
        from google import genai
        from google.genai import types
        settings = get_settings()
        
        client = genai.Client(api_key=settings.gemini_api_key)
        # Použijeme listing modelů jako "ping" test - neskončí 429 pokud klíč funguje
        import httpx
        r = httpx.get(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash?key={settings.gemini_api_key}"
        )
        if r.status_code == 200:
            model_info = r.json()
            print(f"{PASS} Gemini API klíč funguje! Model: {model_info.get('displayName', 'Gemini')}")
            print(f"     → Input limit: {model_info.get('inputTokenLimit', '?')} tokenů")
            results["gemini"] = True
        else:
            print(f"{FAIL} Gemini API klíč neplatný: HTTP {r.status_code}")
            results["gemini"] = False
    except Exception as e:
        print(f"{FAIL} Gemini selhalo: {e}")
        results["gemini"] = False

# ─────────────────────────────────────────────────────────────
# TEST 8: Polymarket (Volné API bez klíče)
# ─────────────────────────────────────────────────────────────
async def test_polymarket():
    print("\n══ TEST 8: Polymarket Economics Sentiment ══")
    try:
        from collectors.polymarket import fetch_polymarket_economics
        markets = await fetch_polymarket_economics()
        if markets and len(markets) > 0:
            print(f"{PASS} Polymarket funguje. Staženo {len(markets)} aktivních trhů.")
            for m in markets[:3]:
                print(f"     → [{m.yes_probability*100:.0f}% YES] {m.title[:60]}")
        else:
            print(f"{WARN} Polymarket vrátil 0 trhů. Možná časový timeout nebo prázdný den.")
        results["polymarket"] = True
    except Exception as e:
        print(f"{FAIL} Polymarket selhalo: {e}")
        results["polymarket"] = False

# ─────────────────────────────────────────────────────────────
# FINÁLNÍ VÝSLEDKY
# ─────────────────────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  EUR/USD Fundamental Analyzer – Kompletní API Test")
    print("=" * 60)
    
    await test_supabase()
    await test_forex_factory()
    await test_cftc()
    await test_alpha_vantage()
    await test_eodhd()
    await test_myfxbook()
    await test_gemini()
    await test_polymarket()
    
    # Shrnutí
    print("\n" + "=" * 60)
    print("  VÝSLEDKY TESTŮ")
    print("=" * 60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = PASS if ok else FAIL
        print(f"  {status}  {name.upper()}")
    print(f"\n  Celkem: {passed}/{total} testů prošlo.")
    if passed == total:
        print("  🚀 VŠECHNA PŘIPOJENÍ FUNGUJÍ! Systém je READY TO GO!")
    else:
        print("  ⚠️  Některé testy selhaly. Zkontroluj detaily výše.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
