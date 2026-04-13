import asyncio
import os
import sys
import httpx
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from loguru import logger

# Nutné, aby to dokázalo přečíst složku \backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.client import get_supabase
from config import get_settings

# ─────────────────────────────────────────────────────────────
# FRED API - Federal Reserve Economic Data (Zdarma, bez klíče)
# Slouží ke kalibraci Z-Score statistik pro makroindikátory
# ─────────────────────────────────────────────────────────────
FRED_SERIES = {
    # Klíč v naší DB → FRED Series ID
    "inflation":       "CPIAUCSL",   # US CPI (All Urban Consumers)
    "core_inflation":  "CPILFESL",   # US Core CPI
    "gdp":             "GDP",        # US GDP
    "labor":           "PAYEMS",     # US Nonfarm Payrolls
    "unemployment":    "UNRATE",     # US Unemployment Rate
    "manufacturing":   "NAPM",       # ISM Manufacturing PMI
    "retail_sales":    "RSXFS",      # US Retail Sales
    "eu_inflation":    "CP0000EZ19M086NEST",  # EU CPI
    "eu_gdp":          "EURGDPQDSNAQ",        # EU GDP
}

async def fetch_fred_series(series_id: str, observation_start: str) -> pd.Series:
    """Stáhne historická data z FRED API (bez klíče, veřejné)."""
    # FRED CSV endpoint - vrací sloupec 'observation_date', ne 'DATE'
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&vintage_date={observation_start}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return pd.Series(dtype=float)
            from io import StringIO
            # Sloupce: observation_date, <SERIES_ID>
            df = pd.read_csv(StringIO(r.text))
            # První sloupec je vždy datum
            date_col = df.columns[0]
            value_col = df.columns[1]
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df = df.set_index(date_col)
            df = df[value_col].replace(".", float("nan"))
            df = pd.to_numeric(df, errors='coerce').dropna()
            return df
    except Exception as e:
        logger.warning(f"FRED {series_id} selhalo: {e}")
        return pd.Series(dtype=float)

async def seed_historical_data():
    """
    Spouští se jednorázově po získání API klíčů pro ostrý režim!
    1) Stáhne historická EUR/USD OHLC data z EODHD (pro referenci).
    2) Stáhne makro data z FRED (Federal Reserve) a kalibruje Z-Score statistiky.
    3) Zapíše nakalibrované Mean/Std do Supabase normalization_stats.
    4) Otestuje COT data z CFTC.
    """
    settings = get_settings()
    db = get_supabase()
    
    today = datetime.now().date()
    one_year_ago = today - timedelta(days=365)
    
    # ─────────────────────────────────────────────────────────
    # ČÁST 1: EODHD - Historická Forex data (EUR/USD OHLC)
    # ─────────────────────────────────────────────────────────
    logger.info("=== START: EODHD - Stahování historických EUR/USD dat ===")
    if not settings.eodhd_api_key:
        logger.warning("EODHD klíč chybí, přeskakuji Forex data z EODHD.")
    else:
        try:
            url = f"https://eodhd.com/api/eod/EURUSD.FOREX"
            params = {
                "api_token": settings.eodhd_api_key,
                "fmt": "json",
                "from": one_year_ago.isoformat(),
                "to": today.isoformat(),
                "period": "d"
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                eodhd_data = resp.json()
                logger.success(f"EODHD: Staženo {len(eodhd_data)} denních EUR/USD svíček za rok.")
                if eodhd_data:
                    logger.info(f"  Nejstarší: {eodhd_data[0]['date']}, Nejnovější: {eodhd_data[-1]['date']}")
        except Exception as e:
            logger.error(f"Chyba při stahování EODHD Forex dat: {e}")

    # ─────────────────────────────────────────────────────────
    # ČÁST 2: FRED API - Z-Score kalibrace makroindikátorů
    # ─────────────────────────────────────────────────────────
    logger.info("=== START: FRED API - Kalibrace Z-Score statistik ===")
    stats_to_upsert = []

    for indicator_name, series_id in FRED_SERIES.items():
        logger.info(f"  Stahuji FRED series: {series_id} ({indicator_name})...")
        series = await fetch_fred_series(series_id, one_year_ago.isoformat())
        
        if len(series) < 4:
            logger.warning(f"  FRED {series_id}: Nedostatek dat ({len(series)} záznamů), přeskakuji.")
            continue
        
        # Výpočet meziperiodních změn (surprise = change)
        changes = series.pct_change().dropna() * 100  # v procentech
        
        if len(changes) < 3:
            continue
            
        mean_s = float(np.mean(changes))
        std_s = float(np.std(changes))
        
        if std_s < 0.0001:
            std_s = 0.01  # Ochrana před division by zero
        
        logger.success(f"  ✅ {indicator_name}: Mean={mean_s:.4f}%, Std={std_s:.4f}% ({len(changes)} datových bodů)")
        
        stats_to_upsert.append({
            "indicator_name": indicator_name,
            "mean_surprise": round(mean_s, 6),
            "std_surprise": round(std_s, 6)
        })

    # Zapsat do Supabase
    if stats_to_upsert:
        db.table("normalization_stats").upsert(stats_to_upsert).execute()
        logger.success(f"=== Nahráno {len(stats_to_upsert)} Z-Score kalibrací do Supabase! ===")
    else:
        logger.warning("Žádné statistiky nebyly uloženy.")

    # ─────────────────────────────────────────────────────────
    # ČÁST 3: CFTC COT Validace
    # ─────────────────────────────────────────────────────────
    logger.info("=== START: KONTROLA HISTORICKÉHO COT (CFTC.GOV) ===")
    from collectors.cot import fetch_cot_data
    cot_test = await fetch_cot_data()
    if cot_test and len(cot_test.eur_history_52w) > 50:
        logger.success(f"CFTC funguje! EUR Net Pos: {cot_test.eur_net_position:+,}, DXY Net Pos: {cot_test.dxy_net_position:+,}")
    else:
        logger.error("CFTC nedostupný nebo bez dat.")

    logger.info("=== SEED HOTOV. Databáze je nakalib rovaná a připravena k ostrému provozu! ===")

if __name__ == "__main__":
    asyncio.run(seed_historical_data())
